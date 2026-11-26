const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("HI03 - Logic Constraints: LTV <= 70%, Real-Balance Pool Liquidity & Position NFT Transfer", function () {
  let deployer, lenderA, lenderB, lenderC, borrowerA, borrowerB, outsider;
  let myUSDT, collateralNFT, receiptNFT, debtToken, positionNFT, mockOracle, pool;

  const parse = (val) => ethers.parseUnits(val, 18);
  const SAMPLE_CID_A = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi";
  const SAMPLE_CID_B = "bafybeih03secondborrowerloanagreementcid0000000000000000002";
  const NFT_URI_A = "ipfs://bafybeih03collateralnft0001";
  const NFT_URI_B = "ipfs://bafybeih03collateralnft0002";

  const minBigInt = (a, b) => (a < b ? a : b);

  async function assertPoolBalanceInvariants(activePositionIds = [], activeBorrowers = []) {
    const poolAddr = await pool.getAddress();
    const rawBalance = await myUSDT.balanceOf(poolAddr);
    const lockedCollateral = await pool.totalTokenCollateralLocked();
    const poolInfo = await pool.getPoolInfo();
    const reserved = poolInfo.reservedLiquidity;
    const expectedAvailable =
      rawBalance > lockedCollateral + reserved ? rawBalance - lockedCollateral - reserved : 0n;

    const available = await pool.getAvailableLiquidity();
    expect(available).to.equal(expectedAvailable);

    for (const posId of activePositionIds) {
      const claimable = await pool.getLenderClaimableBalance(posId);
      const maxWithdrawable = await pool.getMaxWithdrawable(posId);
      expect(maxWithdrawable).to.equal(minBigInt(claimable, available));
    }

    for (const borrower of activeBorrowers) {
      const maxBorrow = await pool.getMaxBorrowable(borrower);
      const totalDebt = await pool.getTotalDebt(borrower);
      const expectedRemaining = maxBorrow > totalDebt ? maxBorrow - totalDebt : 0n;
      expect(await pool.getRemainingBorrowCapacity(borrower)).to.equal(expectedRemaining);
      expect(await pool.getAvailableToBorrow(borrower)).to.equal(
        minBigInt(expectedRemaining, available)
      );
    }
  }

  beforeEach(async function () {
    [deployer, lenderA, lenderB, lenderC, borrowerA, borrowerB, outsider] =
      await ethers.getSigners();

    myUSDT = await ethers.deployContract("MyUSDT", [], deployer);
    collateralNFT = await ethers.deployContract("CollateralNFT", [], deployer);
    receiptNFT = await ethers.deployContract("CollateralReceiptNFT", [], deployer);
    debtToken = await ethers.deployContract("DebtToken", [], deployer);
    positionNFT = await ethers.deployContract("LendingPositionNFT", [], deployer);
    mockOracle = await ethers.deployContract(
      "MockPriceOracle",
      [await collateralNFT.getAddress()],
      deployer
    );

    await Promise.all([
      myUSDT.waitForDeployment(),
      collateralNFT.waitForDeployment(),
      receiptNFT.waitForDeployment(),
      debtToken.waitForDeployment(),
      positionNFT.waitForDeployment(),
      mockOracle.waitForDeployment(),
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
        await mockOracle.getAddress(),
      ],
      deployer
    );
    await pool.waitForDeployment();

    const poolAddr = await pool.getAddress();
    await (await debtToken.connect(deployer).setLendingPool(poolAddr)).wait();
    await (await receiptNFT.connect(deployer).setLendingPool(poolAddr)).wait();
    await (await positionNFT.connect(deployer).setLendingPool(poolAddr)).wait();

    // Seed generous MyUSDT balances for multi-round testing
    for (const signer of [lenderA, lenderB, lenderC, borrowerA, borrowerB]) {
      await (await myUSDT.connect(deployer).transfer(signer.address, parse("5000"))).wait();
    }
  });

  describe("1. Constraint 1 — Maximum LTV <= 70% (borrow, withdrawCollateral & view helpers)", function () {
    it("enforces exact 70% LTV boundary and reverts with typed ExceedsMaxLTV arguments", async function () {
      const poolAddr = await pool.getAddress();

      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("2000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("2000"))).wait();

      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_A)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();

      expect(await pool.getCollateralValue(borrowerA.address)).to.equal(parse("1000"));
      expect(await pool.getMaxBorrowable(borrowerA.address)).to.equal(parse("700"));
      expect(await pool.getRemainingBorrowCapacity(borrowerA.address)).to.equal(parse("700"));
      expect(await pool.getAvailableToBorrow(borrowerA.address)).to.equal(parse("700"));
      expect(await pool.getCurrentLtvBps(borrowerA.address)).to.equal(0n);

      // 1 wei over 70% LTV MUST revert immediately with exact (requestedDebtWad, maxBorrowableWad)
      await expect(pool.connect(borrowerA).borrow(parse("700") + 1n, SAMPLE_CID_A))
        .to.be.revertedWithCustomError(pool, "ExceedsMaxLTV")
        .withArgs(parse("700") + 1n, parse("700"));

      // Exact 70% LTV succeeds
      await (await pool.connect(borrowerA).borrow(parse("700"), SAMPLE_CID_A)).wait();
      expect(await pool.getCurrentLtvBps(borrowerA.address)).to.equal(7_000n);
      expect(await pool.getRemainingBorrowCapacity(borrowerA.address)).to.equal(0n);
      expect(await pool.getAvailableToBorrow(borrowerA.address)).to.equal(0n);

      // Any further 1 wei borrow reverts ExceedsMaxLTV
      await expect(
        pool.connect(borrowerA).borrow(1n, SAMPLE_CID_A)
      ).to.be.revertedWithCustomError(pool, "ExceedsMaxLTV");
    });

    it("includes accrued timestamp interest in LTV headroom across multi-tranche borrows", async function () {
      const poolAddr = await pool.getAddress();

      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_A)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();

      // Tranche 1: borrow 500 (LTV = 50%, Utilization = 50%, Borrow APR = 10%)
      await (await pool.connect(borrowerA).borrow(parse("500"), SAMPLE_CID_A)).wait();
      expect(await pool.getCurrentLtvBps(borrowerA.address)).to.equal(5_000n);

      // Advance 90 days -> ~12.3287 MyUSDT interest accrues, reducing remaining LTV capacity below 200
      await time.increase(90 * 86_400);

      const accrued = await pool.calculateAccruedInterest(borrowerA.address);
      expect(accrued).to.be.greaterThan(parse("12.32"));

      const remainingBefore = await pool.getRemainingBorrowCapacity(borrowerA.address);
      expect(remainingBefore).to.equal(parse("700") - (parse("500") + accrued));
      expect(remainingBefore).to.be.lessThan(parse("188"));

      // Borrowing original 200 headroom MUST revert because currentDebt (500 + accrued) + 200 > 700
      await expect(
        pool.connect(borrowerA).borrow(parse("200"), SAMPLE_CID_A)
      ).to.be.revertedWithCustomError(pool, "ExceedsMaxLTV");

      // Borrowing safely inside remaining LTV headroom (180 MyUSDT) succeeds
      await (await pool.connect(borrowerA).borrow(parse("180"), SAMPLE_CID_A)).wait();
      expect(await pool.getCurrentLtvBps(borrowerA.address)).to.be.lessThanOrEqual(7_000n);
      expect(await pool.getRemainingBorrowCapacity(borrowerA.address)).to.be.greaterThan(0n);
    });

    it("dynamically tightens LTV ceiling when PriceOracle valuation drops for NFT & ERC-20 collateral", async function () {
      const poolAddr = await pool.getAddress();

      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("2000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("2000"))).wait();

      // Borrower A: NFT valued 1,000 -> borrows 400 (40% LTV)
      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_A)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();
      await (await pool.connect(borrowerA).borrow(parse("400"), SAMPLE_CID_A)).wait();

      // Oracle drops multiplier to 50% -> NFT valued 500 -> maxBorrow = 350 < current debt 400
      await (await mockOracle.connect(deployer).setPriceMultiplierBps(5_000)).wait();
      expect(await pool.getCollateralValue(borrowerA.address)).to.equal(parse("500"));
      expect(await pool.getMaxBorrowable(borrowerA.address)).to.equal(parse("350"));
      expect(await pool.getRemainingBorrowCapacity(borrowerA.address)).to.equal(0n);
      expect(await pool.getAvailableToBorrow(borrowerA.address)).to.equal(0n);
      expect(await pool.getCurrentLtvBps(borrowerA.address)).to.be.greaterThanOrEqual(8_000n);

      await expect(
        pool.connect(borrowerA).borrow(1n, SAMPLE_CID_A)
      ).to.be.revertedWithCustomError(pool, "ExceedsMaxLTV");

      // Restore multiplier to 100%, set ERC-20 collateral token price to 0.80 MyUSDT
      await (await mockOracle.connect(deployer).setPriceMultiplierBps(10_000)).wait();
      await (await mockOracle.connect(deployer).setCollateralTokenPrice(parse("0.8"))).wait();

      // Borrower B locks 1,000 ERC-20 collateral -> valuation = 800 -> maxBorrow = 560
      await (await myUSDT.connect(borrowerB).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(borrowerB).depositCollateral(parse("1000"), false)).wait();
      expect(await pool.getCollateralValue(borrowerB.address)).to.equal(parse("800"));
      expect(await pool.getMaxBorrowable(borrowerB.address)).to.equal(parse("560"));

      await expect(pool.connect(borrowerB).borrow(parse("560") + 1n, SAMPLE_CID_B))
        .to.be.revertedWithCustomError(pool, "ExceedsMaxLTV")
        .withArgs(parse("560") + 1n, parse("560"));

      await (await pool.connect(borrowerB).borrow(parse("560"), SAMPLE_CID_B)).wait();
      expect(await pool.getCurrentLtvBps(borrowerB.address)).to.equal(7_000n);
    });

    it("blocks withdrawCollateral() whenever any debt exists and reports exact remainingDebtWad", async function () {
      const poolAddr = await pool.getAddress();

      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_A)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();
      await (await pool.connect(borrowerA).borrow(parse("300"), SAMPLE_CID_A)).wait();

      // Even a tiny active debt blocks withdrawCollateral
      await expect(
        pool.connect(borrowerA).withdrawCollateral()
      ).to.be.revertedWithCustomError(pool, "OutstandingDebtExists");

      // After partial repay (299 MyUSDT), remaining debt still blocks withdrawCollateral
      await (await myUSDT.connect(borrowerA).approve(poolAddr, parse("400"))).wait();
      await (await pool.connect(borrowerA).repay(parse("299"))).wait();
      const debtLeft = await pool.getTotalDebt(borrowerA.address);
      expect(debtLeft).to.be.greaterThan(0n);

      await expect(
        pool.connect(borrowerA).withdrawCollateral()
      ).to.be.revertedWithCustomError(pool, "OutstandingDebtExists");
    });
  });

  describe("2. Constraint 2 — Real-Balance Pool Withdrawal Guards & Reserved Liquidity", function () {
    it("enforces MyUSDT.balanceOf(pool) on withdrawals with exact availableLiquidity and zero phantom liquidity", async function () {
      const poolAddr = await pool.getAddress();

      // Lender A supplies 1,000; Borrower A borrows 600 -> real cash in Pool = 400
      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_A)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();
      await (await pool.connect(borrowerA).borrow(parse("600"), SAMPLE_CID_A)).wait();

      expect(await myUSDT.balanceOf(poolAddr)).to.equal(parse("400"));
      expect(await pool.getAvailableLiquidity()).to.equal(parse("400"));
      expect(await pool.getMaxWithdrawable(1n)).to.equal(parse("400"));

      // Withdrawing 400 + 1 wei MUST revert InsufficientPoolLiquidity(requested, available)
      await expect(pool.connect(lenderA).withdrawLender(1n, parse("400") + 1n))
        .to.be.revertedWithCustomError(pool, "InsufficientPoolLiquidity")
        .withArgs(parse("400") + 1n, parse("400"));

      // Withdrawing exact 400 succeeds -> real Pool balance & availableLiquidity both drop to 0
      await (await pool.connect(lenderA).withdrawLender(1n, parse("400"))).wait();
      expect(await myUSDT.balanceOf(poolAddr)).to.equal(0n);
      expect(await pool.getAvailableLiquidity()).to.equal(0n);
      expect(await pool.getMaxWithdrawable(1n)).to.equal(0n);

      // Zero phantom liquidity: even 1 wei withdrawal reverts with availableLiquidityWad == 0
      await expect(pool.connect(lenderA).withdrawLender(1n, 1n))
        .to.be.revertedWithCustomError(pool, "InsufficientPoolLiquidity")
        .withArgs(1n, 0n);

      // Borrower cannot borrow 1 wei when Pool has 0 available liquidity (even though LTV headroom = 100)
      expect(await pool.getRemainingBorrowCapacity(borrowerA.address)).to.be.greaterThan(parse("99"));
      expect(await pool.getAvailableToBorrow(borrowerA.address)).to.equal(0n);
      await expect(pool.connect(borrowerA).borrow(1n, SAMPLE_CID_A))
        .to.be.revertedWithCustomError(pool, "InsufficientPoolLiquidity")
        .withArgs(1n, 0n);
    });

    it("deducts reservedLiquidity from getAvailableLiquidity() and restricts setReservedLiquidity to owner", async function () {
      const poolAddr = await pool.getAddress();

      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      // Non-owner cannot modify reservedLiquidity
      await expect(
        pool.connect(outsider).setReservedLiquidity(parse("100"))
      ).to.be.revertedWithCustomError(pool, "OwnableUnauthorizedAccount");

      // Owner reserves 250 MyUSDT -> availableLiquidity drops 1,000 -> 750
      await expect(pool.connect(deployer).setReservedLiquidity(parse("250")))
        .to.emit(pool, "ReservedLiquidityUpdated")
        .withArgs(0n, parse("250"));

      expect(await pool.getAvailableLiquidity()).to.equal(parse("750"));
      expect(await pool.getMaxWithdrawable(1n)).to.equal(parse("750"));

      await expect(pool.connect(lenderA).withdrawLender(1n, parse("750") + 1n))
        .to.be.revertedWithCustomError(pool, "InsufficientPoolLiquidity")
        .withArgs(parse("750") + 1n, parse("750"));

      // Reserve larger than pool balance returns 0 cleanly without underflow
      await (await pool.connect(deployer).setReservedLiquidity(parse("5000"))).wait();
      expect(await pool.getAvailableLiquidity()).to.equal(0n);
      expect(await pool.getMaxWithdrawable(1n)).to.equal(0n);
    });

    it("enforces position claimable cap even when other lenders provide abundant Pool liquidity", async function () {
      const poolAddr = await pool.getAddress();

      // Lender A supplies 300 (Position #1), Lender B supplies 700 (Position #2) -> available = 1,000
      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("300"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("300"))).wait();

      await (await myUSDT.connect(lenderB).approve(poolAddr, parse("700"))).wait();
      await (await pool.connect(lenderB).depositLender(parse("700"))).wait();

      expect(await pool.getAvailableLiquidity()).to.equal(parse("1000"));
      expect(await pool.getMaxWithdrawable(1n)).to.equal(parse("300"));
      expect(await pool.getMaxWithdrawable(2n)).to.equal(parse("700"));

      // Lender A MUST NOT touch Lender B's funds
      await expect(pool.connect(lenderA).withdrawLender(1n, parse("300") + 1n))
        .to.be.revertedWithCustomError(pool, "InsufficientClaimableBalance")
        .withArgs(parse("300") + 1n, parse("300"));
    });
  });

  describe("3. Multi-Round Real Pool Balance Accounting (Deposit -> Borrow -> Repay -> Withdraw)", function () {
    it("preserves exact real-balance invariants & solvency across 4 interleaved multi-user rounds", async function () {
      const poolAddr = await pool.getAddress();

      // --- Round 1: Lender A deposits 1,000; Borrower A locks NFT (1,000) and borrows 500 ---
      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("2000"))).wait();
      await (await myUSDT.connect(lenderB).approve(poolAddr, parse("2000"))).wait();
      await (await myUSDT.connect(borrowerA).approve(poolAddr, parse("3000"))).wait();
      await (await myUSDT.connect(borrowerB).approve(poolAddr, parse("3000"))).wait();

      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();
      await assertPoolBalanceInvariants([1n], []);

      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_A)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();
      await (await pool.connect(borrowerA).borrow(parse("500"), SAMPLE_CID_A)).wait();
      await assertPoolBalanceInvariants([1n], [borrowerA.address]);

      // --- Round 2: 30 days pass; Lender B adds 500 (Pos #2); Borrower B locks 1,000 ERC-20 & borrows 600 ---
      await time.increase(30 * 86_400);
      await (await pool.connect(lenderB).depositLender(parse("500"))).wait();
      await assertPoolBalanceInvariants([1n, 2n], [borrowerA.address]);

      await (await pool.connect(borrowerB).depositCollateral(parse("1000"), false)).wait();
      await (await pool.connect(borrowerB).borrow(parse("600"), SAMPLE_CID_B)).wait();
      // Raw balanceOf includes 1,000 locked ERC-20 collateral + 400 free cash = 1,400, but available MUST be 400
      expect(await myUSDT.balanceOf(poolAddr)).to.equal(parse("1400"));
      expect(await pool.getAvailableLiquidity()).to.equal(parse("400"));
      await assertPoolBalanceInvariants([1n, 2n], [borrowerA.address, borrowerB.address]);

      // Lender A withdraws 300 partial -> available drops 400 -> 100
      await (await pool.connect(lenderA).withdrawLender(1n, parse("300"))).wait();
      expect(await pool.getAvailableLiquidity()).to.equal(parse("100"));
      await assertPoolBalanceInvariants([1n, 2n], [borrowerA.address, borrowerB.address]);

      // Lender B tries to withdraw 150 (claimable ~500, available = 100) -> blocked with exact available = 100
      await expect(pool.connect(lenderB).withdrawLender(2n, parse("150")))
        .to.be.revertedWithCustomError(pool, "InsufficientPoolLiquidity")
        .withArgs(parse("150"), parse("100"));

      // --- Round 3: 45 days pass; Borrower A partial repay 250; Borrower B full repay & auto-unlock ERC-20 ---
      await time.increase(45 * 86_400);
      await (await pool.connect(borrowerA).repay(parse("250"))).wait();
      await assertPoolBalanceInvariants([1n, 2n], [borrowerA.address, borrowerB.address]);

      const borrowerBDebt = await pool.getTotalDebt(borrowerB.address);
      await (await pool.connect(borrowerB).repay(borrowerBDebt + parse("5"))).wait();
      expect(await pool.totalTokenCollateralLocked()).to.equal(0n);
      await assertPoolBalanceInvariants([1n, 2n], [borrowerA.address]);

      // --- Round 4: 60 days pass; Borrower A fully repays -> Both Lenders exit 100% cleanly ---
      await time.increase(60 * 86_400);
      const borrowerADebt = await pool.getTotalDebt(borrowerA.address);
      await (await pool.connect(borrowerA).repay(borrowerADebt + parse("5"))).wait();
      await assertPoolBalanceInvariants([1n, 2n], []);

      // Both lenders withdraw 100% of principal + accrued interest with zero insolvency
      const claimA = await pool.getLenderClaimableBalance(1n);
      const claimB = await pool.getLenderClaimableBalance(2n);
      expect(claimA + parse("300")).to.be.greaterThan(parse("1000"));
      expect(claimB).to.be.greaterThan(parse("500"));

      await (await pool.connect(lenderA).withdrawLender(1n, claimA)).wait();
      await assertPoolBalanceInvariants([2n], []);

      await (await pool.connect(lenderB).withdrawLender(2n, claimB)).wait();
      await assertPoolBalanceInvariants([], []);

      const finalInfo = await pool.getPoolInfo();
      expect(finalInfo.totalSupplied).to.equal(0n);
      expect(finalInfo.totalBorrowed).to.equal(0n);
      // Integer-BPS floor truncation on utilizationBps & supplyAprBps guarantees strict positive solvency
      // (total borrower interest collected >= lender interest distributed, leaving tiny surplus < 0.05 MyUSDT).
      const finalPoolBalance = await myUSDT.balanceOf(poolAddr);
      expect(finalPoolBalance).to.be.greaterThanOrEqual(0n);
      expect(finalPoolBalance).to.be.lessThan(parse("0.05"));
      expect(await pool.getAvailableLiquidity()).to.equal(finalPoolBalance);
    });
  });

  describe("4. LendingPositionNFT Multi-Hop Transfer (A -> B -> C) & Owner-Only Withdrawal", function () {
    it("enforces live ownerOf(positionId) across A -> B -> C transfers and prevents double-claiming", async function () {
      const poolAddr = await pool.getAddress();

      // Lender A supplies 1,000; Borrower A borrows 500 for 60 days then repays full debt
      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_A)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();
      await (await pool.connect(borrowerA).borrow(parse("500"), SAMPLE_CID_A)).wait();

      await time.increase(60 * 86_400);
      const fullDebt = await pool.getTotalDebt(borrowerA.address);
      await (await myUSDT.connect(borrowerA).approve(poolAddr, fullDebt + parse("1"))).wait();
      await (await pool.connect(borrowerA).repay(fullDebt + parse("1"))).wait();

      const totalInitialClaimable = await pool.getLenderClaimableBalance(1n);
      expect(totalInitialClaimable).to.be.greaterThan(parse("1008.21"));

      // Hop 1: Lender A -> Lender B
      await (
        await positionNFT
          .connect(lenderA)["safeTransferFrom(address,address,uint256)"](
            lenderA.address,
            lenderB.address,
            1n
          )
      ).wait();

      await expect(pool.connect(lenderA).withdrawLender(1n, parse("10")))
        .to.be.revertedWithCustomError(pool, "NotPositionOwner")
        .withArgs(1n, lenderA.address);

      // Lender B withdraws 300 partial (drains accrued interest + principal slice)
      await (await pool.connect(lenderB).withdrawLender(1n, parse("300"))).wait();

      // Hop 2: Lender B -> Lender C
      await (
        await positionNFT
          .connect(lenderB)["safeTransferFrom(address,address,uint256)"](
            lenderB.address,
            lenderC.address,
            1n
          )
      ).wait();

      await expect(pool.connect(lenderB).withdrawLender(1n, parse("10")))
        .to.be.revertedWithCustomError(pool, "NotPositionOwner")
        .withArgs(1n, lenderB.address);

      const remainingForC = await pool.getLenderClaimableBalance(1n);
      expect(remainingForC).to.equal(totalInitialClaimable - parse("300"));

      // Lender C cannot claim original 1,000
      await expect(pool.connect(lenderC).withdrawLender(1n, parse("1000")))
        .to.be.revertedWithCustomError(pool, "InsufficientClaimableBalance")
        .withArgs(parse("1000"), remainingForC);

      // Lender C withdraws exact remainder -> NFT burned with owner = lenderC
      const balCBefore = await myUSDT.balanceOf(lenderC.address);
      await expect(pool.connect(lenderC).withdrawLender(1n, remainingForC))
        .to.emit(pool, "LenderWithdrawn")
        .and.to.emit(positionNFT, "PositionBurned")
        .withArgs(1n, lenderC.address);

      expect(await myUSDT.balanceOf(lenderC.address)).to.equal(balCBefore + remainingForC);

      // Burned position reverts PositionNotFound
      await expect(pool.connect(lenderC).withdrawLender(1n, 1n))
        .to.be.revertedWithCustomError(pool, "PositionNotFound")
        .withArgs(1n);
    });
  });

  describe("5. Custom Error Completeness for Web3.py / Frontend Decoding", function () {
    it("reverts with explicit custom errors on zero amounts, missing/duplicate collateral, and empty CID", async function () {
      const poolAddr = await pool.getAddress();

      await expect(pool.connect(lenderA).depositLender(0n)).to.be.revertedWithCustomError(
        pool,
        "ZeroAmount"
      );
      await expect(pool.connect(lenderA).withdrawLender(1n, 0n)).to.be.revertedWithCustomError(
        pool,
        "ZeroAmount"
      );
      await expect(
        pool.connect(borrowerA).depositCollateral(0n, false)
      ).to.be.revertedWithCustomError(pool, "ZeroAmount");
      await expect(pool.connect(borrowerA).borrow(0n, SAMPLE_CID_A)).to.be.revertedWithCustomError(
        pool,
        "ZeroAmount"
      );
      await expect(pool.connect(borrowerA).repay(0n)).to.be.revertedWithCustomError(
        pool,
        "ZeroAmount"
      );

      await expect(
        pool.connect(borrowerA).borrow(parse("100"), SAMPLE_CID_A)
      )
        .to.be.revertedWithCustomError(pool, "NoActiveCollateral")
        .withArgs(borrowerA.address);

      await expect(pool.connect(borrowerA).withdrawCollateral())
        .to.be.revertedWithCustomError(pool, "NoActiveCollateral")
        .withArgs(borrowerA.address);

      // Lock collateral once -> duplicate collateral reverts CollateralAlreadyLocked
      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_A)).wait();
      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), NFT_URI_B)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 2n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();

      await expect(pool.connect(borrowerA).depositCollateral(2n, true))
        .to.be.revertedWithCustomError(pool, "CollateralAlreadyLocked")
        .withArgs(borrowerA.address);

      await expect(pool.connect(borrowerA).borrow(parse("100"), "")).to.be.revertedWithCustomError(
        pool,
        "EmptyAgreementCid"
      );
    });
  });
});
