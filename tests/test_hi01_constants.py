"""HI01 Cross-Language Parity & Formula Verification Tests (Solidity <-> Python)."""

from __future__ import annotations

import re
from pathlib import Path

from backend.config import constants as c

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOLIDITY_CONSTANTS_PATH = PROJECT_ROOT / "contracts" / "libraries" / "ProtocolConstants.sol"


def _parse_solidity_uint_constant(source: str, name: str) -> int:
    pattern = rf"uint256\s+internal\s+constant\s+{name}\s*=\s*([^;]+);"
    match = re.search(pattern, source)
    assert match is not None, f"Constant {name} missing in ProtocolConstants.sol"
    raw = match.group(1).strip().replace("_", "")
    if raw == "type(uint256).max":
        return (1 << 256) - 1
    if raw == "1e18":
        return 10**18
    return int(raw)


def test_python_constants_match_solidity_protocol_constants_bit_for_bit() -> None:
    """Guarantee zero drift between ProtocolConstants.sol and backend/config/constants.py."""
    sol_source = SOLIDITY_CONSTANTS_PATH.read_text(encoding="utf-8")
    expected_pairs = [
        ("WAD", c.WAD),
        ("BPS", c.BPS),
        ("SECONDS_PER_YEAR", c.SECONDS_PER_YEAR),
        ("INITIAL_INDEX_WAD", c.INITIAL_INDEX_WAD),
        ("MAX_LTV_BPS", c.MAX_LTV_BPS),
        ("LIQUIDATION_THRESHOLD_BPS", c.LIQUIDATION_THRESHOLD_BPS),
        ("LIQUIDATION_BONUS_BPS", c.LIQUIDATION_BONUS_BPS),
        ("HF_LIQUIDATION_THRESHOLD_WAD", c.HF_LIQUIDATION_THRESHOLD_WAD),
        ("HF_WARNING_THRESHOLD_WAD", c.HF_WARNING_THRESHOLD_WAD),
        ("INFINITE_HEALTH_FACTOR", c.INFINITE_HEALTH_FACTOR),
        ("BASE_BORROW_APR_BPS", c.BASE_BORROW_APR_BPS),
        ("UTILIZATION_SLOPE_BPS", c.UTILIZATION_SLOPE_BPS),
        ("PROTOCOL_RESERVE_FACTOR_BPS", c.PROTOCOL_RESERVE_FACTOR_BPS),
        ("DEFAULT_COLLATERAL_TOKEN_PRICE_WAD", c.DEFAULT_COLLATERAL_TOKEN_PRICE_WAD),
        ("DEFAULT_PRICE_MULTIPLIER_BPS", c.DEFAULT_PRICE_MULTIPLIER_BPS),
    ]
    for const_name, py_val in expected_pairs:
        sol_val = _parse_solidity_uint_constant(sol_source, const_name)
        assert py_val == sol_val, f"Mismatch on {const_name}: py={py_val}, sol={sol_val}"


def test_health_factor_boundary_exact_one_and_zero_debt() -> None:
    """Acceptance check: test HF = 1.0 boundary and zero-debt infinite HF."""
    collateral_1000 = 1_000 * c.WAD

    # 1. Zero debt -> infinite HF, safe, API returns null + is_infinite=True
    hf_zero_debt = c.calculate_health_factor(collateral_1000, 0)
    assert hf_zero_debt == c.INFINITE_HEALTH_FACTOR
    assert c.classify_health_factor(hf_zero_debt) == c.HealthStatus.SAFE
    assert c.is_liquidatable(hf_zero_debt) is False
    api_zero = c.format_health_factor_for_api(hf_zero_debt)
    assert api_zero["health_factor"] is None
    assert api_zero["is_infinite"] is True
    assert api_zero["liquidatable"] is False

    # 2. Exact HF = 1.0 (debt = 800 on 1000 collateral) -> NOT liquidatable
    hf_exact_one = c.calculate_health_factor(collateral_1000, 800 * c.WAD)
    assert hf_exact_one == c.WAD
    assert c.classify_health_factor(hf_exact_one) == c.HealthStatus.WARNING
    assert c.is_liquidatable(hf_exact_one) is False
    api_one = c.format_health_factor_for_api(hf_exact_one)
    assert api_one["health_factor"] == 1.0
    assert api_one["status"] == "WARNING"

    # 3. 1 wei over 800 debt -> HF < 1.0 -> LIQUIDATABLE
    hf_under = c.calculate_health_factor(collateral_1000, 800 * c.WAD + 1)
    assert hf_under < c.WAD
    assert c.classify_health_factor(hf_under) == c.HealthStatus.LIQUIDATABLE
    assert c.is_liquidatable(hf_under) is True


