"""Prepare unsigned client-wallet transactions and verify mined receipts."""

from __future__ import annotations

from collections.abc import Generator
import secrets
import threading
import time
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from web3.exceptions import TransactionNotFound

from backend.api.dependencies import (
    get_agreement_generator_for_service,
    get_web3_service_for_chain_id,
    get_web3_service_for_network,
    lock_for_index,
    require_matching_chain,
    resolve_authenticated_web3_service,
    resolve_requested_network,
)
from backend.config import constants
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
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _required_amount(value: str | None, label: str = "amount_wad") -> int:
    if value is None or not value.isdigit() or int(value) <= 0:
        raise HTTPException(
            status_code=422, detail=f"{label} must be a positive integer in WAD."
        )
    return int(value)


def _required_non_negative_int(value: str | int | None, label: str) -> int:
    if isinstance(value, bool):
        raise HTTPException(status_code=422, detail=f"{label} must be a non-negative integer.")
    if isinstance(value, int):
        if value < 0:
            raise HTTPException(status_code=422, detail=f"{label} must be a non-negative integer.")
        return value
    if value is None or not str(value).isdigit():
        raise HTTPException(status_code=422, detail=f"{label} must be a non-negative integer.")
    return int(value)


def _checksum(service: Web3Service, address: str | None, label: str) -> str:
    if address is None:
        raise HTTPException(status_code=422, detail=f"{label} is required.")
    return service._checksum_address(address, label)


def _format_ltv(ltv_bps: int) -> dict[str, Any]:
    infinite = ltv_bps >= constants.INFINITE_HEALTH_FACTOR
    return {
        "bps": ltv_bps,
        "percent": None if infinite else constants.apr_bps_to_percent(ltv_bps),
        "is_infinite": infinite,
    }


def _block_snapshot(service: Web3Service) -> tuple[int, int]:
    getter = getattr(service, "get_latest_block_context", None)
    if callable(getter):
        ctx = getter()
        return int(ctx["block_number"]), int(ctx["as_of_timestamp"])
    eth = getattr(getattr(service, "w3", None), "eth", None)
    block_number = int(getattr(eth, "block_number", 0) or 0)
    try:
        timestamp = int(service.get_interest_rate_snapshot().get("timestamp", 0))
    except Exception:
        timestamp = 0
    return block_number, timestamp


