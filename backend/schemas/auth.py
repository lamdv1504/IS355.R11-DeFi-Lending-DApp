"""Wallet nonce and session request/response schemas."""

from __future__ import annotations

from pydantic import Field

from backend.schemas.common import APIModel


class NonceRequest(APIModel):
    wallet_address: str = Field(min_length=42, max_length=42)
    chain_id: int = Field(gt=0)
    domain: str | None = Field(default=None, min_length=1, max_length=255)


class NonceResponse(APIModel):
    nonce: str
    message: str
    domain: str
    chain_id: int
    wallet_address: str
    expires_at: int


class VerifyRequest(NonceRequest):
    nonce: str = Field(min_length=1)
    signature: str = Field(min_length=132, max_length=132)


class SessionResponse(APIModel):
    access_token: str
    token_type: str
    expires_in: int
    expires_at: int
    wallet_address: str
    chain_id: int
    roles: list[str]
