"""Local Hardhat demo-only time controls."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.api.dependencies import resolve_authenticated_web3_service
from backend.schemas.demo import DemoTimeRequest
from backend.security.auth import require_roles
from backend.services.time_travel import fast_forward_time
from src.ipfs.rbac import AccessContext, Role

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post("/time")
def fast_forward_local_time(
    body: DemoTimeRequest,
    request: Request,
    network: str | None = Query(
        default=None,
        description="Optional target network ('local' only; non-local sessions/networks are rejected).",
    ),
    context: AccessContext = Depends(require_roles(Role.ADMIN)),
) -> dict[str, object]:
    service = resolve_authenticated_web3_service(
        request,
        query_network=network,
        body_network=body.network,
        body_chain_id=body.chain_id,
        context=context,
    )
    if service.network.name != "local":
        raise HTTPException(status_code=403, detail="Demo time travel is local-network only.")
    try:
        result = fast_forward_time(service.w3, body.seconds)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return result.to_dict()
