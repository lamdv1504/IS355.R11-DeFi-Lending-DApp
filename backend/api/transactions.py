"""Prepare unsigned client-wallet transactions and verify mined receipts."""

from __future__ import annotations

from collections.abc import Generator
import secrets
import threading
import time
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from web3.exceptions import TransactionNotFound

from backend.api.dependencies import (
    get_agreement_generator,
    get_web3_service,
    lock_for_index,
    require_matching_chain,
)
from backend.schemas.transactions import (
    TransactionAction,
    TransactionConfirmRequest,
    TransactionConfirmResponse,
    TransactionPrepareRequest,
    TransactionPrepareResponse,
)
from backend.security.auth import get_current_context
from backend.services.web3_service import Web3Service
from src.ipfs.rbac import AccessContext, Role

router = APIRouter(prefix="/api/transactions", tags=["transactions"])
_intent_lock = threading.Lock()
_INTENT_TTL_SECONDS = 900


def _required_amount(value: str | None, label: str = "amount_wad") -> int:
    if value is None or not value.isdigit() or int(value) <= 0:
        raise HTTPException(
            status_code=422, detail=f"{label} must be a positive integer in WAD."
        )
    return int(value)


def _checksum(service: Web3Service, address: str | None, label: str) -> str:
    if address is None:
        raise HTTPException(status_code=422, detail=f"{label} is required.")
    return service._checksum_address(address, label)


def _transaction_spec(
    body: TransactionPrepareRequest,
    context: AccessContext,
    service: Web3Service,
) -> tuple[str, str, tuple[Any, ...], dict[str, Any]]:
    action = body.action
    pool_address = service.registry.get("contracts", {}).get("LendingPool", {}).get("address")
    if not pool_address:
        raise HTTPException(status_code=503, detail="LendingPool deployment is unavailable.")
    extra: dict[str, Any] = {"agreement_cid": body.agreement_cid}

    if action == TransactionAction.APPROVE_MYUSDT:
        return "MyUSDT", "approve", (pool_address, _required_amount(body.amount_wad)), extra
    if action == TransactionAction.APPROVE_COLLATERAL_NFT:
        if body.token_id is None:
            raise HTTPException(status_code=422, detail="token_id is required.")
        return "CollateralNFT", "approve", (pool_address, body.token_id), extra
    if action == TransactionAction.DEPOSIT_LENDER:
        return "LendingPool", "depositLender", (_required_amount(body.amount_wad),), extra
    if action == TransactionAction.WITHDRAW_LENDER:
        if body.position_id is None:
            raise HTTPException(status_code=422, detail="position_id is required.")
        return (
            "LendingPool",
            "withdrawLender",
            (body.position_id, _required_amount(body.amount_wad)),
            extra,
        )
    if action == TransactionAction.DEPOSIT_COLLATERAL:
        if body.is_nft is None:
            raise HTTPException(status_code=422, detail="is_nft is required.")
        amount_or_token_id = _required_amount(
            body.collateral_amount_or_token_id, "collateral_amount_or_token_id"
        )
        return (
            "LendingPool",
            "depositCollateral",
            (amount_or_token_id, body.is_nft),
            extra,
        )
    if action == TransactionAction.WITHDRAW_COLLATERAL:
        return "LendingPool", "withdrawCollateral", (), extra
    if action == TransactionAction.BORROW:
        amount = _required_amount(body.amount_wad)
        if not body.agreement_cid:
            raise HTTPException(status_code=422, detail="agreement_cid is required for borrow.")
        extra["amount_wad"] = amount
        return "LendingPool", "borrow", (amount, body.agreement_cid), extra
    if action == TransactionAction.REPAY:
        return "LendingPool", "repay", (_required_amount(body.amount_wad),), extra
    if action == TransactionAction.LIQUIDATE:
        return (
            "LendingPool",
            "liquidate",
            (_checksum(service, body.borrower_address, "borrower"),),
            extra,
        )
    if action == TransactionAction.FAUCET_MYUSDT:
        recipient = _checksum(service, body.recipient_address, "recipient") if body.recipient_address else context.wallet_address
        return (
            "MyUSDT",
            "faucet",
            (recipient, _required_amount(body.amount_wad)),
            extra,
        )
    if action == TransactionAction.MOCK_ORACLE_MULTIPLIER:
        if service.network.name != "local":
            raise HTTPException(
                status_code=403, detail="Mock Oracle transactions are local-network only."
            )
        if Role.ADMIN not in context.roles:
            raise HTTPException(status_code=403, detail="Only ADMIN may prepare mock Oracle updates.")
        if body.multiplier_bps is None:
            raise HTTPException(status_code=422, detail="multiplier_bps is required.")
        return "PriceOracle", "setPriceMultiplierBps", (body.multiplier_bps,), extra
    raise HTTPException(status_code=422, detail="Unsupported transaction action.")


