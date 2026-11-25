"""Automated tests for Q01: Blockchain Environment, Security Guardrails & FastAPI Scaffold."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
import pytest
from eth_account import Account
from fastapi.testclient import TestClient

from backend.config.blockchain import load_contracts_registry
from backend.config.settings import (
    HARDHAT_DEFAULT_PRIVATE_KEYS,
    load_settings,
    settings,
)
from backend.main import app

EXPECTED_LOCAL_ACCOUNTS = [
    ("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266", "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"),
    ("0x70997970C51812dc3A010C7d01b50e0d17dc79C8", "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"),
    ("0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC", "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"),
    ("0x90F79bf6EB2c4f870365E785982E1f101E93b906", "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6"),
    ("0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65", "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a"),
    ("0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc", "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba"),
    ("0x976EA74026E726554dB657fA54763abd0C3a0aa9", "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e"),
    ("0x14dC79964da2C08b23698B3D3cc7Ca32193d9955", "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356"),
    ("0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f", "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97"),
    ("0xa0Ee7A142d267C1f36714E4a8F75612F20a79720", "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6"),
]


def test_deterministic_10_hardhat_wallets_match_mnemonic() -> None:
    """Ensure all 10 documented test wallets & private keys match the fixed mnemonic."""
    Account.enable_unaudited_hdwallet_features()
    mnemonic = "test test test test test test test test test test test junk"
    for idx, (expected_addr, expected_pk) in enumerate(EXPECTED_LOCAL_ACCOUNTS):
        derived = Account.from_mnemonic(mnemonic, account_path=f"m/44'/60'/0'/0/{idx}")
        assert derived.address == expected_addr
        assert derived.key.hex().lower() == expected_pk.removeprefix("0x").lower()
        assert expected_pk.lower() in HARDHAT_DEFAULT_PRIVATE_KEYS


def test_network_settings_have_fixed_chain_ids() -> None:
    """Verify Chain ID 31337 for Local and Chain ID 11155111 for Sepolia."""
    local_cfg = settings.get_network("local")
    sepolia_cfg = settings.get_network("sepolia")

    assert local_cfg.chain_id == 31337
    assert local_cfg.is_local is True
    assert sepolia_cfg.chain_id == 11155111
    assert sepolia_cfg.is_local is False
    assert "sepolia.etherscan.io" in sepolia_cfg.explorer_url


def test_hardhat_private_key_blocked_on_sepolia(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure accidental reuse of a local Hardhat test key for Sepolia raises RuntimeError."""
    monkeypatch.setenv(
        "SEPOLIA_DEPLOYER_PRIVATE_KEY",
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    )
    with pytest.raises(RuntimeError, match="SECURITY VIOLATION"):
        load_settings()


def test_contracts_registry_contains_all_7_mvp_contracts() -> None:
    """Verify both local and sepolia registries declare all 7 required contracts."""
    registry = load_contracts_registry()
    expected_contracts = {
        "MyUSDT",
        "CollateralNFT",
        "CollateralReceiptNFT",
        "DebtToken",
        "LendingPositionNFT",
        "PriceOracle",
        "LendingPool",
    }
    assert set(registry["local"]["contracts"].keys()) == expected_contracts
    assert set(registry["sepolia"]["contracts"].keys()) == expected_contracts


def test_fastapi_health_endpoint() -> None:
    """Verify FastAPI /health works and explicitly enforces non-custodial design."""
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["custodial_wallet_keys_stored"] is False


def test_hardhat_config_blocks_all_10_local_keys_on_sepolia() -> None:
    """Verify hardhat.config.js also rejects any Hardhat default key when passed as Sepolia deployer."""
    project_root = Path(__file__).resolve().parents[1]
    hardhat_cli = project_root / "node_modules" / "hardhat" / "internal" / "cli" / "cli.js"
    env = os.environ.copy()
    env["SEPOLIA_DEPLOYER_PRIVATE_KEY"] = EXPECTED_LOCAL_ACCOUNTS[9][1]
    proc = subprocess.run(
        ["node", str(hardhat_cli), "compile"],
        cwd=str(project_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "SECURITY BLOCK" in (proc.stderr + proc.stdout)

