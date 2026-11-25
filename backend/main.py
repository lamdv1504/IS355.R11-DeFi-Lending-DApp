"""FastAPI application scaffold for IS355.R11 DeFi Lending DApp (Q01 foundation)."""

from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.config.blockchain import check_network_connection
from backend.config.settings import settings

app = FastAPI(
    title="IS355.R11 DeFi Lending DApp API",
    description=(
        "Backend REST API sử dụng FastAPI + Web3.py đọc trạng thái Smart Contract, "
        "xây dựng unsigned transaction cho MetaMask và quản lý hồ sơ IPFS."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
def health_check() -> dict:
    """Basic service healthcheck endpoint."""
    return {
        "status": "ok",
        "service": "defi-lending-backend",
        "active_network": settings.active_network,
        "custodial_wallet_keys_stored": False,
    }


@app.get("/api/network-status", tags=["Blockchain"])
def network_status(
    network: str | None = Query(
        default=None,
        description="Tên mạng cần kiểm tra ('local' hoặc 'sepolia'). Mặc định dùng ACTIVE_NETWORK.",
    ),
) -> dict:
    """Check real-time Web3.py RPC connectivity and Chain ID."""
    return check_network_connection(network)
