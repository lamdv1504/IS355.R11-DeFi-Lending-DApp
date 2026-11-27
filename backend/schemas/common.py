"""Shared REST response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class APIError(APIModel):
    detail: str


class DataResponse(APIModel):
    data: dict[str, Any]
