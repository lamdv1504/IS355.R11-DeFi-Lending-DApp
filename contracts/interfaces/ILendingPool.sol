// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title ILendingPool - Canonical contract interface for Core LendingPool (HI01 -> HI02/HI03/HI04/HI05).
/// @notice Defines exact function signatures, data structures, custom errors, and event schemas
///         shared across Smart Contracts (Hiếu/Hùng), Web3.py Backend (Quân), and React UI (Lâm).
interface ILendingPool {
    // -------------------------------------------------------------------------
    // Data Structures
    // -------------------------------------------------------------------------

    struct PoolInfo {
        uint256 totalSupplied;         // Total principal supplied by active lenders (WAD)
        uint256 totalBorrowed;         // Total active principal borrowed (WAD)
        uint256 reservedLiquidity;     // Optional protocol reserve held back from withdrawals (WAD)
        uint256 borrowIndex;           // Cumulative borrow interest index (WAD, starts at 1e18)
        uint256 supplyIndex;           // Cumulative supply interest index (WAD, starts at 1e18)
        uint256 borrowAprBps;          // Current annual simple borrow APR (BPS, 10000 = 100%)
        uint256 supplyAprBps;          // Current annual simple supply APR (BPS, 10000 = 100%)
        uint256 utilizationBps;        // Current pool utilization rate (BPS, 0..10000)
        uint256 lastAccrualTimestamp;  // Last timestamp when indices were accrued
    }

    struct LenderPosition {
        uint256 positionId;            // Matches LendingPositionNFT tokenId
        uint256 principal;             // Remaining deposited principal (WAD)
        uint256 supplyIndexSnapshot;   // Pool supplyIndex when position was created or last settled (WAD)
        uint256 accruedInterest;       // Locked-in unpaid interest earned (WAD)
        uint256 depositedAt;           // Initial deposit timestamp
        bool active;                   // True while position has remaining claimable balance
    }

    struct LoanPosition {
        address borrower;              // Borrower wallet address
        bool isNFTCollateral;          // True if collateral is CollateralNFT, false if ERC-20 collateral
        uint256 collateralAmount;      // ERC-20 collateral amount (WAD) if !isNFTCollateral
        uint256 collateralTokenId;     // CollateralNFT tokenId if isNFTCollateral
        uint256 receiptTokenId;        // CollateralReceiptNFT tokenId issued upon depositCollateral()
        uint256 principal;             // Active borrowed principal in MyUSDT (WAD)
        uint256 borrowIndexSnapshot;   // Pool borrowIndex when loan was opened or last updated (WAD)
        uint256 accruedInterest;       // Locked-in unpaid interest from previous periods (WAD)
        uint256 startTimestamp;        // Initial borrow timestamp
        uint256 lastInterestUpdate;    // Last timestamp borrower interest was checkpointed
        string ipfsAgreementCid;       // IPFS CID of Loan Agreement PDF
        bool active;                   // True while collateral is locked or debt > 0
    }

    struct InterestRateSnapshot {
        uint256 timestamp;             // Current block.timestamp when snapshot is read
        uint256 utilizationBps;        // Current pool utilization rate (BPS, 0..10000)
        uint256 borrowAprBps;          // On-chain simple Borrow APR (BPS)
        uint256 supplyAprBps;          // On-chain simple Supply APR (BPS)
        uint256 borrowApyRefBps;       // Reference daily-compounded Borrow APY (BPS, display only)
        uint256 supplyApyRefBps;       // Reference daily-compounded Supply APY (BPS, display only)
        uint256 borrowIndexWad;        // Live cumulative borrow index preview (WAD)
        uint256 supplyIndexWad;        // Live cumulative supply index preview (WAD)
    }

    // -------------------------------------------------------------------------
    // Standard Custom Errors (Parsed by Web3.py Q02/Q05 & Frontend L02/L03)
    // -------------------------------------------------------------------------

    error ZeroAmount();
    error InvalidAddress();
    error PositionNotFound(uint256 positionId);
    error NotPositionOwner(uint256 positionId, address caller);
    error NoActiveCollateral(address borrower);
    error CollateralAlreadyLocked(address borrower);
    error ExceedsMaxLTV(uint256 requestedDebtWad, uint256 maxBorrowableWad);
    error InsufficientPoolLiquidity(uint256 requestedWad, uint256 availableLiquidityWad);
    error InsufficientClaimableBalance(uint256 requestedWad, uint256 claimableWad);
    error OutstandingDebtExists(uint256 remainingDebtWad);
    error HealthFactorSafe(uint256 currentHealthFactorWad);
    error EmptyAgreementCid();

    // -------------------------------------------------------------------------
    // Canonical Events (Consumed by Q04 Credit Report & Audit Logs Indexer)
    // -------------------------------------------------------------------------

    event LenderDeposited(
        address indexed lender,
        uint256 indexed positionId,
        uint256 amountWad,
        uint256 timestamp
    );

    event LenderWithdrawn(
        address indexed owner,
        uint256 indexed positionId,
        uint256 principalWithdrawnWad,
        uint256 interestWithdrawnWad,
        uint256 timestamp
    );

