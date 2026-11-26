// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";
import {ProtocolConstants} from "./ProtocolConstants.sol";

/// @title InterestMath - Per-second timestamp interest accrual & non-retroactive index math (HI04).
/// @notice Uses Solidity 0.8+ built-in checked arithmetic (automatic overflow/underflow revert)
///         combined with OpenZeppelin v5 `Math.mulDiv` (512-bit intermediate precision) so
///         deprecated OZ v4 `SafeMath` is unnecessary while eliminating integer truncation loss.
/// @dev Strictly distinguishes on-chain simple APR (accrued linearly per second via `block.timestamp`)
///      from reference daily-compounded APY (`n = 365`), which is for display/analytics ONLY.
library InterestMath {
    uint256 internal constant DAYS_PER_YEAR = 365;

    /// @notice Computes exact simple per-second interest in WAD without integer truncation loss.
    /// @dev Formula: `floor(principalWad * aprBps * deltaSeconds / (SECONDS_PER_YEAR * BPS))`.
    ///      Uses 512-bit `Math.mulDiv` so `principalWad` (already scaled by 1e18 WAD) is multiplied
    ///      before dividing once at the end.
    function accrueSimpleInterest(
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

    /// @notice Computes the WAD-scaled index increment for a single interval under simple APR.
    /// @dev Scales by `WAD (1e18)` BEFORE dividing so even a 1-second interval produces non-zero
    ///      precision (`deltaIndex > 0` for any `aprBps > 0` and `deltaSeconds >= 1`).
    function calculateIndexDelta(
        uint256 aprBps,
        uint256 deltaSeconds
    ) internal pure returns (uint256) {
        if (aprBps == 0 || deltaSeconds == 0) {
            return 0;
        }
        return Math.mulDiv(
            ProtocolConstants.WAD,
            aprBps * deltaSeconds,
            ProtocolConstants.SECONDS_PER_YEAR * ProtocolConstants.BPS
        );
    }

    /// @notice Advances an additive cumulative APR index (WAD) for a single non-retroactive period.
    /// @dev Locking historical periods into a cumulative index guarantees that utilization/rate
    ///      changes only apply forward from `block.timestamp` and NEVER retroactively to past periods.
    function advanceCumulativeIndex(
        uint256 previousIndexWad,
        uint256 aprBps,
        uint256 deltaSeconds
    ) internal pure returns (uint256) {
        return previousIndexWad + calculateIndexDelta(aprBps, deltaSeconds);
    }

    /// @notice Computes position interest earned/owed from a cumulative index snapshot delta.
    /// @dev Formula: `floor(principalWad * (currentIndexWad - snapshotIndexWad) / WAD)`.
    function accrueFromIndexDelta(
        uint256 principalWad,
        uint256 currentIndexWad,
        uint256 snapshotIndexWad
    ) internal pure returns (uint256) {
        if (principalWad == 0 || currentIndexWad <= snapshotIndexWad) {
            return 0;
        }
        return Math.mulDiv(
            principalWad,
            currentIndexWad - snapshotIndexWad,
            ProtocolConstants.WAD
        );
    }

    /// @notice Computes exact interest accrued in 1 single second (WAD/sec) for realtime UI counters.
    function calculatePerSecondInterestRateWad(
        uint256 principalWad,
        uint256 aprBps
    ) internal pure returns (uint256) {
        return accrueSimpleInterest(principalWad, aprBps, 1);
    }

    /// @notice Projects additional simple interest over a future horizon (in seconds) at `aprBps`.
    function projectInterest(
        uint256 principalWad,
        uint256 aprBps,
        uint256 horizonSeconds
    ) internal pure returns (uint256) {
        return accrueSimpleInterest(principalWad, aprBps, horizonSeconds);
    }

    /// @notice Computes pool utilization rate in BPS (0..10_000).
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

    /// @notice Converts annual simple APR (BPS) into reference daily-compounded APY in WAD (`1e18 = 100%`).
    /// @dev Formula: `((1 + APR / 365)^365 - 1) * WAD` via O(log n) binary exponentiation.
    ///      Strictly for UI/API reference comparison — on-chain interest accrues strictly by simple APR.
    function calculateReferenceApyWad(uint256 aprBps) internal pure returns (uint256) {
        if (aprBps == 0) {
            return 0;
        }
        uint256 dailyRateWad = Math.mulDiv(
            aprBps,
            ProtocolConstants.WAD,
            ProtocolConstants.BPS * DAYS_PER_YEAR
        );
        uint256 base = ProtocolConstants.WAD + dailyRateWad;
        uint256 result = ProtocolConstants.WAD;
        uint256 exp = DAYS_PER_YEAR;

        while (exp > 0) {
            if ((exp & 1) == 1) {
                result = Math.mulDiv(result, base, ProtocolConstants.WAD);
            }
            exp >>= 1;
            if (exp > 0) {
                base = Math.mulDiv(base, base, ProtocolConstants.WAD);
            }
        }
        return result - ProtocolConstants.WAD;
    }

    /// @notice Converts annual simple APR (BPS) into reference daily-compounded APY in BPS.
    function calculateReferenceApyBps(uint256 aprBps) internal pure returns (uint256) {
        return Math.mulDiv(
            calculateReferenceApyWad(aprBps),
            ProtocolConstants.BPS,
            ProtocolConstants.WAD
        );
    }
}
