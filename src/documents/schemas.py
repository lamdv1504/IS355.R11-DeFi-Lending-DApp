"""Canonical Pydantic v2 schemas for the 3 mandatory IPFS document types (H03 -> Q03, Q04, L04).

Aligned bit-for-bit with:
- `backend/config/constants.py` (HI01 Single Source of Truth)
- `docs/Hieu/smart_contract_spec.md` §5.1 (On-chain <-> IPFS & RBAC)
- `docs/Lam/l01_api_contract.md` §2 & §6 (WAD string serialization, APR vs APY, pre-borrow PDF)
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.config import constants as c
from src.ipfs.rbac import RBAC_MATRIX

_ETH_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TX_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_UINT_STR_RE = re.compile(r"^\d+$")
_HEX_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_VN_TZ = timezone(timedelta(hours=7))

SCHEMA_VERSION = "1.0"


def _validate_eth_address(value: str) -> str:
    cleaned = value.strip()
    if not _ETH_ADDRESS_RE.match(cleaned):
        raise ValueError(f"Invalid Ethereum address: {value!r}")
    return cleaned


def _validate_uint_str(value: str) -> str:
    cleaned = str(value).strip()
    if not _UINT_STR_RE.match(cleaned):
        raise ValueError(f"Expected non-negative decimal integer string, got {value!r}")
    return cleaned


# ==============================================================================
# 1. LOAN AGREEMENT (PDF TEMPLATE INPUT + POST-RECEIPT TX BINDING SCHEMA)
# ==============================================================================
class LoanCollateralInfo(BaseModel):
    """Collateral details included in the Loan Agreement PDF."""

    model_config = ConfigDict(extra="forbid")

    asset_type: Literal["ERC20", "ERC721"] = Field(
        ..., description="Loại tài sản thế chấp: ERC20 token hoặc CollateralNFT (ERC721)."
    )
    token_address: Optional[str] = Field(
        default=None, description="Địa chỉ contract tài sản thế chấp (null nếu chưa deploy)."
    )
    asset_id_or_amount: str = Field(
        ..., description="Token ID (nếu ERC721) hoặc số lượng WAD (nếu ERC20)."
    )
    receipt_token_id: Optional[str] = Field(
        default=None, description="ID của CollateralReceiptNFT đã mint khi khóa tài sản."
    )
    valuation_wad: str = Field(..., description="Định giá tài sản thế chấp theo MyUSDT WAD (1e18).")
    valuation_display: str = Field(..., description="Định giá tài sản hiển thị (MyUSDT).")
    asset_description: str = Field(
        ..., min_length=3, max_length=240, description="Mô tả tài sản số hóa làm thế chấp."
    )

    @field_validator("token_address")
    @classmethod
    def _check_token_address(cls, v: Optional[str]) -> Optional[str]:
        return _validate_eth_address(v) if v is not None else None

    @field_validator("asset_id_or_amount", "valuation_wad")
    @classmethod
    def _check_uint(cls, v: str) -> str:
        return _validate_uint_str(v)


class LoanTermsInfo(BaseModel):
    """Economic terms of the loan — strictly separating APR (on-chain) and APY (reference)."""

    model_config = ConfigDict(extra="forbid")

    principal_wad: str = Field(..., description="Số tiền vay gốc theo MyUSDT WAD (1e18).")
    principal_display: str = Field(..., description="Số tiền vay gốc hiển thị (MyUSDT).")
    requested_ltv_bps: int = Field(
        ..., ge=1, le=c.MAX_LTV_BPS, description="Tỷ lệ LTV thực tế của khoản vay (BPS, tối đa 7000 = 70%)."
    )
    max_ltv_bps: int = Field(default=c.MAX_LTV_BPS, description="Trần LTV tối đa bắt buộc = 7000 BPS (70%).")
    liquidation_threshold_bps: int = Field(
        default=c.LIQUIDATION_THRESHOLD_BPS,
        description="Ngưỡng thanh lý = 8000 BPS (80%).",
    )
    liquidation_bonus_bps: int = Field(
        default=c.LIQUIDATION_BONUS_BPS,
        description="Thưởng thanh lý cho Liquidator = 500 BPS (5%).",
    )
    borrow_apr_bps: int = Field(..., ge=c.BASE_BORROW_APR_BPS, description="Lãi suất vay đơn on-chain (BPS/năm).")
    borrow_apr_percent: float = Field(..., description="Lãi suất vay đơn on-chain (APR %/năm).")
    borrow_apy_percent: float = Field(
        ..., description="Lãi suất hiệu dụng quy đổi lãi kép theo ngày (APY %/năm, chỉ mang tính tham khảo)."
    )
    interest_accrual_basis: str = Field(
        default="Simple per-second accrual via block.timestamp (31,536,000 s/year); APY shown for daily-compounded reference only.",
        description="Quy tắc tính lãi rõ ràng tách biệt APR và APY theo HI01.",
    )

    @field_validator("principal_wad")
    @classmethod
    def _check_principal(cls, v: str) -> str:
        val = _validate_uint_str(v)
        if int(val) <= 0:
            raise ValueError("principal_wad must be > 0")
        return val

    @field_validator("max_ltv_bps")
    @classmethod
    def _check_max_ltv(cls, v: int) -> int:
        if v != c.MAX_LTV_BPS:
            raise ValueError(f"max_ltv_bps must match HI01 constant {c.MAX_LTV_BPS}")
        return v

    @field_validator("liquidation_threshold_bps")
    @classmethod
    def _check_liq_threshold(cls, v: int) -> int:
        if v != c.LIQUIDATION_THRESHOLD_BPS:
            raise ValueError(f"liquidation_threshold_bps must match HI01 constant {c.LIQUIDATION_THRESHOLD_BPS}")
        return v


class LoanAgreementPayload(BaseModel):
    """Input model used to render the Loan Agreement PDF before calling ``borrow(amount, cid)``."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    document_type: Literal["LOAN_AGREEMENT"] = "LOAN_AGREEMENT"
    visibility: Literal["PRIVATE"] = "PRIVATE"
    data_kind: Literal["ON_CHAIN", "SIMULATED"] = "ON_CHAIN"
    agreement_id: str = Field(..., min_length=4, max_length=64)
    agreement_nonce: str = Field(..., min_length=8, max_length=128)
    created_at_utc: str
    created_at_vn: str
    network: Literal["local", "sepolia"] = "local"
    chain_id: int
    lending_pool_address: Optional[str] = None
    borrower_wallet: str
    wallet_auth_signature: Optional[str] = Field(
        default=None,
        description="Chữ ký xác thực phiên nonce của ví Borrower (KHÔNG bao giờ chứa private key).",
    )
    collateral: LoanCollateralInfo
    loan_terms: LoanTermsInfo
    status: Literal["PRE_BORROW_UNSIGNED", "CONFIRMED_ON_CHAIN"] = "PRE_BORROW_UNSIGNED"
    tx_hash: Optional[str] = Field(
        default=None,
        description="BẮT BUỘC là null khi sinh PDF trước giao dịch borrow(); đối chiếu sau khi có receipt.",
    )
    legal_clauses: List[str] = Field(
        default_factory=lambda: [
            "1. Khoan vay duoc thuc thi minh bach boi Smart Contract LendingPool tren nen tang Ethereum; khong can trung gian ngan hang truyen thong.",
            "2. Ty le vay toi da (Max LTV) bi khoa cung <= 70.00% gia tri tai san the chap theo dinh gia PriceOracle.",
            "3. Lai suat on-chain tinh theo lai don (APR) theo tung giay block.timestamp (31,536,000 giay/nam); APY chi la chi so tham khao quy doi lai kep theo ngay.",
            "4. Khi Health Factor < 1.00 (du no cham nguong thanh ly 80.00%), bat ky Liquidator hop le nao co the gui giao dich liquidate() de thanh ly tai san the chap kem thuong 5.00%.",
            "5. Tai lieu nay duoc bam SHA-256, ma hoa AES-256-GCM va luu tren IPFS truoc khi ky borrow(amount, cid); txHash se duoc doi chieu trong bang anh xa CID <-> Loan <-> TxHash sau khi giao dich duoc xac nhan.",
        ]
    )

    @field_validator("borrower_wallet")
    @classmethod
    def _check_borrower(cls, v: str) -> str:
        return _validate_eth_address(v)

    @field_validator("lending_pool_address")
    @classmethod
    def _check_pool(cls, v: Optional[str]) -> Optional[str]:
        return _validate_eth_address(v) if v is not None else None

    @field_validator("tx_hash")
    @classmethod
    def _check_tx_hash(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not _TX_HASH_RE.match(cleaned):
            raise ValueError(f"Invalid transaction hash format: {v!r}")
        return cleaned

    @model_validator(mode="after")
    def _check_business_invariants(self) -> "LoanAgreementPayload":
        # Enforce HI01/Q03 rule: no fake txHash before on-chain confirmation
        if self.status == "PRE_BORROW_UNSIGNED" and self.tx_hash is not None:
            raise ValueError(
                "PRE_BORROW_UNSIGNED Loan Agreement must NOT contain a tx_hash "
                "(bind tx_hash after borrow() receipt confirmation)."
            )
        if self.status == "CONFIRMED_ON_CHAIN" and self.tx_hash is None:
            raise ValueError("CONFIRMED_ON_CHAIN Loan Agreement must provide a confirmed tx_hash")

        # Enforce LTV <= 70% mathematically
        collateral_wad = int(self.collateral.valuation_wad)
        principal_wad = int(self.loan_terms.principal_wad)
        max_borrow = c.calculate_max_borrow(collateral_wad)
        if principal_wad > max_borrow:
            raise ValueError(
                f"Principal {principal_wad} exceeds 70% Max LTV cap ({max_borrow}) for collateral {collateral_wad}"
            )
        return self


class LoanTxBindingRecord(BaseModel):
    """Post-confirmation reconciliation record binding Agreement CID <-> Loan ID <-> TxHash (HI01/Q03)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    agreement_id: str
    agreement_cid: str
    pdf_plaintext_sha256: str
    encrypted_ipfs_sha256: Optional[str] = None
    loan_id: str
    borrower_wallet: str
    principal_wad: str
    network: Literal["local", "sepolia"]
    chain_id: int
    tx_hash: str
    block_number: int = Field(..., ge=0)
    confirmed_at_utc: str

    @field_validator("borrower_wallet")
    @classmethod
    def _check_wallet(cls, v: str) -> str:
        return _validate_eth_address(v)

    @field_validator("tx_hash")
    @classmethod
    def _check_tx(cls, v: str) -> str:
        if not _TX_HASH_RE.match(v.strip()):
            raise ValueError(f"Invalid tx_hash: {v!r}")
        return v.strip()

    @field_validator("pdf_plaintext_sha256")
    @classmethod
    def _check_sha(cls, v: str) -> str:
        if not _HEX_SHA256_RE.match(v.strip()):
            raise ValueError(f"Invalid SHA-256 hex digest: {v!r}")
        return v.strip().lower()


# ==============================================================================
# 2. CREDIT REPORT (PRIVATE JSON METADATA SCHEMA — ENCRYPTED BEFORE IPFS)
# ==============================================================================
class CreditLoanRecord(BaseModel):
    """Individual loan history entry inside a borrower's Credit Report."""

    model_config = ConfigDict(extra="forbid")

    loan_id: str
    agreement_cid: Optional[str] = None
    principal_wad: str
    principal_display: str
    repaid_wad: str
    repaid_display: str
    status: Literal["ACTIVE", "REPAID_ON_TIME", "LIQUIDATED"]
    borrowed_at_utc: str
    closed_at_utc: Optional[str] = None
    borrow_tx_hash: Optional[str] = None
    repay_or_liquidate_tx_hash: Optional[str] = None

    @field_validator("principal_wad", "repaid_wad")
    @classmethod
    def _check_wad(cls, v: str) -> str:
        return _validate_uint_str(v)


class CreditReportSummary(BaseModel):
    """Aggregate on-chain credit metrics for a wallet."""

    model_config = ConfigDict(extra="forbid")

    total_loans: int = Field(..., ge=0)
    repaid_on_time_count: int = Field(..., ge=0)
    active_loans_count: int = Field(..., ge=0)
    liquidation_count: int = Field(..., ge=0)
    total_borrowed_wad: str
    total_borrowed_display: str
    total_repaid_wad: str
    total_repaid_display: str
    current_debt_wad: str
    current_debt_display: str
    on_time_repayment_ratio_bps: int = Field(..., ge=0, le=c.BPS)

    @field_validator("total_borrowed_wad", "total_repaid_wad", "current_debt_wad")
    @classmethod
    def _check_wad(cls, v: str) -> str:
        return _validate_uint_str(v)

    @model_validator(mode="after")
    def _check_counts(self) -> "CreditReportSummary":
        if self.repaid_on_time_count + self.active_loans_count + self.liquidation_count > self.total_loans:
            raise ValueError("Sum of repaid, active, and liquidated loans cannot exceed total_loans")
        return self


class CreditScoreInfo(BaseModel):
    """Decentralized on-chain credit score (300 - 850 scale)."""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(..., ge=300, le=850)
    scale_min: Literal[300] = 300
    scale_max: Literal[850] = 850
    tier: Literal["POOR", "FAIR", "GOOD", "VERY_GOOD", "EXCELLENT"]
    scoring_model_version: str = "defi-onchain-v1"
    rationale: str


class CreditReportDocument(BaseModel):
    """Canonical Credit Report JSON schema (MUST be AES-256-GCM encrypted before IPFS upload)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    document_type: Literal["CREDIT_REPORT"] = "CREDIT_REPORT"
    visibility: Literal["PRIVATE"] = "PRIVATE"
    encryption_required: Literal[True] = True
    data_kind: Literal["ON_CHAIN", "SIMULATED"] = "ON_CHAIN"
    generated_at_utc: str
    network: Literal["local", "sepolia"] = "local"
    chain_id: int
    wallet_address: str
    summary: CreditReportSummary
    credit_score: CreditScoreInfo
    loan_ids: List[str] = Field(default_factory=list)
    loans: List[CreditLoanRecord] = Field(default_factory=list)
    source_events: List[str] = Field(
        default_factory=lambda: [
            "CollateralDeposited",
            "LoanBorrowed",
            "LoanRepaid",
            "LoanLiquidated",
        ]
    )

    @field_validator("wallet_address")
    @classmethod
    def _check_wallet(cls, v: str) -> str:
        return _validate_eth_address(v)


# ==============================================================================
# 3. AUDIT LOGS (PUBLIC AGGREGATE MONTHLY INTEREST RATE LOGS — JSON / CSV)
# ==============================================================================
class AuditRateModelInfo(BaseModel):
    """Snapshot of the HI01 hybrid interest rate model parameters."""

    model_config = ConfigDict(extra="forbid")

    base_borrow_apr_bps: int = c.BASE_BORROW_APR_BPS
    utilization_slope_bps: int = c.UTILIZATION_SLOPE_BPS
    protocol_reserve_factor_bps: int = c.PROTOCOL_RESERVE_FACTOR_BPS
    seconds_per_year: int = c.SECONDS_PER_YEAR
    apr_vs_apy_note: str = (
        "borrow_apr_percent / supply_apr_percent are on-chain simple annual rates (APR); "
        "borrow_apy_percent / supply_apy_percent are daily-compounded (n=365) reference values."
    )


class AuditLogEntry(BaseModel):
    """Single monthly interest rate & pool liquidity audit log entry (no PII)."""

    model_config = ConfigDict(extra="forbid")

    period: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="Tháng ghi nhận (YYYY-MM).")
    recorded_at_utc: str
    data_kind: Literal["SIMULATED", "ON_CHAIN"]
    total_supplied_wad: str
    total_supplied_display: str
    total_borrowed_wad: str
    total_borrowed_display: str
    available_liquidity_wad: str
    available_liquidity_display: str
    utilization_bps: int = Field(..., ge=0, le=c.BPS)
    utilization_percent: float = Field(..., ge=0.0, le=100.0)
    borrow_apr_bps: int = Field(..., ge=0)
    borrow_apr_percent: float = Field(..., ge=0.0)
    borrow_apy_percent: float = Field(..., ge=0.0)
    supply_apr_bps: int = Field(..., ge=0)
    supply_apr_percent: float = Field(..., ge=0.0)
    supply_apy_percent: float = Field(..., ge=0.0)
    event_tx_hash: Optional[str] = None
    notes: str = ""

    @field_validator("total_supplied_wad", "total_borrowed_wad", "available_liquidity_wad")
    @classmethod
    def _check_wad(cls, v: str) -> str:
        return _validate_uint_str(v)


class AuditLogsDocument(BaseModel):
    """Canonical Public Audit Logs JSON schema (safe for public IPFS pinning; no PII/secrets)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    document_type: Literal["AUDIT_LOGS"] = "AUDIT_LOGS"
    visibility: Literal["PUBLIC"] = "PUBLIC"
    encryption_required: Literal[False] = False
    contains_pii: Literal[False] = False
    generated_at_utc: str
    network: Literal["local", "sepolia"] = "local"
    chain_id: int
    lending_pool_address: Optional[str] = None
    rate_model: AuditRateModelInfo = Field(default_factory=AuditRateModelInfo)
    entries: List[AuditLogEntry] = Field(..., min_length=1)

    @field_validator("lending_pool_address")
    @classmethod
    def _check_pool(cls, v: Optional[str]) -> Optional[str]:
        return _validate_eth_address(v) if v is not None else None


def audit_logs_to_csv(doc: AuditLogsDocument) -> str:
    """Serialize an ``AuditLogsDocument`` to UTF-8 CSV (supports JSON/CSV rubric requirement)."""
    output = io.StringIO()
    fieldnames = [
        "period",
        "recorded_at_utc",
        "data_kind",
        "total_supplied_display",
        "total_borrowed_display",
        "available_liquidity_display",
        "utilization_bps",
        "utilization_percent",
        "borrow_apr_bps",
        "borrow_apr_percent",
        "borrow_apy_percent",
        "supply_apr_bps",
        "supply_apr_percent",
        "supply_apy_percent",
        "event_tx_hash",
        "notes",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for entry in doc.entries:
        writer.writerow({name: getattr(entry, name) for name in fieldnames})
    return output.getvalue()


# ==============================================================================
# 4. ENCRYPTED ENVELOPE SCHEMA (FOR MACHINE-READABLE JSON SCHEMA EXPORT)
# ==============================================================================
class EncryptedEnvelopeSchema(BaseModel):
    """Pydantic mirror of ``src.ipfs.encryption.EncryptedEnvelope`` for JSON Schema export."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    encrypted: Literal[True] = True
    algorithm: Literal["AES-256-GCM"] = "AES-256-GCM"
    kdf: Literal["HKDF-SHA256"] = "HKDF-SHA256"
    visibility: Literal["PRIVATE"] = "PRIVATE"
    document_type: Literal["LOAN_AGREEMENT", "CREDIT_REPORT", "COLLATERAL_PROOF"]
    content_type: str
    original_filename: str
    owner_wallet: str
    key_id: str
    key_salt_b64: str
    nonce_b64: str
    aad_b64: str
    ciphertext_b64: str
    plaintext_size_bytes: int = Field(..., ge=0)
    plaintext_sha256: str
    created_at_utc: str


# ==============================================================================
# 5. SAMPLE FIXTURE BUILDERS (MATCHING HI01 DEMO 1000 -> 500 & Q01 WALLET #2)
# ==============================================================================
SAMPLE_BORROWER_A_WALLET = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"  # Q01 Account #2
SAMPLE_LENDER_A_WALLET = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"   # Q01 Account #1
SAMPLE_BORROWER_B_WALLET = "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc"  # Q01 Account #5
SAMPLE_ADMIN_WALLET = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"       # Q01 Account #0


def build_sample_loan_agreement(
    *,
    borrower_wallet: str = SAMPLE_BORROWER_A_WALLET,
    collateral_valuation_usdt: int = 1_000,
    principal_usdt: int = 500,
    utilization_bps: int = 5_000,
    created_at: datetime | None = None,
) -> LoanAgreementPayload:
    """Build a valid SIMULATED sample Loan Agreement aligned with HI01 Demo (1000 -> 500)."""
    now_utc = created_at or datetime(2026, 11, 26, 12, 0, 0, tzinfo=timezone.utc)
    now_vn = now_utc.astimezone(_VN_TZ)

    collateral_wad = collateral_valuation_usdt * c.WAD
    principal_wad = principal_usdt * c.WAD
    requested_ltv_bps = (principal_wad * c.BPS) // collateral_wad
    borrow_apr_bps = c.calculate_borrow_apr_bps(utilization_bps)

    return LoanAgreementPayload(
        data_kind="SIMULATED",
        agreement_id="DEFI-LA-2026-0001-SAMPLE",
        agreement_nonce="sample-nonce-h03-demo-1000-to-500",
        created_at_utc=now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        created_at_vn=now_vn.strftime("%Y-%m-%d %H:%M:%S UTC+07:00"),
        network="local",
        chain_id=31337,
        lending_pool_address=None,
        borrower_wallet=borrower_wallet,
        wallet_auth_signature="SIMULATED_EIP191_NONCE_VERIFIED_SESSION",
        collateral=LoanCollateralInfo(
            asset_type="ERC721",
            token_address=None,
            asset_id_or_amount="1",
            receipt_token_id="1",
            valuation_wad=str(collateral_wad),
            valuation_display=c.wad_to_decimal_str(collateral_wad),
            asset_description="Tokenized Digital Asset CollateralNFT #1 (Sample Valuation 1,000 MyUSDT)",
        ),
        loan_terms=LoanTermsInfo(
            principal_wad=str(principal_wad),
            principal_display=c.wad_to_decimal_str(principal_wad),
            requested_ltv_bps=requested_ltv_bps,
            max_ltv_bps=c.MAX_LTV_BPS,
            liquidation_threshold_bps=c.LIQUIDATION_THRESHOLD_BPS,
            liquidation_bonus_bps=c.LIQUIDATION_BONUS_BPS,
            borrow_apr_bps=borrow_apr_bps,
            borrow_apr_percent=c.apr_bps_to_percent(borrow_apr_bps),
            borrow_apy_percent=c.apr_bps_to_apy_percent(borrow_apr_bps),
        ),
        status="PRE_BORROW_UNSIGNED",
        tx_hash=None,
    )


def build_sample_credit_report(
    *,
    wallet_address: str = SAMPLE_BORROWER_A_WALLET,
    generated_at: datetime | None = None,
) -> CreditReportDocument:
    """Build a valid SIMULATED sample Credit Report JSON matching H03 & HI01 specs."""
    now_utc = generated_at or datetime(2026, 11, 26, 12, 5, 0, tzinfo=timezone.utc)
    loan1_principal = 500 * c.WAD
    loan1_repaid = 508_219_178_082_191_780_821  # Exact 60-day repayment from HI01 spec
    loan2_principal = 300 * c.WAD
    loan2_repaid = 302_465_753_424_657_534_246

    total_borrowed = loan1_principal + loan2_principal
    total_repaid = loan1_repaid + loan2_repaid

    return CreditReportDocument(
        data_kind="SIMULATED",
        generated_at_utc=now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        network="local",
        chain_id=31337,
        wallet_address=wallet_address,
        summary=CreditReportSummary(
            total_loans=2,
            repaid_on_time_count=2,
            active_loans_count=0,
            liquidation_count=0,
            total_borrowed_wad=str(total_borrowed),
            total_borrowed_display=c.wad_to_decimal_str(total_borrowed),
            total_repaid_wad=str(total_repaid),
            total_repaid_display=c.wad_to_decimal_str(total_repaid),
            current_debt_wad="0",
            current_debt_display="0.000000",
            on_time_repayment_ratio_bps=c.BPS,
        ),
        credit_score=CreditScoreInfo(
            score=760,
            tier="VERY_GOOD",
            rationale=(
                "SIMULATED sample score: 2/2 on-time repayments, 0 liquidations, "
                "0 active overdue debt (real score computed from on-chain events in Q04)."
            ),
        ),
        loan_ids=["LOAN-SAMPLE-001", "LOAN-SAMPLE-002"],
        loans=[
            CreditLoanRecord(
                loan_id="LOAN-SAMPLE-001",
                agreement_cid=None,
                principal_wad=str(loan1_principal),
                principal_display=c.wad_to_decimal_str(loan1_principal),
                repaid_wad=str(loan1_repaid),
                repaid_display=c.wad_to_decimal_str(loan1_repaid),
                status="REPAID_ON_TIME",
                borrowed_at_utc="2026-08-01T09:00:00Z",
                closed_at_utc="2026-09-30T09:00:00Z",
                borrow_tx_hash=None,
                repay_or_liquidate_tx_hash=None,
            ),
            CreditLoanRecord(
                loan_id="LOAN-SAMPLE-002",
                agreement_cid=None,
                principal_wad=str(loan2_principal),
                principal_display=c.wad_to_decimal_str(loan2_principal),
                repaid_wad=str(loan2_repaid),
                repaid_display=c.wad_to_decimal_str(loan2_repaid),
                status="REPAID_ON_TIME",
                borrowed_at_utc="2026-10-05T10:30:00Z",
                closed_at_utc="2026-11-04T10:30:00Z",
                borrow_tx_hash=None,
                repay_or_liquidate_tx_hash=None,
            ),
        ],
    )


def build_sample_audit_logs(*, generated_at: datetime | None = None) -> AuditLogsDocument:
    """Build a 6-month SIMULATED Audit Logs fixture verified against HI01 constants."""
    now_utc = generated_at or datetime(2026, 11, 26, 12, 10, 0, tzinfo=timezone.utc)
    monthly_snapshots = [
        ("2026-06", "2026-06-30T23:59:59Z", 1_000, 200, "SIMULATED seed month 1 (low utilization)"),
        ("2026-07", "2026-07-31T23:59:59Z", 1_500, 450, "SIMULATED seed month 2 (growing borrowing)"),
        ("2026-08", "2026-08-31T23:59:59Z", 2_000, 1_000, "SIMULATED seed month 3 (50% target utilization)"),
        ("2026-09", "2026-09-30T23:59:59Z", 2_500, 1_500, "SIMULATED seed month 4 (60% utilization)"),
        ("2026-10", "2026-10-31T23:59:59Z", 3_000, 2_100, "SIMULATED seed month 5 (70% utilization)"),
        ("2026-11", "2026-11-26T12:00:00Z", 1_000, 500, "SIMULATED seed month 6 (Demo 1000->500 baseline)"),
    ]

    entries: List[AuditLogEntry] = []
    for period, recorded_at, supplied_usdt, borrowed_usdt, note in monthly_snapshots:
        supplied_wad = supplied_usdt * c.WAD
        borrowed_wad = borrowed_usdt * c.WAD
        available_wad = supplied_wad - borrowed_wad
        util_bps = c.calculate_utilization_bps(borrowed_wad, supplied_wad)
        borrow_apr_bps = c.calculate_borrow_apr_bps(util_bps)
        supply_apr_bps = c.calculate_supply_apr_bps(borrow_apr_bps, util_bps)
        entries.append(
            AuditLogEntry(
                period=period,
                recorded_at_utc=recorded_at,
                data_kind="SIMULATED",
                total_supplied_wad=str(supplied_wad),
                total_supplied_display=c.wad_to_decimal_str(supplied_wad),
                total_borrowed_wad=str(borrowed_wad),
                total_borrowed_display=c.wad_to_decimal_str(borrowed_wad),
                available_liquidity_wad=str(available_wad),
                available_liquidity_display=c.wad_to_decimal_str(available_wad),
                utilization_bps=util_bps,
                utilization_percent=round(util_bps / 100.0, 2),
                borrow_apr_bps=borrow_apr_bps,
                borrow_apr_percent=c.apr_bps_to_percent(borrow_apr_bps),
                borrow_apy_percent=c.apr_bps_to_apy_percent(borrow_apr_bps),
                supply_apr_bps=supply_apr_bps,
                supply_apr_percent=c.apr_bps_to_percent(supply_apr_bps),
                supply_apy_percent=c.apr_bps_to_apy_percent(supply_apr_bps),
                event_tx_hash=None,
                notes=note,
            )
        )

    return AuditLogsDocument(
        generated_at_utc=now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        network="local",
        chain_id=31337,
        lending_pool_address=None,
        entries=entries,
    )


def export_all_json_schemas(output_dir: str | Path) -> Dict[str, Path]:
    """Export machine-readable JSON Schemas and RBAC matrix into ``output_dir``."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    schema_targets: Dict[str, Any] = {
        "loan_agreement.schema.json": LoanAgreementPayload.model_json_schema(),
        "loan_tx_binding.schema.json": LoanTxBindingRecord.model_json_schema(),
        "credit_report.schema.json": CreditReportDocument.model_json_schema(),
        "audit_logs.schema.json": AuditLogsDocument.model_json_schema(),
        "encrypted_envelope.schema.json": EncryptedEnvelopeSchema.model_json_schema(),
        "rbac_matrix.json": {
            "schema_version": SCHEMA_VERSION,
            "roles": ["GUEST", "BORROWER", "LENDER", "ADMIN"],
            "encryption": {
                "algorithm": "AES-256-GCM",
                "kdf": "HKDF-SHA256",
                "nonce_bytes": 12,
                "key_storage": "Backend-only (.env DOCUMENT_AES_KEY_HEX / KMS); never stored in IPFS CID or on-chain",
            },
            "matrix": RBAC_MATRIX,
        },
    }

    written: Dict[str, Path] = {}
    for filename, payload in schema_targets.items():
        target = out / filename
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written[filename] = target
    return written

