"""Local Hardhat demo-only time controls."""

from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import get_web3_service
from backend.schemas.demo import DemoTimeRequest
from backend.security.auth import require_roles
from backend.services.time_travel import fast_forward_time
from backend.services.web3_service import Web3Service
from src.ipfs.rbac import AccessContext, Role

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post("/time")
def fast_forward_local_time(
    body: DemoTimeRequest,
    _context: AccessContext = Depends(require_roles(Role.ADMIN)),
    service: Web3Service = Depends(get_web3_service),
) -> dict[str, object]:
    if service.network.name != "local":
        raise HTTPException(status_code=403, detail="Demo time travel is local-network only.")
    try:
        result = fast_forward_time(service.w3, body.seconds)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return result.to_dict()
