// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {InterestMath} from "../libraries/InterestMath.sol";

/// @title InterestMathHarness - Test harness exposing internal pure functions of `InterestMath` (HI04).
contract InterestMathHarness {
    function accrueSimpleInterest(
        uint256 principalWad,
        uint256 aprBps,
        uint256 deltaSeconds
    ) external pure returns (uint256) {
        return InterestMath.accrueSimpleInterest(principalWad, aprBps, deltaSeconds);
    }

    function calculateIndexDelta(
        uint256 aprBps,
        uint256 deltaSeconds
    ) external pure returns (uint256) {
        return InterestMath.calculateIndexDelta(aprBps, deltaSeconds);
    }

    function advanceCumulativeIndex(
        uint256 previousIndexWad,
        uint256 aprBps,
        uint256 deltaSeconds
    ) external pure returns (uint256) {
        return InterestMath.advanceCumulativeIndex(previousIndexWad, aprBps, deltaSeconds);
    }

    function accrueFromIndexDelta(
        uint256 principalWad,
        uint256 currentIndexWad,
        uint256 snapshotIndexWad
    ) external pure returns (uint256) {
        return InterestMath.accrueFromIndexDelta(principalWad, currentIndexWad, snapshotIndexWad);
    }

    function calculatePerSecondInterestRateWad(
        uint256 principalWad,
        uint256 aprBps
    ) external pure returns (uint256) {
        return InterestMath.calculatePerSecondInterestRateWad(principalWad, aprBps);
    }

    function projectInterest(
        uint256 principalWad,
        uint256 aprBps,
        uint256 horizonSeconds
    ) external pure returns (uint256) {
        return InterestMath.projectInterest(principalWad, aprBps, horizonSeconds);
    }

    function calculateUtilizationBps(
        uint256 totalBorrowedWad,
        uint256 totalSuppliedWad
    ) external pure returns (uint256) {
        return InterestMath.calculateUtilizationBps(totalBorrowedWad, totalSuppliedWad);
    }

    function calculateBorrowAprBps(uint256 utilizationBps) external pure returns (uint256) {
        return InterestMath.calculateBorrowAprBps(utilizationBps);
    }

    function calculateSupplyAprBps(
        uint256 borrowAprBps,
        uint256 utilizationBps
    ) external pure returns (uint256) {
        return InterestMath.calculateSupplyAprBps(borrowAprBps, utilizationBps);
    }

    function calculateReferenceApyWad(uint256 aprBps) external pure returns (uint256) {
        return InterestMath.calculateReferenceApyWad(aprBps);
    }

    function calculateReferenceApyBps(uint256 aprBps) external pure returns (uint256) {
        return InterestMath.calculateReferenceApyBps(aprBps);
    }
}
