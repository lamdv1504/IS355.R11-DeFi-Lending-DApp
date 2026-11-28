"""Pool, rates, and wallet account read endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from web3.exceptions import ContractLogicError

from backend.api.dependencies import (
    get_web3_service_for_network,
    resolve_analytics_from_block,
    resolve_contract_from_block,
)
from backend.schemas.pool import (
    AccountBalancesResponse,
    AccountLoanResponse,
    AccountPositionsResponse,
    AccountSnapshotResponse,
    PoolResponse,
    RateAnalyticsResponse,
)
from backend.services.credit_and_audit_ipfs import build_monthly_rate_entries
from backend.services.web3_service import Web3Service
from src.documents.schemas import AuditRateModelInfo

router = APIRouter(prefix="/api", tags=["pool"])


def _block_snapshot(service: Web3Service, interest_rates: dict[str, Any]) -> tuple[int, int]:
    getter = getattr(service, "get_latest_block_context", None)
    if callable(getter):
        ctx = getter()
        return int(ctx["block_number"]), int(ctx["as_of_timestamp"])
    block_number = int(getattr(getattr(service, "w3", None), "eth", None).block_number) if hasattr(getattr(getattr(service, "w3", None), "eth", None), "block_number") else 0
    timestamp = int(interest_rates.get("timestamp", 0))
    return block_number, timestamp


@router.get("/pool", response_model=PoolResponse)
def read_pool(
    request: Request,
    network: str | None = Query(
        default=None,
        description="Target network ('local' or 'sepolia'). Defaults to ACTIVE_NETWORK.",
    ),
) -> dict[str, Any]:
    service = get_web3_service_for_network(request, network)
    interest_rates = service.get_interest_rate_snapshot()
    block_number, as_of_timestamp = _block_snapshot(service, interest_rates)
    return {
        "network": service.network.name,
        "chain_id": service.chain_id,
        "block_number": block_number,
        "as_of_timestamp": as_of_timestamp,
        "pool": service.get_pool_info(),
        "available_liquidity": service.get_available_liquidity(),
        "interest_rates": interest_rates,
    }


@router.get(
    "/accounts/{address}/lending-positions",
    response_model=AccountPositionsResponse,
)
def read_lending_positions(
    address: str,
    request: Request,
    from_block: int | None = Query(default=None, ge=0),
    network: str | None = Query(default=None),
) -> dict[str, Any]:
    service = get_web3_service_for_network(request, network)
    wallet = service._checksum_address(address, "account")
    scan_from_block = resolve_contract_from_block(service, "LendingPool", from_block)
    block_number, as_of_timestamp = _block_snapshot(service, {})
    pool = service.get_contract("LendingPool")
    logs = pool.events.LenderDeposited().get_logs(
        from_block=scan_from_block,
        to_block="latest",
        argument_filters={},
    )
    positions: list[dict[str, Any]] = []
    seen: set[int] = set()
    for log in logs:
        args = log["args"]
        position_id = int(args["positionId"])
        if position_id in seen:
            continue
        seen.add(position_id)
        try:
            owner = service.get_lending_position_owner(position_id)
        except ContractLogicError:
            continue
        if owner.lower() != wallet.lower():
            continue
        position = service.get_lender_position(position_id)
        if not position["active"]:
            continue
        positions.append(
            {
                **position,
                "owner": owner,
                "earned_interest": service.get_lender_earned_interest(position_id),
                "claimable_balance": service.get_lender_claimable_balance(position_id),
                "max_withdrawable": service.get_max_withdrawable(position_id),
            }
        )
    return {
        "network": service.network.name,
        "chain_id": service.chain_id,
        "block_number": block_number,
        "as_of_timestamp": as_of_timestamp,
        "wallet_address": wallet,
        "positions": positions,
    }


def _read_wallet_balances(
    service: Web3Service, wallet: str, *, from_block: int | None = None
) -> dict[str, Any]:
    pool_address = service.registry.get("contracts", {}).get("LendingPool", {}).get("address")
    collateral_nft_balance = int(
        service.get_contract("CollateralNFT").functions.balanceOf(wallet).call()
    )
    collateral_nfts: list[dict[str, Any]] = []
    if collateral_nft_balance > 0:
        lister = getattr(service, "get_owned_collateral_nfts", None)
        if callable(lister):
            nft_from_block = resolve_contract_from_block(
                service, "CollateralNFT", from_block
            )
            collateral_nfts = lister(wallet, from_block=nft_from_block)
    balances: dict[str, Any] = {
        "myusdt": service.get_myusdt_balance(wallet),
        "debt_token": service.get_debt_token_balance(wallet),
        "lending_position_nft_balance": int(
            service.get_contract("LendingPositionNFT").functions.balanceOf(wallet).call()
        ),
        "collateral_nft_balance": collateral_nft_balance,
        "collateral_nft_token_ids": [int(item["token_id"]) for item in collateral_nfts],
        "collateral_nfts": collateral_nfts,
        "active_collateral_receipt_id": service.get_active_collateral_receipt(wallet),
    }
    if pool_address:
        balances["myusdt_allowance_to_pool"] = service.get_myusdt_allowance(
            wallet, pool_address
        )
    return balances


@router.get("/accounts/{address}/loan", response_model=AccountLoanResponse)
def read_loan(
    address: str,
    request: Request,
    network: str | None = Query(default=None),
) -> dict[str, Any]:
    service = get_web3_service_for_network(request, network)
    wallet = service._checksum_address(address, "account")
    interest_rates = service.get_interest_rate_snapshot()
    block_number, as_of_timestamp = _block_snapshot(service, interest_rates)
    liquidation_preview: dict[str, Any] | None = None
    preview_fn = getattr(service, "get_liquidation_preview", None)
    if callable(preview_fn):
        liquidation_preview = preview_fn(wallet)
    return {
        "network": service.network.name,
        "chain_id": service.chain_id,
        "block_number": block_number,
        "as_of_timestamp": as_of_timestamp,
        "wallet_address": wallet,
        "loan_position": service.get_loan_position(wallet),
        "risk": service.get_borrower_risk(wallet),
        "borrowing_capacity": {
            "max_borrowable": service.get_max_borrowable(wallet),
            "remaining": service.get_remaining_borrow_capacity(wallet),
            "available_to_borrow": service.get_available_to_borrow(wallet),
            "current_ltv": service.get_current_ltv_bps(wallet),
        },
        "interest": {
            "accrued": service.calculate_accrued_interest(wallet),
            "rates": interest_rates,
        },
        "liquidation_preview": liquidation_preview,
    }


@router.get("/accounts/{address}/balances", response_model=AccountBalancesResponse)
def read_balances(
    address: str,
    request: Request,
    from_block: int | None = Query(default=None, ge=0),
    network: str | None = Query(default=None),
) -> dict[str, Any]:
    service = get_web3_service_for_network(request, network)
    wallet = service._checksum_address(address, "account")
    block_number, as_of_timestamp = _block_snapshot(service, {})
    return {
        "network": service.network.name,
        "chain_id": service.chain_id,
        "block_number": block_number,
        "as_of_timestamp": as_of_timestamp,
        "wallet_address": wallet,
        "balances": _read_wallet_balances(service, wallet, from_block=from_block),
    }


@router.get("/accounts/{address}/snapshot", response_model=AccountSnapshotResponse)
def read_account_snapshot(
    address: str,
    request: Request,
    from_block: int | None = Query(default=None, ge=0),
    network: str | None = Query(default=None),
) -> dict[str, Any]:
    service = get_web3_service_for_network(request, network)
    wallet = service._checksum_address(address, "account")
    interest_rates = service.get_interest_rate_snapshot()
    block_number, as_of_timestamp = _block_snapshot(service, interest_rates)
    return {
        "network": service.network.name,
        "chain_id": service.chain_id,
        "block_number": block_number,
        "as_of_timestamp": as_of_timestamp,
        "wallet_address": wallet,
        "balances": _read_wallet_balances(service, wallet, from_block=from_block),
        "loan_position": service.get_loan_position(wallet),
        "risk": service.get_borrower_risk(wallet),
        "interest": {
            "accrued": service.calculate_accrued_interest(wallet),
            "rates": interest_rates,
        },
    }


@router.get("/analytics/rates", response_model=RateAnalyticsResponse)
def read_rate_analytics(
    request: Request,
    network: str | None = Query(
        default=None,
        description="Target network ('local' or 'sepolia'). Defaults to ACTIVE_NETWORK.",
    ),
    from_block: int | None = Query(default=None, ge=0),
    seed_simulated_months: int = Query(default=6, ge=0, le=120),
) -> dict[str, Any]:
    service = get_web3_service_for_network(request, network)
    interest_rates = service.get_interest_rate_snapshot()
    block_number, as_of_timestamp = _block_snapshot(service, interest_rates)
    scan_from_block = resolve_analytics_from_block(service, from_block)
    entries = build_monthly_rate_entries(
        service,
        from_block=scan_from_block,
        to_block="latest",
        seed_simulated_months=seed_simulated_months,
        include_event_logs=scan_from_block is not None,
    )
    return {
        "network": service.network.name,
        "chain_id": service.chain_id,
        "block_number": block_number,
        "as_of_timestamp": as_of_timestamp,
        "interest_rates": interest_rates,
        "pool": service.get_pool_info(),
        "rate_model": AuditRateModelInfo().model_dump(mode="json"),
        "series": [entry.model_dump(mode="json") for entry in entries],
    }
