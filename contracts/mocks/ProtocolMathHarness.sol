// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ProtocolConstants} from "../libraries/ProtocolConstants.sol";
import {ProtocolMath} from "../libraries/ProtocolMath.sol";

/// @title ProtocolMathHarness - Exposes pure library functions for Hardhat unit tests (HI01).
contract ProtocolMathHarness {
    function constantsSnapshot()
        external
        pure
        returns (
            uint256 wad,
            uint256 bps,
            uint256 secondsPerYear,
            uint256 maxLtvBps,
            uint256 liquidationThresholdBps,
            uint256 liquidationBonusBps,
            uint256 baseBorrowAprBps,
            uint256 utilizationSlopeBps
        )
    {
        return (
            ProtocolConstants.WAD,
            ProtocolConstants.BPS,
            ProtocolConstants.SECONDS_PER_YEAR,
            ProtocolConstants.MAX_LTV_BPS,
            ProtocolConstants.LIQUIDATION_THRESHOLD_BPS,
            ProtocolConstants.LIQUIDATION_BONUS_BPS,
            ProtocolConstants.BASE_BORROW_APR_BPS,
            ProtocolConstants.UTILIZATION_SLOPE_BPS
        );
    }

    function calculateMaxBorrow(uint256 collateralValueWad) external pure returns (uint256) {
        return ProtocolMath.calculateMaxBorrow(collateralValueWad);
    }

    function calculateHealthFactor(
        uint256 collateralValueWad,
        uint256 totalDebtWad
    ) external pure returns (uint256) {
        return ProtocolMath.calculateHealthFactor(collateralValueWad, totalDebtWad);
    }

    function classifyHealthFactor(
        uint256 healthFactorWad
    ) external pure returns (ProtocolMath.HealthStatus) {
        return ProtocolMath.classifyHealthFactor(healthFactorWad);
    }

    function isLiquidatable(uint256 healthFactorWad) external pure returns (bool) {
        return ProtocolMath.isLiquidatable(healthFactorWad);
    }

    function calculateUtilizationBps(
        uint256 totalBorrowedWad,
        uint256 totalSuppliedWad
    ) external pure returns (uint256) {
        return ProtocolMath.calculateUtilizationBps(totalBorrowedWad, totalSuppliedWad);
    }

    function calculateBorrowAprBps(uint256 utilizationBps) external pure returns (uint256) {
        return ProtocolMath.calculateBorrowAprBps(utilizationBps);
    }

    function calculateSupplyAprBps(
        uint256 borrowAprBps,
        uint256 utilizationBps
    ) external pure returns (uint256) {
        return ProtocolMath.calculateSupplyAprBps(borrowAprBps, utilizationBps);
    }

    function calculateSimpleInterest(
        uint256 principalWad,
        uint256 aprBps,
        uint256 deltaSeconds
    ) external pure returns (uint256) {
        return ProtocolMath.calculateSimpleInterest(principalWad, aprBps, deltaSeconds);
    }

    function calculateNextIndex(
        uint256 previousIndexWad,
        uint256 aprBps,
        uint256 deltaSeconds
    ) external pure returns (uint256) {
        return ProtocolMath.calculateNextIndex(previousIndexWad, aprBps, deltaSeconds);
    }

    function calculateLiquidationSeizeValue(
        uint256 debtCoveredWad,
        uint256 totalCollateralValueWad
    ) external pure returns (uint256) {
        return ProtocolMath.calculateLiquidationSeizeValue(debtCoveredWad, totalCollateralValueWad);
    }
}
