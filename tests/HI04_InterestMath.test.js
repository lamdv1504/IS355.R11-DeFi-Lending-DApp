const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("HI04 - Real-Time Timestamp Interest, InterestMath, APR vs APY & Non-Retroactive Accrual", function () {
  let deployer, lenderA, lenderB, borrowerA;
  let myUSDT, collateralNFT, receiptNFT, debtToken, positionNFT, pool, interestHarness, protoHarness;

  const parse = (val) => ethers.parseUnits(val, 18);
  const WAD = 10n ** 18n;
  const BPS = 10_000n;
  const SECONDS_PER_YEAR = 31_536_000n;
  const DAY = 86_400;
  const SAMPLE_CID = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi";
  const NFT_URI = "ipfs://bafybeih04collateralnft0001";

  beforeEach(async function () {
    [deployer, lenderA, lenderB, borrowerA] = await ethers.getSigners();

    myUSDT = await ethers.deployContract("MyUSDT", [], deployer);
    collateralNFT = await ethers.deployContract("CollateralNFT", [], deployer);
    receiptNFT = await ethers.deployContract("CollateralReceiptNFT", [], deployer);
    debtToken = await ethers.deployContract("DebtToken", [], deployer);
    positionNFT = await ethers.deployContract("LendingPositionNFT", [], deployer);
    interestHarness = await ethers.deployContract("InterestMathHarness", [], deployer);
    protoHarness = await ethers.deployContract("ProtocolMathHarness", [], deployer);

    await Promise.all([
      myUSDT.waitForDeployment(),
      collateralNFT.waitForDeployment(),
      receiptNFT.waitForDeployment(),
      debtToken.waitForDeployment(),
      positionNFT.waitForDeployment(),
      interestHarness.waitForDeployment(),
      protoHarness.waitForDeployment(),
    ]);

    pool = await ethers.deployContract(
      "LendingPool",
      [
        await myUSDT.getAddress(),
        await myUSDT.getAddress(),
        await collateralNFT.getAddress(),
        await receiptNFT.getAddress(),
        await debtToken.getAddress(),
        await positionNFT.getAddress(),
        ethers.ZeroAddress,
      ],
      deployer
    );
    await pool.waitForDeployment();

    const poolAddr = await pool.getAddress();
    await (await debtToken.connect(deployer).setLendingPool(poolAddr)).wait();
    await (await receiptNFT.connect(deployer).setLendingPool(poolAddr)).wait();
    await (await positionNFT.connect(deployer).setLendingPool(poolAddr)).wait();

    for (const signer of [lenderA, lenderB, borrowerA]) {
      await (await myUSDT.connect(deployer).transfer(signer.address, parse("5000"))).wait();
    }
  });

  describe("1. InterestMath.sol — Per-Second Precision, Overflow Safety & ProtocolMath Parity", function () {
    it("accrues non-zero interest every single second without integer division truncation", async function () {
      // Scale by 1e18 BEFORE dividing -> even 1 single second at 5% APR yields non-zero index delta
      const deltaIdx1s = await interestHarness.calculateIndexDelta(500n, 1n);
      expect(deltaIdx1s).to.equal((WAD * 500n) / (SECONDS_PER_YEAR * BPS));
      expect(deltaIdx1s).to.be.greaterThan(0n);

      // 500 MyUSDT at 10% APR for 1 second -> 1_585_489_599_188 wei (> 0)
      const perSec500 = await interestHarness.calculatePerSecondInterestRateWad(parse("500"), 1_000n);
      expect(perSec500).to.equal((parse("500") * 1_000n) / (SECONDS_PER_YEAR * BPS));
      expect(perSec500).to.equal(1_585_489_599_188n);

      // Monotonic growth across 1s < 2s < 60s < 1d < 30d < 60d < 365d
      const samples = [1n, 2n, 60n, 86_400n, 30n * 86_400n, 60n * 86_400n, SECONDS_PER_YEAR];
      let prev = 0n;
      for (const dt of samples) {
        const val = await interestHarness.accrueSimpleInterest(parse("500"), 1_000n, dt);
        expect(val).to.be.greaterThan(prev);
        prev = val;
      }
      // Exact 1-year simple APR interest = 50.000000000000000000 MyUSDT (10% of 500)
      expect(prev).to.equal(parse("50"));

      // Exact 60-day Demo interest = 8_219_178_082_191_780_821 wei (matches borrower & lender bit-for-bit)
      const demo60dBorrow = await interestHarness.accrueSimpleInterest(parse("500"), 1_000n, 60n * 86_400n);
      const demo60dSupply = await interestHarness.accrueSimpleInterest(parse("1000"), 500n, 60n * 86_400n);
      expect(demo60dBorrow).to.equal(8_219_178_082_191_780_821n);
      expect(demo60dSupply).to.equal(demo60dBorrow);
    });

    it("reverts safely on arithmetic overflow via Solidity 0.8+ checked math & Math.mulDiv", async function () {
      // Overflow in `aprBps * deltaSeconds` reverts with Panic 0x11
      await expect(
        interestHarness.accrueSimpleInterest(parse("1000"), ethers.MaxUint256, 2n)
      ).to.be.revertedWithPanic(0x11);

      // Overflow in final 256-bit result of `Math.mulDiv` reverts cleanly (no wrap-around)
      await expect(
        interestHarness.accrueSimpleInterest(ethers.MaxUint256, 10_000n, SECONDS_PER_YEAR * 2n)
      ).to.be.reverted;

      // Overflow in `advanceCumulativeIndex` when previousIndex is near MaxUint256 reverts Panic 0x11
      await expect(
        interestHarness.advanceCumulativeIndex(ethers.MaxUint256, 1_000n, 86_400n)
      ).to.be.revertedWithPanic(0x11);
    });

    it("matches ProtocolMath bit-for-bit across utilization, APR, and index functions", async function () {
      for (const util of [0n, 2_500n, 5_000n, 7_000n, 8_000n, 10_000n]) {
        const b1 = await interestHarness.calculateBorrowAprBps(util);
        const b2 = await protoHarness.calculateBorrowAprBps(util);
        expect(b1).to.equal(b2);

        const s1 = await interestHarness.calculateSupplyAprBps(b1, util);
        const s2 = await protoHarness.calculateSupplyAprBps(b2, util);
        expect(s1).to.equal(s2);

        const idx1 = await interestHarness.advanceCumulativeIndex(WAD, b1, 30n * 86_400n);
        const idx2 = await protoHarness.calculateNextIndex(WAD, b2, 30n * 86_400n);
        expect(idx1).to.equal(idx2);
      }
    });
  });

  describe("2. Strict Distinction Between On-Chain Simple APR and Reference Daily APY", function () {
    it("computes reference daily-compounded APY strictly > simple APR and exposes both via getInterestRateSnapshot()", async function () {
      expect(await interestHarness.calculateReferenceApyBps(0n)).to.equal(0n);
      // 5.00% APR -> ~5.1267% APY (512 BPS)
      expect(await interestHarness.calculateReferenceApyBps(500n)).to.equal(512n);
      // 10.00% APR -> ~10.5156% APY (1051 BPS)
      expect(await interestHarness.calculateReferenceApyBps(1_000n)).to.equal(1_051n);
      // 15.00% APR -> ~16.1798% APY (1617 BPS)
      expect(await interestHarness.calculateReferenceApyBps(1_500n)).to.equal(1_617n);

      const poolAddr = await pool.getAddress();
      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();
      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();
      await (await pool.connect(borrowerA).borrow(parse("500"), SAMPLE_CID)).wait();

      const snap = await pool.getInterestRateSnapshot();
      expect(snap.utilizationBps).to.equal(5_000n);
      expect(snap.borrowAprBps).to.equal(1_000n);     // On-chain simple Borrow APR = 10.00%
      expect(snap.supplyAprBps).to.equal(500n);       // On-chain simple Supply APR = 5.00%
      expect(snap.borrowApyRefBps).to.equal(1_051n);  // Reference daily Borrow APY ~ 10.51%
      expect(snap.supplyApyRefBps).to.equal(512n);    // Reference daily Supply APY ~ 5.12%

      // Verify on-chain 1-year accrual is strictly SIMPLE APR (50 MyUSDT), NOT compounded APY (~52.58 MyUSDT)
      await time.increase(365 * DAY);
      const oneYearBorrowerInterest = await pool.calculateAccruedInterest(borrowerA.address);
      const oneYearLenderInterest = await pool.getLenderEarnedInterest(1n);
      expect(oneYearBorrowerInterest).to.be.closeTo(parse("50"), parse("0.001"));
      expect(oneYearLenderInterest).to.be.closeTo(parse("50"), parse("0.001"));
      expect(oneYearBorrowerInterest).to.be.lessThan(parse("51"));
    });
  });

  describe("3. Real-Time Per-Second Accrual & Proportional Lender Share on LendingPool", function () {
    it("ticks borrower & lender interest strictly every second and distributes proportionally by deposit share", async function () {
      const poolAddr = await pool.getAddress();

      // Lender A deposits 750 (75% share), Lender B deposits 250 (25% share) -> totalSupplied = 1,000
      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("750"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("750"))).wait();
      await (await myUSDT.connect(lenderB).approve(poolAddr, parse("250"))).wait();
      await (await pool.connect(lenderB).depositLender(parse("250"))).wait();

      // Borrower A borrows 500 -> U = 50%, Borrow APR = 10%, Supply APR = 5%
      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();
      await (await pool.connect(borrowerA).borrow(parse("500"), SAMPLE_CID)).wait();

      // Advance exactly 1 second -> both borrower & lenders accrue > 0 wei
      await time.increase(1);
      const b1s = await pool.calculateAccruedInterest(borrowerA.address);
      const lA1s = await pool.getLenderEarnedInterest(1n);
      const lB1s = await pool.getLenderEarnedInterest(2n);
      expect(b1s).to.be.greaterThan(0n);
      expect(lA1s).to.be.greaterThan(0n);
      expect(lB1s).to.be.greaterThan(0n);

      // Preview helpers predict exact 30-day future accrued interest
      const previewB30d = await pool.previewBorrowerInterest(borrowerA.address, 30 * DAY);
      const previewLA30d = await pool.previewLenderEarnedInterest(1n, 30 * DAY);

      // Fast-forward 30 days via evm_increaseTime + evm_mine (HI04 demo mechanism)
      await ethers.provider.send("evm_increaseTime", [30 * DAY]);
      await ethers.provider.send("evm_mine", []);

      const actualB30d = await pool.calculateAccruedInterest(borrowerA.address);
      const actualLA30d = await pool.getLenderEarnedInterest(1n);
      const actualLB30d = await pool.getLenderEarnedInterest(2n);

      // Preview matches actual post-time-jump accrual down to exact 0 wei!
      expect(actualB30d).to.equal(previewB30d);
      expect(actualLA30d).to.equal(previewLA30d);

      // Exact 3:1 proportional split between 750-share Lender A and 250-share Lender B,
      // and strict solvency (sum of lender interest <= borrower interest, gap <= 1000 wei floor dust).
      expect(actualLA30d).to.equal(actualLB30d * 3n);
      expect(actualLA30d + actualLB30d).to.be.lessThanOrEqual(actualB30d);
      expect(actualB30d - (actualLA30d + actualLB30d)).to.be.lessThanOrEqual(1_000n);
    });
  });

  describe("4. Non-Retroactive Multi-Period Interest Accrual Across Utilization Changes", function () {
    it("locks historical period interest before rate shifts and never applies new rates retroactively", async function () {
      const poolAddr = await pool.getAddress();

      // Setup: Lender A deposits 1,000; Borrower A locks NFT valued 2,000 (maxBorrow = 1,400)
      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      await (await collateralNFT.mintCollateral(borrowerA.address, parse("2000"), NFT_URI)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();

      // --- Period 1: Borrow 500 -> U = 50%, Borrow APR = 10% (1000 BPS), Supply APR = 5% (500 BPS) ---
      await (await pool.connect(borrowerA).borrow(parse("500"), SAMPLE_CID)).wait();
      const t0 = BigInt((await ethers.provider.getBlock("latest")).timestamp);

      await time.increase(30 * DAY);

      // --- Rate shift at Day 30: Borrower A borrows +300 -> totalBorrowed = 800, U = 80%, Borrow APR = 13%, Supply APR = 10.4% ---
      await expect(pool.connect(borrowerA).borrow(parse("300"), SAMPLE_CID))
        .to.emit(pool, "InterestRateUpdated")
        .withArgs(
          (ts) => ts >= t0 + BigInt(30 * DAY),
          1_300n, // Borrow APR 13.00%
          1_040n, // Supply APR 10.40%
          8_000n, // Utilization 80.00%
          parse("1000"),
          parse("800")
        );

      const t1 = BigInt((await ethers.provider.getBlock("latest")).timestamp);
      const dt1 = t1 - t0;

      // Verify Period 1 locked interest used OLD 10% APR, NOT new 13% APR
      const expectedP1Borrower = await interestHarness.accrueSimpleInterest(parse("500"), 1_000n, dt1);
      const wrongRetroP1 = await interestHarness.accrueSimpleInterest(parse("500"), 1_300n, dt1);
      const loanAtT1 = await pool.getLoanPosition(borrowerA.address);
      expect(loanAtT1.accruedInterest).to.be.closeTo(expectedP1Borrower, 1_000n);
      expect(loanAtT1.accruedInterest).to.be.lessThan(wrongRetroP1);

      // --- Period 2: 30 more days at U = 80% (800 principal @ 13% Borrow APR, 1,000 supplied @ 10.4% Supply APR) ---
      await time.increase(30 * DAY);

      // --- Rate shift at Day 60: Lender B deposits 1,000 -> totalSupplied = 2,000, U drops 80% -> 40% (Borrow 9%, Supply 3.6%) ---
      await (await myUSDT.connect(lenderB).approve(poolAddr, parse("1000"))).wait();
      await expect(pool.connect(lenderB).depositLender(parse("1000")))
        .to.emit(pool, "InterestRateUpdated")
        .withArgs(
          (ts) => ts >= t1 + BigInt(30 * DAY),
          900n,   // Borrow APR 9.00%
          360n,   // Supply APR 3.60%
          4_000n, // Utilization 40.00%
          parse("2000"),
          parse("800")
        );

      const t2 = BigInt((await ethers.provider.getBlock("latest")).timestamp);
      const dt2 = t2 - t1;

      // Lender B entering at Day 60 MUST start at 0 interest (cannot retroactively claim Period 1 or 2)
      expect(await pool.getLenderEarnedInterest(2n)).to.equal(0n);

      const expectedP2Borrower = await interestHarness.accrueSimpleInterest(parse("800"), 1_300n, dt2);
      const accruedAtT2 = await pool.calculateAccruedInterest(borrowerA.address);
      expect(accruedAtT2).to.be.closeTo(expectedP1Borrower + expectedP2Borrower, 1_000n);

      // Strictly between flat 10% and retroactive 13%
      const wrongAllRetro13 = await interestHarness.accrueSimpleInterest(parse("800"), 1_300n, dt1 + dt2);
      expect(accruedAtT2).to.be.lessThan(wrongAllRetro13);

      // --- Period 3: 30 more days at U = 40% (Borrow 9%, Supply 3.6%), checkpointed explicitly via accrueInterest() ---
      await time.increase(30 * DAY);
      await expect(pool.accrueInterest()).to.emit(pool, "InterestRateUpdated");

      const t3 = BigInt((await ethers.provider.getBlock("latest")).timestamp);
      const dt3 = t3 - t2;

      const expectedP3Borrower = await interestHarness.accrueSimpleInterest(parse("800"), 900n, dt3);
      const expectedTotalBorrower = expectedP1Borrower + expectedP2Borrower + expectedP3Borrower;
      const actualTotalBorrower = await pool.calculateAccruedInterest(borrowerA.address);
      expect(actualTotalBorrower).to.be.closeTo(expectedTotalBorrower, 2_000n);

      // Lender B earned ONLY Period 3 interest (1,000 @ 3.6% for dt3)
      const expectedLenderB = await interestHarness.accrueSimpleInterest(parse("1000"), 360n, dt3);
      const actualLenderB = await pool.getLenderEarnedInterest(2n);
      expect(actualLenderB).to.be.closeTo(expectedLenderB, 1_000n);

      // Lender A earned Period 1 (5%) + Period 2 (10.4%) + Period 3 (3.6%)
      const expectedLenderA =
        (await interestHarness.accrueSimpleInterest(parse("1000"), 500n, dt1)) +
        (await interestHarness.accrueSimpleInterest(parse("1000"), 1_040n, dt2)) +
        (await interestHarness.accrueSimpleInterest(parse("1000"), 360n, dt3));
      const actualLenderA = await pool.getLenderEarnedInterest(1n);
      expect(actualLenderA).to.be.closeTo(expectedLenderA, 2_000n);

      // Total lender interest matches total borrower interest (exact solvency across all 3 periods!)
      expect(actualLenderA + actualLenderB).to.be.closeTo(actualTotalBorrower, 5_000n);
    });
  });
});
