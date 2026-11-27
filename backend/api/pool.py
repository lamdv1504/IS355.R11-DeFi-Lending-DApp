"""Pool, rates, and wallet account read endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from web3.exceptions import ContractLogicError

from backend.api.dependencies import get_web3_service, resolve_from_block
from backend.schemas.pool import (
    AccountBalancesResponse,
    AccountLoanResponse,
    AccountPositionsResponse,
    PoolResponse,
    RateAnalyticsResponse,
)
from backend.services.web3_service import Web3Service

router = APIRouter(prefix="/api", tags=["pool"])


@router.get("/pool", response_model=PoolResponse)
def read_pool(
    service: Web3Service = Depends(get_web3_service),
) -> dict[str, Any]:
    return {
        "network": service.network.name,
        "chain_id": service.chain_id,
        "pool": service.get_pool_info(),
        "available_liquidity": service.get_available_liquidity(),
        "interest_rates": service.get_interest_rate_snapshot(),
    }


@router.get(
    "/accounts/{address}/lending-positions",
    response_model=AccountPositionsResponse,
)
def read_lending_positions(
    address: str,
    from_block: int | None = Query(default=None, ge=0),
    service: Web3Service = Depends(get_web3_service),
) -> dict[str, Any]:
    wallet = service._checksum_address(address, "account")
    scan_from_block = resolve_from_block(service, from_block)
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
    return {"wallet_address": wallet, "positions": positions}


@router.get("/accounts/{address}/loan", response_model=AccountLoanResponse)
def read_loan(
    address: str,
    service: Web3Service = Depends(get_web3_service),
) -> dict[str, Any]:
    wallet = service._checksum_address(address, "account")
    return {
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
            "rates": service.get_interest_rate_snapshot(),
        },
    }


@router.get("/accounts/{address}/balances", response_model=AccountBalancesResponse)
def read_balances(
    address: str,
    service: Web3Service = Depends(get_web3_service),
) -> dict[str, Any]:
    wallet = service._checksum_address(address, "account")
    pool_address = service.registry.get("contracts", {}).get("LendingPool", {}).get("address")
    balances: dict[str, Any] = {
        "myusdt": service.get_myusdt_balance(wallet),
        "debt_token": service.get_debt_token_balance(wallet),
        "lending_position_nft_balance": int(
            service.get_contract("LendingPositionNFT").functions.balanceOf(wallet).call()
        ),
        "collateral_nft_balance": int(
            service.get_contract("CollateralNFT").functions.balanceOf(wallet).call()
        ),
        "active_collateral_receipt_id": service.get_active_collateral_receipt(wallet),
    }
    if pool_address:
        balances["myusdt_allowance_to_pool"] = service.get_myusdt_allowance(
            wallet, pool_address
        )
    return {"wallet_address": wallet, "balances": balances}


@router.get("/analytics/rates", response_model=RateAnalyticsResponse)
def read_rate_analytics(
    service: Web3Service = Depends(get_web3_service),
) -> dict[str, Any]:
    return {
        "network": service.network.name,
        "chain_id": service.chain_id,
        "interest_rates": service.get_interest_rate_snapshot(),
        "pool": service.get_pool_info(),
    }
