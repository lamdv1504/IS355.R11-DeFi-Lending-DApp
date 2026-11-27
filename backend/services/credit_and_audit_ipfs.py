"""Generate credit reports and public monthly audit logs from LendingPool history."""

from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from backend.config import constants
from backend.services.agreement_generator import AgreementGeneratorService
from backend.services.web3_service import Web3Service
from src.documents.schemas import (
    AuditLogEntry,
    AuditLogsDocument,
    AuditRateModelInfo,
    CreditLoanRecord,
    CreditReportDocument,
    CreditReportSummary,
    CreditScoreInfo,
    audit_logs_to_csv,
    build_sample_audit_logs,
)
from src.ipfs.cid_utils import sha256_bytes
from src.ipfs.encryption import DocumentEncryptor
from src.ipfs.ipfs_client import IPFSClient
from src.ipfs.rbac import (
    AccessContext,
    AuthorizedDocumentResult,
    AuthorizedIPFSGateway,
    DocumentAccessMetadata,
    DocumentType,
    DocumentVisibility,
)


class CreditAuditIndexError(RuntimeError):
    """Raised when the local Credit Report/Audit Logs ACL index is invalid."""


class CreditAuditIntegrityError(RuntimeError):
    """Raised when a retrieved document does not match its stored content hash."""


_CREDIT_EVENT_NAMES = (
    "CollateralDeposited",
    "LoanBorrowed",
    "LoanRepaid",
    "LoanLiquidated",
)


