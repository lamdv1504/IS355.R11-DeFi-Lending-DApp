"""Wallet nonce and bearer-session endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from backend.schemas.auth import NonceRequest, NonceResponse, SessionResponse, VerifyRequest
from backend.security.auth import (
    AuthenticationError,
    WalletAuthManager,
    get_auth_manager,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/nonce", response_model=NonceResponse)
def request_nonce(
    body: NonceRequest,
    auth_manager: WalletAuthManager = Depends(get_auth_manager),
) -> dict[str, object]:
    try:
        return auth_manager.issue_nonce(
            body.wallet_address, body.chain_id, domain=body.domain
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/verify", response_model=SessionResponse)
def verify_signature(
    body: VerifyRequest,
    auth_manager: WalletAuthManager = Depends(get_auth_manager),
) -> dict[str, object]:
    try:
        return auth_manager.verify_signature(
            body.wallet_address,
            body.chain_id,
            body.nonce,
            body.signature,
            domain=body.domain,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
