"""Pool and account read response schemas."""

from __future__ import annotations

from typing import Any

from backend.schemas.common import APIModel


class PoolResponse(APIModel):
    network: str
    chain_id: int
    pool: dict[str, Any]
    available_liquidity: dict[str, str]
    interest_rates: dict[str, Any]


class AccountPositionsResponse(APIModel):
    wallet_address: str
    positions: list[dict[str, Any]]


class AccountLoanResponse(APIModel):
    wallet_address: str
    loan_position: dict[str, Any]
    risk: dict[str, Any]
    borrowing_capacity: dict[str, Any]
    interest: dict[str, Any]


class AccountBalancesResponse(APIModel):
    wallet_address: str
    balances: dict[str, Any]


class RateAnalyticsResponse(APIModel):
    network: str
    chain_id: int
    interest_rates: dict[str, Any]
    pool: dict[str, Any]