class CreditAndAuditIPFSService:
    """Build private credit reports and public audit log JSON/CSV on IPFS.

    The default gateway uses the configured IPFS provider and server-side
    ``DOCUMENT_AES_KEY_HEX``. It never accepts wallet signing credentials.
    """

    def __init__(
        self,
        web3_service: Web3Service,
        *,
        gateway: AuthorizedIPFSGateway | None = None,
        agreement_generator: AgreementGeneratorService | None = None,
        metadata_store_path: Path | None = None,
    ) -> None:
        self.web3_service = web3_service
        self.gateway = gateway or AuthorizedIPFSGateway(
            IPFSClient(),
            DocumentEncryptor.from_env("DOCUMENT_AES_KEY_HEX"),
        )
        self.agreement_generator = agreement_generator
        self.metadata_store_path = (
            Path(metadata_store_path)
            if metadata_store_path is not None
            else Path(__file__).resolve().parents[1]
            / "data"
            / "credit_audit_ipfs_index.json"
        )

    def generate_credit_report(
        self,
        wallet_address: str,
        *,
        from_block: int = 0,
        to_block: int | str = "latest",
    ) -> dict[str, Any]:
        """Aggregate borrower events, calculate a 300-850 score, and upload encrypted JSON."""
        borrower = self.web3_service._checksum_address(wallet_address, "borrower")
        pool = self.web3_service.get_contract("LendingPool")
        events: dict[str, list[dict[str, Any]]] = {}
        for event_name in _CREDIT_EVENT_NAMES:
            events[event_name] = self._get_event_logs(
                pool,
                event_name,
                from_block=from_block,
                to_block=to_block,
                filters={"borrower": borrower},
            )

        borrowed_events = events["LoanBorrowed"]
        risk = self.web3_service.get_borrower_risk(borrower)
        current_debt_wad = int(risk["total_debt"]["wad"])
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        agreements = self._agreement_bindings()
        loans_by_id: dict[str, dict[str, Any]] = {}
        sorted_borrows = sorted(borrowed_events, key=self._event_sort_key)
        for event in sorted_borrows:
            args = event["args"]
            tx_hash = self._tx_hash(event)
            log_index = int(event.get("logIndex", event.get("log_index", 0)))
            loan_id = f"{tx_hash}:{log_index}"
            principal_wad = int(args["amountWad"])
            timestamp = int(args["timestamp"])
            agreement_cid = str(args.get("agreementCid", "") or "")
            if not agreement_cid:
                agreement_cid = agreements.get(tx_hash.lower(), {}).get("agreement_cid")
            loans_by_id[loan_id] = {
                "loan_id": loan_id,
                "agreement_cid": agreement_cid,
                "principal_wad": principal_wad,
                "repaid_wad": 0,
                "status": "ACTIVE",
                "borrowed_at_utc": self._iso_timestamp(timestamp),
                "closed_at_utc": None,
                "borrow_tx_hash": tx_hash,
                "repay_or_liquidate_tx_hash": None,
                "sort_key": self._event_sort_key(event),
            }

        active_loan_ids: list[str] = []
        timeline = sorted(
            (
                (self._event_sort_key(event), event_name, event)
                for event_name in ("LoanBorrowed", "LoanRepaid", "LoanLiquidated")
                for event in events[event_name]
            ),
            key=lambda item: item[0],
        )
        for event_key, event_name, event in timeline:
            args = event["args"]
            if event_name == "LoanBorrowed":
                log_index = int(event.get("logIndex", event.get("log_index", 0)))
                loan_id = f"{self._tx_hash(event)}:{log_index}"
                if loan_id in loans_by_id:
                    active_loan_ids.append(loan_id)
                    loans_by_id[loan_id]["sort_key"] = event_key
                continue

            loan = self._latest_open_loan(loans_by_id, active_loan_ids)
            if loan is None:
                continue
            loan["repay_or_liquidate_tx_hash"] = self._tx_hash(event)
            if event_name == "LoanRepaid":
                loan["repaid_wad"] += int(args["amountPaidWad"])
                if int(args["remainingDebtWad"]) == 0:
                    loan["status"] = "REPAID_ON_TIME"
                    loan["closed_at_utc"] = self._iso_timestamp(int(args["timestamp"]))
                    active_loan_ids.remove(loan["loan_id"])
            else:
                loan["status"] = "LIQUIDATED"
                loan["repaid_wad"] += int(args["debtCoveredWad"])
                loan["closed_at_utc"] = self._iso_timestamp(int(args["timestamp"]))
                active_loan_ids.remove(loan["loan_id"])

        loan_records = [
            CreditLoanRecord(
                loan_id=loan["loan_id"],
                agreement_cid=loan["agreement_cid"],
                principal_wad=str(loan["principal_wad"]),
                principal_display=constants.wad_to_decimal_str(loan["principal_wad"]),
                repaid_wad=str(loan["repaid_wad"]),
                repaid_display=constants.wad_to_decimal_str(loan["repaid_wad"]),
                status=loan["status"],
                borrowed_at_utc=loan["borrowed_at_utc"],
                closed_at_utc=loan["closed_at_utc"],
                borrow_tx_hash=loan["borrow_tx_hash"],
                repay_or_liquidate_tx_hash=loan["repay_or_liquidate_tx_hash"],
            )
            for loan in loans_by_id.values()
        ]
        total_borrowed = sum(int(loan.principal_wad) for loan in loan_records)
        total_repaid = sum(int(loan.repaid_wad) for loan in loan_records)
        repaid_count = sum(loan.status == "REPAID_ON_TIME" for loan in loan_records)
        active_count = sum(loan.status == "ACTIVE" for loan in loan_records)
        liquidation_count = sum(loan.status == "LIQUIDATED" for loan in loan_records)
        closed_loan_count = repaid_count + liquidation_count
        repayment_ratio = (
            (repaid_count * constants.BPS) // closed_loan_count
            if closed_loan_count
            else 0
        )
        score = self._credit_score(
            total_loans=len(loan_records),
            repaid_count=repaid_count,
            active_count=active_count,
            liquidation_count=liquidation_count,
            repayment_ratio_bps=repayment_ratio,
        )
        summary = CreditReportSummary(
            total_loans=len(loan_records),
            repaid_on_time_count=repaid_count,
            active_loans_count=active_count,
            liquidation_count=liquidation_count,
            total_borrowed_wad=str(total_borrowed),
            total_borrowed_display=constants.wad_to_decimal_str(total_borrowed),
            total_repaid_wad=str(total_repaid),
            total_repaid_display=constants.wad_to_decimal_str(total_repaid),
            current_debt_wad=str(current_debt_wad),
            current_debt_display=constants.wad_to_decimal_str(current_debt_wad),
            on_time_repayment_ratio_bps=repayment_ratio,
        )
        report = CreditReportDocument(
            generated_at_utc=generated_at,
            network=self.web3_service.network.name,
            chain_id=int(self.web3_service.chain_id),
            wallet_address=borrower,
            summary=summary,
            credit_score=score,
            loan_ids=[loan.loan_id for loan in loan_records],
            loans=loan_records,
        )
        payload = self._model_json_bytes(report)
        upload, acl, _ = self.gateway.upload_document(
            payload,
            document_type=DocumentType.CREDIT_REPORT,
            filename=f"credit_report_{borrower.lower()}.json",
            content_type="application/json",
            owner_wallet=borrower,
            visibility=DocumentVisibility.PRIVATE,
            extra_metadata={"network": self.web3_service.network.name},
        )
        if not acl.encrypted or not acl.ciphertext_sha256:
            raise CreditAuditIntegrityError(
                "Private credit report upload did not return encrypted metadata."
            )
        if acl.plaintext_sha256 != sha256_bytes(payload):
            raise CreditAuditIntegrityError(
                "Uploaded credit report metadata has an unexpected SHA-256."
            )
        self._save_metadata(acl)
        return {
            "cid": upload.cid,
            "gateway_url": upload.gateway_url,
            "plaintext_sha256": acl.plaintext_sha256,
            "encrypted_ipfs_sha256": acl.ciphertext_sha256,
            "wallet_address": borrower,
            "credit_score": report.credit_score.model_dump(mode="json"),
            "summary": report.summary.model_dump(mode="json"),
            "acl_metadata": acl.to_dict(),
        }

    def generate_monthly_audit_logs(
        self,
        *,
        from_block: int = 0,
        to_block: int | str = "latest",
        seed_simulated_months: int = 6,
    ) -> dict[str, Any]:
        """Aggregate monthly InterestRateUpdated events and upload public JSON and CSV."""
        if (
            isinstance(seed_simulated_months, bool)
            or not isinstance(seed_simulated_months, int)
            or seed_simulated_months < 0
        ):
            raise ValueError("seed_simulated_months must be a non-negative integer.")
        pool = self.web3_service.get_contract("LendingPool")
        rate_events = self._get_event_logs(
            pool,
            "InterestRateUpdated",
            from_block=from_block,
            to_block=to_block,
        )
        events_by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in rate_events:
            timestamp = int(event["args"]["timestamp"])
            period = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m")
            events_by_month[period].append(event)

        entries_by_period: dict[str, AuditLogEntry] = {}
        for period, month_events in events_by_month.items():
            event = max(month_events, key=self._event_sort_key)
            args = event["args"]
            supplied = int(args["totalSuppliedWad"])
            borrowed = int(args["totalBorrowedWad"])
            available = max(0, supplied - borrowed)
            borrow_apr = int(args["borrowAprBps"])
            supply_apr = int(args["supplyAprBps"])
            timestamp = int(args["timestamp"])
            entries_by_period[period] = AuditLogEntry(
                period=period,
                recorded_at_utc=self._iso_timestamp(timestamp),
                data_kind="ON_CHAIN",
                total_supplied_wad=str(supplied),
                total_supplied_display=constants.wad_to_decimal_str(supplied),
                total_borrowed_wad=str(borrowed),
                total_borrowed_display=constants.wad_to_decimal_str(borrowed),
                available_liquidity_wad=str(available),
                available_liquidity_display=constants.wad_to_decimal_str(available),
                utilization_bps=int(args["utilizationBps"]),
                utilization_percent=constants.apr_bps_to_percent(
                    int(args["utilizationBps"])
                ),
                borrow_apr_bps=borrow_apr,
                borrow_apr_percent=constants.apr_bps_to_percent(borrow_apr),
                borrow_apy_percent=constants.apr_bps_to_apy_percent(borrow_apr),
                supply_apr_bps=supply_apr,
                supply_apr_percent=constants.apr_bps_to_percent(supply_apr),
                supply_apy_percent=constants.apr_bps_to_apy_percent(supply_apr),
                event_tx_hash=self._tx_hash(event),
                notes="ON_CHAIN InterestRateUpdated snapshot; available liquidity derived as supplied minus borrowed.",
            )

        live_pool = self.web3_service.get_pool_info()
        live_rates = self.web3_service.get_interest_rate_snapshot()
        current_timestamp = int(live_rates["timestamp"])
        current_period = datetime.fromtimestamp(
            current_timestamp, timezone.utc
        ).strftime("%Y-%m")
        live_supplied = int(live_pool["total_supplied"]["wad"])
        live_borrowed = int(live_pool["total_borrowed"]["wad"])
        live_borrow_apr = int(live_rates["borrow_apr"]["bps"])
        live_supply_apr = int(live_rates["supply_apr"]["bps"])
        live_available = int(self.web3_service.get_available_liquidity()["wad"])
        entries_by_period[current_period] = AuditLogEntry(
            period=current_period,
            recorded_at_utc=self._iso_timestamp(current_timestamp),
            data_kind="ON_CHAIN",
            total_supplied_wad=str(live_supplied),
            total_supplied_display=constants.wad_to_decimal_str(live_supplied),
            total_borrowed_wad=str(live_borrowed),
            total_borrowed_display=constants.wad_to_decimal_str(live_borrowed),
            available_liquidity_wad=str(live_available),
            available_liquidity_display=constants.wad_to_decimal_str(live_available),
            utilization_bps=int(live_rates["utilization"]["bps"]),
            utilization_percent=float(live_rates["utilization"]["percent"]),
            borrow_apr_bps=live_borrow_apr,
            borrow_apr_percent=constants.apr_bps_to_percent(live_borrow_apr),
            borrow_apy_percent=float(
                live_rates["borrow_apy_reference"]["percent"]
            ),
            supply_apr_bps=live_supply_apr,
            supply_apr_percent=constants.apr_bps_to_percent(live_supply_apr),
            supply_apy_percent=float(
                live_rates["supply_apy_reference"]["percent"]
            ),
            event_tx_hash=None,
            notes="ON_CHAIN live Web3Service pool and interest-rate snapshot.",
        )

        simulated_entries = self._simulated_audit_entries(seed_simulated_months)
        for entry in simulated_entries:
            entries_by_period.setdefault(entry.period, entry)
        entries = [entries_by_period[key] for key in sorted(entries_by_period)]
        if not entries:
            raise ValueError(
                "No on-chain InterestRateUpdated events or simulated seed months are available."
            )

        registry_contracts = self.web3_service.registry.get("contracts", {})
        pool_address = registry_contracts.get("LendingPool", {}).get("address") or None
        audit_document = AuditLogsDocument(
            generated_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            network=self.web3_service.network.name,
            chain_id=int(self.web3_service.chain_id),
            lending_pool_address=pool_address,
            rate_model=AuditRateModelInfo(),
            entries=entries,
        )
        json_bytes = self._model_json_bytes(audit_document)
        csv_bytes = audit_logs_to_csv(audit_document).encode("utf-8")
        json_upload, json_acl, _ = self.gateway.upload_document(
            json_bytes,
            document_type=DocumentType.AUDIT_LOGS,
            filename="audit_logs.json",
            content_type="application/json",
            visibility=DocumentVisibility.PUBLIC,
        )
        csv_upload, csv_acl, _ = self.gateway.upload_document(
            csv_bytes,
            document_type=DocumentType.AUDIT_LOGS,
            filename="audit_logs.csv",
            content_type="text/csv",
            visibility=DocumentVisibility.PUBLIC,
        )
        if json_acl.encrypted or csv_acl.encrypted:
            raise CreditAuditIntegrityError("Public audit logs must not be encrypted.")
        if json_acl.plaintext_sha256 != sha256_bytes(json_bytes):
            raise CreditAuditIntegrityError("Audit JSON upload SHA-256 does not match.")
        if csv_acl.plaintext_sha256 != sha256_bytes(csv_bytes):
            raise CreditAuditIntegrityError("Audit CSV upload SHA-256 does not match.")
        self._save_metadata(json_acl)
        self._save_metadata(csv_acl)
        return {
            "document": audit_document,
            "entries": [entry.model_dump(mode="json") for entry in entries],
            "json": {
                "cid": json_upload.cid,
                "gateway_url": json_upload.gateway_url,
                "sha256": json_acl.plaintext_sha256,
                "acl_metadata": json_acl.to_dict(),
            },
            "csv": {
                "cid": csv_upload.cid,
                "gateway_url": csv_upload.gateway_url,
                "sha256": csv_acl.plaintext_sha256,
                "acl_metadata": csv_acl.to_dict(),
            },
        }

    def retrieve_credit_report(
        self, cid: str, context: AccessContext
    ) -> CreditReportDocument:
        """RBAC-check and decrypt a Credit Report, returning its validated Pydantic model."""
        result = self.retrieve_from_ipfs(cid, context)
        if result.document_type != DocumentType.CREDIT_REPORT:
            raise ValueError(f"CID {cid!r} is not a Credit Report.")
        report = CreditReportDocument.model_validate_json(result.content)
        if sha256_bytes(result.content) != result.plaintext_sha256:
            raise CreditAuditIntegrityError("Credit Report SHA-256 verification failed.")
        return report

    def retrieve_audit_logs(
        self, cid: str
    ) -> AuditLogsDocument | str:
        """Retrieve public audit JSON as its schema model or CSV as UTF-8 text."""
        result = self.retrieve_from_ipfs(cid, AccessContext.guest())
        if result.document_type != DocumentType.AUDIT_LOGS:
            raise ValueError(f"CID {cid!r} is not an Audit Logs document.")
        if result.content_type == "application/json":
            return AuditLogsDocument.model_validate_json(result.content)
        if result.content_type == "text/csv":
            return result.content.decode("utf-8")
        raise ValueError(f"Unsupported Audit Logs content type: {result.content_type!r}.")

    def retrieve_from_ipfs(
        self, cid: str, context: AccessContext | None = None
    ) -> AuthorizedDocumentResult:
        """Retrieve with stored ACL metadata; private docs require authorized context."""
        metadata = self._load_metadata().get(cid)
        result = self.gateway.retrieve_authorized_document(
            cid,
            context or AccessContext.guest(),
            metadata=metadata,
        )
        if sha256_bytes(result.content) != result.plaintext_sha256:
            raise CreditAuditIntegrityError("Retrieved IPFS document SHA-256 verification failed.")
        return result

    def _get_event_logs(
        self,
        pool: Any,
        event_name: str,
        *,
        from_block: int,
        to_block: int | str,
        filters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if from_block < 0:
            raise ValueError("from_block must be non-negative.")
        event = getattr(pool.events, event_name)()
        logs = event.get_logs(
            from_block=from_block,
            to_block=to_block,
            argument_filters=dict(filters or {}),
        )
        return [self._normalize_event_log(log) for log in logs]

    @staticmethod
    def _normalize_event_log(log: Any) -> dict[str, Any]:
        if isinstance(log, Mapping):
            raw = dict(log)
            args = raw.get("args")
        else:
            raw = {
                key: getattr(log, key)
                for key in ("blockNumber", "logIndex", "transactionHash")
                if hasattr(log, key)
            }
            args = getattr(log, "args", None)
        if args is None:
            raise ValueError("Decoded LendingPool event log is missing args.")
        raw["args"] = dict(args)
        return raw

    @staticmethod
    def _event_sort_key(event: Mapping[str, Any]) -> tuple[int, int]:
        return (
            int(event.get("blockNumber", event.get("block_number", 0))),
            int(event.get("logIndex", event.get("log_index", 0))),
        )

    @staticmethod
    def _tx_hash(event: Mapping[str, Any]) -> str:
        value = event.get("transactionHash", event.get("transaction_hash"))
        if value is None:
            return ""
        if isinstance(value, str):
            return value if value.startswith("0x") else f"0x{value}"
        from web3 import Web3

        return Web3.to_hex(value)

    @staticmethod
    def _iso_timestamp(timestamp: int) -> str:
        return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _latest_open_loan(
        loans_by_id: Mapping[str, dict[str, Any]], active_loan_ids: list[str]
    ) -> dict[str, Any] | None:
        active = [loans_by_id[loan_id] for loan_id in active_loan_ids if loan_id in loans_by_id]
        if not active:
            return None
        return max(active, key=lambda loan: loan["sort_key"])

    @staticmethod
    def _credit_score(
        *,
        total_loans: int,
        repaid_count: int,
        active_count: int,
        liquidation_count: int,
        repayment_ratio_bps: int,
    ) -> CreditScoreInfo:
        if total_loans == 0:
            score = 600
            rationale = "No historical LoanBorrowed events were found; neutral starter score."
        else:
            score = (
                550
                + (200 * repayment_ratio_bps // constants.BPS)
                + min(repaid_count, 5) * 10
                - min(liquidation_count, 3) * 120
                - min(active_count, 5) * 10
            )
            score = max(300, min(850, score))
            rationale = (
                f"Derived from {total_loans} on-chain loans: {repaid_count} fully repaid, "
                f"{active_count} active, {liquidation_count} liquidated; "
                f"repayment ratio {repayment_ratio_bps} BPS. Scoring model is "
                "deterministic and informational, not a financial decision."
            )
        if score < 580:
            tier = "POOR"
        elif score < 670:
            tier = "FAIR"
        elif score < 740:
            tier = "GOOD"
        elif score < 800:
            tier = "VERY_GOOD"
        else:
            tier = "EXCELLENT"
        return CreditScoreInfo(score=score, tier=tier, rationale=rationale)

    @staticmethod
    def _model_json_bytes(model: Any) -> bytes:
        return json.dumps(
            model.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def _simulated_audit_entries(month_count: int) -> list[AuditLogEntry]:
        if month_count == 0:
            return []
        samples = build_sample_audit_logs().entries
        return CreditAndAuditIPFSService._extend_simulated_entries(
            samples, month_count
        )

    @staticmethod
    def _extend_simulated_entries(
        samples: list[AuditLogEntry], month_count: int
    ) -> list[AuditLogEntry]:
        from calendar import monthrange
        from datetime import date

        now = datetime.now(timezone.utc)
        year, month = now.year, now.month
        periods: list[tuple[int, int]] = []
        for _ in range(month_count):
            periods.append((year, month))
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        periods.reverse()
        entries: list[AuditLogEntry] = []
        for index, (year, month) in enumerate(periods):
            sample = samples[index % len(samples)]
            timestamp = datetime(
                year,
                month,
                monthrange(year, month)[1],
                23,
                59,
                59,
                tzinfo=timezone.utc,
            )
            entries.append(
                sample.model_copy(
                    update={
                        "period": f"{year:04d}-{month:02d}",
                        "recorded_at_utc": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "notes": f"SIMULATED seed snapshot: {sample.notes}",
                    }
                )
            )
        return entries

    def _agreement_bindings(self) -> dict[str, dict[str, Any]]:
        if self.agreement_generator is None:
            return {}
        path = self.agreement_generator.binding_store_path
        if not path.exists():
            return {}
        try:
            index = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CreditAuditIndexError(
                f"Cannot load Q03 agreement bindings: {path}"
            ) from exc
        bindings = index.get("loan_tx_bindings", [])
        if not isinstance(bindings, list):
            raise CreditAuditIndexError("Q03 agreement binding index has an invalid structure.")
        return {
            str(record["tx_hash"]).lower(): record
            for record in bindings
            if isinstance(record, Mapping) and record.get("tx_hash")
        }

    def _load_metadata(self) -> dict[str, DocumentAccessMetadata]:
        if not self.metadata_store_path.exists():
            return {}
        try:
            root = json.loads(self.metadata_store_path.read_text(encoding="utf-8"))
            raw_metadata = root["acl_metadata"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise CreditAuditIndexError(
                f"Cannot load Credit Report/Audit Logs ACL index: {self.metadata_store_path}"
            ) from exc
        if not isinstance(raw_metadata, dict):
            raise CreditAuditIndexError("Credit Report/Audit Logs ACL index has invalid ACL metadata.")
        return {
            cid: DocumentAccessMetadata(
                cid=str(raw["cid"]),
                document_type=DocumentType(raw["document_type"]),
                visibility=DocumentVisibility(raw["visibility"]),
                owner_wallet=raw.get("owner_wallet"),
                encrypted=bool(raw["encrypted"]),
                content_type=str(raw["content_type"]),
                filename=str(raw["filename"]),
                plaintext_sha256=str(raw["plaintext_sha256"]),
                ciphertext_sha256=raw.get("ciphertext_sha256"),
                key_id=raw.get("key_id"),
            )
            for cid, raw in raw_metadata.items()
        }

    def _save_metadata(self, metadata: DocumentAccessMetadata) -> None:
        existing = {
            cid: item.to_dict() for cid, item in self._load_metadata().items()
        }
        existing[metadata.cid] = metadata.to_dict()
        self.metadata_store_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.metadata_store_path.parent,
                prefix=f"{self.metadata_store_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as output:
                temporary_path = Path(output.name)
                json.dump(
                    {"schema_version": "1.0", "acl_metadata": existing},
                    output,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            temporary_path.replace(self.metadata_store_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