@router.post("/prepare", response_model=TransactionPrepareResponse)
def prepare_transaction(
    body: TransactionPrepareRequest,
    request: Request,
    context: AccessContext = Depends(get_current_context),
    service: Web3Service = Depends(get_web3_service),
) -> dict[str, Any]:
    require_matching_chain(context, service)
    if body.network and body.network.strip().lower() != service.network.name:
        raise HTTPException(
            status_code=403, detail="Transaction network does not match the active network."
        )
    if body.chain_id is not None and body.chain_id != service.chain_id:
        raise HTTPException(
            status_code=403, detail="Transaction chain_id does not match the active network."
        )
    wallet_address = body.wallet_address
    if not wallet_address:
        raise HTTPException(status_code=422, detail="wallet_address or account is required.")
    if not context.wallet_address or context.wallet_address.lower() != wallet_address.lower():
        raise HTTPException(status_code=403, detail="Transaction wallet must match the authenticated wallet.")
    sender = service._checksum_address(wallet_address, "wallet")
    contract_name, function_name, args, intent_data = _transaction_spec(body, context, service)
    build_options: dict[str, Any] = {
        "from_address": sender,
        "eth_usd_price": body.eth_usd_price,
    }
    if body.action == TransactionAction.BORROW:
        rates = service.get_interest_rate_snapshot()
        build_options.update(
            principal_wad=intent_data["amount_wad"],
            apr_bps=int(rates["borrow_apr"]["bps"]),
            duration_seconds=body.duration_seconds or 365 * 24 * 60 * 60,
        )
    quote = service.build_unsigned_transaction(
        contract_name, function_name, args, **build_options
    )
    intent_id = secrets.token_urlsafe(24)
    intent = {
        "wallet_address": sender,
        "action": body.action.value,
        "transaction": quote["transaction"],
        "data": intent_data,
        "expires_at": int(time.time()) + _INTENT_TTL_SECONDS,
    }
    with _intent_lock:
        intents = getattr(request.app.state, "prepared_intents", {})
        now = int(time.time())
        intents = {
            key: value
            for key, value in intents.items()
            if int(value["expires_at"]) > now
        }
        intents[intent_id] = intent
        request.app.state.prepared_intents = intents
    return {
        "intent_id": intent_id,
        "unsignedTransaction": quote["transaction"],
        "gas_quote": quote["gas_quote"],
        "interest_quote": quote["interest_quote"],
        "signing": "client_wallet",
    }


def _value(mapping: Any, *keys: str) -> Any:
    for key in keys:
        try:
            return mapping[key]
        except (KeyError, TypeError, AttributeError):
            try:
                return getattr(mapping, key)
            except AttributeError:
                continue
    return None


@contextmanager
def _claim_intent(request: Request, intent_id: str) -> Generator[dict[str, Any], None, None]:
    with _intent_lock:
        intents = getattr(request.app.state, "prepared_intents", {})
        intent = intents.get(intent_id)
        if intent is None or int(intent["expires_at"]) <= int(time.time()):
            raise HTTPException(
                status_code=401, detail="Transaction intent is missing or expired."
            )
        if intent.get("confirming"):
            raise HTTPException(status_code=409, detail="Transaction intent is already being confirmed.")
        intent["confirming"] = True
    succeeded = False
    try:
        yield intent
        succeeded = True
    finally:
        with _intent_lock:
            current_intents = getattr(request.app.state, "prepared_intents", {})
            if succeeded:
                current_intents.pop(intent_id, None)
            else:
                intent["confirming"] = False


