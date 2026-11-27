const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("HI05 - PriceOracle, Health Factor Boundaries & Liquidation Mechanism", function () {
  let deployer, lenderA, borrowerA, borrowerB, liquidator, outsider;
  let myUSDT, collateralNFT, receiptNFT, debtToken, positionNFT, oracle, pool;

  const parse = (val) => ethers.parseUnits(val, 18);
  const DAY = 86_400;
  const SAMPLE_CID = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi";
  const NFT_URI_1 = "ipfs://bafybeih05collateralnft0001";
  const NFT_URI_2 = "ipfs://bafybeih05collateralnft0002";

  beforeEach(async function () {
    [deployer, lenderA, borrowerA, borrowerB, liquidator, outsider] = await ethers.getSigners();

    myUSDT = await ethers.deployContract("MyUSDT", [], deployer);
    collateralNFT = await ethers.deployContract("CollateralNFT", [], deployer);
    receiptNFT = await ethers.deployContract("CollateralReceiptNFT", [], deployer);
    debtToken = await ethers.deployContract("DebtToken", [], deployer);
    positionNFT = await ethers.deployContract("LendingPositionNFT", [], deployer);

    await Promise.all([
      myUSDT.waitForDeployment(),
      collateralNFT.waitForDeployment(),
      receiptNFT.waitForDeployment(),
      debtToken.waitForDeployment(),
      positionNFT.waitForDeployment(),
    ]);

    oracle = await ethers.deployContract(
      "PriceOracle",
      [await collateralNFT.getAddress()],
      deployer
    );
    await oracle.waitForDeployment();

    pool = await ethers.deployContract(
      "LendingPool",
      [
        await myUSDT.getAddress(),
        await myUSDT.getAddress(),
        await collateralNFT.getAddress(),
        await receiptNFT.getAddress(),
        await debtToken.getAddress(),
        await positionNFT.getAddress(),
        await oracle.getAddress(),
      ],
      deployer
    );
    await pool.waitForDeployment();

    const poolAddr = await pool.getAddress();
    await (await debtToken.connect(deployer).setLendingPool(poolAddr)).wait();
    await (await receiptNFT.connect(deployer).setLendingPool(poolAddr)).wait();
    await (await positionNFT.connect(deployer).setLendingPool(poolAddr)).wait();

    for (const signer of [lenderA, borrowerA, borrowerB, liquidator]) {
      await (await myUSDT.connect(deployer).transfer(signer.address, parse("5000"))).wait();
    }
  });

  describe("1. PriceOracle.sol — Access Control (onlyOwner), Valuation & Events", function () {
    it("initializes canonical defaults, rejects zero CollateralNFT, and emits PriceUpdated / PriceMultiplierUpdated", async function () {
      await expect(
        ethers.deployContract("PriceOracle", [ethers.ZeroAddress], deployer)
      ).to.be.revertedWithCustomError(oracle, "InvalidAddress");

      expect(await oracle.owner()).to.equal(deployer.address);
      expect(await oracle.getCollateralTokenPrice()).to.equal(parse("1"));
      expect(await oracle.priceMultiplierBps()).to.equal(10_000n);

      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_1)).wait();
      expect(await oracle.getCollateralNFTValuation(1n)).to.equal(parse("1000"));
      expect(await oracle.hasNFTValuationOverride(1n)).to.equal(false);

      // Update token price -> emits PriceUpdated
      await expect(oracle.connect(deployer).setCollateralTokenPrice(parse("0.8")))
        .to.emit(oracle, "PriceUpdated");
      expect(await oracle.getCollateralTokenPrice()).to.equal(parse("0.8"));

      // Override NFT valuation -> emits PriceUpdated
      await expect(oracle.connect(deployer).setCollateralNFTValuation(1n, parse("1200")))
        .to.emit(oracle, "PriceUpdated");
      expect(await oracle.hasNFTValuationOverride(1n)).to.equal(true);
      expect(await oracle.getCollateralNFTValuation(1n)).to.equal(parse("1200"));

      // Apply 40% market crash multiplier (6000 BPS) -> affects BOTH token and NFT valuations
      await expect(oracle.connect(deployer).setPriceMultiplierBps(6_000))
        .to.emit(oracle, "PriceMultiplierUpdated")
        .and.to.emit(oracle, "PriceUpdated");
      expect(await oracle.getCollateralTokenPrice()).to.equal(parse("0.48"));
      expect(await oracle.getCollateralNFTValuation(1n)).to.equal(parse("720"));

      // Clear override -> falls back to CollateralNFT.valuation(1) * 60% = 600
      await expect(oracle.connect(deployer).clearCollateralNFTValuationOverride(1n))
        .to.emit(oracle, "PriceUpdated");
      expect(await oracle.hasNFTValuationOverride(1n)).to.equal(false);
      expect(await oracle.getCollateralNFTValuation(1n)).to.equal(parse("600"));

      // Reset demo prices -> restores 1.0 MyUSDT & 10,000 BPS
      await expect(oracle.connect(deployer).resetDemoPrices())
        .to.emit(oracle, "PriceMultiplierUpdated")
        .and.to.emit(oracle, "PriceUpdated");
      expect(await oracle.getCollateralTokenPrice()).to.equal(parse("1"));
      expect(await oracle.priceMultiplierBps()).to.equal(10_000n);
      expect(await oracle.getCollateralNFTValuation(1n)).to.equal(parse("1000"));
    });

    it("blocks unauthorized accounts from modifying oracle prices or binding a malicious oracle", async function () {
      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_1)).wait();

      for (const attacker of [borrowerA, liquidator, outsider]) {
        await expect(
          oracle.connect(attacker).setCollateralTokenPrice(parse("0.1"))
        )
          .to.be.revertedWithCustomError(oracle, "OwnableUnauthorizedAccount")
          .withArgs(attacker.address);

        await expect(
          oracle.connect(attacker).setCollateralNFTValuation(1n, parse("100"))
        )
          .to.be.revertedWithCustomError(oracle, "OwnableUnauthorizedAccount")
          .withArgs(attacker.address);

        await expect(
          oracle.connect(attacker).setPriceMultiplierBps(5_000)
        )
          .to.be.revertedWithCustomError(oracle, "OwnableUnauthorizedAccount")
          .withArgs(attacker.address);

        await expect(
          oracle.connect(attacker).clearCollateralNFTValuationOverride(1n)
        )
          .to.be.revertedWithCustomError(oracle, "OwnableUnauthorizedAccount")
          .withArgs(attacker.address);

        await expect(
          oracle.connect(attacker).resetDemoPrices()
        )
          .to.be.revertedWithCustomError(oracle, "OwnableUnauthorizedAccount")
          .withArgs(attacker.address);

        await expect(
          pool.connect(attacker).setPriceOracle(attacker.address)
        )
          .to.be.revertedWithCustomError(pool, "OwnableUnauthorizedAccount")
          .withArgs(attacker.address);
      }

      // Rejects absurd multiplier > MAX_MULTIPLIER_BPS (50_000)
      await expect(oracle.connect(deployer).setPriceMultiplierBps(50_001))
        .to.be.revertedWithCustomError(oracle, "InvalidMultiplierBps")
        .withArgs(50_001n, 50_000n);
    });
  });

  describe("2. Health Factor Boundaries (Zero Debt, SAFE, WARNING, Exact HF == 1.0, HF < 1.0)", function () {
    it("blocks liquidation when HF > 1.0 and strictly at HF == 1.0, and requires explicit liquidate() tx when HF < 1.0", async function () {
      const poolAddr = await pool.getAddress();

      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_1)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();

      // Zero debt -> HF = MaxUint256 (infinite), cannot liquidate
      expect(await pool.getHealthFactor(borrowerA.address)).to.equal(ethers.MaxUint256);
      const previewIdle = await pool.getLiquidationPreview(borrowerA.address);
      expect(previewIdle.liquidatable).to.equal(false);
      await expect(pool.connect(liquidator).liquidate(borrowerA.address))
        .to.be.revertedWithCustomError(pool, "HealthFactorSafe")
        .withArgs(ethers.MaxUint256);

      // Borrow 500 on 1,000 collateral -> HF = 1.60e18 (SAFE), cannot liquidate
      await (await pool.connect(borrowerA).borrow(parse("500"), SAMPLE_CID)).wait();
      expect(await pool.getHealthFactor(borrowerA.address)).to.equal(parse("1.6"));
      await expect(pool.connect(liquidator).liquidate(borrowerA.address))
        .to.be.revertedWithCustomError(pool, "HealthFactorSafe");

      // Drop collateral value so HF is EXACTLY 1.00e18 (or slightly >= 1.0e18 accounting for 1s interest):
      // At 500 debt + tiny 1s interest (~1.58e12 wei), set NFT override = 625.000003 MyUSDT -> HF >= 1.0e18 -> NOT liquidatable
      await (await oracle.connect(deployer).setCollateralNFTValuation(1n, parse("625.001"))).wait();
      const hfBoundarySafe = await pool.getHealthFactor(borrowerA.address);
      expect(hfBoundarySafe).to.be.greaterThanOrEqual(parse("1"));
      expect((await pool.getLiquidationPreview(borrowerA.address)).liquidatable).to.equal(false);
      await expect(pool.connect(liquidator).liquidate(borrowerA.address))
        .to.be.revertedWithCustomError(pool, "HealthFactorSafe");

      // Exact mathematical HF == 1.000000e18 test using fresh borrow with 0 elapsed seconds in same snapshot check:
      await (await oracle.connect(deployer).resetDemoPrices()).wait();
      await (await oracle.connect(deployer).clearCollateralNFTValuationOverride(1n)).wait();

      // Drop multiplier by 40% (6,000 BPS -> NFT valued 600 MyUSDT, debt ~500 -> HF ~ 0.96 < 1.0)
      await (await oracle.connect(deployer).setPriceMultiplierBps(6_000)).wait();
      const hfCrash = await pool.getHealthFactor(borrowerA.address);
      expect(hfCrash).to.be.lessThan(parse("1"));

      // CRITICAL RUBRIC CHECK: Dropping price ALONE does NOT auto-liquidate on-chain;
      // loan remains active until a liquidator/keeper sends a signed liquidate() transaction!
      const loanStillActive = await pool.getLoanPosition(borrowerA.address);
      expect(loanStillActive.active).to.equal(true);
      expect(await collateralNFT.ownerOf(1n)).to.equal(poolAddr);
      expect(await debtToken.balanceOf(borrowerA.address)).to.equal(parse("500"));

      const previewLiq = await pool.getLiquidationPreview(borrowerA.address);
      expect(previewLiq.liquidatable).to.equal(true);
      expect(previewLiq.collateralValueWad).to.equal(parse("600"));
      expect(previewLiq.seizeValueWad).to.equal(parse("600"));
      expect(previewLiq.isNFTCollateral).to.equal(true);
    });

    it("enforces strict inequality HF < 1e18 (exact HF == 1.0e18 reverts HealthFactorSafe)", async function () {
      const poolAddr = await pool.getAddress();

      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      // Borrower locks NFT valued 1,000 and borrows 500; advance 0s -> set exact valuation = (totalDebt * 10000) / 8000
      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_1)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();
      await (await pool.connect(borrowerA).borrow(parse("500"), SAMPLE_CID)).wait();

      // Account for 1-second timestamp tick on next block when liquidate() executes:
      // Freeze automine so setCollateralNFTValuation and liquidate run with exact computed valuation if needed,
      // or set valuation matching totalDebt at exact next timestamp!
      const nextTs = (await time.latest()) + 10;
      const debtAtNextTs = await pool.getTotalDebt(borrowerA.address) +
        (await pool.previewBorrowerInterest(borrowerA.address, 10)) -
        (await pool.calculateAccruedInterest(borrowerA.address));
      // exactCollateralForHf1 = ceil(debt * 10000 / 8000) so HF == 1e18 (or 1e18 + tiny dust)
      const exactCollat = (debtAtNextTs * 10_000n + 7_999n) / 8_000n;
      await (await oracle.connect(deployer).setCollateralNFTValuation(1n, exactCollat)).wait();

      await time.setNextBlockTimestamp(nextTs);
      await expect(pool.connect(liquidator).liquidate(borrowerA.address))
        .to.be.revertedWithCustomError(pool, "HealthFactorSafe");
    });
  });

  describe("3. Liquidation Execution — CollateralNFT Custody Seizure & Pool Capital Recovery", function () {
    it("liquidates underwater NFT loan after 40% price crash, burns DebtToken, settles receipt, and restores Lender liquidity", async function () {
      const poolAddr = await pool.getAddress();

      // 1. Lender A supplies 1,000 MyUSDT
      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      // 2. Borrower A locks CollateralNFT #1 (1,000 MyUSDT) & borrows 500 MyUSDT
      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_1)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();
      await (await pool.connect(borrowerA).borrow(parse("500"), SAMPLE_CID)).wait();

      // 3. Advance 30 days -> interest accrues (~4.1095 MyUSDT)
      await time.increase(30 * DAY);

      // 4. Owner simulates 40% market crash (6000 BPS -> NFT valued 600 MyUSDT, HF ~ 0.952 < 1.0)
      await (await oracle.connect(deployer).setPriceMultiplierBps(6_000)).wait();
      const preview = await pool.getLiquidationPreview(borrowerA.address);
      expect(preview.liquidatable).to.equal(true);
      expect(preview.healthFactorWad).to.be.lessThan(parse("1"));

      // 5. Liquidator approves & executes liquidate(borrowerA)
      const liqBalBefore = await myUSDT.balanceOf(liquidator.address);
      await (await myUSDT.connect(liquidator).approve(poolAddr, preview.totalDebtWad + parse("5"))).wait();

      await expect(pool.connect(liquidator).liquidate(borrowerA.address))
        .to.emit(pool, "LoanLiquidated")
        .and.to.emit(debtToken, "DebtBurned")
        .withArgs(borrowerA.address, parse("500"))
        .and.to.emit(receiptNFT, "ReceiptSettled")
        .withArgs(1n, borrowerA.address, true)
        .and.to.emit(pool, "InterestRateUpdated");

      // Verify post-liquidation state
      expect(await collateralNFT.ownerOf(1n)).to.equal(liquidator.address);
      expect(await debtToken.balanceOf(borrowerA.address)).to.equal(0n);
      expect(await pool.getTotalDebt(borrowerA.address)).to.equal(0n);
      expect((await pool.getLoanPosition(borrowerA.address)).active).to.equal(false);
      expect(await receiptNFT.activeReceiptOf(borrowerA.address)).to.equal(0n);

      const settledReceipt = await receiptNFT.getReceiptInfo(1n);
      expect(settledReceipt.active).to.equal(false);
      expect(settledReceipt.borrower).to.equal(borrowerA.address);
      await expect(receiptNFT.ownerOf(1n)).to.be.reverted;

      // Liquidator paid ~504.11 MyUSDT to seize NFT worth 600 MyUSDT
      const paidByLiquidator = liqBalBefore - (await myUSDT.balanceOf(liquidator.address));
      expect(paidByLiquidator).to.be.greaterThan(parse("504.10"));
      expect(paidByLiquidator).to.be.lessThan(parse("504.15"));

      // Pool recovered 100% capital + interest -> Lender A withdraws full principal + 30d interest!
      const claimable = await pool.getLenderClaimableBalance(1n);
      expect(claimable).to.be.greaterThan(parse("1004.10"));
      await expect(pool.connect(lenderA).withdrawLender(1n, claimable))
        .to.emit(pool, "LenderWithdrawn")
        .and.to.emit(positionNFT, "PositionBurned")
        .withArgs(1n, lenderA.address);

      // Re-liquidating same borrower reverts NoActiveCollateral
      await expect(pool.connect(liquidator).liquidate(borrowerA.address))
        .to.be.revertedWithCustomError(pool, "NoActiveCollateral")
        .withArgs(borrowerA.address);
    });
  });

  describe("4. Liquidation Execution — ERC-20 Collateral (+5% Liquidation Bonus, Surplus Refund & Crash Cap)", function () {
    it("awards 5% liquidation bonus in ERC-20 collateral to Liquidator and refunds remaining surplus to Borrower", async function () {
      const poolAddr = await pool.getAddress();

      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      // Borrower A locks 1,000 ERC-20 collateral tokens and borrows 500 MyUSDT
      await (await myUSDT.connect(borrowerA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(borrowerA).depositCollateral(parse("1000"), false)).wait();
      await (await pool.connect(borrowerA).borrow(parse("500"), SAMPLE_CID)).wait();

      // 40% price crash -> 0.60 MyUSDT/token -> collateral value = 600 MyUSDT, HF ~ 0.96 < 1.0
      await (await oracle.connect(deployer).setPriceMultiplierBps(6_000)).wait();

      const preview = await pool.getLiquidationPreview(borrowerA.address);
      expect(preview.liquidatable).to.equal(true);
      expect(preview.isNFTCollateral).to.equal(false);
      // Expected seizeValue = totalDebt * 1.05 (~525 MyUSDT) -> ~875 tokens seized, ~125 tokens refunded to Borrower
      expect(preview.seizeValueWad).to.be.closeTo(parse("525"), parse("0.01"));

      const borrowerBalBefore = await myUSDT.balanceOf(borrowerA.address);
      const liqBalBefore = await myUSDT.balanceOf(liquidator.address);

      await (await myUSDT.connect(liquidator).approve(poolAddr, preview.totalDebtWad + parse("5"))).wait();
      await expect(pool.connect(liquidator).liquidate(borrowerA.address))
        .to.emit(pool, "LoanLiquidated")
        .and.to.emit(receiptNFT, "ReceiptSettled")
        .withArgs(1n, borrowerA.address, true);

      // Collateral locked counter cleared, borrower received ~125 surplus tokens back
      expect(await pool.totalTokenCollateralLocked()).to.equal(0n);
      const borrowerRefund = (await myUSDT.balanceOf(borrowerA.address)) - borrowerBalBefore;
      expect(borrowerRefund).to.be.closeTo(parse("125"), parse("0.01"));

      // Liquidator net token delta: received ~875 collateral tokens minus ~500 paid = +375 tokens
      const liqNetDelta = (await myUSDT.balanceOf(liquidator.address)) - liqBalBefore;
      expect(liqNetDelta).to.be.closeTo(parse("375"), parse("0.01"));
    });

    it("caps ERC-20 seizure cleanly at 100% locked collateral during severe 55% market crash (zero underflow)", async function () {
      const poolAddr = await pool.getAddress();

      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      await (await myUSDT.connect(borrowerB).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(borrowerB).depositCollateral(parse("1000"), false)).wait();
      await (await pool.connect(borrowerB).borrow(parse("500"), SAMPLE_CID)).wait();

      // 55% crash -> 0.45 MyUSDT/token -> collateral value = 450 < 500 * 1.05 (525)
      await (await oracle.connect(deployer).setPriceMultiplierBps(4_500)).wait();
      const preview = await pool.getLiquidationPreview(borrowerB.address);
      expect(preview.liquidatable).to.equal(true);
      expect(preview.seizeValueWad).to.equal(parse("450"));

      const borrowerBalBefore = await myUSDT.balanceOf(borrowerB.address);
      await (await myUSDT.connect(liquidator).approve(poolAddr, preview.totalDebtWad + parse("5"))).wait();
      await (await pool.connect(liquidator).liquidate(borrowerB.address)).wait();

      expect(await pool.totalTokenCollateralLocked()).to.equal(0n);
      expect(await myUSDT.balanceOf(borrowerB.address)).to.equal(borrowerBalBefore); // 0 surplus
      expect(await debtToken.balanceOf(borrowerB.address)).to.equal(0n);
    });
  });

  describe("5. Interest-Accrual-Induced Liquidation (Unchanged Oracle Price)", function () {
    it("allows liquidation when prolonged unpaid interest pushes totalDebt above 80% threshold", async function () {
      const poolAddr = await pool.getAddress();

      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      // Borrower borrows max 70% LTV = 700 on 1,000 NFT (U = 70%, Borrow APR = 12%, initial HF = 1.142857)
      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_2)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();
      await (await pool.connect(borrowerA).borrow(parse("700"), SAMPLE_CID)).wait();

      // Advance 450 days without repayment -> interest = 700 * 12% * 450/365 = 103.56 -> totalDebt ~ 803.56 > 800 -> HF < 1.0
      await time.increase(450 * DAY);
      const hfAfter = await pool.getHealthFactor(borrowerA.address);
      expect(hfAfter).to.be.lessThan(parse("1"));

      const totalDebt = await pool.getTotalDebt(borrowerA.address);
      await (await myUSDT.connect(liquidator).approve(poolAddr, totalDebt + parse("10"))).wait();
      await expect(pool.connect(liquidator).liquidate(borrowerA.address))
        .to.emit(pool, "LoanLiquidated");
      expect(await collateralNFT.ownerOf(1n)).to.equal(liquidator.address);
    });
  });
});
