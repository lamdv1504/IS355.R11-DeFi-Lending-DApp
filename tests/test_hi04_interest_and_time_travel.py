"""HI04 Python APR/APY Parity, ABI Verification & Local-Only Time-Travel Guard Tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.config import constants as c
from backend.services.time_travel import (
    LOCAL_HARDHAT_CHAIN_ID,
    MAX_FAST_FORWARD_SECONDS,
    fast_forward_days,
    fast_forward_time,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POOL_ABI_PATH = PROJECT_ROOT / "deployments" / "abi" / "LendingPool.json"
INTERFACE_ABI_PATH = PROJECT_ROOT / "deployments" / "abi" / "interfaces" / "ILendingPool.json"


class _StubProvider:
    def __init__(self, state: dict[str, int]) -> None:
        self._state = state
        self.calls: list[tuple[str, list[Any]]] = []

    def make_request(self, method: str, params: list[Any]) -> dict[str, Any]:
        self.calls.append((method, params))
        if method == "evm_increaseTime":
            self._state["timestamp"] += int(params[0])
            return {"jsonrpc": "2.0", "id": 1, "result": hex(self._state["timestamp"])}
        if method == "evm_mine":
            self._state["block"] += 1
            return {"jsonrpc": "2.0", "id": 2, "result": "0x0"}
        raise AssertionError(f"Unexpected RPC method: {method}")


class _StubEth:
    def __init__(self, chain_id: int, state: dict[str, int]) -> None:
        self.chain_id = chain_id
        self._state = state

    def get_block(self, _identifier: str) -> dict[str, int]:
        return {"timestamp": self._state["timestamp"], "number": self._state["block"]}


class _StubWeb3:
    def __init__(self, chain_id: int, initial_timestamp: int = 1_700_000_000, initial_block: int = 10) -> None:
        self._state = {"timestamp": initial_timestamp, "block": initial_block}
        self.eth = _StubEth(chain_id, self._state)
        self.provider = _StubProvider(self._state)


def test_python_reference_apy_matches_solidity_interest_math_exact_bps() -> None:
    """Verify exact integer parity between Python `calculate_reference_apy_bps` and Solidity `InterestMath`."""
    assert c.calculate_reference_apy_bps(0) == 0
    assert c.calculate_reference_apy_bps(500) == 512     # 5.00% APR -> 5.1267% APY -> 512 BPS
    assert c.calculate_reference_apy_bps(1_000) == 1_051 # 10.00% APR -> 10.5156% APY -> 1051 BPS
    assert c.calculate_reference_apy_bps(1_500) == 1_617 # 15.00% APR -> 16.1798% APY -> 1617 BPS

    # Ensure API rate formatter clearly distinguishes simple APR from reference compounded APY
    snap = c.format_rate_snapshot_for_api(borrow_apr_bps=1_000, supply_apr_bps=500, utilization_bps=5_000)
    assert snap["borrow_apr_percent"] == 10.0
    assert snap["borrow_apy_ref_percent"] == 10.5156
    assert snap["borrow_apy_ref_percent"] > snap["borrow_apr_percent"]
    assert snap["supply_apr_percent"] == 5.0
    assert snap["supply_apy_ref_percent"] == 5.1267
    assert snap["accrual_model"] == "SIMPLE_APR_PER_SECOND"
    assert "APR" in snap["apy_disclaimer_vi"]


def test_exported_abi_exposes_hi04_realtime_interest_functions() -> None:
    """Verify LendingPool & ILendingPool exported ABIs include all HI04 realtime functions."""
    for path in (POOL_ABI_PATH, INTERFACE_ABI_PATH):
        assert path.exists(), f"Missing exported ABI: {path}"
        abi = json.loads(path.read_text(encoding="utf-8"))["abi"]
        fn_names = {item["name"] for item in abi if item.get("type") == "function"}
        for fn in (
            "accrueInterest",
            "getInterestRateSnapshot",
            "calculateAccruedInterest",
            "previewBorrowerInterest",
            "getLenderEarnedInterest",
            "previewLenderEarnedInterest",
        ):
            assert fn in fn_names, f"Missing HI04 function `{fn}` in {path.name}"


def test_fast_forward_time_blocks_sepolia_and_invalid_durations() -> None:
    """Rubric security guard: time-travel MUST be strictly blocked on Sepolia (11155111) & mainnet."""
    sepolia_w3 = _StubWeb3(chain_id=11155111)
    with pytest.raises(PermissionError, match="11155111"):
        fast_forward_days(sepolia_w3, 30)

    mainnet_w3 = _StubWeb3(chain_id=1)
    with pytest.raises(PermissionError, match="1"):
        fast_forward_time(mainnet_w3, 3600)

    local_w3 = _StubWeb3(chain_id=LOCAL_HARDHAT_CHAIN_ID)
    for bad in (0, -100, True, MAX_FAST_FORWARD_SECONDS + 1):
        with pytest.raises(ValueError):
            fast_forward_time(local_w3, bad)  # type: ignore[arg-type]


def test_fast_forward_days_advances_local_hardhat_chain_cleanly() -> None:
    """Verify local Chain ID 31337 fast-forward invokes evm_increaseTime + evm_mine and reports audit metadata."""
    local_w3 = _StubWeb3(chain_id=LOCAL_HARDHAT_CHAIN_ID, initial_timestamp=1_700_000_000, initial_block=42)
    res = fast_forward_days(local_w3, 60)

    assert res.chain_id == 31337
    assert res.seconds_requested == 60 * 86_400
    assert res.seconds_elapsed == 60 * 86_400
    assert res.days_elapsed == 60.0
    assert res.timestamp_before == 1_700_000_000
    assert res.timestamp_after == 1_700_000_000 + 60 * 86_400
    assert res.block_before == 42
    assert res.block_after == 43
    assert local_w3.provider.calls == [("evm_increaseTime", [60 * 86_400]), ("evm_mine", [])]
    assert res.to_dict()["environment"] == "LOCAL_DEMO_ONLY"
