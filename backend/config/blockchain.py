"""Web3.py provider factory and network diagnostics for Local Hardhat & Sepolia."""

from __future__ import annotations

import json
from typing import Any, Dict

from web3 import HTTPProvider, Web3

from backend.config.settings import NetworkSettings, settings


def get_web3(network_name: str | None = None, request_timeout: int = 10) -> Web3:
    """Create a configured Web3 HTTP client for 'local' (31337) or 'sepolia' (11155111)."""
    net_cfg: NetworkSettings = settings.get_network(network_name)
    provider = HTTPProvider(net_cfg.rpc_url, request_kwargs={"timeout": request_timeout})
    return Web3(provider)


def check_network_connection(network_name: str | None = None) -> Dict[str, Any]:
    """Verify Web3 RPC connectivity and validate that the RPC chainId matches config."""
    net_cfg: NetworkSettings = settings.get_network(network_name)
    w3 = get_web3(net_cfg.name)

    try:
        connected = bool(w3.is_connected())
    except Exception as exc:
        return {
            "network": net_cfg.name,
            "rpc_url": net_cfg.rpc_url,
            "expected_chain_id": net_cfg.chain_id,
            "connected": False,
            "chain_id_matches": False,
            "error": str(exc),
        }

    if not connected:
        return {
            "network": net_cfg.name,
            "rpc_url": net_cfg.rpc_url,
            "expected_chain_id": net_cfg.chain_id,
            "connected": False,
            "chain_id_matches": False,
            "error": "RPC endpoint unreachable (w3.is_connected() == False)",
        }

    actual_chain_id = int(w3.eth.chain_id)
    latest_block = int(w3.eth.block_number)
    return {
        "network": net_cfg.name,
        "rpc_url": net_cfg.rpc_url,
        "explorer_url": net_cfg.explorer_url,
        "is_local": net_cfg.is_local,
        "connected": True,
        "expected_chain_id": net_cfg.chain_id,
        "actual_chain_id": actual_chain_id,
        "chain_id_matches": actual_chain_id == net_cfg.chain_id,
        "latest_block": latest_block,
    }


def load_contracts_registry() -> Dict[str, Any]:
    """Load contract addresses and ABI metadata from backend/config/contracts.json."""
    if not settings.contracts_config_path.exists():
        return {}
    with settings.contracts_config_path.open("r", encoding="utf-8") as fp:
        return json.load(fp)
