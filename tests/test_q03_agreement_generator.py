"""Q03 tests for pre-borrow agreements, encrypted IPFS access, and receipt binding."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from web3 import Web3

from backend.config import constants
from backend.services.agreement_generator import (
    AgreementGeneratorService,
    AgreementTransactionError,
)
from src.ipfs.cid_utils import sha256_bytes
from src.ipfs.encryption import DocumentEncryptor
from src.ipfs.ipfs_client import IPFSClient, IPFSConfig
from src.ipfs.rbac import (
    AccessContext,
    AccessDeniedError,
    AuthorizedIPFSGateway,
    Role,
)
from src.documents.schemas import LoanTxBindingRecord

BORROWER = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"
OTHER_BORROWER = "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc"
LENDER = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
ADMIN = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


class _FakeWeb3Service:
    w3 = Web3()
    network = SimpleNamespace(name="local")
    chain_id = 31337
    registry = {
        "contracts": {
            "LendingPool": {"address": "0x0000000000000000000000000000000000000010"},
            "MyUSDT": {"address": "0x0000000000000000000000000000000000000020"},
            "CollateralNFT": {"address": "0x0000000000000000000000000000000000000030"},
        }
    }

    def get_loan_position(self, borrower: str) -> dict[str, Any]:
        assert borrower == Web3.to_checksum_address(BORROWER)
        return {
            "active": True,
            "receipt_token_id": 7,
            "is_nft_collateral": False,
            "collateral_amount": {"wad": str(1_000 * constants.WAD)},
            "collateral_token_id": 0,
        }

    def get_borrower_risk(self, borrower: str) -> dict[str, Any]:
        return {
            "collateral_value": {"wad": str(1_000 * constants.WAD)},
            "total_debt": {"wad": str(100 * constants.WAD)},
        }

    def get_current_ltv_bps(self, borrower: str) -> dict[str, Any]:
        return {"bps": 1_000, "percent": 10.0, "is_infinite": False}

    def get_interest_rate_snapshot(self) -> dict[str, Any]:
        return {
            "borrow_apr": {"bps": 1_000, "percent": 10.0},
            "borrow_apy_reference": {"bps": 1_051, "percent": 10.5156},
        }

    def get_collateral_receipt_info(self, receipt_id: int) -> dict[str, Any]:
        assert receipt_id == 7
        return {
            "active": True,
            "is_nft": False,
            "asset_id_or_amount": {"wad": str(1_000 * constants.WAD)},
        }

    def get_max_borrowable(self, borrower: str) -> dict[str, str]:
        return {"wad": str(700 * constants.WAD)}


@pytest.fixture
def agreement_service(tmp_path: Path) -> AgreementGeneratorService:
    ipfs = IPFSClient(
        IPFSConfig(provider="local_store", local_store_dir=tmp_path / "ipfs")
    )
    gateway = AuthorizedIPFSGateway(
        ipfs_client=ipfs,
        encryptor=DocumentEncryptor.from_hex_key("11" * 32),
    )
    return AgreementGeneratorService(
        _FakeWeb3Service(),
        gateway=gateway,
        binding_store_path=tmp_path / "q03-agreement-index.json",
    )


def _create_agreement(service: AgreementGeneratorService) -> dict[str, Any]:
    return service.create_pre_borrow_agreement(
        BORROWER,
        500 * constants.WAD,
        asset_description="Tokenized MyUSDT collateral for Q03 integration test.",
    )


def test_pre_borrow_pdf_is_private_encrypted_and_retrievable(
    agreement_service: AgreementGeneratorService,
) -> None:
    result = _create_agreement(agreement_service)

    assert result["status"] == "PRE_BORROW_UNSIGNED"
    assert result["tx_hash"] is None
    assert result["agreement_id"]
    assert len(result["agreement_nonce"]) >= 8
    assert len(result["pdf_plaintext_sha256"]) == 64
    assert len(result["encrypted_ipfs_sha256"]) == 64
    assert result["acl_metadata"]["encrypted"] is True
    assert result["acl_metadata"]["visibility"] == "PRIVATE"

    raw = agreement_service.gateway.retrieve_raw_by_cid(result["cid"])
    encrypted_envelope = json.loads(raw.content.decode("utf-8"))
    assert encrypted_envelope["encrypted"] is True
    assert encrypted_envelope["algorithm"] == "AES-256-GCM"
    assert b"%PDF-" not in raw.content

    owner_context = AccessContext.for_wallet(BORROWER, {Role.BORROWER})
    pdf = agreement_service.retrieve_agreement_pdf(result["cid"], owner_context)
    assert pdf.startswith(b"%PDF-")
    assert sha256_bytes(pdf) == result["pdf_plaintext_sha256"]


def test_pre_borrow_agreement_rejects_borrow_above_70_percent_ltv(
    agreement_service: AgreementGeneratorService,
) -> None:
    with pytest.raises(ValueError, match="exceed max borrow"):
        agreement_service.create_pre_borrow_agreement(
            BORROWER,
            601 * constants.WAD,
            asset_description="Tokenized MyUSDT collateral for an over-limit test.",
        )


def test_agreement_retrieval_enforces_owner_and_admin_rbac(
    agreement_service: AgreementGeneratorService,
) -> None:
    result = _create_agreement(agreement_service)
    contexts = (
        (AccessContext.guest(), 401),
        (AccessContext.for_wallet(LENDER, {Role.LENDER}), 403),
        (AccessContext.for_wallet(OTHER_BORROWER, {Role.BORROWER}), 403),
    )
    for context, expected_status in contexts:
        with pytest.raises(AccessDeniedError) as error:
            agreement_service.retrieve_agreement_pdf(result["cid"], context)
        assert error.value.http_status == expected_status

    owner = AccessContext.for_wallet(BORROWER, {Role.BORROWER})
    admin = AccessContext.for_wallet(ADMIN, {Role.ADMIN})
    assert agreement_service.retrieve_agreement_pdf(result["cid"], owner).startswith(b"%PDF-")
    assert agreement_service.retrieve_agreement_pdf(result["cid"], admin).startswith(b"%PDF-")


def test_confirmed_borrow_receipt_creates_loan_tx_binding_record(
    agreement_service: AgreementGeneratorService,
) -> None:
    result = _create_agreement(agreement_service)
    tx_hash = "0x" + "ab" * 32

    record = agreement_service.bind_loan_transaction(
        result["cid"],
        "loan-7",
        BORROWER,
        {"status": 1, "transactionHash": tx_hash, "blockNumber": 42},
    )

    assert isinstance(record, LoanTxBindingRecord)
    assert record.agreement_cid == result["cid"]
    assert record.agreement_id == result["agreement_id"]
    assert record.loan_id == "loan-7"
    assert record.borrower_wallet.lower() == BORROWER.lower()
    assert record.tx_hash == tx_hash
    assert record.block_number == 42
    saved_index = json.loads(agreement_service.binding_store_path.read_text(encoding="utf-8"))
    assert saved_index["loan_tx_bindings"][0]["tx_hash"] == tx_hash


def test_failed_borrow_receipt_is_not_bound(
    agreement_service: AgreementGeneratorService,
) -> None:
    result = _create_agreement(agreement_service)

    with pytest.raises(AgreementTransactionError, match="status must be 1"):
        agreement_service.bind_loan_transaction(
            result["cid"],
            "loan-7",
            BORROWER,
            {"status": 0, "transactionHash": "0x" + "ab" * 32, "blockNumber": 42},
        )
    saved_index = json.loads(agreement_service.binding_store_path.read_text(encoding="utf-8"))
    assert saved_index["loan_tx_bindings"] == []
