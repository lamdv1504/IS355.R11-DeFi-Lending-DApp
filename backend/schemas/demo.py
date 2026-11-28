"""Local-only demo operation schemas."""

from __future__ import annotations

from pydantic import Field

from backend.schemas.common import APIModel


class DemoTimeRequest(APIModel):
    seconds: int = Field(gt=0, le=31_536_000)
    network: str | None = Field(default=None, min_length=1, max_length=32)
    chain_id: int | None = Field(default=None, gt=0)


class DemoTimeResponse(APIModel):
    environment: str
    chain_id: int
    seconds_requested: int
    seconds_elapsed: int
    timestamp_before: int
    timestamp_after: int
    block_before: int
    block_after: int
