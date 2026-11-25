// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title ProtocolConstants - Single Source of Truth for DeFi Lending DApp parameters (HI01).
/// @notice Shared across LendingPool, PriceOracle, InterestMath, Token/NFT contracts,
///         and mirrored identically in `backend/config/constants.py`.
library ProtocolConstants {
    // -------------------------------------------------------------------------
    // Scaling & Time Units
    // -------------------------------------------------------------------------

    /// @notice Fixed-point scaling factor (18 decimals, matching MyUSDT & DebtToken).
    uint256 internal constant WAD = 1e18;

    /// @notice Basis points denominator (100.00% = 10_000 BPS, 1 BPS = 0.01%).
    uint256 internal constant BPS = 10_000;

    /// @notice Exact seconds in a standard 365-day year (365 * 86_400).
    uint256 internal constant SECONDS_PER_YEAR = 31_536_000;

    /// @notice Initial cumulative interest index in WAD (1.0).
    uint256 internal constant INITIAL_INDEX_WAD = 1e18;

    // -------------------------------------------------------------------------
    // Capital Safety & Liquidation Parameters (Rubric TC1 & TC2)
    // -------------------------------------------------------------------------

    /// @notice Maximum Loan-to-Value ratio: 70.00% (7_000 / 10_000).
    uint256 internal constant MAX_LTV_BPS = 7_000;

    /// @notice Liquidation threshold: 80.00% (8_000 / 10_000).
    uint256 internal constant LIQUIDATION_THRESHOLD_BPS = 8_000;

    /// @notice Liquidator bonus: 5.00% (500 / 10_000).
    uint256 internal constant LIQUIDATION_BONUS_BPS = 500;

    /// @notice Health Factor liquidation cutoff: HF < 1.00 (1e18) is liquidatable.
    uint256 internal constant HF_LIQUIDATION_THRESHOLD_WAD = 1e18;

    /// @notice Health Factor warning cutoff: 1.00 <= HF < 1.50 displays Warning (Yellow/Orange).
    uint256 internal constant HF_WARNING_THRESHOLD_WAD = 1_500_000_000_000_000_000;

    /// @notice Sentinel Health Factor when total borrower debt is 0 (infinite safety).
    uint256 internal constant INFINITE_HEALTH_FACTOR = type(uint256).max;

    // -------------------------------------------------------------------------
    // Hybrid Interest Rate Model Parameters (APR in BPS, non-retroactive)
    // -------------------------------------------------------------------------

    /// @notice Fixed base borrow APR at 0% utilization: 5.00% / year.
    uint256 internal constant BASE_BORROW_APR_BPS = 500;

    /// @notice Variable borrow APR slope across 0% -> 100% utilization: +10.00% / year.
    /// @dev At 50% utilization (Demo 1000 supplied -> 500 borrowed):
    ///      Borrow APR = 500 + 500 = 1000 BPS (10.00%), Supply APR = 500 BPS (5.00%).
    uint256 internal constant UTILIZATION_SLOPE_BPS = 1_000;

    /// @notice Protocol reserve factor (0% in academic MVP so 100% borrower interest goes to lenders).
    uint256 internal constant PROTOCOL_RESERVE_FACTOR_BPS = 0;

    // -------------------------------------------------------------------------
    // Collateral Type Identifiers
    // -------------------------------------------------------------------------

    /// @notice Default 1:1 token collateral price in MyUSDT WAD (1 token = 1.00 MyUSDT).
    uint256 internal constant DEFAULT_COLLATERAL_TOKEN_PRICE_WAD = 1e18;

    /// @notice Default price multiplier in BPS (100% = 10_000 BPS; 40% drop = 6_000 BPS).
    uint256 internal constant DEFAULT_PRICE_MULTIPLIER_BPS = 10_000;
}
