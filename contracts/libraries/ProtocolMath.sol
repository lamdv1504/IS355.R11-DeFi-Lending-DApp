// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";
import {ProtocolConstants} from "./ProtocolConstants.sol";

/// @title ProtocolMath - Pure fixed-point math for LTV, Health Factor, and APR interest (HI01).
/// @notice Uses Solidity 0.8+ overflow protection and OpenZeppelin v5 `Math.mulDiv`
///         (512-bit intermediate precision) to eliminate integer rounding drift.
library ProtocolMath {
    enum HealthStatus {
        LIQUIDATABLE, // HF < 1.0e18 (Red)
        WARNING,      // 1.0e18 <= HF < 1.5e18 (Yellow/Orange)
        SAFE          // HF >= 1.5e18 or TotalDebt == 0 (Green)
    }

    /// @notice Maximum MyUSDT borrowable for a given collateral value under LTV <= 70%.
    /// @param collateralValueWad Collateral valuation in MyUSDT WAD (1e18).
    function calculateMaxBorrow(uint256 collateralValueWad) internal pure returns (uint256) {
        return Math.mulDiv(
            collateralValueWad,
            ProtocolConstants.MAX_LTV_BPS,
            ProtocolConstants.BPS
        );
    }

    /// @notice Computes current Loan-to-Value ratio in BPS (0 if debt == 0, type(uint256).max if collateral == 0 && debt > 0).
    function calculateLtvBps(
        uint256 totalDebtWad,
        uint256 collateralValueWad
    ) internal pure returns (uint256) {
        if (totalDebtWad == 0) {
            return 0;
        }
        if (collateralValueWad == 0) {
            return type(uint256).max;
        }
        return Math.mulDiv(totalDebtWad, ProtocolConstants.BPS, collateralValueWad);
    }

    /// @notice Computes Health Factor in WAD (1e18) using 8000 BPS liquidation threshold.
    /// @dev Formula: HF_WAD = (CollateralValue * 8000 * 1e18) / (TotalDebt * 10000).
    ///      Returns `type(uint256).max` when `totalDebtWad == 0`.
    function calculateHealthFactor(
        uint256 collateralValueWad,
        uint256 totalDebtWad
    ) internal pure returns (uint256) {
        if (totalDebtWad == 0) {
            return ProtocolConstants.INFINITE_HEALTH_FACTOR;
        }
        return Math.mulDiv(
            collateralValueWad,
            ProtocolConstants.LIQUIDATION_THRESHOLD_BPS * ProtocolConstants.WAD,
            totalDebtWad * ProtocolConstants.BPS
        );
    }

    /// @notice Maps Health Factor WAD to the 3-level UI/Risk status.
    function classifyHealthFactor(uint256 healthFactorWad) internal pure returns (HealthStatus) {
        if (healthFactorWad < ProtocolConstants.HF_LIQUIDATION_THRESHOLD_WAD) {
            return HealthStatus.LIQUIDATABLE;
        }
        if (healthFactorWad < ProtocolConstants.HF_WARNING_THRESHOLD_WAD) {
            return HealthStatus.WARNING;
        }
        return HealthStatus.SAFE;
    }

    /// @notice Returns true strictly when HF < 1.0e18 (HF == 1.0e18 is still safe).
    function isLiquidatable(uint256 healthFactorWad) internal pure returns (bool) {
        return healthFactorWad < ProtocolConstants.HF_LIQUIDATION_THRESHOLD_WAD;
    }

    /// @notice Computes pool utilization in BPS (0..10_000).
    function calculateUtilizationBps(
        uint256 totalBorrowedWad,
        uint256 totalSuppliedWad
    ) internal pure returns (uint256) {
        if (totalSuppliedWad == 0 || totalBorrowedWad == 0) {
            return 0;
        }
        uint256 rawBps = Math.mulDiv(totalBorrowedWad, ProtocolConstants.BPS, totalSuppliedWad);
        return rawBps > ProtocolConstants.BPS ? ProtocolConstants.BPS : rawBps;
    }

    /// @notice Computes annual simple Borrow APR in BPS: Base (500) + Utilization * Slope (1000) / 10000.
    function calculateBorrowAprBps(uint256 utilizationBps) internal pure returns (uint256) {
        uint256 cappedUtilization =
            utilizationBps > ProtocolConstants.BPS ? ProtocolConstants.BPS : utilizationBps;
        uint256 variablePart = Math.mulDiv(
            cappedUtilization,
            ProtocolConstants.UTILIZATION_SLOPE_BPS,
            ProtocolConstants.BPS
        );
        return ProtocolConstants.BASE_BORROW_APR_BPS + variablePart;
    }

    /// @notice Computes annual simple Supply APR in BPS distributed to lenders.
    function calculateSupplyAprBps(
        uint256 borrowAprBps,
        uint256 utilizationBps
    ) internal pure returns (uint256) {
        uint256 cappedUtilization =
            utilizationBps > ProtocolConstants.BPS ? ProtocolConstants.BPS : utilizationBps;
        uint256 grossSupplyBps = Math.mulDiv(borrowAprBps, cappedUtilization, ProtocolConstants.BPS);
        return Math.mulDiv(
            grossSupplyBps,
            ProtocolConstants.BPS - ProtocolConstants.PROTOCOL_RESERVE_FACTOR_BPS,
            ProtocolConstants.BPS
        );
    }

    /// @notice Computes simple per-second interest for a single period using APR in BPS.
    /// @dev Formula: (principalWad * aprBps * deltaSeconds) / (SECONDS_PER_YEAR * BPS).
    function calculateSimpleInterest(
        uint256 principalWad,
        uint256 aprBps,
        uint256 deltaSeconds
    ) internal pure returns (uint256) {
        if (principalWad == 0 || aprBps == 0 || deltaSeconds == 0) {
            return 0;
        }
        return Math.mulDiv(
            principalWad,
            aprBps * deltaSeconds,
            ProtocolConstants.SECONDS_PER_YEAR * ProtocolConstants.BPS
        );
    }

    /// @notice Advances an additive cumulative APR index (WAD) for a single non-retroactive period.
    /// @dev Simple-APR cumulative index: `nextIndex = previousIndex + floor(WAD * aprBps * deltaSeconds / (SECONDS_PER_YEAR * BPS))`.
    ///      Ensures historical periods are locked before any utilization/rate change and guarantees
    ///      total lender simple-APR interest never exceeds collected borrower simple-APR interest.
    function calculateNextIndex(
        uint256 previousIndexWad,
        uint256 aprBps,
        uint256 deltaSeconds
    ) internal pure returns (uint256) {
        if (deltaSeconds == 0 || aprBps == 0) {
            return previousIndexWad;
        }
        uint256 deltaIndex = Math.mulDiv(
            ProtocolConstants.WAD,
            aprBps * deltaSeconds,
            ProtocolConstants.SECONDS_PER_YEAR * ProtocolConstants.BPS
        );
        return previousIndexWad + deltaIndex;
    }

    /// @notice Computes total collateral value seized by a liquidator including the 5% bonus.
    function calculateLiquidationSeizeValue(
        uint256 debtCoveredWad,
        uint256 totalCollateralValueWad
    ) internal pure returns (uint256) {
        uint256 targetSeize = Math.mulDiv(
            debtCoveredWad,
            ProtocolConstants.BPS + ProtocolConstants.LIQUIDATION_BONUS_BPS,
            ProtocolConstants.BPS
        );
        return targetSeize > totalCollateralValueWad ? totalCollateralValueWad : targetSeize;
    }
}
