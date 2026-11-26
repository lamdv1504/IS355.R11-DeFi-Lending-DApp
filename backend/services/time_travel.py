"""Local-only EVM time-travel helper for HI04/Q05/HI06 demos.

Wraps Hardhat JSON-RPC `evm_increaseTime` + `evm_mine` with strict local Chain ID (31337)
enforcement so demo time-skipping can NEVER be invoked against Sepolia (11155111) or mainnet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from web3 import Web3

LOCAL_HARDHAT_CHAIN_ID: int = 31337
SECONDS_PER_DAY: int = 86_400
MAX_FAST_FORWARD_SECONDS: int = 10 * 365 * SECONDS_PER_DAY  # 10 years


@dataclass(frozen=True)
class FastForwardResult:
    """Structured audit summary returned after local EVM time advancement."""

    chain_id: int
    seconds_requested: int
    seconds_elapsed: int
    days_elapsed: float
    timestamp_before: int
    timestamp_after: int
    block_before: int
    block_after: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "seconds_requested": self.seconds_requested,
            "seconds_elapsed": self.seconds_elapsed,
            "days_elapsed": self.days_elapsed,
            "timestamp_before": self.timestamp_before,
            "timestamp_after": self.timestamp_after,
            "block_before": self.block_before,
            "block_after": self.block_after,
            "environment": "LOCAL_DEMO_ONLY",
        }


def assert_local_demo_chain(w3: Web3) -> int:
    """Ensure the connected Web3 provider is strictly local Hardhat (Chain ID 31337)."""
    chain_id = int(w3.eth.chain_id)
    if chain_id != LOCAL_HARDHAT_CHAIN_ID:
        raise PermissionError(
            f"Fast-forward time is strictly disabled on Chain ID {chain_id}. "
            f"Only local Hardhat Chain ID {LOCAL_HARDHAT_CHAIN_ID} is permitted."
        )
    return chain_id


def fast_forward_time(w3: Web3, seconds_to_skip: int) -> FastForwardResult:
    """Advance local Hardhat EVM block.timestamp by `seconds_to_skip` and mine 1 block."""
    chain_id = assert_local_demo_chain(w3)

    if isinstance(seconds_to_skip, bool) or not isinstance(seconds_to_skip, int):
        raise ValueError("seconds_to_skip must be an integer")
    if seconds_to_skip <= 0 or seconds_to_skip > MAX_FAST_FORWARD_SECONDS:
        raise ValueError(
            f"seconds_to_skip must be between 1 and {MAX_FAST_FORWARD_SECONDS} seconds"
        )

    block_before = w3.eth.get_block("latest")
    ts_before = int(block_before["timestamp"])
    num_before = int(block_before["number"])

    inc_resp = w3.provider.make_request("evm_increaseTime", [seconds_to_skip])
    if "error" in inc_resp:
        raise RuntimeError(f"evm_increaseTime failed: {inc_resp['error']}")

    mine_resp = w3.provider.make_request("evm_mine", [])
    if "error" in mine_resp:
        raise RuntimeError(f"evm_mine failed: {mine_resp['error']}")

    block_after = w3.eth.get_block("latest")
    ts_after = int(block_after["timestamp"])
    num_after = int(block_after["number"])
    elapsed = ts_after - ts_before

    return FastForwardResult(
        chain_id=chain_id,
        seconds_requested=seconds_to_skip,
        seconds_elapsed=elapsed,
        days_elapsed=round(elapsed / float(SECONDS_PER_DAY), 4),
        timestamp_before=ts_before,
        timestamp_after=ts_after,
        block_before=num_before,
        block_after=num_after,
    )


def fast_forward_days(w3: Web3, days: int) -> FastForwardResult:
    """Convenience helper for 1-click 30/60/90-day demo time-jumps on local Hardhat."""
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise ValueError("days must be a positive integer")
    return fast_forward_time(w3, days * SECONDS_PER_DAY)


__all__ = [
    "FastForwardResult",
    "LOCAL_HARDHAT_CHAIN_ID",
    "MAX_FAST_FORWARD_SECONDS",
    "SECONDS_PER_DAY",
    "assert_local_demo_chain",
    "fast_forward_days",
    "fast_forward_time",
]
