"""FastAPI application for the IS355.R11 DeFi Lending DApp."""

from __future__ import annotations

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from requests.exceptions import RequestException
from web3.exceptions import ContractLogicError, Web3Exception

from backend.api import auth, demo, ipfs, pool, transactions
from backend.config.blockchain import check_network_connection
from backend.config.errors import decode_contract_error
from backend.config.settings import settings
from backend.services.web3_service import (
    ContractConfigurationError,
    ContractNotDeployedError,
    TransactionValidationError,
    Web3ServiceError,
)
from src.ipfs.rbac import AccessDeniedError
from src.ipfs.ipfs_client import IPFSNotFoundError, IPFSError


def create_app() -> FastAPI:
    application = FastAPI(
        title="IS355.R11 DeFi Lending DApp API",
        description=(
            "Backend REST API uses non-custodial wallet sessions, reads contract "
            "state, prepares unsigned MetaMask transactions, and manages IPFS documents."
        ),
        version="0.5.0",
    )
    cors_origins = list(
        dict.fromkeys(
            [*settings.cors_origins, "http://localhost:3000", "http://127.0.0.1:3000"]
        )
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(auth.router)
    application.include_router(pool.router)
    application.include_router(transactions.router)
    application.include_router(ipfs.router)
    application.include_router(demo.router)

    @application.exception_handler(AccessDeniedError)
    async def access_denied_handler(
        _request: Request, exc: AccessDeniedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"detail": exc.reason},
        )

    @application.exception_handler(ContractNotDeployedError)
    @application.exception_handler(ContractConfigurationError)
    async def contract_configuration_handler(
        _request: Request, exc: Web3ServiceError
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @application.exception_handler(TransactionValidationError)
    async def transaction_validation_handler(
        _request: Request, exc: TransactionValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.exception_handler(Web3ServiceError)
    async def web3_service_handler(
        _request: Request, exc: Web3ServiceError
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @application.exception_handler(ContractLogicError)
    async def contract_logic_handler(
        _request: Request, exc: ContractLogicError
    ) -> JSONResponse:
        decoded = decode_contract_error(exc)
        return JSONResponse(status_code=decoded.http_status, content=decoded.to_dict())

    @application.exception_handler(IPFSNotFoundError)
    async def ipfs_not_found_handler(
        _request: Request, exc: IPFSNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(IPFSError)
    async def ipfs_service_handler(
        _request: Request, exc: IPFSError
    ) -> JSONResponse:
        del _request, exc
        return JSONResponse(status_code=503, content={"detail": "IPFS storage is unavailable."})

    @application.exception_handler(Web3Exception)
    async def web3_rpc_handler(
        _request: Request, exc: Web3Exception
    ) -> JSONResponse:
        del _request, exc
        return JSONResponse(
            status_code=503,
            content={"detail": "Blockchain RPC is unavailable or rejected the request."},
        )

    @application.exception_handler(RequestException)
    async def upstream_network_handler(
        _request: Request, exc: RequestException
    ) -> JSONResponse:
        del _request, exc
        return JSONResponse(status_code=503, content={"detail": "Upstream network is unavailable."})

    @application.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @application.get("/health", tags=["System"])
    def health_check() -> dict:
        """Basic service healthcheck endpoint."""
        return {
            "status": "ok",
            "service": "defi-lending-backend",
            "active_network": settings.active_network,
            "custodial_wallet_keys_stored": False,
        }

    @application.get("/api/network-status", tags=["Blockchain"])
    def network_status(
        network: str | None = Query(
            default=None,
            description="Tên mạng cần kiểm tra ('local' hoặc 'sepolia'). Mặc định dùng ACTIVE_NETWORK.",
        ),
    ) -> dict:
        """Check real-time Web3.py RPC connectivity and Chain ID."""
        return check_network_connection(network)

    return application


app = create_app()