def _transaction_spec(
    body: TransactionPrepareRequest,
    context: AccessContext,
    service: Web3Service,
    sender: str,
) -> tuple[str, str, tuple[Any, ...], dict[str, Any]]:
    action = body.action
    pool_address = service.registry.get("contracts", {}).get("LendingPool", {}).get("address")
    if not pool_address:
        raise HTTPException(status_code=503, detail="LendingPool deployment is unavailable.")
    extra: dict[str, Any] = {"agreement_cid": body.agreement_cid}

    if action == TransactionAction.APPROVE_MYUSDT:
        amount = _required_amount(body.amount_wad)
        extra["amount_wad"] = amount
        return "MyUSDT", "approve", (pool_address, amount), extra
    if action == TransactionAction.APPROVE_COLLATERAL_NFT:
        if body.token_id is None:
            raise HTTPException(status_code=422, detail="token_id is required.")
        extra["token_id"] = body.token_id
        return "CollateralNFT", "approve", (pool_address, body.token_id), extra
    if action == TransactionAction.DEPOSIT_LENDER:
        amount = _required_amount(body.amount_wad)
        extra["amount_wad"] = amount
        return "LendingPool", "depositLender", (amount,), extra
    if action == TransactionAction.WITHDRAW_LENDER:
        if body.position_id is None:
            raise HTTPException(status_code=422, detail="position_id is required.")
        amount = _required_amount(body.amount_wad)
        extra["amount_wad"] = amount
        extra["position_id"] = body.position_id
        return (
            "LendingPool",
            "withdrawLender",
            (body.position_id, amount),
            extra,
        )
    if action == TransactionAction.TRANSFER_LENDING_POSITION_NFT:
        raw_position_id = body.position_id if body.position_id is not None else body.token_id
        position_id = _required_non_negative_int(raw_position_id, "position_id")
        recipient = _checksum(service, body.recipient_address, "recipient_address")
        if recipient.lower() == ZERO_ADDRESS:
            raise HTTPException(
                status_code=422,
                detail="recipient_address must not be the zero address.",
            )
        extra["position_id"] = position_id
        extra["recipient_address"] = recipient
        return (
            "LendingPositionNFT",
            "safeTransferFrom",
            (sender, recipient, position_id),
            extra,
        )
    if action == TransactionAction.DEPOSIT_COLLATERAL:
        if body.is_nft is None:
            raise HTTPException(status_code=422, detail="is_nft is required.")
        if body.is_nft:
            raw_token_id = (
                body.collateral_amount_or_token_id
                if body.collateral_amount_or_token_id is not None
                else body.token_id
            )
            amount_or_token_id = _required_non_negative_int(
                raw_token_id, "collateral_amount_or_token_id"
            )
        else:
            amount_or_token_id = _required_amount(
                body.collateral_amount_or_token_id, "collateral_amount_or_token_id"
            )
        extra["is_nft"] = body.is_nft
        extra["collateral_amount_or_token_id"] = amount_or_token_id
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
        amount = _required_amount(body.amount_wad)
        extra["amount_wad"] = amount
        return "LendingPool", "repay", (amount,), extra
    if action == TransactionAction.LIQUIDATE:
        borrower = _checksum(service, body.borrower_address, "borrower")
        extra["borrower_address"] = borrower
        return (
            "LendingPool",
            "liquidate",
            (borrower,),
            extra,
        )
    if action == TransactionAction.FAUCET_MYUSDT:
        recipient = _checksum(service, body.recipient_address, "recipient") if body.recipient_address else sender
        amount = _required_amount(body.amount_wad)
        extra["amount_wad"] = amount
        extra["recipient_address"] = recipient
        return (
            "MyUSDT",
            "faucet",
            (recipient, amount),
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
        extra["multiplier_bps"] = body.multiplier_bps
        return "PriceOracle", "setPriceMultiplierBps", (body.multiplier_bps,), extra
    raise HTTPException(status_code=422, detail="Unsupported transaction action.")


def _build_prepare_allowance(
    action: TransactionAction,
    sender: str,
    intent_data: dict[str, Any],
    service: Web3Service,
) -> dict[str, Any]:
    contracts = service.registry.get("contracts", {})
    pool_address = contracts.get("LendingPool", {}).get("address")
    token_address = contracts.get("MyUSDT", {}).get("address")
    nft_address = contracts.get("CollateralNFT", {}).get("address")

    if action in (
        TransactionAction.DEPOSIT_LENDER,
        TransactionAction.REPAY,
    ) or (action == TransactionAction.DEPOSIT_COLLATERAL and not intent_data.get("is_nft")):
        required_wad = int(
            intent_data.get(
                "amount_wad", intent_data.get("collateral_amount_or_token_id", 0)
            )
        )
        current_wad = (
            int(service.get_myusdt_allowance(sender, pool_address)["wad"])
            if pool_address
            else 0
        )
        return {
            "token_address": token_address,
            "spender_address": pool_address,
            "amount_wad": str(required_wad),
            "current_allowance_wad": str(current_wad),
            "approval_required": current_wad < required_wad,
        }

    if action == TransactionAction.LIQUIDATE:
        borrower = str(intent_data["borrower_address"])
        target_risk = service.get_borrower_risk(borrower)
        required_wad = int(target_risk["total_debt"]["wad"])
        current_wad = (
            int(service.get_myusdt_allowance(sender, pool_address)["wad"])
            if pool_address
            else 0
        )
        return {
            "token_address": token_address,
            "spender_address": pool_address,
            "amount_wad": str(required_wad),
            "current_allowance_wad": str(current_wad),
            "approval_required": required_wad > 0 and current_wad < required_wad,
        }

    if action == TransactionAction.DEPOSIT_COLLATERAL and intent_data.get("is_nft"):
        token_id = int(intent_data["collateral_amount_or_token_id"])
        is_approved = False
        checker = getattr(service, "get_collateral_nft_approval_status", None)
        if callable(checker) and pool_address:
            try:
                is_approved = bool(checker(sender, pool_address, token_id)["is_approved"])
            except Exception:
                is_approved = False
        return {
            "token_address": nft_address,
            "spender_address": pool_address,
            "token_id": token_id,
            "amount_wad": None,
            "current_allowance_wad": None,
            "approval_required": not is_approved,
        }

    return {
        "token_address": None,
        "spender_address": None,
        "amount_wad": None,
        "current_allowance_wad": None,
        "approval_required": False,
    }


def _build_prepare_preview(
    action: TransactionAction,
    sender: str,
    intent_data: dict[str, Any],
    service: Web3Service,
) -> dict[str, Any]:
    pool_info = service.get_pool_info()
    total_supplied = int(pool_info["total_supplied"]["wad"])
    total_borrowed = int(pool_info["total_borrowed"]["wad"])
    current_util_bps = constants.calculate_utilization_bps(total_borrowed, total_supplied)
    current_borrow_apr_bps = int(
        pool_info.get(
            "borrow_apr_bps", constants.calculate_borrow_apr_bps(current_util_bps)
        )
    )
    current_supply_apr_bps = int(
        pool_info.get(
            "supply_apr_bps",
            constants.calculate_supply_apr_bps(current_borrow_apr_bps, current_util_bps),
        )
    )

    risk_wallet = (
        str(intent_data["borrower_address"])
        if action == TransactionAction.LIQUIDATE and intent_data.get("borrower_address")
        else sender
    )
    risk = service.get_borrower_risk(risk_wallet)
    current_collateral = int(risk["collateral_value"]["wad"])
    current_debt = int(risk["total_debt"]["wad"])
    current_ltv_bps = constants.calculate_ltv_bps(current_debt, current_collateral)
    current_hf_wad = constants.calculate_health_factor(current_collateral, current_debt)

    resulting_collateral = current_collateral
    resulting_debt = current_debt
    resulting_supplied = total_supplied
    resulting_borrowed = total_borrowed
    amount_wad: str | None = (
        str(intent_data["amount_wad"]) if "amount_wad" in intent_data else None
    )

    if action == TransactionAction.BORROW:
        borrow_amount = int(intent_data["amount_wad"])
        resulting_debt = current_debt + borrow_amount
        resulting_borrowed = total_borrowed + borrow_amount
    elif action == TransactionAction.REPAY:
        repay_amount = int(intent_data["amount_wad"])
        repaid_effective = min(repay_amount, current_debt)
        resulting_debt = current_debt - repaid_effective
        resulting_borrowed = max(0, total_borrowed - repaid_effective)
    elif action == TransactionAction.DEPOSIT_LENDER:
        deposit_amount = int(intent_data["amount_wad"])
        resulting_supplied = total_supplied + deposit_amount
    elif action == TransactionAction.WITHDRAW_LENDER:
        withdraw_amount = int(intent_data["amount_wad"])
        resulting_supplied = max(0, total_supplied - withdraw_amount)
    elif action == TransactionAction.DEPOSIT_COLLATERAL:
        if intent_data.get("is_nft"):
            token_id = int(intent_data["collateral_amount_or_token_id"])
            valuation_fn = getattr(service, "get_collateral_nft_valuation", None)
            added_val = 0
            if callable(valuation_fn):
                try:
                    added_val = int(valuation_fn(token_id)["wad"])
                except Exception:
                    added_val = 0
            amount_wad = str(added_val)
            resulting_collateral = current_collateral + added_val
        else:
            added_val = int(intent_data["collateral_amount_or_token_id"])
            amount_wad = str(added_val)
            resulting_collateral = current_collateral + added_val
    elif action == TransactionAction.WITHDRAW_COLLATERAL:
        resulting_collateral = 0
        resulting_debt = 0
    elif action == TransactionAction.LIQUIDATE:
        resulting_borrowed = max(0, total_borrowed - current_debt)
        resulting_collateral = 0
        resulting_debt = 0
        amount_wad = str(current_debt)

    resulting_util_bps = constants.calculate_utilization_bps(
        resulting_borrowed, resulting_supplied
    )
    resulting_borrow_apr_bps = constants.calculate_borrow_apr_bps(resulting_util_bps)
    resulting_supply_apr_bps = constants.calculate_supply_apr_bps(
        resulting_borrow_apr_bps, resulting_util_bps
    )
    resulting_ltv_bps = constants.calculate_ltv_bps(resulting_debt, resulting_collateral)
    resulting_hf_wad = constants.calculate_health_factor(
        resulting_collateral, resulting_debt
    )

    preview: dict[str, Any] = {
        "amount_wad": amount_wad,
        "current_debt_wad": str(current_debt),
        "resulting_debt_wad": str(resulting_debt),
        "collateral_value_wad": str(current_collateral),
        "resulting_collateral_value_wad": str(resulting_collateral),
        "current_ltv_bps": current_ltv_bps,
        "resulting_ltv_bps": resulting_ltv_bps,
        "resulting_ltv": _format_ltv(resulting_ltv_bps),
        "current_hf_wad": str(current_hf_wad),
        "resulting_hf_wad": str(resulting_hf_wad),
        "resulting_hf": constants.format_health_factor_for_api(resulting_hf_wad),
        "current_borrow_apr_bps": current_borrow_apr_bps,
        "resulting_borrow_apr_bps": resulting_borrow_apr_bps,
        "current_supply_apr_bps": current_supply_apr_bps,
        "resulting_supply_apr_bps": resulting_supply_apr_bps,
        "rate_basis": "simple_apr_per_second",
        "is_estimate": True,
    }
    if action == TransactionAction.TRANSFER_LENDING_POSITION_NFT:
        preview["position_id"] = intent_data["position_id"]
        preview["recipient_address"] = intent_data["recipient_address"]
    return preview


@router.post("/prepare", response_model=TransactionPrepareResponse)
def prepare_transaction(
    body: TransactionPrepareRequest,
    request: Request,
    network: str | None = Query(
        default=None,
        description=(
            "Target network ('local' or 'sepolia'). Defaults to body.network, "
            "chain_id, authenticated session chain, or ACTIVE_NETWORK."
        ),
    ),
    context: AccessContext = Depends(get_current_context),
) -> dict[str, Any]:
    service = resolve_authenticated_web3_service(
        request,
        query_network=network,
        body_network=body.network,
        body_chain_id=body.chain_id,
        context=context,
    )
    wallet_address = body.wallet_address
    if not wallet_address:
        raise HTTPException(status_code=422, detail="wallet_address or account is required.")
    if not context.wallet_address or context.wallet_address.lower() != wallet_address.lower():
        raise HTTPException(status_code=403, detail="Transaction wallet must match the authenticated wallet.")
    sender = service._checksum_address(wallet_address, "wallet")
    contract_name, function_name, args, intent_data = _transaction_spec(
        body, context, service, sender
    )
    allowance = _build_prepare_allowance(body.action, sender, intent_data, service)
    build_options: dict[str, Any] = {
        "from_address": sender,
        "eth_usd_price": body.eth_usd_price,
    }
    if allowance.get("approval_required"):
        build_options["skip_gas_estimation"] = True
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
    block_number, as_of_timestamp = _block_snapshot(service)
    preview = _build_prepare_preview(body.action, sender, intent_data, service)
    intent_id = secrets.token_urlsafe(24)
    intent = {
        "wallet_address": sender,
        "action": body.action.value,
        "network": service.network.name,
        "chain_id": int(service.chain_id),
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
        "context": {
            "network": service.network.name,
            "chain_id": service.chain_id,
            "account": sender,
            "action": body.action.value,
            "block_number": block_number,
            "as_of_timestamp": as_of_timestamp,
        },
        "availability": {
            "ready": True,
            "blocked_reason": None,
            "missing_contracts": [],
        },
        "allowance": allowance,
        "preview": preview,
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
    network: str | None = Query(
        default=None,
        description="Optional target network ('local' or 'sepolia'); must match the prepared intent.",
    ),
    context: AccessContext = Depends(get_current_context),
) -> dict[str, Any]:
    requested_network = resolve_requested_network(network, body.network)
    with _claim_intent(request, body.intent_id) as intent:
        if (
            not context.wallet_address
            or context.wallet_address.lower() != str(intent["wallet_address"]).lower()
        ):
            raise HTTPException(status_code=403, detail="Transaction intent belongs to another wallet.")

        intent_network = intent.get("network")
        intent_chain_id = intent.get("chain_id")
        if requested_network is not None and intent_network and requested_network != str(intent_network):
            raise HTTPException(
                status_code=403,
                detail="Transaction confirmation network does not match the prepared intent.",
            )
        if (
            body.chain_id is not None
            and intent_chain_id is not None
            and int(body.chain_id) != int(intent_chain_id)
        ):
            raise HTTPException(
                status_code=403,
                detail="Transaction confirmation chain_id does not match the prepared intent.",
            )

        if intent_network:
            service = get_web3_service_for_network(request, str(intent_network))
        elif intent_chain_id is not None:
            service = get_web3_service_for_chain_id(request, int(intent_chain_id))
        else:
            service = get_web3_service_for_network(request, requested_network)

        require_matching_chain(context, service)
        if intent_chain_id is not None and int(intent_chain_id) != int(service.chain_id):
            raise HTTPException(
                status_code=403,
                detail="Prepared transaction intent chain does not match the target network.",
            )

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
        if isinstance(tx_input, (bytes, bytearray)):
            tx_input_hex = service.w3.to_hex(tx_input)
        elif tx_input is None:
            tx_input_hex = ""
        else:
            tx_input_hex = str(tx_input)
            if tx_input_hex and not tx_input_hex.startswith("0x"):
                tx_input_hex = "0x" + tx_input_hex
        expected_from = expected.get("from")
        expected_to = expected.get("to")
        expected_data = str(expected.get("data", ""))
        if expected_data and not expected_data.startswith("0x"):
            expected_data = "0x" + expected_data
        tx_value = _value(transaction, "value")
        if (
            not tx_from
            or service.w3.to_checksum_address(tx_from) != service.w3.to_checksum_address(expected_from)
            or not tx_to
            or service.w3.to_checksum_address(tx_to) != service.w3.to_checksum_address(expected_to)
            or tx_input_hex.lower() != expected_data.lower()
            or tx_value is None
            or int(tx_value) != int(expected.get("value", 0))
        ):
            raise HTTPException(status_code=400, detail="Mined transaction does not match prepared intent.")
        tx_chain_id = _value(transaction, "chainId", "chain_id")
        if isinstance(tx_chain_id, str) and tx_chain_id.startswith("0x"):
            parsed_chain_id: int | None = int(tx_chain_id, 16)
        elif tx_chain_id is not None:
            parsed_chain_id = int(tx_chain_id)
        else:
            tx_v = _value(transaction, "v")
            if isinstance(tx_v, str) and tx_v.startswith("0x"):
                parsed_v = int(tx_v, 16)
            elif tx_v is not None:
                parsed_v = int(tx_v)
            else:
                parsed_v = None
            parsed_chain_id = (
                (parsed_v - 35) // 2 if parsed_v is not None and parsed_v >= 35 else None
            )
        if parsed_chain_id is None or parsed_chain_id != service.chain_id:
            raise HTTPException(status_code=400, detail="Transaction chainId does not match service network.")

        binding: dict[str, object] | None = None
        if intent["action"] == TransactionAction.BORROW.value:
            agreement_generator = get_agreement_generator_for_service(request, service)
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
                    expected_chain_id=int(service.chain_id),
                )
            binding = record.model_dump(mode="json")

        return {
            "tx_hash": body.tx_hash,
            "status": int(_value(receipt, "status")),
            "block_number": int(_value(receipt, "blockNumber", "block_number")),
            "loan_binding": binding,
        }
