"""Shared FastAPI providers, block-range validation, and local index locks."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from fastapi import HTTPException, Request

from backend.config.settings import settings
from backend.services.agreement_generator import AgreementGeneratorService
from backend.services.credit_and_audit_ipfs import CreditAndAuditIPFSService
from backend.services.web3_service import Web3Service
from src.ipfs.rbac import AccessContext

_index_locks: dict[str, threading.Lock] = {}
_index_locks_guard = threading.Lock()
_web3_services_lock = threading.Lock()


def normalize_network_name(network: str) -> str:
    target = network.strip().lower()
    if target in ("local", "localhost", "hardhat"):
        return "local"
    if target == "sepolia":
        return "sepolia"
    raise HTTPException(
        status_code=422,
        detail=f"Unsupported network '{network}'. Expected 'local' or 'sepolia'.",
    )


def get_web3_service(request: Request) -> Web3Service:
    service = getattr(request.app.state, "web3_service", None)
    if service is None:
        service = Web3Service()
        request.app.state.web3_service = service
    return service


def get_web3_service_for_network(
    request: Request, network: str | None = None
) -> Web3Service:
    if network is None:
        return get_web3_service(request)
    target = normalize_network_name(network)
    with _web3_services_lock:
        services_by_network = getattr(request.app.state, "web3_services", None)
        if isinstance(services_by_network, dict) and target in services_by_network:
            return services_by_network[target]
        default_service = getattr(request.app.state, "web3_service", None)
        if default_service is not None and default_service.network.name == target:
            return default_service
        service = Web3Service(network_name=target)
        if not isinstance(services_by_network, dict):
            services_by_network = {}
            request.app.state.web3_services = services_by_network
        services_by_network[target] = service
        return service


def get_web3_service_for_chain_id(request: Request, chain_id: int) -> Web3Service:
    services_by_network = getattr(request.app.state, "web3_services", None)
    if isinstance(services_by_network, dict):
        for cached in services_by_network.values():
            if int(cached.chain_id) == int(chain_id):
                return cached
    default_service = getattr(request.app.state, "web3_service", None)
    if default_service is not None and int(default_service.chain_id) == int(chain_id):
        return default_service
    if int(chain_id) == int(settings.local_network.chain_id):
        return get_web3_service_for_network(request, "local")
    if int(chain_id) == int(settings.sepolia_network.chain_id):
        return get_web3_service_for_network(request, "sepolia")
    raise HTTPException(
        status_code=403,
        detail=f"Unsupported transaction chain_id {chain_id}.",
    )


def resolve_requested_network(
    query_network: str | None,
    body_network: str | None,
) -> str | None:
    normalized_query = (
        normalize_network_name(query_network) if query_network is not None else None
    )
    normalized_body = (
        normalize_network_name(body_network) if body_network is not None else None
    )
    if (
        normalized_query is not None
        and normalized_body is not None
        and normalized_query != normalized_body
    ):
        raise HTTPException(
            status_code=403,
            detail="Query network does not match request body network.",
        )
    return normalized_query or normalized_body


def resolve_authenticated_web3_service(
    request: Request,
    *,
    query_network: str | None = None,
    body_network: str | None = None,
    body_chain_id: int | None = None,
    context: AccessContext,
) -> Web3Service:
    target_network = resolve_requested_network(query_network, body_network)
    if target_network is not None:
        service = get_web3_service_for_network(request, target_network)
    elif body_chain_id is not None:
        service = get_web3_service_for_chain_id(request, body_chain_id)
    else:
        default_service = get_web3_service(request)
        if (
            context.authenticated
            and context.chain_id is not None
            and int(context.chain_id) != int(default_service.chain_id)
        ):
            service = get_web3_service_for_chain_id(request, int(context.chain_id))
        else:
            service = default_service

    require_matching_chain(context, service)
    if target_network is not None and target_network != service.network.name:
        raise HTTPException(
            status_code=403,
            detail="Requested network does not match the target network.",
        )
    if body_chain_id is not None and int(body_chain_id) != int(service.chain_id):
        raise HTTPException(
            status_code=403,
            detail="Requested chain_id does not match the target network.",
        )
    return service


def resolve_contract_from_block(
    web3_service: Web3Service,
    contract_name: str,
    requested_from_block: int | None,
) -> int:
    if requested_from_block is not None:
        if requested_from_block < 0:
            raise HTTPException(status_code=422, detail="from_block must be non-negative.")
        return requested_from_block
    if web3_service.network.name != "sepolia":
        return 0
    contract_entry = web3_service.registry.get("contracts", {}).get(contract_name, {})
    deploy_block = (
        contract_entry.get("blockNumber") if isinstance(contract_entry, dict) else None
    )
    if isinstance(deploy_block, int) and deploy_block >= 0:
        return deploy_block
    raise HTTPException(
        status_code=422,
        detail="from_block is required on Sepolia to bound historical log scans.",
    )


def resolve_analytics_from_block(
    web3_service: Web3Service, requested_from_block: int | None
) -> int | None:
    if requested_from_block is not None:
        if requested_from_block < 0:
            raise HTTPException(status_code=422, detail="from_block must be non-negative.")
        return requested_from_block
    if web3_service.network.name != "sepolia":
        return 0
    pool_entry = web3_service.registry.get("contracts", {}).get("LendingPool", {})
    deploy_block = pool_entry.get("blockNumber") if isinstance(pool_entry, dict) else None
    if isinstance(deploy_block, int) and deploy_block >= 0:
        return deploy_block
    return None


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


def get_agreement_generator_for_service(
    request: Request, web3_service: Web3Service
) -> AgreementGeneratorService:
    base = get_agreement_generator(request)
    if base.web3_service is web3_service:
        return base
    return AgreementGeneratorService(
        web3_service,
        binding_store_path=base.binding_store_path,
        gateway=base.gateway,
    )


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


def get_credit_audit_service_for_service(
    request: Request, web3_service: Web3Service
) -> CreditAndAuditIPFSService:
    base = get_credit_audit_service(request)
    if base.web3_service is web3_service:
        return base
    agreement_gen = get_agreement_generator_for_service(request, web3_service)
    return CreditAndAuditIPFSService(
        web3_service,
        gateway=base.gateway,
        agreement_generator=agreement_gen,
        metadata_store_path=base.metadata_store_path,
    )


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


