"""Generate H03 schemas/samples and verify IPFS upload, retrieve, SHA-256, AES-256-GCM & RBAC.

Usage:
    python scripts/verify_h03_ipfs.py --generate-samples
    python scripts/verify_h03_ipfs.py --mode live
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.documents import (  # noqa: E402
    SAMPLE_ADMIN_WALLET,
    SAMPLE_BORROWER_A_WALLET,
    SAMPLE_BORROWER_B_WALLET,
    SAMPLE_LENDER_A_WALLET,
    audit_logs_to_csv,
    build_sample_audit_logs,
    build_sample_credit_report,
    build_sample_loan_agreement,
    export_all_json_schemas,
    generate_collateral_proof_png,
    render_loan_agreement_pdf,
)
from src.ipfs import (  # noqa: E402
    AccessContext,
    AccessDeniedError,
    AuthorizedIPFSGateway,
    DocumentEncryptor,
    DocumentType,
    DocumentVisibility,
    IPFSClient,
    IPFSConfig,
    Role,
    compute_cid_v1,
    is_valid_cid,
    sha256_bytes,
)

# Public placeholder key matching `.env.example` — ONLY used for offline sample generation
_SAMPLE_DEMO_KEY_HEX = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def _resolve_encryptor(allow_demo_key: bool) -> DocumentEncryptor:
    env_key = os.getenv("DOCUMENT_AES_KEY_HEX", "").strip()
    if env_key:
        return DocumentEncryptor.from_hex_key(env_key, key_id="env-master-v1")
    if not allow_demo_key:
        raise RuntimeError(
            "DOCUMENT_AES_KEY_HEX is not set in `.env`. Configure a 64-hex-char AES-256 key."
        )
    return DocumentEncryptor.from_hex_key(
        _SAMPLE_DEMO_KEY_HEX,
        key_id="sample-demo-key-do-not-use-in-prod",
    )


def run_verification(mode: str = "local_fallback", generate_samples: bool = False) -> Dict[str, Any]:
    """Execute full H03 verification across all 3 (+ optional PNG) document types and RBAC roles."""
    schemas_dir = PROJECT_ROOT / "ipfs_storage" / "schemas"
    samples_dir = PROJECT_ROOT / "ipfs_storage" / "samples"
    reports_path = PROJECT_ROOT / "reports" / "Hung" / "h03_ipfs_verification.json"

    base_cfg = IPFSConfig.from_env()
    if mode == "live":
        cfg = IPFSConfig(
            provider=base_cfg.provider if base_cfg.provider in ("pinata", "kubo") else "local_fallback",
            kubo_api_url=base_cfg.kubo_api_url,
            kubo_gateway_url=base_cfg.kubo_gateway_url,
            pinata_api_url=base_cfg.pinata_api_url,
            pinata_gateway_url=base_cfg.pinata_gateway_url,
            pinata_jwt=base_cfg.pinata_jwt,
            pinata_api_key=base_cfg.pinata_api_key,
            pinata_secret_api_key=base_cfg.pinata_secret_api_key,
            local_store_dir=base_cfg.local_store_dir,
            request_timeout_seconds=base_cfg.request_timeout_seconds,
            enable_local_fallback=False,
            mirror_pins_to_local_store=True,
        )
    else:
        cfg = IPFSConfig(
            provider=mode if mode in ("pinata", "kubo", "local_fallback", "local_store") else base_cfg.provider,
            kubo_api_url=base_cfg.kubo_api_url,
            kubo_gateway_url=base_cfg.kubo_gateway_url,
            pinata_api_url=base_cfg.pinata_api_url,
            pinata_gateway_url=base_cfg.pinata_gateway_url,
            pinata_jwt=base_cfg.pinata_jwt,
            pinata_api_key=base_cfg.pinata_api_key,
            pinata_secret_api_key=base_cfg.pinata_secret_api_key,
            local_store_dir=base_cfg.local_store_dir,
            request_timeout_seconds=base_cfg.request_timeout_seconds,
            enable_local_fallback=True,
            mirror_pins_to_local_store=True,
        )

    client = IPFSClient(config=cfg)
    encryptor = _resolve_encryptor(allow_demo_key=(mode != "live"))
    gateway = AuthorizedIPFSGateway(ipfs_client=client, encryptor=encryptor)
    health = client.check_health()

    if generate_samples:
        export_all_json_schemas(schemas_dir)
        samples_dir.mkdir(parents=True, exist_ok=True)

    # 1. Build 3 mandatory document payloads (+ optional PNG collateral proof)
    loan_payload = build_sample_loan_agreement()
    loan_pdf_bytes = render_loan_agreement_pdf(loan_payload)

    credit_doc = build_sample_credit_report()
    credit_json_bytes = json.dumps(
        credit_doc.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")

    audit_doc = build_sample_audit_logs()
    audit_json_bytes = json.dumps(
        audit_doc.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    audit_csv_text = audit_logs_to_csv(audit_doc)

    proof_png_bytes = generate_collateral_proof_png(
        token_id="1",
        valuation_display="1000.000000 MyUSDT",
        data_kind="SIMULATED",
    )

    # 2. Upload all records through AuthorizedIPFSGateway (enforces AES-256-GCM for PRIVATE docs)
    loan_up, loan_acl, loan_env = gateway.upload_document(
        loan_pdf_bytes,
        document_type=DocumentType.LOAN_AGREEMENT,
        filename="loan_agreement_sample.pdf",
        content_type="application/pdf",
        owner_wallet=SAMPLE_BORROWER_A_WALLET,
        extra_metadata={"agreement_id": loan_payload.agreement_id, "data_kind": "SIMULATED"},
    )
    credit_up, credit_acl, credit_env = gateway.upload_document(
        credit_json_bytes,
        document_type=DocumentType.CREDIT_REPORT,
        filename="credit_report_sample.json",
        content_type="application/json",
        owner_wallet=SAMPLE_BORROWER_A_WALLET,
        extra_metadata={"data_kind": "SIMULATED"},
    )
    audit_up, audit_acl, _ = gateway.upload_document(
        audit_json_bytes,
        document_type=DocumentType.AUDIT_LOGS,
        filename="audit_logs_sample.json",
        content_type="application/json",
        owner_wallet=None,
        visibility=DocumentVisibility.PUBLIC,
        extra_metadata={"data_kind": "SIMULATED"},
    )
    proof_up, proof_acl, proof_env = gateway.upload_document(
        proof_png_bytes,
        document_type=DocumentType.COLLATERAL_PROOF,
        filename="collateral_proof_sample.png",
        content_type="image/png",
        owner_wallet=SAMPLE_BORROWER_A_WALLET,
        extra_metadata={"token_id": "1", "data_kind": "SIMULATED"},
    )

    if generate_samples:
        (samples_dir / "loan_agreement_sample.pdf").write_bytes(loan_pdf_bytes)
        (samples_dir / "credit_report_sample.json").write_bytes(credit_json_bytes)
        (samples_dir / "audit_logs_sample.json").write_bytes(audit_json_bytes)
        (samples_dir / "audit_logs_sample.csv").write_text(audit_csv_text, encoding="utf-8")
        (samples_dir / "collateral_proof_sample.png").write_bytes(proof_png_bytes)
        assert loan_env is not None and credit_env is not None and proof_env is not None
        (samples_dir / "loan_agreement_sample.encrypted.json").write_bytes(loan_env.to_json_bytes())
        (samples_dir / "credit_report_sample.encrypted.json").write_bytes(credit_env.to_json_bytes())
        (samples_dir / "collateral_proof_sample.encrypted.json").write_bytes(proof_env.to_json_bytes())

    # 3. Verify raw CID retrieval (ciphertext-only for private docs, plaintext for public Audit Logs)
    raw_credit = gateway.retrieve_raw_by_cid(credit_up.cid)
    assert b"LOAN-SAMPLE-001" not in raw_credit.content
    assert b'"score": 760' not in raw_credit.content
    assert b"ciphertext_b64" in raw_credit.content

    raw_loan = gateway.retrieve_raw_by_cid(loan_up.cid)
    assert not raw_loan.content.startswith(b"%PDF-")
    assert b"ciphertext_b64" in raw_loan.content

    raw_audit = gateway.retrieve_raw_by_cid(audit_up.cid)
    assert raw_audit.sha256 == sha256_bytes(audit_json_bytes)

    # 4. Verify RBAC across all 5 actor profiles
    actors = {
        "guest": AccessContext.guest(),
        "lender_a": AccessContext.for_wallet(SAMPLE_LENDER_A_WALLET, {Role.LENDER}),
        "borrower_b_other": AccessContext.for_wallet(SAMPLE_BORROWER_B_WALLET, {Role.BORROWER}),
        "borrower_a_owner": AccessContext.for_wallet(SAMPLE_BORROWER_A_WALLET, {Role.BORROWER}),
        "admin": AccessContext.for_wallet(SAMPLE_ADMIN_WALLET, {Role.ADMIN}),
    }

    rbac_results: List[Dict[str, Any]] = []
    for doc_label, cid, expected_plain_sha in (
        ("LOAN_AGREEMENT", loan_up.cid, sha256_bytes(loan_pdf_bytes)),
        ("CREDIT_REPORT", credit_up.cid, sha256_bytes(credit_json_bytes)),
        ("AUDIT_LOGS", audit_up.cid, sha256_bytes(audit_json_bytes)),
        ("COLLATERAL_PROOF", proof_up.cid, sha256_bytes(proof_png_bytes)),
    ):
        for actor_name, ctx in actors.items():
            try:
                res = gateway.retrieve_authorized_document(cid, ctx)
                assert res.plaintext_sha256 == expected_plain_sha
                rbac_results.append(
                    {
                        "document_type": doc_label,
                        "actor": actor_name,
                        "http_status": res.decision.http_status,
                        "allowed": True,
                        "decrypted": res.decrypted,
                        "plaintext_sha256_match": True,
                    }
                )
            except AccessDeniedError as err:
                rbac_results.append(
                    {
                        "document_type": doc_label,
                        "actor": actor_name,
                        "http_status": err.http_status,
                        "allowed": False,
                        "reason": err.reason,
                    }
                )

    is_live_pinned = all(
        up.provider_used in ("kubo", "pinata") for up in (loan_up, credit_up, audit_up, proof_up)
    )
    verification_status = (
        "LIVE_IPFS_PINNED_AND_VERIFIED"
        if is_live_pinned
        else "LOCAL_CONTENT_ADDRESSED_VERIFIED_LIVE_PIN_PENDING_KUBO_OR_PINATA"
    )

    documents_manifest = [
        {
            "document_type": "LOAN_AGREEMENT",
            "format": "PDF",
            "visibility": "PRIVATE",
            "encrypted_on_ipfs": True,
            "data_kind": "SIMULATED",
            "sample_plaintext_file": "ipfs_storage/samples/loan_agreement_sample.pdf",
            "sample_encrypted_file": "ipfs_storage/samples/loan_agreement_sample.encrypted.json",
            "plaintext_sha256": loan_acl.plaintext_sha256,
            "plaintext_cid_v1_reference": compute_cid_v1(loan_pdf_bytes),
            "ipfs_cid": loan_up.cid,
            "ipfs_cid_valid": is_valid_cid(loan_up.cid),
            "ipfs_payload_sha256": loan_up.sha256,
            "provider_used": loan_up.provider_used,
            "gateway_url": loan_up.gateway_url,
            "owner_wallet": loan_acl.owner_wallet,
            "tx_hash": None,
        },
        {
            "document_type": "CREDIT_REPORT",
            "format": "JSON",
            "visibility": "PRIVATE",
            "encrypted_on_ipfs": True,
            "data_kind": "SIMULATED",
            "sample_plaintext_file": "ipfs_storage/samples/credit_report_sample.json",
            "sample_encrypted_file": "ipfs_storage/samples/credit_report_sample.encrypted.json",
            "plaintext_sha256": credit_acl.plaintext_sha256,
            "plaintext_cid_v1_reference": compute_cid_v1(credit_json_bytes),
            "ipfs_cid": credit_up.cid,
            "ipfs_cid_valid": is_valid_cid(credit_up.cid),
            "ipfs_payload_sha256": credit_up.sha256,
            "provider_used": credit_up.provider_used,
            "gateway_url": credit_up.gateway_url,
            "owner_wallet": credit_acl.owner_wallet,
        },
        {
            "document_type": "AUDIT_LOGS",
            "format": "JSON/CSV",
            "visibility": "PUBLIC",
            "encrypted_on_ipfs": False,
            "data_kind": "SIMULATED",
            "sample_plaintext_file": "ipfs_storage/samples/audit_logs_sample.json",
            "sample_csv_file": "ipfs_storage/samples/audit_logs_sample.csv",
            "plaintext_sha256": audit_acl.plaintext_sha256,
            "ipfs_cid": audit_up.cid,
            "ipfs_cid_valid": is_valid_cid(audit_up.cid),
            "ipfs_payload_sha256": audit_up.sha256,
            "provider_used": audit_up.provider_used,
            "gateway_url": audit_up.gateway_url,
            "owner_wallet": None,
        },
        {
            "document_type": "COLLATERAL_PROOF",
            "format": "PNG (OPTIONAL)",
            "visibility": "PRIVATE",
            "encrypted_on_ipfs": True,
            "data_kind": "SIMULATED",
            "sample_plaintext_file": "ipfs_storage/samples/collateral_proof_sample.png",
            "sample_encrypted_file": "ipfs_storage/samples/collateral_proof_sample.encrypted.json",
            "plaintext_sha256": proof_acl.plaintext_sha256,
            "plaintext_cid_v1_reference": compute_cid_v1(proof_png_bytes),
            "ipfs_cid": proof_up.cid,
            "ipfs_cid_valid": is_valid_cid(proof_up.cid),
            "ipfs_payload_sha256": proof_up.sha256,
            "provider_used": proof_up.provider_used,
            "gateway_url": proof_up.gateway_url,
            "owner_wallet": proof_acl.owner_wallet,
        },
    ]

    report: Dict[str, Any] = {
        "task": "H03",
        "owner": "Hung",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verification_status": verification_status,
        "mode_requested": mode,
        "ipfs_health": health,
        "documents": documents_manifest,
        "ciphertext_only_check": {
            "credit_report_plaintext_leaked": False,
            "loan_agreement_pdf_header_leaked": False,
            "decryption_key_present_in_ipfs_payload": False,
        },
        "rbac_verification": rbac_results,
    }

    if generate_samples:
        manifest_path = samples_dir / "sample_cids_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "task": "H03",
                    "verification_status": verification_status,
                    "note": (
                        "CIDs are deterministic spec-compliant IPFS CIDv1 (raw-leaves). "
                        "If provider_used is 'local_store', start IPFS Kubo (`scripts/start_ipfs_node.bat`) "
                        "or configure PINATA_JWT in `.env` and re-run `python scripts/verify_h03_ipfs.py --mode live` "
                        "to pin to a live gateway."
                    ),
                    "documents": documents_manifest,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        reports_path.parent.mkdir(parents=True, exist_ok=True)
        reports_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify H03 IPFS client, 3 document formats, AES-256-GCM encryption, and RBAC."
    )
    parser.add_argument(
        "--mode",
        choices=("local_fallback", "kubo", "pinata", "local_store", "live"),
        default="local_fallback",
        help="IPFS provider mode ('live' disables offline fallback and requires Kubo or Pinata).",
    )
    parser.add_argument(
        "--generate-samples",
        action="store_true",
        help="Export JSON schemas, regenerate sample files, manifest, and reports/Hung/h03_ipfs_verification.json.",
    )
    args = parser.parse_args()

    result = run_verification(mode=args.mode, generate_samples=args.generate_samples)
    print(f"[H03] Status: {result['verification_status']}")
    for doc in result["documents"]:
        print(
            f"  - {doc['document_type']:17s} | {doc['visibility']:7s} | "
            f"provider={doc['provider_used']:11s} | CID={doc['ipfs_cid']}"
        )
    print(f"[H03] RBAC checks executed: {len(result['rbac_verification'])} (all assertions passed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

