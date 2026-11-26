"""Canonical protocol constants & exact Wei-parity math helpers (HI01).

Single Source of Truth mirroring `contracts/libraries/ProtocolConstants.sol`
and `contracts/libraries/ProtocolMath.sol` for Backend Web3.py (Q02-Q05)
and Frontend JSON API responses (L01-L05).
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Tuple

# ------------------------------------------------------------------------------
# 1. Scaling & Time Units (MUST match ProtocolConstants.sol bit-for-bit)
# ------------------------------------------------------------------------------
WAD: int = 10**18
BPS: int = 10_000
SECONDS_PER_YEAR: int = 31_536_000  # 365 * 86_400
INITIAL_INDEX_WAD: int = 10**18

# ------------------------------------------------------------------------------
# 2. Capital Safety & Liquidation Parameters (Rubric TC1 & TC2)
# ------------------------------------------------------------------------------
MAX_LTV_BPS: int = 7_000                  # 70.00%
LIQUIDATION_THRESHOLD_BPS: int = 8_000    # 80.00%
LIQUIDATION_BONUS_BPS: int = 500          # 5.00%

HF_LIQUIDATION_THRESHOLD_WAD: int = 10**18                 # 1.00
HF_WARNING_THRESHOLD_WAD: int = 1_500_000_000_000_000_000  # 1.50
INFINITE_HEALTH_FACTOR: int = (1 << 256) - 1               # type(uint256).max

# ------------------------------------------------------------------------------
# 3. Hybrid Interest Rate Model Parameters (Annual Simple APR in BPS)
# ------------------------------------------------------------------------------
BASE_BORROW_APR_BPS: int = 500            # 5.00% / year at 0% utilization
UTILIZATION_SLOPE_BPS: int = 1_000        # +10.00% / year at 100% utilization
PROTOCOL_RESERVE_FACTOR_BPS: int = 0      # 0% reserve (100% interest to lenders in MVP)

DEFAULT_COLLATERAL_TOKEN_PRICE_WAD: int = 10**18
DEFAULT_PRICE_MULTIPLIER_BPS: int = 10_000

# ------------------------------------------------------------------------------
# 4. Canonical Contract & Event Names (Shared across Hiếu HI02-HI05 & Quân Q02-Q04)
# ------------------------------------------------------------------------------
MVP_CONTRACT_NAMES: Tuple[str, ...] = (
    "MyUSDT",
    "CollateralNFT",
    "CollateralReceiptNFT",
    "DebtToken",
    "LendingPositionNFT",
    "PriceOracle",
    "LendingPool",
)

LENDING_POOL_EVENTS: Tuple[str, ...] = (
    "LenderDeposited",
    "LenderWithdrawn",
    "CollateralDeposited",
    "CollateralWithdrawn",
    "LoanBorrowed",
    "LoanRepaid",
    "LoanLiquidated",
    "InterestRateUpdated",
)


class HealthStatus(str, Enum):
    """3-level risk status matching `ProtocolMath.HealthStatus` and UI Borrowing Console."""

    LIQUIDATABLE = "LIQUIDATABLE"  # HF < 1.00 (Red)
    WARNING = "WARNING"            # 1.00 <= HF < 1.50 (Yellow/Orange)
    SAFE = "SAFE"                  # HF >= 1.50 or TotalDebt == 0 (Green)


# ------------------------------------------------------------------------------
# 5. Exact Integer Fixed-Point Math (Zero drift vs Solidity Math.mulDiv)
# ------------------------------------------------------------------------------
def calculate_max_borrow(collateral_value_wad: int) -> int:
    """Maximum MyUSDT borrowable in WAD under LTV <= 70%."""
    if collateral_value_wad < 0:
        raise ValueError("collateral_value_wad must be non-negative")
    return (collateral_value_wad * MAX_LTV_BPS) // BPS


def calculate_health_factor(collateral_value_wad: int, total_debt_wad: int) -> int:
    """Compute Health Factor in WAD (1e18). Returns 2^256 - 1 if total_debt_wad == 0."""
    if collateral_value_wad < 0 or total_debt_wad < 0:
        raise ValueError("collateral_value_wad and total_debt_wad must be non-negative")
    if total_debt_wad == 0:
        return INFINITE_HEALTH_FACTOR
    return (collateral_value_wad * LIQUIDATION_THRESHOLD_BPS * WAD) // (total_debt_wad * BPS)


def classify_health_factor(health_factor_wad: int) -> HealthStatus:
    """Classify Health Factor WAD into SAFE / WARNING / LIQUIDATABLE."""
    if health_factor_wad < HF_LIQUIDATION_THRESHOLD_WAD:
        return HealthStatus.LIQUIDATABLE
    if health_factor_wad < HF_WARNING_THRESHOLD_WAD:
        return HealthStatus.WARNING
    return HealthStatus.SAFE


def is_liquidatable(health_factor_wad: int) -> bool:
    """True strictly when HF < 1.0e18 (HF == 1.0e18 is NOT liquidatable)."""
    return health_factor_wad < HF_LIQUIDATION_THRESHOLD_WAD


def calculate_utilization_bps(total_borrowed_wad: int, total_supplied_wad: int) -> int:
    """Pool utilization rate in BPS (0..10_000)."""
    if total_borrowed_wad < 0 or total_supplied_wad < 0:
        raise ValueError("amounts must be non-negative")
    if total_supplied_wad == 0 or total_borrowed_wad == 0:
        return 0
    return min(BPS, (total_borrowed_wad * BPS) // total_supplied_wad)


def calculate_borrow_apr_bps(utilization_bps: int) -> int:
    """Annual simple Borrow APR in BPS: Base (500) + Utilization * Slope (1000) / 10000."""
    capped = min(max(utilization_bps, 0), BPS)
    variable_part = (capped * UTILIZATION_SLOPE_BPS) // BPS
    return BASE_BORROW_APR_BPS + variable_part


def calculate_supply_apr_bps(borrow_apr_bps: int, utilization_bps: int) -> int:
    """Annual simple Supply APR in BPS distributed to lenders."""
    capped = min(max(utilization_bps, 0), BPS)
    gross_supply_bps = (borrow_apr_bps * capped) // BPS
    return (gross_supply_bps * (BPS - PROTOCOL_RESERVE_FACTOR_BPS)) // BPS


def calculate_simple_interest(principal_wad: int, apr_bps: int, delta_seconds: int) -> int:
    """Exact per-second simple interest in WAD matching Solidity `ProtocolMath.calculateSimpleInterest`."""
    if principal_wad < 0 or apr_bps < 0 or delta_seconds < 0:
        raise ValueError("inputs must be non-negative")
    if principal_wad == 0 or apr_bps == 0 or delta_seconds == 0:
        return 0
    return (principal_wad * apr_bps * delta_seconds) // (SECONDS_PER_YEAR * BPS)


def calculate_next_index(previous_index_wad: int, apr_bps: int, delta_seconds: int) -> int:
    """Advance additive cumulative APR WAD index for a single non-retroactive period."""
    if previous_index_wad <= 0 or apr_bps < 0 or delta_seconds < 0:
        raise ValueError("invalid index accrual inputs")
    if delta_seconds == 0 or apr_bps == 0:
        return previous_index_wad
    delta_index = (WAD * apr_bps * delta_seconds) // (SECONDS_PER_YEAR * BPS)
    return previous_index_wad + delta_index


def calculate_liquidation_seize_value(debt_covered_wad: int, total_collateral_value_wad: int) -> int:
    """Collateral value seized by liquidator (debt + 5% bonus, capped by collateral value)."""
    target_seize = (debt_covered_wad * (BPS + LIQUIDATION_BONUS_BPS)) // BPS
    return min(target_seize, total_collateral_value_wad)


# ------------------------------------------------------------------------------
# 6. Display & JSON API Normalization Helpers (APR vs APY, Safe JS Serialization)
# ------------------------------------------------------------------------------
def apr_bps_to_percent(apr_bps: int) -> float:
    """Convert BPS integer (e.g., 1000) to percentage float (10.00)."""
    return round(apr_bps / 100.0, 4)


def apr_bps_to_apy_percent(apr_bps: int, compounding_periods_per_year: int = 365) -> float:
    """Convert annual simple APR (BPS) into reference compounded APY (%).

    Formula: APY = ((1 + APR / n) ** n - 1) * 100, default daily compounding n = 365.
    UI MUST label on-chain accrual rate as APR and display APY strictly as compounded reference.
    """
    if apr_bps <= 0:
        return 0.0
    apr_decimal = apr_bps / float(BPS)
    apy_decimal = (1.0 + apr_decimal / compounding_periods_per_year) ** compounding_periods_per_year - 1.0
    return round(apy_decimal * 100.0, 4)


def wad_to_decimal_str(value_wad: int, precision: int = 6) -> str:
    """Format WAD integer into human-readable decimal string without float precision loss."""
    val = Decimal(value_wad) / Decimal(WAD)
    quant = Decimal(10) ** (-precision)
    return str(val.quantize(quant))


def format_health_factor_for_api(health_factor_wad: int) -> Dict[str, Any]:
    """Serialize Health Factor safely for JSON APIs & JavaScript frontends.

    Prevents JS `Number` overflow when `health_factor_wad == 2^256 - 1` (zero debt).
    """
    status = classify_health_factor(health_factor_wad)
    is_infinite = health_factor_wad >= INFINITE_HEALTH_FACTOR
    return {
        "health_factor_wad": str(health_factor_wad),
        "health_factor": None if is_infinite else round(float(Decimal(health_factor_wad) / Decimal(WAD)), 6),
        "is_infinite": is_infinite,
        "status": status.value,
        "liquidatable": is_liquidatable(health_factor_wad),
    }
