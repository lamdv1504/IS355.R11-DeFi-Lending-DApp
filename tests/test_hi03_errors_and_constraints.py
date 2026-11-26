"""HI03 Python Constraint Math Parity & Custom Error Decoder Verification Tests."""

from __future__ import annotations

import json
from pathlib import Path

from eth_abi import encode as abi_encode
from web3 import Web3

from backend.config import constants as c
from backend.config.errors import (
    CONTRACT_ERROR_CATALOG,
    ERRORS_BY_CODE,
    decode_contract_error,
    format_error_for_api,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POOL_ABI_PATH = PROJECT_ROOT / "deployments" / "abi" / "LendingPool.json"
INTERFACE_ABI_PATH = PROJECT_ROOT / "deployments" / "abi" / "interfaces" / "ILendingPool.json"


def _encode_custom_error(signature: str, arg_types: list[str], args: list[object]) -> str:
    selector = Web3.keccak(text=signature)[:4]
    encoded_args = abi_encode(arg_types, args) if arg_types else b""
    return "0x" + (selector + encoded_args).hex()


def test_hi03_python_constraint_helpers_match_solidity_rules() -> None:
    """Verify LTV, remaining borrow capacity, real pool liquidity & max withdrawable edge cases."""
    # Zero debt -> 0 BPS LTV, full 70% LTV capacity
    assert c.calculate_ltv_bps(0, 1_000 * c.WAD) == 0
    assert c.calculate_remaining_borrow_capacity(1_000 * c.WAD, 0) == 700 * c.WAD

    # 500 debt on 1,000 collateral -> 5000 BPS (50% LTV), 200 remaining capacity
    assert c.calculate_ltv_bps(500 * c.WAD, 1_000 * c.WAD) == 5_000
    assert c.calculate_remaining_borrow_capacity(1_000 * c.WAD, 500 * c.WAD) == 200 * c.WAD

    # Price drop: 500 collateral vs 400 debt -> 8000 BPS (80% LTV), 0 remaining capacity
    assert c.calculate_ltv_bps(400 * c.WAD, 500 * c.WAD) == 8_000
    assert c.calculate_remaining_borrow_capacity(500 * c.WAD, 400 * c.WAD) == 0
    assert c.calculate_available_to_borrow(500 * c.WAD, 400 * c.WAD, 1_000 * c.WAD) == 0

    # Zero collateral with non-zero debt -> sentinel max uint256
    assert c.calculate_ltv_bps(1, 0) == c.INFINITE_HEALTH_FACTOR

    # Real available liquidity deducts both reservedLiquidity and locked ERC-20 collateral
    assert c.calculate_available_liquidity(2_000 * c.WAD, 250 * c.WAD, 1_000 * c.WAD) == 750 * c.WAD
    assert c.calculate_available_liquidity(500 * c.WAD, 800 * c.WAD, 0) == 0

    # Borrowable & withdrawable capped by pool liquidity
    assert c.calculate_available_to_borrow(1_000 * c.WAD, 0, 400 * c.WAD) == 400 * c.WAD
    assert c.calculate_available_to_borrow(1_000 * c.WAD, 0, 900 * c.WAD) == 700 * c.WAD
    assert c.calculate_max_withdrawable(1_000 * c.WAD, 400 * c.WAD) == 400 * c.WAD
    assert c.calculate_max_withdrawable(300 * c.WAD, 1_000 * c.WAD) == 300 * c.WAD


def test_compiled_lending_pool_abi_exposes_hi03_views_and_all_custom_errors() -> None:
    """Verify exported ABI includes HI03 view functions and every ILendingPool error is in errors.py."""
    assert POOL_ABI_PATH.exists(), "Run `npm run export:hi02` to export LendingPool ABI"
    assert INTERFACE_ABI_PATH.exists(), "Run `npm run export:hi02` to export ILendingPool ABI"

    pool_abi = json.loads(POOL_ABI_PATH.read_text(encoding="utf-8"))["abi"]
    iface_abi = json.loads(INTERFACE_ABI_PATH.read_text(encoding="utf-8"))["abi"]

    for abi in (pool_abi, iface_abi):
        fn_names = {item["name"] for item in abi if item.get("type") == "function"}
        for hi03_view in (
            "getMaxBorrowable",
            "getAvailableLiquidity",
            "getRemainingBorrowCapacity",
            "getAvailableToBorrow",
            "getCurrentLtvBps",
            "getMaxWithdrawable",
        ):
            assert hi03_view in fn_names, f"Missing HI03 view function: {hi03_view}"

    # Verify every custom error declared in ILendingPool ABI is registered with exact selector match
    iface_errors = [item for item in iface_abi if item.get("type") == "error"]
    assert len(iface_errors) >= 12
    for err in iface_errors:
        name = err["name"]
        assert name in ERRORS_BY_CODE, f"Custom error `{name}` missing in backend/config/errors.py"
        sig = f"{name}({','.join(inp['type'] for inp in err['inputs'])})"
        expected_selector = "0x" + Web3.keccak(text=sig)[:4].hex()
        assert ERRORS_BY_CODE[name].signature == sig
        assert ERRORS_BY_CODE[name].selector == expected_selector

    # Ensure no selector collisions across entire catalog
    selectors = [spec.selector for spec in CONTRACT_ERROR_CATALOG]
    assert len(selectors) == len(set(selectors))


def test_decode_contract_error_produces_clear_vietnamese_messages_and_structured_details() -> None:
    """Verify ABI revert decoding for HI03 core errors used by Web3.py (Q02/Q05) & React (L02/L03)."""
    # 1. ExceedsMaxLTV(requestedDebtWad, maxBorrowableWad)
    payload_ltv = _encode_custom_error(
        "ExceedsMaxLTV(uint256,uint256)",
        ["uint256", "uint256"],
        [705 * c.WAD, 700 * c.WAD],
    )
    decoded_ltv = format_error_for_api(payload_ltv)
    assert decoded_ltv["code"] == "ExceedsMaxLTV"
    assert decoded_ltv["http_status"] == 400
    assert "70% LTV" in decoded_ltv["message_vi"]
    assert "705.0000" in decoded_ltv["message_vi"]
    assert "700.0000" in decoded_ltv["message_vi"]
    assert decoded_ltv["details"]["requestedDebtWad"] == str(705 * c.WAD)
    assert decoded_ltv["details"]["maxBorrowableWad"] == str(700 * c.WAD)

    # 2. InsufficientPoolLiquidity(requestedWad, availableLiquidityWad)
    payload_liq = _encode_custom_error(
        "InsufficientPoolLiquidity(uint256,uint256)",
        ["uint256", "uint256"],
        [600 * c.WAD, 400 * c.WAD],
    )
    decoded_liq = decode_contract_error(f"execution reverted: {payload_liq}")
    assert decoded_liq.code == "InsufficientPoolLiquidity"
    assert decoded_liq.http_status == 409
    assert "600.0000" in decoded_liq.message_vi
    assert "400.0000" in decoded_liq.message_vi
    assert decoded_liq.details["availableLiquidityWad"] == str(400 * c.WAD)

    # 3. InsufficientClaimableBalance(requestedWad, claimableWad)
    payload_claim = _encode_custom_error(
        "InsufficientClaimableBalance(uint256,uint256)",
        ["uint256", "uint256"],
        [500 * c.WAD, 300 * c.WAD],
    )
    decoded_claim = decode_contract_error(payload_claim)
    assert decoded_claim.code == "InsufficientClaimableBalance"
    assert "500.0000" in decoded_claim.message_vi
    assert "300.0000" in decoded_claim.message_vi

    # 4. NotPositionOwner(positionId, caller)
    caller = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
    payload_owner = _encode_custom_error(
        "NotPositionOwner(uint256,address)",
        ["uint256", "address"],
        [1, caller],
    )
    decoded_owner = decode_contract_error(payload_owner)
    assert decoded_owner.code == "NotPositionOwner"
    assert decoded_owner.http_status == 403
    assert "#1" in decoded_owner.message_vi
    assert caller in decoded_owner.message_vi

    # 5. OutstandingDebtExists(remainingDebtWad)
    payload_debt = _encode_custom_error(
        "OutstandingDebtExists(uint256)",
        ["uint256"],
        [125 * c.WAD],
    )
    decoded_debt = decode_contract_error(payload_debt)
    assert decoded_debt.code == "OutstandingDebtExists"
    assert "125.0000" in decoded_debt.message_vi

    # 6. Sub-0.0001 WAD dust precision & address-before-payload exception extraction
    payload_dust = _encode_custom_error(
        "ExceedsMaxLTV(uint256,uint256)",
        ["uint256", "uint256"],
        [700 * c.WAD + 1, 700 * c.WAD],
    )
    decoded_dust = decode_contract_error(payload_dust)
    assert "700.000000000000000001" in decoded_dust.message_vi
    assert "700.0000" in decoded_dust.message_vi

    mixed_exc = ValueError(f"caller {caller} reverted with data {payload_owner}")
    decoded_mixed = decode_contract_error(mixed_exc)
    assert decoded_mixed.code == "NotPositionOwner"
    assert "#1" in decoded_mixed.message_vi
    assert caller in decoded_mixed.message_vi

    # 7. Text fallback & unknown revert fallback
    decoded_text = decode_contract_error("VM Exception: reverted with custom error 'EmptyAgreementCid()'")
    assert decoded_text.code == "EmptyAgreementCid"
    assert "CID" in decoded_text.message_vi

    decoded_unknown = decode_contract_error("0xdeadbeef")
    assert decoded_unknown.code == "ContractRevert"
    assert decoded_unknown.selector == "0xdeadbeef"
