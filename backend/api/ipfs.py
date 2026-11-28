"""RBAC-protected document creation, listing, and retrieval endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from backend.api.dependencies import (
    get_agreement_generator,
    get_agreement_generator_for_service,
    get_credit_audit_service,
    get_credit_audit_service_for_service,
    lock_for_index,
    resolve_authenticated_web3_service,
    resolve_block_range,
)
from backend.schemas.ipfs import (
    AuditLogsRequest,
    CreateAgreementRequest,
    CreditReportRequest,
)
from backend.security.auth import get_current_context, get_optional_context, require_roles
from backend.services.agreement_generator import AgreementGeneratorService
from backend.services.credit_and_audit_ipfs import CreditAndAuditIPFSService
from src.ipfs.cid_utils import sha256_bytes
from src.ipfs.rbac import (
    AccessContext,
    AccessDeniedError,
    DocumentAccessMetadata,
    DocumentType,
    DocumentVisibility,
    Role,
)

router = APIRouter(prefix="/api/ipfs", tags=["ipfs"])


def _require_owner_or_admin(context: AccessContext, address: str) -> None:
    if not context.authenticated or context.wallet_address is None:
        raise HTTPException(status_code=401, detail="A verified wallet session is required.")
    if (
        context.wallet_address.lower() != address.lower()
        and Role.ADMIN not in context.roles
    ):
        raise HTTPException(status_code=403, detail="Wallet cannot create a document for another account.")


def _metadata_from_raw(raw: dict[str, Any]) -> DocumentAccessMetadata:
    return DocumentAccessMetadata(
        cid=str(raw["cid"]),
        document_type=DocumentType(raw["document_type"]),
        visibility=DocumentVisibility(raw["visibility"]),
        owner_wallet=raw.get("owner_wallet"),
        encrypted=bool(raw["encrypted"]),
        content_type=str(raw["content_type"]),
        filename=str(raw["filename"]),
        plaintext_sha256=str(raw["plaintext_sha256"]),
        ciphertext_sha256=raw.get("ciphertext_sha256"),
        key_id=raw.get("key_id"),
    )


def _document_metadata(
    agreement_generator: AgreementGeneratorService,
    credit_audit_service: CreditAndAuditIPFSService,
) -> dict[str, DocumentAccessMetadata]:
    agreements = agreement_generator._load_index().get("acl_metadata", {})
    credit = credit_audit_service._load_metadata()
    result = {
        cid: _metadata_from_raw(raw)
        for cid, raw in agreements.items()
        if isinstance(raw, dict)
    }
    result.update(credit)
    return result


@router.post("/create-agreement")
def create_agreement(
    body: CreateAgreementRequest,
    request: Request,
    network: str | None = Query(
        default=None,
        description="Target network ('local' or 'sepolia'). Defaults to body.network, session chain, or ACTIVE_NETWORK.",
    ),
    context: AccessContext = Depends(get_current_context),
) -> dict[str, Any]:
    web3_service = resolve_authenticated_web3_service(
        request,
        query_network=network,
        body_network=body.network,
        context=context,
    )
    if not context.wallet_address:
        raise HTTPException(status_code=401, detail="A verified wallet session is required.")
    _require_owner_or_admin(context, context.wallet_address)
    service = get_agreement_generator_for_service(request, web3_service)
    with lock_for_index(service.binding_store_path):
        return service.create_pre_borrow_agreement(
            context.wallet_address,
            int(body.principal_wad),
            asset_description=body.asset_description,
        )


@router.post("/credit-report/{address}")
def create_credit_report(
    address: str,
    body: CreditReportRequest,
    request: Request,
    network: str | None = Query(
        default=None,
        description="Target network ('local' or 'sepolia'). Defaults to body.network, session chain, or ACTIVE_NETWORK.",
    ),
    context: AccessContext = Depends(get_current_context),
) -> dict[str, Any]:
    web3_service = resolve_authenticated_web3_service(
        request,
        query_network=network,
        body_network=body.network,
        context=context,
    )
    wallet = web3_service._checksum_address(address, "wallet")
    _require_owner_or_admin(context, wallet)
    from_block, to_block = resolve_block_range(
        web3_service, body.from_block, body.to_block
    )
    service = get_credit_audit_service_for_service(request, web3_service)
    with lock_for_index(service.metadata_store_path):
        return service.generate_credit_report(
            wallet, from_block=from_block, to_block=to_block
        )


@router.post("/audit-logs")
def create_audit_logs(
    body: AuditLogsRequest,
    request: Request,
    network: str | None = Query(
        default=None,
        description="Target network ('local' or 'sepolia'). Defaults to body.network, session chain, or ACTIVE_NETWORK.",
    ),
    context: AccessContext = Depends(require_roles(Role.ADMIN)),
) -> dict[str, Any]:
    web3_service = resolve_authenticated_web3_service(
        request,
        query_network=network,
        body_network=body.network,
        context=context,
    )
    from_block, to_block = resolve_block_range(
        web3_service, body.from_block, body.to_block
    )
    service = get_credit_audit_service_for_service(request, web3_service)
    with lock_for_index(service.metadata_store_path):
        return service.generate_monthly_audit_logs(
            from_block=from_block,
            to_block=to_block,
            seed_simulated_months=body.seed_simulated_months,
        )


@router.get("/documents")
def list_documents(
    context: AccessContext = Depends(get_optional_context),
    agreement_generator: AgreementGeneratorService = Depends(get_agreement_generator),
    credit_audit_service: CreditAndAuditIPFSService = Depends(get_credit_audit_service),
) -> dict[str, list[dict[str, Any]]]:
    metadata = _document_metadata(agreement_generator, credit_audit_service)
    visible: list[dict[str, Any]] = []
    for item in metadata.values():
        is_public = item.visibility == DocumentVisibility.PUBLIC
        is_owner = (
            context.authenticated
            and context.wallet_address is not None
            and item.normalized_owner() == context.wallet_address.lower()
        )
        is_admin = context.authenticated and Role.ADMIN in context.roles
        if is_public or is_owner or is_admin:
            visible.append(item.to_dict())
    return {"documents": sorted(visible, key=lambda item: item["cid"])}


@router.get("/documents/{cid}/retrieve")
def retrieve_document(
    cid: str,
    context: AccessContext = Depends(get_optional_context),
    agreement_generator: AgreementGeneratorService = Depends(get_agreement_generator),
    credit_audit_service: CreditAndAuditIPFSService = Depends(get_credit_audit_service),
) -> Response:
    metadata = _document_metadata(agreement_generator, credit_audit_service).get(cid)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Document CID is not indexed by this backend.")

    if metadata.document_type == DocumentType.LOAN_AGREEMENT:
        content = agreement_generator.retrieve_agreement_pdf(cid, context)
        if sha256_bytes(content) != metadata.plaintext_sha256:
            raise RuntimeError("Retrieved agreement failed SHA-256 integrity verification.")
        return Response(
            content=content,
            media_type=metadata.content_type,
            headers={"X-Content-SHA256": metadata.plaintext_sha256},
        )

    result = credit_audit_service.retrieve_from_ipfs(cid, context)
    if sha256_bytes(result.content) != metadata.plaintext_sha256:
        raise RuntimeError("Retrieved IPFS document failed SHA-256 integrity verification.")
    headers = {"X-Content-SHA256": metadata.plaintext_sha256}
    if metadata.document_type == DocumentType.CREDIT_REPORT:
        if not context.authenticated:
            raise AccessDeniedError(401, "Authentication is required for a private Credit Report.")
        return JSONResponse(
            content={
                "cid": cid,
                "document_type": metadata.document_type.value,
                "sha256": metadata.plaintext_sha256,
                "content": json.loads(result.content),
            },
            headers=headers,
        )
    if metadata.document_type == DocumentType.AUDIT_LOGS:
        if metadata.content_type == "application/json":
            content: Any = json.loads(result.content)
            return JSONResponse(
                content={
                    "cid": cid,
                    "document_type": metadata.document_type.value,
                    "sha256": metadata.plaintext_sha256,
                    "content": content,
                },
                headers=headers,
            )
        return Response(
            content=result.content,
            media_type=metadata.content_type,
            headers=headers,
        )
    raise HTTPException(status_code=415, detail="Unsupported IPFS document type.")
