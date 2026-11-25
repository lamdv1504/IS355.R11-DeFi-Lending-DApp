const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("HI01 - ProtocolConstants, ProtocolMath & Interface Compatibility", function () {
  let harness;

  const WAD = ethers.parseUnits("1", 18);
  const BPS = 10_000n;
  const SECONDS_PER_YEAR = 31_536_000n;
  const MAX_UINT256 = ethers.MaxUint256;

  // Enum indices from ProtocolMath.HealthStatus
  const STATUS_LIQUIDATABLE = 0n;
  const STATUS_WARNING = 1n;
  const STATUS_SAFE = 2n;

  beforeEach(async function () {
    const Harness = await ethers.getContractFactory("ProtocolMathHarness");
    harness = await Harness.deploy();
    await harness.waitForDeployment();
  });

  describe("1. Single Source of Truth Constants", function () {
    it("matches canonical WAD, BPS, LTV 70%, Liquidation 80%, Bonus 5%, and APR model", async function () {
      const snap = await harness.constantsSnapshot();
      expect(snap.wad).to.equal(WAD);
      expect(snap.bps).to.equal(BPS);
      expect(snap.secondsPerYear).to.equal(SECONDS_PER_YEAR);
      expect(snap.maxLtvBps).to.equal(7_000n);
      expect(snap.liquidationThresholdBps).to.equal(8_000n);
      expect(snap.liquidationBonusBps).to.equal(500n);
      expect(snap.baseBorrowAprBps).to.equal(500n);
      expect(snap.utilizationSlopeBps).to.equal(1_000n);
    });
  });

  describe("2. Max LTV (70% / 7000 BPS)", function () {
    it("allows borrowing up to 700 MyUSDT for 1,000 MyUSDT collateral", async function () {
      const collateral = ethers.parseUnits("1000", 18);
      const maxBorrow = await harness.calculateMaxBorrow(collateral);
      expect(maxBorrow).to.equal(ethers.parseUnits("700", 18));
    });

    it("handles zero and fractional Wei collateral values without overflow", async function () {
      expect(await harness.calculateMaxBorrow(0n)).to.equal(0n);
      const oddCollateral = ethers.parseUnits("750", 18);
      expect(await harness.calculateMaxBorrow(oddCollateral)).to.equal(
        ethers.parseUnits("525", 18)
      );
    });
  });

  describe("3. Health Factor (BPS 8000 / WAD 1e18) & Boundary Cases", function () {
    it("returns infinite HF (MaxUint256) and SAFE when totalDebt == 0", async function () {
      const collateral = ethers.parseUnits("1000", 18);
      const hf = await harness.calculateHealthFactor(collateral, 0n);
      expect(hf).to.equal(MAX_UINT256);
      expect(await harness.classifyHealthFactor(hf)).to.equal(STATUS_SAFE);
      expect(await harness.isLiquidatable(hf)).to.equal(false);
    });

    it("returns HF == 1.0e18 exactly at 80% threshold and treats HF == 1.0 as NOT liquidatable", async function () {
      const collateral = ethers.parseUnits("1000", 18);
      const debtAtExactThreshold = ethers.parseUnits("800", 18);
      const hf = await harness.calculateHealthFactor(collateral, debtAtExactThreshold);

      expect(hf).to.equal(WAD);
      expect(await harness.classifyHealthFactor(hf)).to.equal(STATUS_WARNING);
      expect(await harness.isLiquidatable(hf)).to.equal(false);
    });

    it("triggers LIQUIDATABLE strictly when debt exceeds 80% threshold by even 1 wei", async function () {
      const collateral = ethers.parseUnits("1000", 18);
      const debtAboveThreshold = ethers.parseUnits("800", 18) + 1n;
      const hf = await harness.calculateHealthFactor(collateral, debtAboveThreshold);

      expect(hf).to.be.lessThan(WAD);
      expect(await harness.classifyHealthFactor(hf)).to.equal(STATUS_LIQUIDATABLE);
      expect(await harness.isLiquidatable(hf)).to.equal(true);
    });

    it("computes HF = 1.60 (SAFE) for Demo 1000 collateral / 500 borrow, and HF = 0.96 (LIQUIDATABLE) after 40% drop", async function () {
      const debt = ethers.parseUnits("500", 18);

      const hfInitial = await harness.calculateHealthFactor(ethers.parseUnits("1000", 18), debt);
      expect(hfInitial).to.equal(ethers.parseUnits("1.6", 18));
      expect(await harness.classifyHealthFactor(hfInitial)).to.equal(STATUS_SAFE);
      expect(await harness.isLiquidatable(hfInitial)).to.equal(false);

      const hfAfterDrop = await harness.calculateHealthFactor(ethers.parseUnits("600", 18), debt);
      expect(hfAfterDrop).to.equal(ethers.parseUnits("0.96", 18));
      expect(await harness.classifyHealthFactor(hfAfterDrop)).to.equal(STATUS_LIQUIDATABLE);
      expect(await harness.isLiquidatable(hfAfterDrop)).to.equal(true);
    });

    it("classifies max-LTV (700 debt / 1000 collateral -> HF ~ 1.142857) as WARNING", async function () {
      const hf = await harness.calculateHealthFactor(
        ethers.parseUnits("1000", 18),
        ethers.parseUnits("700", 18)
      );
      expect(hf).to.equal(1_142_857_142_857_142_857n);
      expect(await harness.classifyHealthFactor(hf)).to.equal(STATUS_WARNING);
      expect(await harness.isLiquidatable(hf)).to.equal(false);
    });

    it("handles exact HF = 1.50 boundary and zero-collateral edge cases safely", async function () {
      // Exact HF = 1.50 (1500 * 0.8 / 800 = 1.5e18) -> SAFE
      const hfExact150 = await harness.calculateHealthFactor(
        ethers.parseUnits("1500", 18),
        ethers.parseUnits("800", 18)
      );
      expect(hfExact150).to.equal(ethers.parseUnits("1.5", 18));
      expect(await harness.classifyHealthFactor(hfExact150)).to.equal(STATUS_SAFE);
      expect(await harness.classifyHealthFactor(hfExact150 - 1n)).to.equal(STATUS_WARNING);

      // Zero collateral + zero debt -> infinite HF (SAFE); zero collateral + debt > 0 -> HF = 0 (LIQUIDATABLE)
      expect(await harness.calculateHealthFactor(0n, 0n)).to.equal(MAX_UINT256);
      const hfZeroCollatWithDebt = await harness.calculateHealthFactor(0n, ethers.parseUnits("100", 18));
      expect(hfZeroCollatWithDebt).to.equal(0n);
      expect(await harness.classifyHealthFactor(hfZeroCollatWithDebt)).to.equal(STATUS_LIQUIDATABLE);
      expect(await harness.isLiquidatable(hfZeroCollatWithDebt)).to.equal(true);
    });

    it("applies 5% liquidation bonus capped by total collateral value", async function () {
      const debtCovered = ethers.parseUnits("500", 18);
      const collateral600 = ethers.parseUnits("600", 18);
      expect(await harness.calculateLiquidationSeizeValue(debtCovered, collateral600)).to.equal(
        ethers.parseUnits("525", 18)
      );

      // Capped if collateral drops below debt * 1.05
      const collateral510 = ethers.parseUnits("510", 18);
      expect(await harness.calculateLiquidationSeizeValue(debtCovered, collateral510)).to.equal(
        collateral510
      );
    });
  });

  describe("4. Hybrid APR Interest Model & Non-Retroactive Multi-Period Accrual", function () {
    it("computes Borrow APR = 10% and Supply APR = 5% at 50% utilization (Demo 1000 -> 500)", async function () {
      const supplied = ethers.parseUnits("1000", 18);
      const borrowed = ethers.parseUnits("500", 18);

      const utilization = await harness.calculateUtilizationBps(borrowed, supplied);
      const borrowApr = await harness.calculateBorrowAprBps(utilization);
      const supplyApr = await harness.calculateSupplyAprBps(borrowApr, utilization);

      expect(utilization).to.equal(5_000n);
      expect(borrowApr).to.equal(1_000n);
      expect(supplyApr).to.equal(500n);

      // Verify exact 60-day accounting parity between borrower interest paid and lender interest earned
      const sixtyDays = 60n * 86_400n;
      const borrowerInterest = await harness.calculateSimpleInterest(borrowed, borrowApr, sixtyDays);
      const lenderInterest = await harness.calculateSimpleInterest(supplied, supplyApr, sixtyDays);
      expect(borrowerInterest).to.equal(8_219_178_082_191_780_821n);
      expect(lenderInterest).to.equal(borrowerInterest);
    });

    it("accrues multi-period index without retroactively applying a new rate to past time", async function () {
      const thirtyDays = 30n * 86_400n;
      // Period 1: 30 days at 10% APR (1000 BPS)
      const indexAfterP1 = await harness.calculateNextIndex(WAD, 1_000n, thirtyDays);
      // Period 2: 30 days at 15% APR (1500 BPS) after utilization rises to 100%
      const indexAfterP2 = await harness.calculateNextIndex(indexAfterP1, 1_500n, thirtyDays);

      // Retroactively applying 15% to all 60 days would produce a strictly larger index
      const wrongRetroactiveIndex = await harness.calculateNextIndex(WAD, 1_500n, 2n * thirtyDays);
      expect(indexAfterP2).to.be.lessThan(wrongRetroactiveIndex);

      // Strictly greater than staying at 10% for all 60 days
      const flatTenPercentIndex = await harness.calculateNextIndex(WAD, 1_000n, 2n * thirtyDays);
      expect(indexAfterP2).to.be.greaterThan(flatTenPercentIndex);
    });
  });

  describe("5. H01 MyUSDT Interface Compatibility Check", function () {
    it("interacts with deployed H01 MyUSDT through IMyUSDT ABI seamlessly", async function () {
      const MyUSDT = await ethers.getContractFactory("MyUSDT");
      const token = await MyUSDT.deploy();
      await token.waitForDeployment();

      const [deployer, lender] = await ethers.getSigners();
      const myUsdtViaInterface = await ethers.getContractAt("IMyUSDT", await token.getAddress());

      expect(await myUsdtViaInterface.INITIAL_SUPPLY()).to.equal(ethers.parseUnits("1000000", 18));
      expect(await myUsdtViaInterface.MAX_FAUCET_AMOUNT()).to.equal(ethers.parseUnits("1000", 18));

      const demoAmount = ethers.parseUnits("1000", 18);
      await myUsdtViaInterface.connect(lender).faucet(lender.address, demoAmount);
      expect(await myUsdtViaInterface.balanceOf(lender.address)).to.equal(demoAmount);
      expect(await myUsdtViaInterface.balanceOf(deployer.address)).to.equal(
        ethers.parseUnits("1000000", 18)
      );
    });
  });
});
