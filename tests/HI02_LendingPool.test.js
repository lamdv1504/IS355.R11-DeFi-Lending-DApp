const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("HI02 - LendingPool Core Lifecycle (depositLender, depositCollateral, borrow, repay)", function () {
  let deployer, lenderA, borrowerA, lenderB, liquidator, outsider;
  let myUSDT, collateralNFT, receiptNFT, debtToken, positionNFT, pool;

  const parse = (val) => ethers.parseUnits(val, 18);
  const SAMPLE_CID = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi";
  const SAMPLE_NFT_URI = "ipfs://bafybeih02fixturecollateralnft0001";

  beforeEach(async function () {
    [deployer, lenderA, borrowerA, lenderB, liquidator, outsider] = await ethers.getSigners();

    // 1. Deploy H01 MyUSDT + H02 Token/NFT suite
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

    // 2. Deploy HI02 LendingPool (priceOracle = ZeroAddress until HI05)
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

    // 3. One-time Pool binding on all H02 PoolControlled contracts
    const poolAddr = await pool.getAddress();
    await (await debtToken.connect(deployer).setLendingPool(poolAddr)).wait();
    await (await receiptNFT.connect(deployer).setLendingPool(poolAddr)).wait();
    await (await positionNFT.connect(deployer).setLendingPool(poolAddr)).wait();

    // 4. Seed test accounts via H01 faucet (1,000 MyUSDT each)
    for (const signer of [lenderA, borrowerA, lenderB, liquidator]) {
      await (await myUSDT.connect(signer).faucet(signer.address, parse("1000"))).wait();
    }
  });

  describe("1. Deployment, Binding & Custody Safety", function () {
    it("wires all H01/H02 contracts properly and rejects zero-address deployment", async function () {
      const poolAddr = await pool.getAddress();
      expect(await pool.myUSDT()).to.equal(await myUSDT.getAddress());
      expect(await pool.collateralNFT()).to.equal(await collateralNFT.getAddress());
      expect(await pool.collateralReceiptNFT()).to.equal(await receiptNFT.getAddress());
      expect(await pool.debtToken()).to.equal(await debtToken.getAddress());
      expect(await pool.lendingPositionNFT()).to.equal(await positionNFT.getAddress());

      expect(await debtToken.lendingPool()).to.equal(poolAddr);
      expect(await receiptNFT.lendingPool()).to.equal(poolAddr);
      expect(await positionNFT.lendingPool()).to.equal(poolAddr);

      await expect(
        ethers.deployContract(
          "LendingPool",
          [
            ethers.ZeroAddress,
            await myUSDT.getAddress(),
            await collateralNFT.getAddress(),
            await receiptNFT.getAddress(),
            await debtToken.getAddress(),
            await positionNFT.getAddress(),
            ethers.ZeroAddress,
          ],
          deployer
        )
      ).to.be.revertedWithCustomError(pool, "InvalidAddress");
    });

    it("rejects direct ERC-721 safeTransferFrom into Pool bypassing depositCollateral", async function () {
      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), SAMPLE_NFT_URI)).wait();
      const poolAddr = await pool.getAddress();
      await expect(
        collateralNFT.connect(borrowerA)["safeTransferFrom(address,address,uint256)"](
          borrowerA.address,
          poolAddr,
          1n
        )
      ).to.be.revertedWithCustomError(pool, "UnauthorizedNFTTransfer");
    });
  });

  describe("2. Core Lifecycle with CollateralNFT (Lend -> Collateral -> Borrow -> Repay -> Unlock)", function () {
    it("executes full 4-step lifecycle with receipt issuance, DebtToken mint/burn, and auto-unlock on full repay", async function () {
      const poolAddr = await pool.getAddress();

      // Step 1: Lender A deposits 1,000 MyUSDT -> mints LendingPositionNFT #1
      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await expect(pool.connect(lenderA).depositLender(parse("1000")))
        .to.emit(pool, "LenderDeposited")
        .and.to.emit(positionNFT, "PositionMinted")
        .withArgs(1n, lenderA.address, parse("1000"))
        .and.to.emit(pool, "InterestRateUpdated");

      expect(await positionNFT.ownerOf(1n)).to.equal(lenderA.address);
      expect(await pool.getAvailableLiquidity()).to.equal(parse("1000"));

      // Step 2a: Borrower A pledges CollateralNFT #1 (valuation = 1,000 MyUSDT) -> mints CollateralReceiptNFT #1
      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), SAMPLE_NFT_URI)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();

      await expect(pool.connect(borrowerA).depositCollateral(1n, true))
        .to.emit(pool, "CollateralDeposited")
        .and.to.emit(receiptNFT, "ReceiptMinted")
        .withArgs(1n, borrowerA.address, true, 1n);

      expect(await collateralNFT.ownerOf(1n)).to.equal(poolAddr);
      expect(await receiptNFT.ownerOf(1n)).to.equal(borrowerA.address);
      expect(await receiptNFT.activeReceiptOf(borrowerA.address)).to.equal(1n);
      expect(await pool.getCollateralValue(borrowerA.address)).to.equal(parse("1000"));
      expect(await pool.getMaxBorrowable(borrowerA.address)).to.equal(parse("700"));

      // Step 2b: Borrower A borrows 500 MyUSDT with IPFS agreement CID -> mints 500 DebtToken
      await expect(pool.connect(borrowerA).borrow(parse("500"), SAMPLE_CID))
        .to.emit(pool, "LoanBorrowed")
        .and.to.emit(debtToken, "DebtMinted")
        .withArgs(borrowerA.address, parse("500"))
        .and.to.emit(pool, "InterestRateUpdated");

      expect(await myUSDT.balanceOf(borrowerA.address)).to.equal(parse("1500"));
      expect(await debtToken.balanceOf(borrowerA.address)).to.equal(parse("500"));
      expect(await pool.getAvailableLiquidity()).to.equal(parse("500"));
      expect(await pool.getHealthFactor(borrowerA.address)).to.equal(parse("1.6"));

      const loan = await pool.getLoanPosition(borrowerA.address);
      expect(loan.active).to.equal(true);
      expect(loan.isNFTCollateral).to.equal(true);
      expect(loan.collateralTokenId).to.equal(1n);
      expect(loan.receiptTokenId).to.equal(1n);
      expect(loan.principal).to.equal(parse("500"));
      expect(loan.ipfsAgreementCid).to.equal(SAMPLE_CID);

      const poolInfo = await pool.getPoolInfo();
      expect(poolInfo.utilizationBps).to.equal(5_000n);
      expect(poolInfo.borrowAprBps).to.equal(1_000n); // 10.00% APR
      expect(poolInfo.supplyAprBps).to.equal(500n);   // 5.00% APR

      // Cannot withdraw collateral while debt > 0
      await expect(pool.connect(borrowerA).withdrawCollateral()).to.be.revertedWithCustomError(
        pool,
        "OutstandingDebtExists"
      );

      // Step 3a: Advance 60 days -> verify interest accrues > 0
      await time.increase(60 * 86_400);
      const accrued = await pool.calculateAccruedInterest(borrowerA.address);
      expect(accrued).to.be.greaterThan(parse("8.21"));
      expect(accrued).to.be.lessThan(parse("8.23"));

      // Partial repay of 200 MyUSDT pays interest first + reduces principal, keeps collateral locked
      await (await myUSDT.connect(borrowerA).approve(poolAddr, parse("600"))).wait();
      await expect(pool.connect(borrowerA).repay(parse("200")))
        .to.emit(pool, "LoanRepaid")
        .and.to.emit(debtToken, "DebtBurned");

      expect(await collateralNFT.ownerOf(1n)).to.equal(poolAddr);
      expect(await receiptNFT.activeReceiptOf(borrowerA.address)).to.equal(1n);

      // Step 3b: Repay remaining debt (pass generous buffer; pool caps exact payment so zero overpayment)
      const remainingBefore = await pool.getTotalDebt(borrowerA.address);
      const borrowerBalBefore = await myUSDT.balanceOf(borrowerA.address);

      await expect(pool.connect(borrowerA).repay(remainingBefore + parse("10")))
        .to.emit(pool, "LoanRepaid")
        .and.to.emit(pool, "CollateralWithdrawn")
        .and.to.emit(receiptNFT, "ReceiptSettled")
        .withArgs(1n, borrowerA.address, false);

      // Verify exact settlement: 0 debt, 0 DebtToken, CollateralNFT returned, Receipt settled & burned
      expect(await debtToken.balanceOf(borrowerA.address)).to.equal(0n);
      expect(await pool.getTotalDebt(borrowerA.address)).to.equal(0n);
      expect(await collateralNFT.ownerOf(1n)).to.equal(borrowerA.address);
      expect(await receiptNFT.activeReceiptOf(borrowerA.address)).to.equal(0n);
      await expect(receiptNFT.ownerOf(1n)).to.be.reverted;

      // Receipt history remains queryable with active = false
      const receiptHistory = await receiptNFT.getReceiptInfo(1n);
      expect(receiptHistory.active).to.equal(false);
      expect(receiptHistory.borrower).to.equal(borrowerA.address);

      // Borrower was NOT overcharged the +10 MyUSDT buffer
      const borrowerBalAfter = await myUSDT.balanceOf(borrowerA.address);
      expect(borrowerBalBefore - borrowerBalAfter).to.be.lessThan(remainingBefore + parse("0.01"));

      // Borrower can re-pledge the returned NFT for a new loan (no stale state / duplicate receipt)
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await expect(pool.connect(borrowerA).depositCollateral(1n, true))
        .to.emit(receiptNFT, "ReceiptMinted")
        .withArgs(2n, borrowerA.address, true, 1n);

      // Step 4: Lender A withdraws 1,000 principal + earned interest cleanly
      const claimable = await pool.getLenderClaimableBalance(1n);
      expect(claimable).to.be.greaterThan(parse("1008.21"));
      await expect(pool.connect(lenderA).withdrawLender(1n, claimable))
        .to.emit(pool, "LenderWithdrawn")
        .and.to.emit(positionNFT, "PositionBurned")
        .withArgs(1n, lenderA.address);

      expect(await myUSDT.balanceOf(lenderA.address)).to.equal(claimable);
      await expect(positionNFT.ownerOf(1n)).to.be.reverted;
    });
  });

  describe("3. ERC-20 Collateral Custody & Liquidity Segregation", function () {
    it("segregates locked ERC-20 collateral from lender available liquidity and allows idle withdrawCollateral()", async function () {
      const poolAddr = await pool.getAddress();

      // Lender A deposits 1,000 MyUSDT
      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      // Borrower A deposits 1,000 MyUSDT as ERC-20 collateral (isNFT = false)
      await (await myUSDT.connect(borrowerA).approve(poolAddr, parse("1000"))).wait();
      await expect(pool.connect(borrowerA).depositCollateral(parse("1000"), false))
        .to.emit(pool, "CollateralDeposited")
        .and.to.emit(receiptNFT, "ReceiptMinted")
        .withArgs(1n, borrowerA.address, false, parse("1000"));

      // Raw pool balance is 2,000, but available liquidity for lenders/borrows is strictly 1,000
      expect(await myUSDT.balanceOf(poolAddr)).to.equal(parse("2000"));
      expect(await pool.totalTokenCollateralLocked()).to.equal(parse("1000"));
      expect(await pool.getAvailableLiquidity()).to.equal(parse("1000"));

      // Borrower A borrows 500 -> available liquidity becomes 500 (not 1,500!)
      await (await pool.connect(borrowerA).borrow(parse("500"), SAMPLE_CID)).wait();
      expect(await pool.getAvailableLiquidity()).to.equal(parse("500"));

      // Lender A CANNOT withdraw 600 (even though raw balanceOf is 1,500) because 1,000 belongs to Borrower collateral
      await expect(
        pool.connect(lenderA).withdrawLender(1n, parse("600"))
      ).to.be.revertedWithCustomError(pool, "InsufficientPoolLiquidity");

      // Borrower A gets a small faucet top-up to cover accrued interest, then repays full debt
      await (await myUSDT.connect(borrowerA).faucet(borrowerA.address, parse("10"))).wait();
      const totalDebt = await pool.getTotalDebt(borrowerA.address);
      await (await myUSDT.connect(borrowerA).approve(poolAddr, totalDebt + parse("1"))).wait();
      await (await pool.connect(borrowerA).repay(totalDebt + parse("1"))).wait();
      expect(await pool.totalTokenCollateralLocked()).to.equal(0n);

      // Borrower A deposits 500 ERC-20 collateral without borrowing, then withdraws via withdrawCollateral()
      await (await myUSDT.connect(borrowerA).approve(poolAddr, parse("500"))).wait();
      await (await pool.connect(borrowerA).depositCollateral(parse("500"), false)).wait();
      await expect(pool.connect(borrowerA).withdrawCollateral())
        .to.emit(pool, "CollateralWithdrawn")
        .and.to.emit(receiptNFT, "ReceiptSettled")
        .withArgs(2n, borrowerA.address, false);
      expect(await pool.totalTokenCollateralLocked()).to.equal(0n);
    });
  });

  describe("4. LendingPositionNFT Transfer Ownership & Anti-Double-Claiming", function () {
    it("transfers exclusive withdrawal rights for principal + interest to new NFT owner without double-claiming", async function () {
      const poolAddr = await pool.getAddress();

      // Lender A deposits 1,000 MyUSDT -> Position #1
      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      // Borrower A locks NFT & borrows 500 for 60 days, then repays
      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), SAMPLE_NFT_URI)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();
      await (await pool.connect(borrowerA).borrow(parse("500"), SAMPLE_CID)).wait();

      await time.increase(60 * 86_400);
      const totalDebt = await pool.getTotalDebt(borrowerA.address);
      await (await myUSDT.connect(borrowerA).approve(poolAddr, totalDebt + parse("1"))).wait();
      await (await pool.connect(borrowerA).repay(totalDebt + parse("1"))).wait();

      // Lender A transfers LendingPositionNFT #1 to Lender B (emits ERC-721 Transfer event, no duplicate position)
      await expect(
        positionNFT
          .connect(lenderA)["safeTransferFrom(address,address,uint256)"](
            lenderA.address,
            lenderB.address,
            1n
          )
      )
        .to.emit(positionNFT, "Transfer")
        .withArgs(lenderA.address, lenderB.address, 1n);

      expect(await positionNFT.ownerOf(1n)).to.equal(lenderB.address);
      expect(await positionNFT.balanceOf(lenderA.address)).to.equal(0n);
      expect(await positionNFT.balanceOf(lenderB.address)).to.equal(1n);
      expect((await pool.getLenderPosition(2n)).active).to.equal(false);

      // Previous owner (Lender A) is blocked from withdrawing
      await expect(
        pool.connect(lenderA).withdrawLender(1n, parse("100"))
      ).to.be.revertedWithCustomError(pool, "NotPositionOwner");

      // Lender B withdraws partial 400 MyUSDT (takes all accrued interest first + remainder from principal)
      const claimableBefore = await pool.getLenderClaimableBalance(1n);
      const lenderBBalBefore = await myUSDT.balanceOf(lenderB.address);
      await (await pool.connect(lenderB).withdrawLender(1n, parse("400"))).wait();

      // Transfer back to Lender A: Lender A can ONLY claim the remaining balance (never double-claims the 400!)
      const remainingClaimable = await pool.getLenderClaimableBalance(1n);
      expect(remainingClaimable).to.equal(claimableBefore - parse("400"));

      await (
        await positionNFT
          .connect(lenderB)["safeTransferFrom(address,address,uint256)"](
            lenderB.address,
            lenderA.address,
            1n
          )
      ).wait();

      // Attempting to over-claim original 1,000 fails
      await expect(
        pool.connect(lenderA).withdrawLender(1n, parse("1000"))
      ).to.be.revertedWithCustomError(pool, "InsufficientClaimableBalance");

      // Claiming exact remaining balance succeeds and burns Position #1 with currentOwner = lenderA
      await expect(pool.connect(lenderA).withdrawLender(1n, remainingClaimable))
        .to.emit(positionNFT, "PositionBurned")
        .withArgs(1n, lenderA.address);

      expect(await myUSDT.balanceOf(lenderB.address)).to.equal(lenderBBalBefore + parse("400"));
      expect(await myUSDT.balanceOf(lenderA.address)).to.equal(remainingClaimable);

      // Re-withdrawing burned position reverts PositionNotFound
      await expect(
        pool.connect(lenderA).withdrawLender(1n, 1n)
      ).to.be.revertedWithCustomError(pool, "PositionNotFound");
    });
  });

  describe("5. Validation Guards & Reentrancy Protection", function () {
    it("enforces LTV <= 70%, non-empty agreement CID, and active collateral requirement", async function () {
      const poolAddr = await pool.getAddress();
      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("1000"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("1000"))).wait();

      // Borrow without collateral reverts
      await expect(
        pool.connect(borrowerA).borrow(parse("100"), SAMPLE_CID)
      ).to.be.revertedWithCustomError(pool, "NoActiveCollateral");

      // Lock 1,000 NFT collateral -> max LTV 70% = 700
      await (await collateralNFT.mintCollateral(borrowerA.address, parse("1000"), SAMPLE_NFT_URI)).wait();
      await (await collateralNFT.connect(borrowerA).approve(poolAddr, 1n)).wait();
      await (await pool.connect(borrowerA).depositCollateral(1n, true)).wait();

      // Empty CID reverts
      await expect(
        pool.connect(borrowerA).borrow(parse("100"), "")
      ).to.be.revertedWithCustomError(pool, "EmptyAgreementCid");

      // Exceeding 70% LTV (700 MyUSDT + 1 wei) reverts ExceedsMaxLTV
      await expect(
        pool.connect(borrowerA).borrow(parse("700") + 1n, SAMPLE_CID)
      ).to.be.revertedWithCustomError(pool, "ExceedsMaxLTV");

      // Exact 70% LTV (700 MyUSDT) succeeds
      await (await pool.connect(borrowerA).borrow(parse("700"), SAMPLE_CID)).wait();
      expect(await debtToken.balanceOf(borrowerA.address)).to.equal(parse("700"));
    });

    it("blocks reentrancy callbacks on depositLender, depositCollateral, and borrow via ReentrancyGuard", async function () {
      const poolAddr = await pool.getAddress();
      const attacker = await ethers.deployContract(
        "ReentrantAttacker",
        [poolAddr, await myUSDT.getAddress()],
        outsider
      );
      await attacker.waitForDeployment();
      const attackerAddr = await attacker.getAddress();

      // Fund attacker contract with MyUSDT
      await (await myUSDT.connect(outsider).faucet(attackerAddr, parse("1000"))).wait();

      // 1. Re-entering depositLender during LendingPositionNFT._safeMint is blocked
      await (await attacker.attackDepositLender(parse("100"))).wait();
      expect(await attacker.reentrancyAttempted()).to.equal(true);
      expect(await attacker.reentrancyBlocked()).to.equal(true);

      // 2. Re-entering depositCollateral during CollateralReceiptNFT._safeMint is blocked
      await (await attacker.attackDepositCollateralToken(parse("100"))).wait();
      expect(await attacker.reentrancyAttempted()).to.equal(true);
      expect(await attacker.reentrancyBlocked()).to.equal(true);

      // 3. Re-entering borrow() during CollateralReceiptNFT._safeMint on a fresh attacker is blocked
      const attacker2 = await ethers.deployContract(
        "ReentrantAttacker",
        [poolAddr, await myUSDT.getAddress()],
        outsider
      );
      await attacker2.waitForDeployment();
      const attacker2Addr = await attacker2.getAddress();
      await (await myUSDT.connect(outsider).faucet(attacker2Addr, parse("500"))).wait();
      await (await attacker2.attackBorrowDuringCollateralMint(parse("200"))).wait();
      expect(await attacker2.reentrancyAttempted()).to.equal(true);
      expect(await attacker2.reentrancyBlocked()).to.equal(true);

      // 4. Re-entering repay() during CollateralNFT safeTransferFrom unlock callback is blocked
      const attacker3 = await ethers.deployContract(
        "ReentrantAttacker",
        [poolAddr, await myUSDT.getAddress()],
        outsider
      );
      await attacker3.waitForDeployment();
      const attacker3Addr = await attacker3.getAddress();
      await (await myUSDT.connect(outsider).faucet(attacker3Addr, parse("200"))).wait();
      await (await myUSDT.connect(lenderA).approve(poolAddr, parse("500"))).wait();
      await (await pool.connect(lenderA).depositLender(parse("500"))).wait();
      await (await collateralNFT.mintCollateral(attacker3Addr, parse("1000"), SAMPLE_NFT_URI)).wait();
      await (
        await attacker3.setupAndAttackRepayWithNFT(
          await collateralNFT.getAddress(),
          1n,
          parse("100"),
          SAMPLE_CID
        )
      ).wait();
      expect(await attacker3.reentrancyAttempted()).to.equal(true);
      expect(await attacker3.reentrancyBlocked()).to.equal(true);
      expect(await collateralNFT.ownerOf(1n)).to.equal(attacker3Addr);
      expect(await receiptNFT.balanceOf(attacker3Addr)).to.equal(0n);
    });
  });
});