@router.post("/confirm", response_model=TransactionConfirmResponse)
def confirm_transaction(
    body: TransactionConfirmRequest,
    request: Request,
    context: AccessContext = Depends(get_current_context),
    service: Web3Service = Depends(get_web3_service),
) -> dict[str, Any]:
    require_matching_chain(context, service)
    with _claim_intent(request, body.intent_id) as intent:
        if (
            not context.wallet_address
            or context.wallet_address.lower() != str(intent["wallet_address"]).lower()
        ):
            raise HTTPException(status_code=403, detail="Transaction intent belongs to another wallet.")

        try:
            transaction = service.w3.eth.get_transaction(body.tx_hash)
            receipt = service.w3.eth.get_transaction_receipt(body.tx_hash)
        except TransactionNotFound as exc:
            raise HTTPException(status_code=404, detail="Transaction was not found on-chain.") from exc
        receipt_hash = _value(receipt, "transactionHash", "transaction_hash")
        if receipt_hash is not None and service.w3.to_hex(receipt_hash).lower() != body.tx_hash.lower():
            raise HTTPException(status_code=400, detail="Receipt transaction hash does not match request.")
        if int(_value(receipt, "status") or 0) != 1:
            raise HTTPException(status_code=400, detail="Transaction receipt status is not successful.")
        expected = intent["transaction"]
        tx_from = _value(transaction, "from")
        tx_to = _value(transaction, "to")
        tx_input = _value(transaction, "input", "data")
        expected_from = expected.get("from")
        expected_to = expected.get("to")
        expected_data = expected.get("data")
        tx_value = _value(transaction, "value")
        if (
            not tx_from
            or service.w3.to_checksum_address(tx_from) != service.w3.to_checksum_address(expected_from)
            or not tx_to
            or service.w3.to_checksum_address(tx_to) != service.w3.to_checksum_address(expected_to)
            or str(tx_input).lower() != str(expected_data).lower()
            or tx_value is None
            or int(tx_value) != int(expected.get("value", 0))
        ):
            raise HTTPException(status_code=400, detail="Mined transaction does not match prepared intent.")
        tx_chain_id = _value(transaction, "chainId", "chain_id")
        if tx_chain_id is None or int(tx_chain_id) != service.chain_id:
            raise HTTPException(status_code=400, detail="Transaction chainId does not match service network.")

        binding: dict[str, object] | None = None
        if intent["action"] == TransactionAction.BORROW.value:
            agreement_generator = get_agreement_generator(request)
            agreement_cid = intent["data"].get("agreement_cid")
            if not agreement_cid:
                raise HTTPException(status_code=400, detail="Borrow intent is missing agreement CID.")
            pool_address = service._checksum_address(
                service.registry.get("contracts", {}).get("LendingPool", {}).get("address", ""),
                "LendingPool",
            )
            logs = service.get_contract("LendingPool").events.LoanBorrowed().process_receipt(
                receipt
            )
            event_matches = any(
                log.get("address")
                and service.w3.to_checksum_address(log["address"]).lower()
                == pool_address.lower()
                and str(log["args"].get("borrower", "")).lower()
                == str(intent["wallet_address"]).lower()
                and str(log["args"].get("agreementCid", ""))
                == str(agreement_cid)
                and int(log["args"].get("amountWad", -1))
                == int(intent["data"]["amount_wad"])
                for log in logs
            )
            if not event_matches:
                raise HTTPException(
                    status_code=400,
                    detail="Successful receipt does not contain the expected LoanBorrowed event.",
                )
            tx_hash = service.w3.to_hex(receipt_hash or body.tx_hash)
            with lock_for_index(agreement_generator.binding_store_path):
                record = agreement_generator.bind_loan_transaction(
                    str(agreement_cid),
                    tx_hash,
                    str(intent["wallet_address"]),
                    receipt,
                )
            binding = record.model_dump(mode="json")

        return {
            "tx_hash": body.tx_hash,
            "status": int(_value(receipt, "status")),
            "block_number": int(_value(receipt, "blockNumber", "block_number")),
            "loan_binding": binding,
        }
