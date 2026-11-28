"""Unsigned transaction preparation and receipt confirmation schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from backend.schemas.common import APIModel


class TransactionAction(str, Enum):
    APPROVE_MYUSDT = "APPROVE_MYUSDT"
    APPROVE_COLLATERAL_NFT = "APPROVE_COLLATERAL_NFT"
    DEPOSIT_LENDER = "DEPOSIT_LENDER"
    WITHDRAW_LENDER = "WITHDRAW_LENDER"
    TRANSFER_LENDING_POSITION_NFT = "TRANSFER_LENDING_POSITION_NFT"
    DEPOSIT_COLLATERAL = "DEPOSIT_COLLATERAL"
    WITHDRAW_COLLATERAL = "WITHDRAW_COLLATERAL"
    BORROW = "BORROW"
    REPAY = "REPAY"
    LIQUIDATE = "LIQUIDATE"
    FAUCET_MYUSDT = "FAUCET_MYUSDT"
    MOCK_ORACLE_MULTIPLIER = "MOCK_ORACLE_MULTIPLIER"


class TransactionPrepareRequest(APIModel):
    wallet_address: str | None = Field(default=None, min_length=42, max_length=42)
    account: str | None = Field(default=None, min_length=42, max_length=42)
    network: str | None = Field(default=None, min_length=1, max_length=32)
    chain_id: int | None = Field(default=None, gt=0)
    action: TransactionAction
    args: dict[str, Any] = Field(default_factory=dict)
    amount_wad: str | None = None
    position_id: int | None = Field(default=None, ge=0)
    borrower_address: str | None = Field(default=None, min_length=42, max_length=42)
    is_nft: bool | None = None
    collateral_amount_or_token_id: str | None = None
    agreement_cid: str | None = Field(default=None, max_length=256)
    token_id: int | None = Field(default=None, ge=0)
    recipient_address: str | None = Field(default=None, min_length=42, max_length=42)
    multiplier_bps: int | None = Field(default=None, ge=0, le=100_000)
    eth_usd_price: str | None = None
    duration_seconds: int | None = Field(default=None, gt=0)

    @field_validator("amount_wad", "collateral_amount_or_token_id", "eth_usd_price")
    @classmethod
    def reject_blank_numeric_strings(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Value must not be blank.")
        return value

    @model_validator(mode="before")
    @classmethod
    def expand_args(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        args = data.get("args") or {}
        if not isinstance(args, dict):
            raise ValueError("args must be an object.")
        aliases = {
            "amount_wad": ("amount_wad", "amount"),
            "position_id": ("position_id", "positionId"),
            "borrower_address": ("borrower_address", "borrower"),
            "is_nft": ("is_nft",),
            "collateral_amount_or_token_id": (
                "collateral_amount_or_token_id",
                "amount_or_token_id",
            ),
            "agreement_cid": ("agreement_cid",),
            "token_id": ("token_id", "tokenId"),
            "recipient_address": ("recipient_address", "to", "recipient"),
            "multiplier_bps": ("multiplier_bps", "new_multiplier_bps"),
        }
        for field_name, keys in aliases.items():
            if data.get(field_name) is None:
                for key in keys:
                    if key in args:
                        data[field_name] = args[key]
                        break
        for numeric_str_field in ("amount_wad", "collateral_amount_or_token_id"):
            raw_val = data.get(numeric_str_field)
            if isinstance(raw_val, int) and not isinstance(raw_val, bool):
                data[numeric_str_field] = str(raw_val)
        return data

    @model_validator(mode="after")
    def normalize_api_contract_fields(self) -> "TransactionPrepareRequest":
        if self.account and self.wallet_address and self.account.lower() != self.wallet_address.lower():
            raise ValueError("account and wallet_address must refer to the same wallet.")
        wallet = self.wallet_address or self.account
        if wallet is None:
            raise ValueError("wallet_address or account is required.")
        self.wallet_address = wallet
        self.account = self.account or wallet
        return self


class TransactionPrepareResponse(APIModel):
    intent_id: str
    unsignedTransaction: dict[str, object]
    gas_quote: dict[str, object]
    interest_quote: dict[str, object] | None = None
    signing: str
    context: dict[str, Any]
    availability: dict[str, Any]
    allowance: dict[str, Any]
    preview: dict[str, Any]


class TransactionConfirmRequest(APIModel):
    intent_id: str = Field(min_length=1)
    tx_hash: str = Field(pattern=r"^0x[0-9a-fA-F]{64}$")
    network: str | None = Field(default=None, min_length=1, max_length=32)
    chain_id: int | None = Field(default=None, gt=0)


class TransactionConfirmResponse(APIModel):
    tx_hash: str
    status: int
    block_number: int
    loan_binding: dict[str, object] | None = None