    event CollateralDeposited(
        address indexed borrower,
        bool isNFT,
        uint256 assetIdOrAmount,
        uint256 indexed receiptTokenId,
        uint256 valuationWad,
        uint256 timestamp
    );

    event CollateralWithdrawn(
        address indexed borrower,
        bool isNFT,
        uint256 assetIdOrAmount,
        uint256 indexed receiptTokenId,
        uint256 timestamp
    );

    event LoanBorrowed(
        address indexed borrower,
        uint256 amountWad,
        uint256 totalPrincipalWad,
        uint256 borrowAprBps,
        string agreementCid,
        uint256 timestamp
    );

    event LoanRepaid(
        address indexed borrower,
        uint256 amountPaidWad,
        uint256 interestPaidWad,
        uint256 principalPaidWad,
        uint256 remainingDebtWad,
        uint256 timestamp
    );

    event LoanLiquidated(
        address indexed borrower,
        address indexed liquidator,
        uint256 debtCoveredWad,
        uint256 collateralSeizedWad,
        uint256 healthFactorBeforeWad,
        uint256 timestamp
    );

    event InterestRateUpdated(
        uint256 timestamp,
        uint256 borrowAprBps,
        uint256 supplyAprBps,
        uint256 utilizationBps,
        uint256 totalSuppliedWad,
        uint256 totalBorrowedWad
    );

    // -------------------------------------------------------------------------
    // Core Write Functions (Rubric TC1 mandatory names: depositCollateral, borrow, repay)
    // -------------------------------------------------------------------------

    /// @notice Lender deposits MyUSDT into the pool and receives a transferable LendingPositionNFT.
    function depositLender(uint256 amount) external returns (uint256 positionId);

    /// @notice Current owner of `positionId` withdraws up to available pool balance & claimable entitlement.
    function withdrawLender(uint256 positionId, uint256 amount) external;

    /// @notice Borrower locks either ERC-20 collateral or a `CollateralNFT` and receives a `CollateralReceiptNFT`.
    function depositCollateral(uint256 amountOrTokenId, bool isNFT) external returns (uint256 receiptId);

    /// @notice Borrower withdraws unlocked collateral when remaining debt satisfies LTV <= 70% (or debt == 0).
    function withdrawCollateral() external;

    /// @notice Borrower draws MyUSDT up to 70% LTV, stores IPFS agreement CID, and mints DebtToken.
    function borrow(uint256 amount, string calldata agreementCid) external;

    /// @notice Borrower repays accrued interest first, then principal; unlocks collateral & settles receipt at 0 debt.
    function repay(uint256 amount) external;

    /// @notice Liquidator settles an underwater borrower's debt strictly when `getHealthFactor(borrower) < 1e18`.
    function liquidate(address borrower) external;

    /// @notice Checkpoints pool indices up to `block.timestamp` and emits `InterestRateUpdated` for Audit Logs.
    function accrueInterest() external;

    // -------------------------------------------------------------------------
    // View Functions (Consumed by Web3.py Q02/Q05 and Frontend L02/L03/L04)
    // -------------------------------------------------------------------------

    function getPoolInfo() external view returns (PoolInfo memory);

    /// @notice Returns live APR (on-chain simple) vs reference APY (daily compounded) and live indices.
    function getInterestRateSnapshot() external view returns (InterestRateSnapshot memory);

    function getAvailableLiquidity() external view returns (uint256);

    function getCollateralValue(address borrower) external view returns (uint256);

    function getMaxBorrowable(address borrower) external view returns (uint256);

    /// @notice Remaining additional MyUSDT borrowable under 70% LTV: max(0, maxBorrowable - totalDebt).
    function getRemainingBorrowCapacity(address borrower) external view returns (uint256);

    /// @notice Actual maximum additional MyUSDT borrowable right now: min(remainingBorrowCapacity, availableLiquidity).
    function getAvailableToBorrow(address borrower) external view returns (uint256);

    /// @notice Current Loan-to-Value ratio in BPS (0 if debt == 0, type(uint256).max if collateral == 0 && debt > 0).
    function getCurrentLtvBps(address borrower) external view returns (uint256);

    function calculateAccruedInterest(address borrower) external view returns (uint256);

    /// @notice Projects total borrower accrued interest after `extraSeconds` at the current borrow APR.
    function previewBorrowerInterest(address borrower, uint256 extraSeconds) external view returns (uint256);

    function getTotalDebt(address borrower) external view returns (uint256);

    function getHealthFactor(address borrower) external view returns (uint256);

    function getLenderEarnedInterest(uint256 positionId) external view returns (uint256);

    /// @notice Projects total lender earned interest for `positionId` after `extraSeconds` at the current supply APR.
    function previewLenderEarnedInterest(uint256 positionId, uint256 extraSeconds) external view returns (uint256);

    function getLenderClaimableBalance(uint256 positionId) external view returns (uint256);

    /// @notice Actual maximum MyUSDT withdrawable right now for `positionId`: min(claimable, availableLiquidity).
    function getMaxWithdrawable(uint256 positionId) external view returns (uint256);

    function getLoanPosition(address borrower) external view returns (LoanPosition memory);

    function getLenderPosition(uint256 positionId) external view returns (LenderPosition memory);
}
