"""Shared FastAPI providers, block-range validation, and local index locks."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from fastapi import HTTPException, Request

from backend.services.agreement_generator import AgreementGeneratorService
from backend.services.credit_and_audit_ipfs import CreditAndAuditIPFSService
from backend.services.web3_service import Web3Service
from src.ipfs.rbac import AccessContext

_index_locks: dict[str, threading.Lock] = {}
_index_locks_guard = threading.Lock()


def get_web3_service(request: Request) -> Web3Service:
    service = getattr(request.app.state, "web3_service", None)
    if service is None:
        service = Web3Service()
        request.app.state.web3_service = service
    return service


def get_agreement_generator(request: Request) -> AgreementGeneratorService:
    service = getattr(request.app.state, "agreement_generator", None)
    if service is None:
        binding_path = Path(
            os.getenv(
                "Q03_BINDING_STORE_PATH",
                str(Path(__file__).resolve().parents[1] / "data" / "agreement_index.json"),
            )
        )
        try:
            service = AgreementGeneratorService(
                get_web3_service(request), binding_store_path=binding_path
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=503,
                detail="IPFS document encryption is not configured correctly.",
            ) from exc
        request.app.state.agreement_generator = service
    return service


def get_credit_audit_service(request: Request) -> CreditAndAuditIPFSService:
    service = getattr(request.app.state, "credit_audit_service", None)
    if service is None:
        metadata_path = Path(
            os.getenv(
                "Q04_METADATA_STORE_PATH",
                str(
                    Path(__file__).resolve().parents[1]
                    / "data"
                    / "credit_audit_ipfs_index.json"
                ),
            )
        )
        try:
            service = CreditAndAuditIPFSService(
                get_web3_service(request),
                agreement_generator=get_agreement_generator(request),
                metadata_store_path=metadata_path,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=503,
                detail="IPFS document encryption is not configured correctly.",
            ) from exc
        request.app.state.credit_audit_service = service
    return service


def lock_for_index(path: Path) -> threading.Lock:
    normalized = str(Path(path).resolve()).casefold()
    with _index_locks_guard:
        lock = _index_locks.get(normalized)
        if lock is None:
            lock = threading.Lock()
            _index_locks[normalized] = lock
        return lock


def resolve_from_block(
    web3_service: Web3Service, requested_from_block: int | None
) -> int:
    if requested_from_block is None:
        if web3_service.network.name == "sepolia":
            raise HTTPException(
                status_code=422,
                detail="from_block is required on Sepolia to bound historical log scans.",
            )
        return 0
    if requested_from_block < 0:
        raise HTTPException(status_code=422, detail="from_block must be non-negative.")
    return requested_from_block


def resolve_block_range(
    web3_service: Web3Service,
    requested_from_block: int | None,
    requested_to_block: int | str,
) -> tuple[int, int | str]:
    from_block = resolve_from_block(web3_service, requested_from_block)
    if isinstance(requested_to_block, int) and requested_to_block < from_block:
        raise HTTPException(
            status_code=422, detail="to_block must be greater than or equal to from_block."
        )
    return from_block, requested_to_block


def require_matching_chain(context: AccessContext, web3_service: Web3Service) -> None:
    if not context.authenticated:
        raise HTTPException(status_code=401, detail="A verified wallet session is required.")
    if context.chain_id != web3_service.chain_id:
        raise HTTPException(
            status_code=403,
            detail="Authenticated wallet session chain does not match the active network.",
        )


