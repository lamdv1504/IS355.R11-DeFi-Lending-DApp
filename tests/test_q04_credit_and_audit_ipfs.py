"""Q04 tests for on-chain credit aggregation and public/private IPFS documents."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from backend.config import constants
from backend.services.credit_and_audit_ipfs import CreditAndAuditIPFSService
from src.ipfs.cid_utils import sha256_bytes
from src.ipfs.encryption import DocumentEncryptor
from src.ipfs.ipfs_client import IPFSClient, IPFSConfig
from src.ipfs.rbac import (
    AccessContext,
    AccessDeniedError,
    AuthorizedIPFSGateway,
    Role,
)

BORROWER = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"
OTHER_BORROWER = "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc"
LENDER = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
ADMIN = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


def _event(
    args: dict[str, Any],
    *,
    block: int,
    log_index: int,
    tx_hash: str,
) -> dict[str, Any]:
    return {
        "args": args,
        "blockNumber": block,
        "logIndex": log_index,
        "transactionHash": tx_hash,
    }


class _FakeEvent:
    def __init__(self, events: dict[str, list[dict[str, Any]]], name: str) -> None:
        self.events = events
        self.name = name

    def get_logs(
        self,
        *,
        from_block: int,
        to_block: int | str,
        argument_filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            item
            for item in self.events.get(self.name, [])
            if item["blockNumber"] >= from_block
            and all(item["args"].get(key) == value for key, value in argument_filters.items())
        ]


class _FakeEvents:
    def __init__(self, events: dict[str, list[dict[str, Any]]]) -> None:
        self.events = events

    def __getattr__(self, name: str) -> Any:
        return lambda: _FakeEvent(self.events, name)


class _FakeWeb3Service:
    def __init__(self, events: dict[str, list[dict[str, Any]]]) -> None:
        self.events = events
        self.network = SimpleNamespace(name="local")
        self.chain_id = 31337
        self.registry = {
            "contracts": {
                "LendingPool": {
                    "address": "0x0000000000000000000000000000000000000010"
                }
            }
        }

    def _checksum_address(self, address: str, field_name: str) -> str:
        if len(address) != 42 or not address.startswith("0x"):
            raise ValueError(f"Invalid {field_name} address")
        return address

    def get_contract(self, name: str) -> Any:
        assert name == "LendingPool"
        return SimpleNamespace(events=_FakeEvents(self.events))

    def get_borrower_risk(self, borrower: str) -> dict[str, Any]:
        return {
            "collateral_value": {"wad": str(1_000 * constants.WAD)},
            "total_debt": {"wad": str(200 * constants.WAD)},
            "health_factor_wad": str(constants.WAD * 4),
        }

    def get_pool_info(self) -> dict[str, Any]:
        return {
            "total_supplied": {"wad": str(1_000 * constants.WAD)},
            "total_borrowed": {"wad": str(200 * constants.WAD)},
        }

    def get_interest_rate_snapshot(self) -> dict[str, Any]:
        return {
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
            "utilization": {"bps": 2_000, "percent": 20.0},
            "borrow_apr": {"bps": 700, "percent": 7.0},
            "supply_apr": {"bps": 140, "percent": 1.4},
            "borrow_apy_reference": {"bps": 725, "percent": 7.2501},
            "supply_apy_reference": {"bps": 140, "percent": 1.4098},
        }

    def get_available_liquidity(self) -> dict[str, str]:
        return {"wad": str(800 * constants.WAD)}


@pytest.fixture
def credit_audit_service(tmp_path: Path) -> CreditAndAuditIPFSService:
    borrowed_at = int(datetime(2026, 8, 15, tzinfo=timezone.utc).timestamp())
    repaid_at = int(datetime(2026, 10, 2, tzinfo=timezone.utc).timestamp())
    rate_at = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp())
    events = {
        "CollateralDeposited": [
            _event(
                {
                    "borrower": BORROWER,
                    "isNFT": False,
                    "assetIdOrAmount": 1_000 * constants.WAD,
                    "receiptTokenId": 4,
                    "valuationWad": 1_000 * constants.WAD,
                    "timestamp": borrowed_at,
                },
                block=1,
                log_index=0,
                tx_hash="0x" + "01" * 32,
            )
        ],
        "LoanBorrowed": [
            _event(
                {
                    "borrower": BORROWER,
                    "amountWad": 500 * constants.WAD,
                    "totalPrincipalWad": 500 * constants.WAD,
                    "borrowAprBps": 1_000,
                    "agreementCid": "bafy-agreement-from-event",
                    "timestamp": borrowed_at,
                },
                block=2,
                log_index=0,
                tx_hash="0x" + "02" * 32,
            ),
            _event(
                {
                    "borrower": BORROWER,
                    "amountWad": 200 * constants.WAD,
                    "totalPrincipalWad": 200 * constants.WAD,
                    "borrowAprBps": 700,
                    "agreementCid": "",
                    "timestamp": int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp()),
                },
                block=4,
                log_index=0,
                tx_hash="0x" + "04" * 32,
            ),
        ],
        "LoanRepaid": [
            _event(
                {
                    "borrower": BORROWER,
                    "amountPaidWad": 510 * constants.WAD,
                    "interestPaidWad": 10 * constants.WAD,
                    "principalPaidWad": 500 * constants.WAD,
                    "remainingDebtWad": 0,
                    "timestamp": repaid_at,
                },
                block=3,
                log_index=0,
                tx_hash="0x" + "03" * 32,
            )
        ],
        "LoanLiquidated": [],
        "InterestRateUpdated": [
            _event(
                {
                    "timestamp": rate_at,
                    "borrowAprBps": 1_000,
                    "supplyAprBps": 500,
                    "utilizationBps": 5_000,
                    "totalSuppliedWad": 1_000 * constants.WAD,
                    "totalBorrowedWad": 500 * constants.WAD,
                },
                block=5,
                log_index=0,
                tx_hash="0x" + "05" * 32,
            )
        ],
    }
    ipfs = IPFSClient(
        IPFSConfig(provider="local_store", local_store_dir=tmp_path / "ipfs")
    )
    gateway = AuthorizedIPFSGateway(
        ipfs_client=ipfs,
        encryptor=DocumentEncryptor.from_hex_key("22" * 32),
    )
    return CreditAndAuditIPFSService(
        _FakeWeb3Service(events),
        gateway=gateway,
        metadata_store_path=tmp_path / "credit-audit-index.json",
    )


def test_credit_report_aggregates_events_scores_and_encrypts_private_json(
    credit_audit_service: CreditAndAuditIPFSService,
) -> None:
    result = credit_audit_service.generate_credit_report(BORROWER)

    assert 300 <= result["credit_score"]["score"] <= 850
    assert result["credit_score"]["tier"] == "VERY_GOOD"
    assert result["summary"]["total_loans"] == 2
    assert result["summary"]["repaid_on_time_count"] == 1
    assert result["summary"]["active_loans_count"] == 1
    assert result["summary"]["current_debt_wad"] == str(200 * constants.WAD)
    assert result["acl_metadata"]["encrypted"] is True
    assert result["acl_metadata"]["visibility"] == "PRIVATE"

    raw = credit_audit_service.gateway.retrieve_raw_by_cid(result["cid"])
    envelope = json.loads(raw.content.decode("utf-8"))
    assert envelope["algorithm"] == "AES-256-GCM"
    assert BORROWER.encode("ascii") not in raw.content
    assert b"bafy-agreement-from-event" not in raw.content

    owner_context = AccessContext.for_wallet(BORROWER, {Role.BORROWER})
    report = credit_audit_service.retrieve_credit_report(result["cid"], owner_context)
    assert report.wallet_address == BORROWER
    assert report.data_kind == "ON_CHAIN"
    assert len(report.loans) == 2
    assert report.loans[0].agreement_cid == "bafy-agreement-from-event"
    assert report.loans[0].status == "REPAID_ON_TIME"
    assert report.loans[1].status == "ACTIVE"


def test_credit_report_private_rbac_returns_401_403_and_200(
    credit_audit_service: CreditAndAuditIPFSService,
) -> None:
    result = credit_audit_service.generate_credit_report(BORROWER)
    for context, expected_status in (
        (AccessContext.guest(), 401),
        (AccessContext.for_wallet(LENDER, {Role.LENDER}), 403),
        (AccessContext.for_wallet(OTHER_BORROWER, {Role.BORROWER}), 403),
    ):
        with pytest.raises(AccessDeniedError) as error:
            credit_audit_service.retrieve_credit_report(result["cid"], context)
        assert error.value.http_status == expected_status

    admin = AccessContext.for_wallet(ADMIN, {Role.ADMIN})
    assert credit_audit_service.retrieve_credit_report(result["cid"], admin).wallet_address == BORROWER


def test_credit_report_score_penalizes_liquidation_events(
    tmp_path: Path,
) -> None:
    event_time = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    events = {
        "CollateralDeposited": [],
        "LoanBorrowed": [
            _event(
                {
                    "borrower": BORROWER,
                    "amountWad": 100 * constants.WAD,
                    "totalPrincipalWad": 100 * constants.WAD,
                    "borrowAprBps": 700,
                    "agreementCid": "",
                    "timestamp": event_time,
                },
                block=1,
                log_index=0,
                tx_hash="0x" + "11" * 32,
            )
        ],
        "LoanRepaid": [],
        "LoanLiquidated": [
            _event(
                {
                    "borrower": BORROWER,
                    "liquidator": LENDER,
                    "debtCoveredWad": 100 * constants.WAD,
                    "collateralSeizedWad": 105 * constants.WAD,
                    "healthFactorBeforeWad": constants.WAD - 1,
                    "timestamp": event_time + 1,
                },
                block=2,
                log_index=0,
                tx_hash="0x" + "12" * 32,
            )
        ],
    }
    gateway = AuthorizedIPFSGateway(
        IPFSClient(IPFSConfig(provider="local_store", local_store_dir=tmp_path / "ipfs")),
        DocumentEncryptor.from_hex_key("33" * 32),
    )
    service = CreditAndAuditIPFSService(
        _FakeWeb3Service(events),
        gateway=gateway,
        metadata_store_path=tmp_path / "metadata.json",
    )

    report = service.generate_credit_report(BORROWER)

    assert report["credit_score"]["score"] == 430
    assert report["credit_score"]["tier"] == "POOR"
    assert report["summary"]["liquidation_count"] == 1


def test_credit_report_uses_q03_binding_when_borrow_event_cid_is_empty(
    credit_audit_service: CreditAndAuditIPFSService,
    tmp_path: Path,
) -> None:
    binding_path = tmp_path / "agreement-bindings.json"
    binding_path.write_text(
        json.dumps(
            {
                "loan_tx_bindings": [
                    {
                        "tx_hash": "0x" + "04" * 32,
                        "agreement_cid": "bafy-q03-index-binding",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    credit_audit_service.agreement_generator = SimpleNamespace(
        binding_store_path=binding_path
    )

    result = credit_audit_service.generate_credit_report(BORROWER)
    report = credit_audit_service.retrieve_credit_report(
        result["cid"], AccessContext.for_wallet(BORROWER, {Role.BORROWER})
    )

    assert report.loans[1].agreement_cid == "bafy-q03-index-binding"


def test_monthly_audit_uploads_json_and_csv_with_simulated_and_onchain_rows(
    credit_audit_service: CreditAndAuditIPFSService,
) -> None:
    result = credit_audit_service.generate_monthly_audit_logs()

    assert result["json"]["cid"] != result["csv"]["cid"]
    assert result["json"]["acl_metadata"]["visibility"] == "PUBLIC"
    assert result["json"]["acl_metadata"]["encrypted"] is False
    assert result["csv"]["acl_metadata"]["encrypted"] is False
    assert all(not row["contains_pii"] for row in [result["document"].model_dump()])
    rows = result["entries"]
    assert any(row["data_kind"] == "SIMULATED" for row in rows)
    assert any(row["data_kind"] == "ON_CHAIN" for row in rows)
    assert any(row["period"] == "2026-08" and row["event_tx_hash"] for row in rows)
    assert all("borrower" not in row and "wallet" not in row for row in rows)

    json_document = credit_audit_service.retrieve_audit_logs(result["json"]["cid"])
    csv_document = credit_audit_service.retrieve_audit_logs(result["csv"]["cid"])
    assert json_document.contains_pii is False
    assert len(json_document.entries) == len(rows)
    assert csv_document.startswith("period,recorded_at_utc,data_kind,")
    assert "SIMULATED" in csv_document
    assert "ON_CHAIN" in csv_document

    raw_json = credit_audit_service.gateway.retrieve_raw_by_cid(result["json"]["cid"])
    raw_csv = credit_audit_service.gateway.retrieve_raw_by_cid(result["csv"]["cid"])
    assert sha256_bytes(raw_json.content) == result["json"]["sha256"]
    assert sha256_bytes(raw_csv.content) == result["csv"]["sha256"]


def test_audit_logs_are_publicly_retrievable_and_persisted_metadata_survives_restart(
    credit_audit_service: CreditAndAuditIPFSService,
) -> None:
    result = credit_audit_service.generate_monthly_audit_logs(seed_simulated_months=2)
    guest_result = credit_audit_service.retrieve_from_ipfs(result["json"]["cid"])
    assert guest_result.decision.http_status == 200
    assert guest_result.plaintext_sha256 == result["json"]["sha256"]

    restarted = CreditAndAuditIPFSService(
        credit_audit_service.web3_service,
        gateway=credit_audit_service.gateway,
        metadata_store_path=credit_audit_service.metadata_store_path,
    )
    assert restarted.retrieve_audit_logs(result["json"]["cid"]).contains_pii is False
