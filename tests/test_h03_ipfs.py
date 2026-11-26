"""Comprehensive unit & HTTP-integration tests for H03: IPFS Client, 3 Document Types, AES-256-GCM & RBAC."""

from __future__ import annotations

import base64
import csv
import io
import json
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from requests.adapters import BaseAdapter

from backend.config import constants as c
from src.documents import (
    SAMPLE_ADMIN_WALLET,
    SAMPLE_BORROWER_A_WALLET,
    SAMPLE_BORROWER_B_WALLET,
    SAMPLE_LENDER_A_WALLET,
    AuditLogsDocument,
    CreditReportDocument,
    LoanAgreementPayload,
    LoanTxBindingRecord,
    audit_logs_to_csv,
    build_sample_audit_logs,
    build_sample_credit_report,
    build_sample_loan_agreement,
    generate_collateral_proof_png,
    render_loan_agreement_pdf,
)
from src.ipfs import (
    AccessAction,
    AccessContext,
    AccessDeniedError,
    AuthorizedIPFSGateway,
    DecryptionError,
    DocumentAccessMetadata,
    DocumentEncryptor,
    DocumentType,
    DocumentVisibility,
    EncryptedEnvelope,
    EncryptionError,
    IPFSClient,
    IPFSConfig,
    IPFSIntegrityError,
    IPFSUploadError,
    Role,
    authorize_document_access,
    compute_cid_v1,
    compute_unixfs_cid_v0,
    detect_cid_version,
    is_valid_cid,
    sha256_bytes,
    verify_content_integrity,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_MASTER_KEY_HEX = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
WRONG_MASTER_KEY_HEX = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"


# ==============================================================================
# 1. CIDv1 / CIDv0 & SHA-256 SPECIFICATION TESTS
# ==============================================================================
def test_cid_v1_and_v0_match_official_ipfs_test_vectors() -> None:
    """Verify pure-Python CIDv1 (raw) and CIDv0 (UnixFS) against canonical IPFS vectors."""
    # Empty raw leaf vector: `echo -n "" | ipfs add --cid-version=1 --raw-leaves --only-hash`
    assert compute_cid_v1(b"") == "bafkreihdwdcefgh4dqkjv67uzcmw7ojee6xedzdetojuzjevtenxquvyku"
    assert detect_cid_version("bafkreihdwdcefgh4dqkjv67uzcmw7ojee6xedzdetojuzjevtenxquvyku") == 1

    # "hello world" (no newline) canonical IPFS CIDv1 raw vector
    hello_no_nl = b"hello world"
    assert compute_cid_v1(hello_no_nl) == "bafkreifzjut3te2nhyekklss27nh3k72ysco7y32koao5eei66wof36n5e"

    # "hello world\n" canonical IPFS CIDv1 raw + CIDv0 UnixFS vectors
    hello_nl = b"hello world\n"
    assert compute_cid_v1(hello_nl) == "bafkreifjjcie6lypi6ny7amxnfftagclbuxndqonfipmb64f2km2devei4"
    assert compute_unixfs_cid_v0(hello_nl) == "QmT78zSuBmuS4z925WZfrqQ1qHaJ56DQaTfyMUF7F8ff5o"
    assert detect_cid_version("QmT78zSuBmuS4z925WZfrqQ1qHaJ56DQaTfyMUF7F8ff5o") == 0

    check = verify_content_integrity(
        hello_no_nl,
        expected_sha256=sha256_bytes(hello_no_nl),
        expected_cid="bafkreifzjut3te2nhyekklss27nh3k72ysco7y32koao5eei66wof36n5e",
    )
    assert check["integrity_verified"] is True
    assert check["sha256_verified"] is True
    assert check["cid_verified"] is True

    # Also verify CIDv0 compatibility matching in verify_content_integrity
    check_v0 = verify_content_integrity(
        hello_nl,
        expected_sha256=sha256_bytes(hello_nl),
        expected_cid="QmT78zSuBmuS4z925WZfrqQ1qHaJ56DQaTfyMUF7F8ff5o",
    )
    assert check_v0["integrity_verified"] is True
    assert check_v0["cid_verified"] is True


def test_multichunk_cid_v1_and_invalid_cid_rejection() -> None:
    """Payloads > 256 KiB produce valid dag-pb CIDv1 ('bafybei...') and invalid CIDs are rejected."""
    large_payload = b"IS355-DEFI-CHUNK-" * 20_000  # ~340 KiB (> 262,144 bytes)
    cid = compute_cid_v1(large_payload)
    assert cid.startswith("bafybei")
    assert is_valid_cid(cid) is True
    assert verify_content_integrity(large_payload, expected_cid=cid)["cid_verified"] is True
    assert verify_content_integrity(large_payload + b"X", expected_cid=cid)["cid_verified"] is False

    for bad_cid in ("", "not-a-cid", "QmTooShort", "BAFKREIUPPERCASE", "b12345"):
        assert is_valid_cid(bad_cid) is False


# ==============================================================================
# 2. AES-256-GCM ENCRYPTION & ENVELOPE SECURITY TESTS
# ==============================================================================
def test_aes_256_gcm_roundtrip_fresh_nonce_and_no_key_leak() -> None:
    """Same plaintext encrypts with unique nonces/salts, decrypts cleanly, and never leaks keys."""
    enc = DocumentEncryptor.from_hex_key(TEST_MASTER_KEY_HEX, key_id="unit-test-key-v1")
    secret_payload = b'{"wallet": "0x3C44...", "credit_score": 760, "secret_note": "unbanked-loan"}'

    env1 = enc.encrypt_bytes(
        secret_payload,
        document_type="CREDIT_REPORT",
        owner_wallet=SAMPLE_BORROWER_A_WALLET,
        original_filename="credit_report.json",
        content_type="application/json",
    )
    env2 = enc.encrypt_bytes(
        secret_payload,
        document_type="CREDIT_REPORT",
        owner_wallet=SAMPLE_BORROWER_A_WALLET,
        original_filename="credit_report.json",
        content_type="application/json",
    )

    assert env1.nonce_b64 != env2.nonce_b64
    assert env1.key_salt_b64 != env2.key_salt_b64
    assert env1.ciphertext_b64 != env2.ciphertext_b64
    assert env1.plaintext_sha256 == sha256_bytes(secret_payload)

    raw_json = env1.to_json_bytes()
    assert b"unbanked-loan" not in raw_json
    assert TEST_MASTER_KEY_HEX.encode("ascii") not in raw_json
    assert b"decryption_key" not in raw_json

    decrypted = enc.decrypt_envelope(
        raw_json,
        expected_owner_wallet=SAMPLE_BORROWER_A_WALLET,
        expected_document_type="CREDIT_REPORT",
    )
    assert decrypted == secret_payload


def test_aes_256_gcm_rejects_wrong_key_tampered_ciphertext_and_swapped_owner() -> None:
    """Wrong key, modified ciphertext, modified AAD, or swapped owner MUST fail authentication."""
    enc = DocumentEncryptor.from_hex_key(TEST_MASTER_KEY_HEX)
    wrong_enc = DocumentEncryptor.from_hex_key(WRONG_MASTER_KEY_HEX)
    plaintext = b"Sensitive DeFi Borrower Credit Report"

    env = enc.encrypt_bytes(
        plaintext,
        document_type="CREDIT_REPORT",
        owner_wallet=SAMPLE_BORROWER_A_WALLET,
        original_filename="credit.json",
    )

    # 1. Wrong master key
    with pytest.raises(DecryptionError):
        wrong_enc.decrypt_envelope(env)

    # 2. Tampered ciphertext bit flip
    tampered = env.to_dict()
    ct_bytes = bytearray(base64.b64decode(tampered["ciphertext_b64"]))
    ct_bytes[0] ^= 0x01
    tampered["ciphertext_b64"] = base64.b64encode(bytes(ct_bytes)).decode("ascii")
    with pytest.raises(DecryptionError):
        enc.decrypt_envelope(tampered)

    # 3. Swapped owner_wallet (AAD mismatch)
    swapped = env.to_dict()
    swapped["owner_wallet"] = SAMPLE_BORROWER_B_WALLET.lower()
    with pytest.raises(DecryptionError):
        enc.decrypt_envelope(swapped)

    # 4. Forbidden secret field injected into envelope
    leaked = env.to_dict()
    leaked["aes_key"] = TEST_MASTER_KEY_HEX
    with pytest.raises(DecryptionError, match="forbidden secret fields"):
        EncryptedEnvelope.from_dict(leaked)

    # 5. Invalid key size
    with pytest.raises(EncryptionError):
        DocumentEncryptor.from_hex_key("deadbeef")


# ==============================================================================
# 3. THREE DOCUMENT SCHEMAS, PDF TEMPLATE, CSV & OPTIONAL PNG TESTS
# ==============================================================================
def test_loan_agreement_schema_and_pdf_template() -> None:
    """Loan Agreement enforces <=70% LTV, forbids pre-borrow txHash, and renders valid PDF."""
    sample = build_sample_loan_agreement()
    assert sample.tx_hash is None
    assert sample.status == "PRE_BORROW_UNSIGNED"
    assert sample.loan_terms.max_ltv_bps == c.MAX_LTV_BPS == 7_000
    assert sample.loan_terms.liquidation_threshold_bps == c.LIQUIDATION_THRESHOLD_BPS == 8_000
    assert sample.loan_terms.borrow_apr_percent == 10.0
    assert sample.loan_terms.borrow_apy_percent == 10.5156

    pdf_bytes = render_loan_agreement_pdf(sample)
    assert pdf_bytes.startswith(b"%PDF-")
    assert b"%%EOF" in pdf_bytes[-64:]
    assert len(pdf_bytes) > 1_500

    # Reject pre-borrow agreement carrying a fake txHash (HI01 / Q03 invariant)
    bad_data = sample.model_dump()
    bad_data["tx_hash"] = "0x" + "ab" * 32
    with pytest.raises(ValueError, match="must NOT contain a tx_hash"):
        LoanAgreementPayload.model_validate(bad_data)

    # Reject principal > 70% LTV (e.g. 750 MyUSDT on 1000 MyUSDT collateral)
    over_ltv = sample.model_dump()
    over_ltv["loan_terms"]["principal_wad"] = str(750 * c.WAD)
    over_ltv["loan_terms"]["principal_display"] = "750.000000"
    over_ltv["loan_terms"]["requested_ltv_bps"] = 7_000
    with pytest.raises(ValueError, match="exceeds 70% Max LTV cap"):
        LoanAgreementPayload.model_validate(over_ltv)

    # Validate post-confirmation CID <-> Loan <-> TxHash binding record
    binding = LoanTxBindingRecord(
        agreement_id=sample.agreement_id,
        agreement_cid=compute_cid_v1(pdf_bytes),
        pdf_plaintext_sha256=sha256_bytes(pdf_bytes),
        loan_id="1",
        borrower_wallet=SAMPLE_BORROWER_A_WALLET,
        principal_wad=sample.loan_terms.principal_wad,
        network="local",
        chain_id=31337,
        tx_hash="0x" + "12" * 32,
        block_number=42,
        confirmed_at_utc="2026-11-26T12:01:00Z",
    )
    assert binding.block_number == 42


def test_credit_report_and_audit_logs_schemas_match_hi01_constants() -> None:
    """Credit Report (private) & Audit Logs (public JSON/CSV) validate cleanly against HI01 math."""
    credit = build_sample_credit_report()
    assert credit.visibility == "PRIVATE"
    assert credit.encryption_required is True
    assert 300 <= credit.credit_score.score <= 850
    assert set(credit.source_events) == {
        "CollateralDeposited",
        "LoanBorrowed",
        "LoanRepaid",
        "LoanLiquidated",
    }

    # Invalid score rejected
    bad_credit = credit.model_dump()
    bad_credit["credit_score"]["score"] = 900
    with pytest.raises(ValueError):
        CreditReportDocument.model_validate(bad_credit)

    # Audit Logs math parity with HI01 constants
    audit = build_sample_audit_logs()
    assert audit.visibility == "PUBLIC"
    assert audit.contains_pii is False
    assert len(audit.entries) == 6
    for entry in audit.entries:
        assert entry.data_kind == "SIMULATED"
        expected_u = c.calculate_utilization_bps(int(entry.total_borrowed_wad), int(entry.total_supplied_wad))
        expected_b_apr = c.calculate_borrow_apr_bps(expected_u)
        expected_s_apr = c.calculate_supply_apr_bps(expected_b_apr, expected_u)
        assert entry.utilization_bps == expected_u
        assert entry.borrow_apr_bps == expected_b_apr
        assert entry.supply_apr_bps == expected_s_apr
        assert entry.borrow_apy_percent > entry.borrow_apr_percent

    # CSV export
    csv_text = audit_logs_to_csv(audit)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == 6
    assert rows[-1]["period"] == "2026-11"
    assert rows[-1]["data_kind"] == "SIMULATED"

    # Optional 3rd format (PNG)
    png = generate_collateral_proof_png()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"IEND" in png[-16:]


# ==============================================================================
# 4. MOCK HTTP SERVER FOR KUBO RPC + PINATA CLOUD + FALLBACK INTEGRATION TESTS
# ==============================================================================
class _MockIPFSState:
    def __init__(self) -> None:
        self.kubo_blocks: Dict[str, bytes] = {}
        self.pinata_blocks: Dict[str, bytes] = {}
        self.pinata_fail = False
        self.kubo_fail = False
        self.corrupt_gateway = False
        self.last_pinata_auth = ""
        self.last_pinata_metadata: Dict[str, Any] = {}


def _extract_multipart_file(body: bytes, content_type: str) -> bytes:
    """Extract the `file` field bytes from a multipart/form-data HTTP request body."""
    boundary_token = content_type.split("boundary=")[-1].strip().strip('"').encode("ascii")
    delimiter = b"--" + boundary_token
    for part in body.split(delimiter):
        if b'name="file"' in part:
            header_end = part.find(b"\r\n\r\n")
            if header_end != -1:
                payload = part[header_end + 4 :]
                if payload.endswith(b"\r\n"):
                    payload = payload[:-2]
                return payload
    raise ValueError("multipart body missing file field")


def _extract_multipart_field(body: bytes, content_type: str, field_name: str) -> str:
    boundary_token = content_type.split("boundary=")[-1].strip().strip('"').encode("ascii")
    delimiter = b"--" + boundary_token
    marker = f'name="{field_name}"'.encode("ascii")
    for part in body.split(delimiter):
        if marker in part:
            header_end = part.find(b"\r\n\r\n")
            if header_end != -1:
                payload = part[header_end + 4 :]
                if payload.endswith(b"\r\n"):
                    payload = payload[:-2]
                return payload.decode("utf-8")
    return ""


class _InMemoryIPFSAdapter(BaseAdapter):
    """Sandbox-safe HTTP transport adapter simulating IPFS Kubo RPC and Pinata Cloud HTTP APIs."""

    def __init__(self, state: _MockIPFSState) -> None:
        super().__init__()
        self.state = state

    @staticmethod
    def _build_response(
        request: requests.PreparedRequest,
        status_code: int,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> requests.Response:
        resp = requests.Response()
        resp.status_code = status_code
        resp.url = request.url or ""
        resp.request = request
        resp.headers["Content-Type"] = content_type
        resp._content = content
        return resp

    def send(self, request: requests.PreparedRequest, **kwargs: Any) -> requests.Response:
        parsed = urlparse(request.url or "")
        body = request.body if isinstance(request.body, bytes) else (request.body or "").encode("utf-8")
        ctype = str(request.headers.get("Content-Type", ""))
        method = (request.method or "GET").upper()

        if method == "POST" and parsed.path == "/api/v0/version":
            if self.state.kubo_fail:
                raise requests.ConnectionError("kubo offline")
            return self._build_response(
                request, 200, json.dumps({"Version": "0.31.0-mock"}).encode("utf-8"), "application/json"
            )

        if method == "POST" and parsed.path == "/api/v0/add":
            if self.state.kubo_fail:
                raise requests.ConnectionError("kubo offline")
            file_bytes = _extract_multipart_file(body, ctype)
            cid = compute_cid_v1(file_bytes)
            self.state.kubo_blocks[cid] = file_bytes
            payload = json.dumps({"Name": "upload", "Hash": cid, "Size": str(len(file_bytes))}).encode("utf-8")
            return self._build_response(request, 200, payload, "application/json")

        if method == "POST" and parsed.path == "/api/v0/cat":
            if self.state.kubo_fail:
                raise requests.ConnectionError("kubo offline")
            cid = parse_qs(parsed.query).get("arg", [""])[0]
            if cid not in self.state.kubo_blocks:
                return self._build_response(request, 404, b'{"Message":"not found"}', "application/json")
            data = self.state.kubo_blocks[cid]
            if self.state.corrupt_gateway:
                data = data + b"CORRUPTED"
            return self._build_response(request, 200, data)

        if method == "POST" and parsed.path == "/pinning/pinFileToIPFS":
            if self.state.pinata_fail:
                return self._build_response(request, 503, b'{"error":"pinata unavailable"}', "application/json")
            self.state.last_pinata_auth = str(request.headers.get("Authorization", ""))
            meta_raw = _extract_multipart_field(body, ctype, "pinataMetadata")
            if meta_raw:
                self.state.last_pinata_metadata = json.loads(meta_raw)
            file_bytes = _extract_multipart_file(body, ctype)
            cid = compute_cid_v1(file_bytes)
            self.state.pinata_blocks[cid] = file_bytes
            payload = json.dumps({"IpfsHash": cid, "PinSize": len(file_bytes)}).encode("utf-8")
            return self._build_response(request, 200, payload, "application/json")

        if method == "GET" and parsed.path == "/data/testAuthentication":
            if self.state.pinata_fail:
                return self._build_response(request, 503, b'{"error":"down"}', "application/json")
            if request.headers.get("Authorization") == "Bearer mock-jwt-token":
                return self._build_response(
                    request, 200, b'{"message":"Congratulations! You are authenticated."}', "application/json"
                )
            return self._build_response(request, 401, b'{"error":"invalid token"}', "application/json")

        if method == "GET" and parsed.path.startswith("/kubo-gw/"):
            cid = parsed.path.removeprefix("/kubo-gw/")
            if self.state.kubo_fail or cid not in self.state.kubo_blocks:
                return self._build_response(request, 404, b"not found")
            data = self.state.kubo_blocks[cid]
            if self.state.corrupt_gateway:
                data = data + b"CORRUPTED"
            return self._build_response(request, 200, data)

        if method == "GET" and parsed.path.startswith("/pinata-gw/"):
            cid = parsed.path.removeprefix("/pinata-gw/")
            if self.state.pinata_fail or cid not in self.state.pinata_blocks:
                return self._build_response(request, 404, b"not found")
            data = self.state.pinata_blocks[cid]
            if self.state.corrupt_gateway:
                data = data + b"CORRUPTED"
            return self._build_response(request, 200, data)

        return self._build_response(request, 404, b"not found")

    def close(self) -> None:
        return


def test_ipfs_client_kubo_pinata_fallback_and_integrity(tmp_path: Path) -> None:
    """Verify Kubo RPC, Pinata API, automatic fallback chain, and SHA-256 tamper detection."""
    state = _MockIPFSState()
    session = requests.Session()
    adapter = _InMemoryIPFSAdapter(state)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    base_url = "http://mock-ipfs.local"

    # 1. Pinata primary mode
    pinata_cfg = IPFSConfig(
        provider="pinata",
        kubo_api_url=base_url,
        kubo_gateway_url=f"{base_url}/kubo-gw",
        pinata_api_url=base_url,
        pinata_gateway_url=f"{base_url}/pinata-gw",
        pinata_jwt="mock-jwt-token",
        local_store_dir=tmp_path / "store1",
        request_timeout_seconds=3.0,
    )
    client = IPFSClient(config=pinata_cfg, session=session)
    health = client.check_health()
    assert health["kubo_local"]["reachable"] is True
    assert health["pinata_cloud"]["authenticated"] is True
    assert "mock-jwt-token" not in json.dumps(health)

    pdf_bytes = render_loan_agreement_pdf(build_sample_loan_agreement())
    up = client.upload_bytes(
        pdf_bytes,
        filename="loan_agreement.pdf",
        content_type="application/pdf",
        metadata={"document_type": "LOAN_AGREEMENT"},
    )
    assert up.provider_used == "pinata"
    assert is_valid_cid(up.cid)
    assert state.last_pinata_auth == "Bearer mock-jwt-token"
    assert state.last_pinata_metadata["keyvalues"]["document_type"] == "LOAN_AGREEMENT"

    ret = client.retrieve_bytes(up.cid, expected_sha256=up.sha256)
    assert ret.provider_used == "pinata_gateway"
    assert ret.content == pdf_bytes
    assert ret.integrity_verified is True

    # 2. Pinata fails -> automatically falls back to Kubo local node
    state.pinata_fail = True
    audit_payload = build_sample_audit_logs().model_dump(mode="json")
    up_kubo = client.upload_json(audit_payload, filename="audit_logs.json")
    assert up_kubo.provider_used == "kubo"
    parsed_audit, ret_kubo = client.retrieve_json(up_kubo.cid, expected_sha256=up_kubo.sha256)
    assert ret_kubo.provider_used == "kubo_gateway"
    assert parsed_audit["document_type"] == "AUDIT_LOGS"

    # 3. Both Pinata and Kubo go offline -> previously mirrored pin still loads from local_store!
    state.kubo_fail = True
    offline_ret = client.retrieve_bytes(up.cid, expected_sha256=up.sha256)
    assert offline_ret.provider_used == "local_store"
    assert offline_ret.content == pdf_bytes

    # 4. Upload while offline -> falls back to local_store cleanly
    up_local = client.upload_bytes(b'{"offline": true}', filename="offline.json")
    assert up_local.provider_used == "local_store"
    assert client.retrieve_bytes(up_local.cid, expected_sha256=up_local.sha256).content == b'{"offline": true}'

    # 5. Gateway corruption raises IPFSIntegrityError
    state.kubo_fail = False
    state.corrupt_gateway = True
    with pytest.raises(IPFSIntegrityError):
        client.retrieve_bytes(up_kubo.cid, expected_sha256=up_kubo.sha256)

    # 6. Sensitive metadata keys refused
    with pytest.raises(ValueError, match="Refusing to attach sensitive key"):
        client.upload_bytes(b"data", filename="x.json", metadata={"aes_key": "secret"})

    # 7. Strict live mode (fallback disabled) raises IPFSUploadError when backends are offline
    state.corrupt_gateway = False
    state.kubo_fail = True
    strict_client = IPFSClient(
        config=IPFSConfig(
            provider="kubo",
            kubo_api_url=base_url,
            enable_local_fallback=False,
            local_store_dir=tmp_path / "strict",
        ),
        session=session,
    )
    with pytest.raises(IPFSUploadError):
        strict_client.upload_bytes(b"test", filename="test.bin")


# ==============================================================================
# 5. RBAC MATRIX & UNAUTHORIZED CID ACCESS DENIAL TESTS (401 / 403 / 200)
# ==============================================================================
def test_rbac_private_documents_encrypted_and_blocked_for_unauthorized_wallets(tmp_path: Path) -> None:
    """Core H03 acceptance check: knowing CID cannot decrypt private docs; RBAC enforces 401/403/200."""
    client = IPFSClient(config=IPFSConfig(provider="local_store", local_store_dir=tmp_path / "ipfs"))
    encryptor = DocumentEncryptor.from_hex_key(TEST_MASTER_KEY_HEX, key_id="h03-test-v1")
    gateway = AuthorizedIPFSGateway(ipfs_client=client, encryptor=encryptor)

    loan_pdf = render_loan_agreement_pdf(build_sample_loan_agreement())
    credit_json = json.dumps(build_sample_credit_report().model_dump(mode="json"), sort_keys=True).encode("utf-8")
    audit_json = json.dumps(build_sample_audit_logs().model_dump(mode="json"), sort_keys=True).encode("utf-8")
    proof_png = generate_collateral_proof_png()

    loan_up, loan_acl, _ = gateway.upload_document(
        loan_pdf,
        document_type=DocumentType.LOAN_AGREEMENT,
        filename="loan_agreement.pdf",
        owner_wallet=SAMPLE_BORROWER_A_WALLET,
    )
    credit_up, credit_acl, _ = gateway.upload_document(
        credit_json,
        document_type=DocumentType.CREDIT_REPORT,
        filename="credit_report.json",
        owner_wallet=SAMPLE_BORROWER_A_WALLET,
    )
    audit_up, audit_acl, _ = gateway.upload_document(
        audit_json,
        document_type=DocumentType.AUDIT_LOGS,
        filename="audit_logs.json",
        visibility=DocumentVisibility.PUBLIC,
    )
    proof_up, proof_acl, _ = gateway.upload_document(
        proof_png,
        document_type=DocumentType.COLLATERAL_PROOF,
        filename="collateral_proof.png",
        owner_wallet=SAMPLE_BORROWER_A_WALLET,
    )

    # 1. Raw CID fetch on IPFS only exposes ciphertext for private docs (NO plaintext or key)
    raw_credit = gateway.retrieve_raw_by_cid(credit_up.cid).content
    assert b"LOAN-SAMPLE-001" not in raw_credit
    assert b"760" not in raw_credit
    assert TEST_MASTER_KEY_HEX.encode("ascii") not in raw_credit
    assert b"ciphertext_b64" in raw_credit

    raw_loan = gateway.retrieve_raw_by_cid(loan_up.cid).content
    assert not raw_loan.startswith(b"%PDF-")
    assert b"ciphertext_b64" in raw_loan

    guest = AccessContext.guest()
    lender_a = AccessContext.for_wallet(SAMPLE_LENDER_A_WALLET, {Role.LENDER})
    borrower_b = AccessContext.for_wallet(SAMPLE_BORROWER_B_WALLET, {Role.BORROWER})
    borrower_a = AccessContext.for_wallet(SAMPLE_BORROWER_A_WALLET, {Role.BORROWER})
    admin = AccessContext.for_wallet(SAMPLE_ADMIN_WALLET, {Role.ADMIN})

    # 2. Private docs: Guest -> 401; Lender & Borrower B -> 403; Owner Borrower A & Admin -> 200 + exact plaintext
    for cid, expected_bytes in (
        (loan_up.cid, loan_pdf),
        (credit_up.cid, credit_json),
        (proof_up.cid, proof_png),
    ):
        with pytest.raises(AccessDeniedError) as exc_guest:
            gateway.retrieve_authorized_document(cid, guest)
        assert exc_guest.value.http_status == 401

        for unauthorized in (lender_a, borrower_b):
            with pytest.raises(AccessDeniedError) as exc_forbidden:
                gateway.retrieve_authorized_document(cid, unauthorized)
            assert exc_forbidden.value.http_status == 403

        for authorized in (borrower_a, admin):
            res = gateway.retrieve_authorized_document(cid, authorized)
            assert res.decision.http_status == 200
            assert res.decrypted is True
            assert res.content == expected_bytes
            assert res.plaintext_sha256 == sha256_bytes(expected_bytes)

    # 3. Public Audit Logs: ALL roles allowed (200), unencrypted
    for actor in (guest, lender_a, borrower_b, borrower_a, admin):
        res = gateway.retrieve_authorized_document(audit_up.cid, actor)
        assert res.decision.http_status == 200
        assert res.decrypted is False
        assert res.content == audit_json

    # 4. Upload RBAC: only ADMIN may publish public Audit Logs
    assert authorize_document_access(borrower_a, audit_acl, AccessAction.UPLOAD).http_status == 403
    assert authorize_document_access(admin, audit_acl, AccessAction.UPLOAD).http_status == 200
    assert authorize_document_access(borrower_b, credit_acl, AccessAction.UPLOAD).http_status == 403
    assert authorize_document_access(borrower_a, credit_acl, AccessAction.UPLOAD).http_status == 200

    # 5. Unknown CID fails closed (403)
    with pytest.raises(AccessDeniedError) as exc_unknown:
        gateway.retrieve_authorized_document(compute_cid_v1(b"unregistered"), borrower_a)
    assert exc_unknown.value.http_status == 403


# ==============================================================================
# 6. REPOSITORY SCHEMAS, SAMPLE ARTIFACTS & SECURITY GUARDRAILS
# ==============================================================================
def test_h03_exported_schemas_samples_and_git_hygiene() -> None:
    """Confirm all H03 schemas & samples exist, validate cleanly, and contain no secrets."""
    schemas_dir = PROJECT_ROOT / "ipfs_storage" / "schemas"
    samples_dir = PROJECT_ROOT / "ipfs_storage" / "samples"

    for schema_file in (
        "loan_agreement.schema.json",
        "loan_tx_binding.schema.json",
        "credit_report.schema.json",
        "audit_logs.schema.json",
        "encrypted_envelope.schema.json",
        "rbac_matrix.json",
    ):
        path = schemas_dir / schema_file
        assert path.is_file(), f"Missing exported H03 schema: {path}"
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)

    # Verify sample files & manifest
    manifest_path = samples_dir / "sample_cids_manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc_types = {item["document_type"] for item in manifest["documents"]}
    assert {"LOAN_AGREEMENT", "CREDIT_REPORT", "AUDIT_LOGS", "COLLATERAL_PROOF"}.issubset(doc_types)

    for item in manifest["documents"]:
        assert is_valid_cid(item["ipfs_cid"]) is True
        if item["visibility"] == "PRIVATE":
            assert item["encrypted_on_ipfs"] is True
            enc_path = PROJECT_ROOT / item["sample_encrypted_file"]
            enc_env = EncryptedEnvelope.from_json_bytes(enc_path.read_bytes())
            assert enc_env.algorithm == "AES-256-GCM"
            assert enc_env.encrypted is True
            assert compute_cid_v1(enc_path.read_bytes()) == item["ipfs_cid"]

    # Validate plaintext samples against Pydantic schemas
    CreditReportDocument.model_validate_json((samples_dir / "credit_report_sample.json").read_text(encoding="utf-8"))
    AuditLogsDocument.model_validate_json((samples_dir / "audit_logs_sample.json").read_text(encoding="utf-8"))
    assert (samples_dir / "loan_agreement_sample.pdf").read_bytes().startswith(b"%PDF-")
    assert (samples_dir / "collateral_proof_sample.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    # Confirm `.env` is ignored by `.gitignore`
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore


def test_ipfs_client_file_roundtrip_api_key_headers_and_kubo_rpc_fallback(tmp_path: Path) -> None:
    """Verify disk upload/retrieve roundtrip, Pinata API Key/Secret header auth, and Kubo RPC /cat fallback."""
    state = _MockIPFSState()

    class GatewayDownAdapter(_InMemoryIPFSAdapter):
        def send(self, request: requests.PreparedRequest, **kwargs: Any) -> requests.Response:
            parsed = urlparse(request.url or "")
            if parsed.path.startswith("/kubo-gw/"):
                return self._build_response(request, 502, b"gateway bad gateway")
            return super().send(request, **kwargs)

    session = requests.Session()
    adapter = GatewayDownAdapter(state)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # 1. File upload via Kubo + retrieve falling back from /kubo-gw (502) -> /api/v0/cat (200)
    kubo_cfg = IPFSConfig(
        provider="kubo",
        kubo_api_url="http://mock-ipfs.local",
        kubo_gateway_url="http://mock-ipfs.local/kubo-gw",
        local_store_dir=tmp_path / "kubo_store",
        enable_local_fallback=False,
    )
    kubo_client = IPFSClient(config=kubo_cfg, session=session)
    src_file = tmp_path / "sample_audit.json"
    src_file.write_bytes(b'{"document_type":"AUDIT_LOGS","ok":true}')
    up = kubo_client.upload_file(src_file)
    assert up.provider_used == "kubo"

    out_file = tmp_path / "downloaded" / "sample_audit.json"
    ret = kubo_client.retrieve_file(up.cid, out_file, expected_sha256=up.sha256)
    assert ret.provider_used == "kubo_rpc"
    assert out_file.read_bytes() == src_file.read_bytes()

    # 2. Pinata API Key + Secret Key header mode (non-JWT)
    pinata_key_cfg = IPFSConfig(
        provider="pinata",
        pinata_api_url="http://mock-ipfs.local",
        pinata_gateway_url="http://mock-ipfs.local/pinata-gw",
        pinata_api_key="test-api-key",
        pinata_secret_api_key="test-secret-key",
        local_store_dir=tmp_path / "pinata_store",
    )
    pinata_client = IPFSClient(config=pinata_key_cfg, session=session)
    assert pinata_client.config.has_pinata_credentials is True
    assert pinata_client._pinata_headers() == {
        "pinata_api_key": "test-api-key",
        "pinata_secret_api_key": "test-secret-key",
    }

