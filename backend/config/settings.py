"""Centralized environment settings for Backend FastAPI, Web3.py, and IPFS."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# Danh sách 10 private key mặc định của Hardhat (chỉ cho phép dùng trên mạng local)
HARDHAT_DEFAULT_PRIVATE_KEYS = {
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
    "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
    "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
    "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
    "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
    "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",
}


def _normalize_hex_key(raw_key: str) -> str:
    cleaned = raw_key.strip()
    if not cleaned:
        return ""
    return cleaned.lower() if cleaned.lower().startswith("0x") else f"0x{cleaned.lower()}"


@dataclass(frozen=True)
class NetworkSettings:
    """Configuration for a single Ethereum-compatible network."""

    name: str
    rpc_url: str
    chain_id: int
    explorer_url: str
    is_local: bool


@dataclass(frozen=True)
class AppSettings:
    """Global application configuration loaded from environment variables."""

    active_network: str
    local_network: NetworkSettings
    sepolia_network: NetworkSettings
    local_system_private_key: str
    sepolia_deployer_private_key: str
    backend_host: str
    backend_port: int
    cors_origins: List[str]
    contracts_config_path: Path
    ipfs_provider: str
    ipfs_local_api_url: str
    ipfs_local_gateway_url: str
    pinata_gateway_url: str
    auth_token_secret: str = ""
    auth_domain: str = "localhost"
    auth_nonce_ttl_seconds: int = 300
    auth_session_ttl_seconds: int = 3600
    admin_wallets: Tuple[str, ...] = ()
    lender_wallets: Tuple[str, ...] = ()

    def get_network(self, network_name: str | None = None) -> NetworkSettings:
        target = (network_name or self.active_network).strip().lower()
        if target in ("local", "localhost", "hardhat"):
            return self.local_network
        if target == "sepolia":
            return self.sepolia_network
        raise ValueError(f"Unsupported network '{target}'. Expected 'local' or 'sepolia'.")

    def validate_security_rules(self) -> None:
        """Enforce strict separation between Hardhat local keys and Sepolia testnet."""
        if (
            self.sepolia_deployer_private_key
            and self.sepolia_deployer_private_key in HARDHAT_DEFAULT_PRIVATE_KEYS
        ):
            raise RuntimeError(
                "SECURITY VIOLATION: SEPOLIA_DEPLOYER_PRIVATE_KEY không được phép dùng "
                "private key mặc định của Hardhat Local!"
            )


def load_settings() -> AppSettings:
    active_network = os.getenv("ACTIVE_NETWORK", "local").strip().lower()

    local_net = NetworkSettings(
        name="local",
        rpc_url=os.getenv("LOCAL_RPC_URL", "http://127.0.0.1:8545").strip(),
        chain_id=int(os.getenv("LOCAL_CHAIN_ID", "31337")),
        explorer_url="http://127.0.0.1:8545",
        is_local=True,
    )

    sepolia_net = NetworkSettings(
        name="sepolia",
        rpc_url=os.getenv(
            "SEPOLIA_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com"
        ).strip(),
        chain_id=int(os.getenv("SEPOLIA_CHAIN_ID", "11155111")),
        explorer_url=os.getenv(
            "SEPOLIA_EXPLORER_URL", "https://sepolia.etherscan.io"
        ).strip(),
        is_local=False,
    )

    cors_raw = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
    )
    cors_origins = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]

    app_settings = AppSettings(
        active_network=active_network,
        local_network=local_net,
        sepolia_network=sepolia_net,
        local_system_private_key=_normalize_hex_key(
            os.getenv("LOCAL_SYSTEM_PRIVATE_KEY", "")
        ),
        sepolia_deployer_private_key=_normalize_hex_key(
            os.getenv("SEPOLIA_DEPLOYER_PRIVATE_KEY", "")
        ),
        backend_host=os.getenv("BACKEND_HOST", "127.0.0.1").strip(),
        backend_port=int(os.getenv("BACKEND_PORT", "8000")),
        cors_origins=cors_origins,
        contracts_config_path=PROJECT_ROOT / "backend" / "config" / "contracts.json",
        ipfs_provider=os.getenv("IPFS_PROVIDER", "local_fallback").strip(),
        ipfs_local_api_url=os.getenv("IPFS_LOCAL_API_URL", "http://127.0.0.1:5001").strip(),
        ipfs_local_gateway_url=os.getenv(
            "IPFS_LOCAL_GATEWAY_URL", "http://127.0.0.1:8080/ipfs"
        ).strip(),
        pinata_gateway_url=os.getenv(
            "PINATA_GATEWAY_URL", "https://gateway.pinata.cloud/ipfs"
        ).strip(),
        auth_token_secret=os.getenv("AUTH_TOKEN_SECRET", ""),
        auth_domain=os.getenv("AUTH_DOMAIN", "localhost").strip(),
        auth_nonce_ttl_seconds=int(os.getenv("AUTH_NONCE_TTL_SECONDS", "300")),
        auth_session_ttl_seconds=int(os.getenv("AUTH_SESSION_TTL_SECONDS", "3600")),
        admin_wallets=tuple(
            wallet.strip()
            for wallet in os.getenv("ADMIN_WALLETS", "").split(",")
            if wallet.strip()
        ),
        lender_wallets=tuple(
            wallet.strip()
            for wallet in os.getenv("LENDER_WALLETS", "").split(",")
            if wallet.strip()
        ),
    )
    app_settings.validate_security_rules()
    return app_settings


settings = load_settings()
