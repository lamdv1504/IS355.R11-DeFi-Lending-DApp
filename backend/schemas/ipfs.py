"""IPFS document request and response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from backend.schemas.common import APIModel


class CreateAgreementRequest(APIModel):
    principal_wad: str = Field(pattern=r"^[1-9][0-9]*$")
    asset_description: str = Field(min_length=1, max_length=500)
    network: str | None = Field(default=None, min_length=1, max_length=32)


class CreditReportRequest(APIModel):
    from_block: int | None = Field(default=None, ge=0)
    to_block: int | str = "latest"
    network: str | None = Field(default=None, min_length=1, max_length=32)

    @field_validator("to_block")
    @classmethod
    def valid_to_block(cls, value: int | str) -> int | str:
        if isinstance(value, bool):
            raise ValueError("to_block must be a non-negative block number or 'latest'.")
        if isinstance(value, int):
            if value < 0:
                raise ValueError("to_block must be non-negative.")
            return value
        if value != "latest":
            raise ValueError("to_block must be a non-negative block number or 'latest'.")
        return value


class AuditLogsRequest(APIModel):
    from_block: int | None = Field(default=None, ge=0)
    to_block: int | str = "latest"
    seed_simulated_months: int = Field(default=6, ge=0, le=120)
    network: str | None = Field(default=None, min_length=1, max_length=32)

    @field_validator("to_block")
    @classmethod
    def valid_to_block(cls, value: int | str) -> int | str:
        if isinstance(value, bool):
            raise ValueError("to_block must be a non-negative block number or 'latest'.")
        if isinstance(value, int):
            if value < 0:
                raise ValueError("to_block must be non-negative.")
            return value
        if value != "latest":
            raise ValueError("to_block must be a non-negative block number or 'latest'.")
        return value


class IPFSDocumentListResponse(APIModel):
    documents: list[dict[str, Any]]


class IPFSDocumentResponse(APIModel):
    cid: str
    document_type: str
    visibility: str
    content_type: str
    sha256: str
    content: Any
