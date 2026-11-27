"""Create, privately store, and reconcile pre-borrow loan agreements."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.config import constants
from backend.services.web3_service import Web3Service
from src.documents.loan_agreement_template import render_loan_agreement_pdf
from src.documents.schemas import (
    LoanAgreementPayload,
    LoanCollateralInfo,
    LoanTermsInfo,
    LoanTxBindingRecord,
)
from src.ipfs.cid_utils import sha256_bytes
from src.ipfs.encryption import DocumentEncryptor, normalize_wallet_address
from src.ipfs.ipfs_client import IPFSClient
from src.ipfs.rbac import (
    AccessContext,
    AuthorizedIPFSGateway,
    DocumentAccessMetadata,
    DocumentType,
    DocumentVisibility,
)

_VN_TZ = timezone(timedelta(hours=7))


class AgreementIndexError(RuntimeError):
    """Raised when the local agreement metadata index cannot be read or written."""


class AgreementIntegrityError(RuntimeError):
    """Raised when retrieved agreement bytes do not match their recorded PDF hash."""


class AgreementTransactionError(ValueError):
    """Raised when a borrow receipt is not a successful confirmed transaction."""


class AgreementGeneratorService:
    """Build unsigned loan agreements and bind them to confirmed borrow receipts."""

    def __init__(
        self,
        web3_service: Web3Service,
        *,
        binding_store_path: Path,
        gateway: AuthorizedIPFSGateway | None = None,
    ) -> None:
        self.web3_service = web3_service
        self.gateway = gateway or AuthorizedIPFSGateway(
            IPFSClient(),
            DocumentEncryptor.from_env("DOCUMENT_AES_KEY_HEX"),
        )
        self.binding_store_path = Path(binding_store_path)

    def create_pre_borrow_agreement(
        self,
        borrower_wallet: str,
        principal_wad: int,
        *,
        asset_description: str,
        wallet_auth_signature: str | None = None,
    ) -> dict[str, Any]:
        """Render and privately upload a pre-borrow PDF after checking the on-chain LTV cap."""
        if (
            isinstance(principal_wad, bool)
            or not isinstance(principal_wad, int)
            or principal_wad <= 0
        ):
            raise ValueError("principal_wad must be a positive integer in WAD.")
        borrower = self.web3_service.w3.to_checksum_address(borrower_wallet)
        position = self.web3_service.get_loan_position(borrower)
        risk = self.web3_service.get_borrower_risk(borrower)
        current_ltv = self.web3_service.get_current_ltv_bps(borrower)
        rates = self.web3_service.get_interest_rate_snapshot()

        receipt_id = int(position["receipt_token_id"])
        if not position["active"] or receipt_id <= 0:
            raise ValueError("Borrower has no active collateral receipt.")
        receipt = self.web3_service.get_collateral_receipt_info(receipt_id)
        if not receipt["active"]:
            raise ValueError("Borrower collateral receipt is not active.")

        collateral_wad = int(risk["collateral_value"]["wad"])
        current_debt_wad = int(risk["total_debt"]["wad"])
        if collateral_wad <= 0:
            raise ValueError("Borrower has no collateral with a positive on-chain valuation.")

        expected_ltv_bps = (current_debt_wad * constants.BPS) // collateral_wad
        if int(current_ltv["bps"]) != expected_ltv_bps:
            raise ValueError(
                "Borrower LTV does not match the current debt and collateral valuation."
            )

        max_borrow_wad = int(self.web3_service.get_max_borrowable(borrower)["wad"])
        total_debt_after_borrow = current_debt_wad + principal_wad
        if total_debt_after_borrow > max_borrow_wad:
            raise ValueError(
                f"Requested principal would exceed max borrow: "
                f"{total_debt_after_borrow} > {max_borrow_wad} WAD."
            )

        proposed_ltv_bps = (total_debt_after_borrow * constants.BPS) // collateral_wad
        if proposed_ltv_bps > constants.MAX_LTV_BPS:
            raise ValueError("Requested principal would exceed the 70% LTV limit.")

        is_nft = bool(receipt["is_nft"])
        asset_id_or_amount = receipt["asset_id_or_amount"]
        if is_nft:
            asset_id_or_amount_str = str(int(asset_id_or_amount))
            token_name = "CollateralNFT"
        else:
            asset_id_or_amount_str = str(int(asset_id_or_amount["wad"]))
            token_name = "MyUSDT"

        token_entry = self.web3_service.registry.get("contracts", {}).get(token_name, {})
        pool_entry = self.web3_service.registry.get("contracts", {}).get("LendingPool", {})
        token_address = token_entry.get("address") or None
        pool_address = pool_entry.get("address") or None
        now_utc = datetime.now(timezone.utc)
        now_vn = now_utc.astimezone(_VN_TZ)
        borrow_apr_bps = int(rates["borrow_apr"]["bps"])
        agreement_id = f"Q03-{uuid.uuid4()}"
        payload = LoanAgreementPayload(
            agreement_id=agreement_id,
            agreement_nonce=uuid.uuid4().hex + uuid.uuid4().hex,
            created_at_utc=now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            created_at_vn=now_vn.strftime("%Y-%m-%d %H:%M:%S UTC+07:00"),
            network=self.web3_service.network.name,
            chain_id=int(self.web3_service.chain_id),
            lending_pool_address=pool_address,
            borrower_wallet=borrower,
            wallet_auth_signature=wallet_auth_signature,
            collateral=LoanCollateralInfo(
                asset_type="ERC721" if is_nft else "ERC20",
                token_address=token_address,
                asset_id_or_amount=asset_id_or_amount_str,
                receipt_token_id=str(receipt_id),
                valuation_wad=str(collateral_wad),
                valuation_display=constants.wad_to_decimal_str(collateral_wad),
                asset_description=asset_description,
            ),
            loan_terms=LoanTermsInfo(
                principal_wad=str(principal_wad),
                principal_display=constants.wad_to_decimal_str(principal_wad),
                requested_ltv_bps=proposed_ltv_bps,
                borrow_apr_bps=borrow_apr_bps,
                borrow_apr_percent=constants.apr_bps_to_percent(borrow_apr_bps),
                borrow_apy_percent=float(rates["borrow_apy_reference"]["percent"]),
            ),
            status="PRE_BORROW_UNSIGNED",
            tx_hash=None,
        )

        pdf_bytes = render_loan_agreement_pdf(payload)
        pdf_sha256 = sha256_bytes(pdf_bytes)
        upload, acl, _ = self.gateway.upload_document(
            pdf_bytes,
            document_type=DocumentType.LOAN_AGREEMENT,
            filename=f"{agreement_id}.pdf",
            content_type="application/pdf",
            owner_wallet=borrower,
            visibility=DocumentVisibility.PRIVATE,
            extra_metadata={"agreement_id": agreement_id},
        )
        if not acl.encrypted or not acl.ciphertext_sha256:
            raise AgreementIntegrityError(
                "Private agreement upload did not return encrypted metadata."
            )
        if acl.plaintext_sha256 != pdf_sha256:
            raise AgreementIntegrityError("Uploaded agreement metadata has an unexpected PDF SHA-256.")

        index = self._load_index()
        index["acl_metadata"][upload.cid] = acl.to_dict()
        index["agreements"][upload.cid] = {
            "agreement_id": agreement_id,
            "borrower_wallet": normalize_wallet_address(borrower),
            "principal_wad": str(principal_wad),
            "pdf_plaintext_sha256": pdf_sha256,
            "encrypted_ipfs_sha256": acl.ciphertext_sha256,
            "network": self.web3_service.network.name,
            "chain_id": int(self.web3_service.chain_id),
        }
        self._save_index(index)

        return {
            "cid": upload.cid,
            "pdf_plaintext_sha256": pdf_sha256,
            "encrypted_ipfs_sha256": acl.ciphertext_sha256,
            "gateway_url": upload.gateway_url,
            "agreement_id": agreement_id,
            "agreement_nonce": payload.agreement_nonce,
            "status": payload.status,
            "tx_hash": None,
            "acl_metadata": acl.to_dict(),
        }

    def bind_loan_transaction(
        self,
        agreement_cid: str,
        loan_id: str,
        borrower_wallet: str,
        transaction_receipt: Mapping[str, Any],
    ) -> LoanTxBindingRecord:
        """Persist the CID/loan/tx binding only after a successful borrow receipt."""
        index = self._load_index()
        agreement = index["agreements"].get(agreement_cid)
        acl_raw = index["acl_metadata"].get(agreement_cid)
        if agreement is None or acl_raw is None:
            raise ValueError(f"No locally indexed agreement for CID {agreement_cid!r}.")
        borrower = normalize_wallet_address(borrower_wallet)
        if borrower != normalize_wallet_address(agreement["borrower_wallet"]):
            raise ValueError("Borrower wallet does not own this agreement.")

        status = self._receipt_value(transaction_receipt, "status")
        if isinstance(status, str):
            status = int(status, 16) if status.startswith("0x") else int(status)
        if int(status) != 1:
            raise AgreementTransactionError("borrow() transaction receipt status must be 1.")

        tx_value = self._receipt_value(
            transaction_receipt, "transactionHash", "transaction_hash", "tx_hash"
        )
        if isinstance(tx_value, str):
            tx_hash = tx_value
        else:
            tx_hash = self.web3_service.w3.to_hex(tx_value)
        block_number = int(
            self._receipt_value(transaction_receipt, "blockNumber", "block_number")
        )
        if not loan_id.strip():
            raise ValueError("loan_id must be non-empty.")

        record = LoanTxBindingRecord(
            agreement_id=agreement["agreement_id"],
            agreement_cid=agreement_cid,
            pdf_plaintext_sha256=agreement["pdf_plaintext_sha256"],
            encrypted_ipfs_sha256=agreement["encrypted_ipfs_sha256"],
            loan_id=loan_id,
            borrower_wallet=borrower,
            principal_wad=agreement["principal_wad"],
            network=agreement["network"],
            chain_id=agreement["chain_id"],
            tx_hash=tx_hash,
            block_number=block_number,
            confirmed_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        index["loan_tx_bindings"].append(record.model_dump(mode="json"))
        self._save_index(index)
        return record

    def retrieve_agreement_pdf(self, cid: str, context: AccessContext) -> bytes:
        """Authorize, decrypt, and verify an agreement PDF before returning its bytes."""
        index = self._load_index()
        acl_raw = index["acl_metadata"].get(cid)
        metadata = self._metadata_from_dict(acl_raw) if acl_raw else None
        result = self.gateway.retrieve_authorized_document(cid, context, metadata=metadata)
        actual_sha256 = sha256_bytes(result.content)
        if actual_sha256 != result.plaintext_sha256:
            raise AgreementIntegrityError("Retrieved agreement PDF failed SHA-256 verification.")
        if metadata is not None and actual_sha256 != metadata.plaintext_sha256:
            raise AgreementIntegrityError("Retrieved agreement PDF does not match indexed SHA-256.")
        if not result.content.startswith(b"%PDF-"):
            raise AgreementIntegrityError("Retrieved agreement content is not a PDF.")
        return result.content

    def _load_index(self) -> dict[str, Any]:
        if not self.binding_store_path.exists():
            return {
                "schema_version": "1.0",
                "acl_metadata": {},
                "agreements": {},
                "loan_tx_bindings": [],
            }
        try:
            index = json.loads(self.binding_store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AgreementIndexError(
                f"Cannot load agreement binding index: {self.binding_store_path}"
            ) from exc
        if (
            not isinstance(index, dict)
            or not isinstance(index.get("acl_metadata"), dict)
            or not isinstance(index.get("agreements"), dict)
            or not isinstance(index.get("loan_tx_bindings"), list)
        ):
            raise AgreementIndexError("Agreement binding index has an invalid structure.")
        return index

    def _save_index(self, index: dict[str, Any]) -> None:
        self.binding_store_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.binding_store_path.parent,
                prefix=f"{self.binding_store_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(index, temporary_file, ensure_ascii=False, indent=2, sort_keys=True)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            temporary_path.replace(self.binding_store_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _metadata_from_dict(raw: Mapping[str, Any]) -> DocumentAccessMetadata:
        return DocumentAccessMetadata(
            cid=str(raw["cid"]),
            document_type=DocumentType(raw["document_type"]),
            visibility=DocumentVisibility(raw["visibility"]),
            owner_wallet=raw["owner_wallet"],
            encrypted=bool(raw["encrypted"]),
            content_type=str(raw["content_type"]),
            filename=str(raw["filename"]),
            plaintext_sha256=str(raw["plaintext_sha256"]),
            ciphertext_sha256=raw.get("ciphertext_sha256"),
            key_id=raw.get("key_id"),
        )

    @staticmethod
    def _receipt_value(receipt: Mapping[str, Any], *names: str) -> Any:
        for name in names:
            if isinstance(receipt, Mapping) and name in receipt:
                return receipt[name]
        raise AgreementTransactionError(
            f"Transaction receipt is missing required field: {', '.join(names)}."
        )