def test_demo_scenario_exact_wei_accounting_and_apr_vs_apy() -> None:
    """Verify Demo 1000 -> 500 for 60 days matches Solidity down to exact Wei and distinguishes APR vs APY."""
    supplied = 1_000 * c.WAD
    borrowed = 500 * c.WAD
    collateral = 1_000 * c.WAD

    # Max LTV 70% = 700 MyUSDT
    assert c.calculate_max_borrow(collateral) == 700 * c.WAD

    # Utilization = 50% -> Borrow APR = 10% (1000 BPS), Supply APR = 5% (500 BPS)
    util_bps = c.calculate_utilization_bps(borrowed, supplied)
    borrow_apr_bps = c.calculate_borrow_apr_bps(util_bps)
    supply_apr_bps = c.calculate_supply_apr_bps(borrow_apr_bps, util_bps)
    assert util_bps == 5_000
    assert borrow_apr_bps == 1_000
    assert supply_apr_bps == 500

    # APR vs APY distinction (daily compounded APY > simple APR)
    assert c.apr_bps_to_percent(borrow_apr_bps) == 10.0
    assert c.apr_bps_to_apy_percent(borrow_apr_bps) == 10.5156
    assert c.apr_bps_to_percent(supply_apr_bps) == 5.0
    assert c.apr_bps_to_apy_percent(supply_apr_bps) == 5.1267

    # Exact 60-day interest matches Solidity ProtocolMath test value bit-for-bit
    sixty_days = 60 * 86_400
    borrower_interest = c.calculate_simple_interest(borrowed, borrow_apr_bps, sixty_days)
    lender_interest = c.calculate_simple_interest(supplied, supply_apr_bps, sixty_days)
    assert borrower_interest == 8_219_178_082_191_780_821
    assert lender_interest == borrower_interest

    # Price drops 40% -> collateral 600, debt 500 -> HF = 0.96 -> Liquidatable
    hf_drop = c.calculate_health_factor(600 * c.WAD, borrowed)
    assert hf_drop == 960_000_000_000_000_000
    assert c.is_liquidatable(hf_drop) is True
    assert c.calculate_liquidation_seize_value(borrowed, 600 * c.WAD) == 525 * c.WAD


def test_non_retroactive_multi_period_index_accrual() -> None:
    """Ensure rate changes only apply forward and never retroactively."""
    thirty_days = 30 * 86_400
    idx_p1 = c.calculate_next_index(c.WAD, 1_000, thirty_days)
    idx_p2 = c.calculate_next_index(idx_p1, 1_500, thirty_days)
    wrong_retroactive = c.calculate_next_index(c.WAD, 1_500, 2 * thirty_days)
    flat_lower = c.calculate_next_index(c.WAD, 1_000, 2 * thirty_days)
    assert flat_lower < idx_p2 < wrong_retroactive


def test_ilending_pool_abi_declares_mandatory_rubric_functions_and_events() -> None:
    """Verify compiled ILendingPool artifact exposes exact Rubric TC1 functions & Q04 events."""
    import json

    artifact_path = (
        PROJECT_ROOT
        / "artifacts"
        / "contracts"
        / "interfaces"
        / "ILendingPool.sol"
        / "ILendingPool.json"
    )
    assert artifact_path.exists(), "Run `npm run compile` before testing compiled ABI artifacts"
    abi = json.loads(artifact_path.read_text(encoding="utf-8"))["abi"]
    fn_names = {item["name"] for item in abi if item.get("type") == "function"}
    event_names = {item["name"] for item in abi if item.get("type") == "event"}

    for mandatory_fn in (
        "depositLender",
        "withdrawLender",
        "depositCollateral",
        "withdrawCollateral",
        "borrow",
        "repay",
        "liquidate",
        "getHealthFactor",
        "getMaxBorrowable",
        "getAvailableLiquidity",
        "calculateAccruedInterest",
        "getLenderEarnedInterest",
    ):
        assert mandatory_fn in fn_names, f"Missing required function in ILendingPool ABI: {mandatory_fn}"

    for expected_event in c.LENDING_POOL_EVENTS:
        assert expected_event in event_names, f"Missing required event in ILendingPool ABI: {expected_event}"

