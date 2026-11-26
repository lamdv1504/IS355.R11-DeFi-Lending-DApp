"""RBAC Policy Matrix, Document Classification & Key-Release Guard for IPFS Records (H03).

Design handoff from Hùng (H03) to Quân (Q05 FastAPI RBAC enforcement) and Lâm (L04 IPFS Hub).
Aligned with:
- `docs/Hieu/smart_contract_spec.md` §5.1 (On-chain <-> IPFS & RBAC)
- `docs/Lam/ui_wireframes.md` §6 (Role Matrix)
- `docs/Lam/l01_api_contract.md` §6 (Nonce auth, 401/403 status codes)

Core principle:
IPFS is a content-addressed public network — knowing a CID NEVER grants plaintext access to
private documents. Private documents are encrypted with AES-256-GCM before upload; decryption
keys / plaintext are only released by the Backend after verifying a wallet-signed nonce session
and enforcing RBAC + resource ownership.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, FrozenSet, Iterable, List, Optional

from src.ipfs.encryption import (
    DocumentEncryptor,
    EncryptedEnvelope,
    normalize_wallet_address,
)
from src.ipfs.ipfs_client import IPFSClient, RetrieveResult, UploadResult


class Role(str, Enum):
    """Canonical RBAC roles shared across H03, Q05, and L04."""

    GUEST = "GUEST"
    BORROWER = "BORROWER"
    LENDER = "LENDER"
    ADMIN = "ADMIN"


class DocumentType(str, Enum):
    """Supported IPFS document categories (Rubric TC3 + optional collateral proof image)."""

    LOAN_AGREEMENT = "LOAN_AGREEMENT"
    CREDIT_REPORT = "CREDIT_REPORT"
    AUDIT_LOGS = "AUDIT_LOGS"
    COLLATERAL_PROOF = "COLLATERAL_PROOF"


class DocumentVisibility(str, Enum):
    """Public vs Private classification for IPFS records."""

    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"


class AccessAction(str, Enum):
    """Actions guarded by RBAC policy."""

    UPLOAD = "UPLOAD"
    RETRIEVE_CIPHERTEXT = "RETRIEVE_CIPHERTEXT"
    RETRIEVE_PLAINTEXT = "RETRIEVE_PLAINTEXT"
    REQUEST_DECRYPTION_KEY = "REQUEST_DECRYPTION_KEY"
    LIST_METADATA = "LIST_METADATA"


DOCUMENT_CLASSIFICATION: Dict[DocumentType, Dict[str, Any]] = {
    DocumentType.LOAN_AGREEMENT: {
        "visibility": DocumentVisibility.PRIVATE,
        "encryption_required": True,
        "default_content_type": "application/pdf",
        "formats": ["PDF"],
        "allowed_readers": ["OWNER_BORROWER", "ADMIN"],
        "description": (
            "Thỏa thuận vay vốn phi tập trung (PDF) sinh trước khi ký borrow(); "
            "mã hóa AES-256-GCM trước khi upload IPFS, đối chiếu CID <-> Loan <-> txHash sau xác nhận."
        ),
    },
    DocumentType.CREDIT_REPORT: {
        "visibility": DocumentVisibility.PRIVATE,
        "encryption_required": True,
        "default_content_type": "application/json",
        "formats": ["JSON"],
        "allowed_readers": ["OWNER_BORROWER", "ADMIN"],
        "description": (
            "Báo cáo tín dụng on-chain (JSON, điểm 300-850); BẮT BUỘC mã hóa AES-256-GCM "
            "trước khi upload IPFS. Ví khác không có quyền bị chặn HTTP 403."
        ),
    },
    DocumentType.AUDIT_LOGS: {
        "visibility": DocumentVisibility.PUBLIC,
        "encryption_required": False,
        "default_content_type": "application/json",
        "formats": ["JSON", "CSV"],
        "allowed_readers": ["GUEST", "BORROWER", "LENDER", "ADMIN"],
        "description": (
            "Nhật ký kiểm toán biến động lãi suất hàng tháng toàn Pool (chỉ số tổng hợp công khai, "
            "không chứa dữ liệu cá nhân hay khóa bí mật; dữ liệu seed gắn nhãn SIMULATED)."
        ),
    },
    DocumentType.COLLATERAL_PROOF: {
        "visibility": DocumentVisibility.PRIVATE,
        "encryption_required": True,
        "default_content_type": "image/png",
        "formats": ["PNG", "JPEG"],
        "allowed_readers": ["OWNER_BORROWER", "ADMIN"],
        "description": (
            "Ảnh minh chứng tài sản thế chấp số hóa (tùy chọn, bổ sung định dạng hình ảnh "
            "cùng PDF/JSON); mã hóa AES-256-GCM trước khi đẩy lên IPFS."
        ),
    },
}

RBAC_MATRIX: List[Dict[str, Any]] = [
    {
        "resource": "Audit Logs (JSON/CSV)",
        "document_type": DocumentType.AUDIT_LOGS.value,
        "visibility": DocumentVisibility.PUBLIC.value,
        "encrypted_on_ipfs": False,
        "guest": "ALLOW (200)",
        "lender": "ALLOW (200)",
        "borrower_owner": "ALLOW (200)",
        "borrower_other": "ALLOW (200)",
        "admin": "ALLOW (200)",
        "notes": "Chỉ chứa chỉ số tổng hợp Pool (APR/APY/Utilization/TVL); không chứa PII hay secret.",
    },
    {
        "resource": "Loan Agreement (PDF) – Bản rõ / Giải mã",
        "document_type": DocumentType.LOAN_AGREEMENT.value,
        "visibility": DocumentVisibility.PRIVATE.value,
        "encrypted_on_ipfs": True,
        "guest": "DENY (401)",
        "lender": "DENY (403)",
        "borrower_owner": "ALLOW (200)",
        "borrower_other": "DENY (403)",
        "admin": "ALLOW (200)",
        "notes": "Lender không mặc nhiên xem thỏa thuận vay riêng của Borrower; cần phiên ký nonce ví.",
    },
    {
        "resource": "Credit Report (JSON) – Bản rõ / Giải mã",
        "document_type": DocumentType.CREDIT_REPORT.value,
        "visibility": DocumentVisibility.PRIVATE.value,
        "encrypted_on_ipfs": True,
        "guest": "DENY (401)",
        "lender": "DENY (403)",
        "borrower_owner": "ALLOW (200)",
        "borrower_other": "DENY (403)",
        "admin": "ALLOW (200)",
        "notes": "Bắt buộc mã hóa AES-256-GCM trước khi upload IPFS; biết CID chỉ tải được bản mã.",
    },
    {
        "resource": "Collateral Proof (PNG) – Tùy chọn",
        "document_type": DocumentType.COLLATERAL_PROOF.value,
        "visibility": DocumentVisibility.PRIVATE.value,
        "encrypted_on_ipfs": True,
        "guest": "DENY (401)",
        "lender": "DENY (403)",
        "borrower_owner": "ALLOW (200)",
        "borrower_other": "DENY (403)",
        "admin": "ALLOW (200)",
        "notes": "Minh chứng định dạng ảnh thứ 3 (tùy chọn); bảo vệ cùng chính sách chủ sở hữu/Admin.",
    },
    {
        "resource": "Raw Ciphertext qua Public IPFS Gateway (biết CID)",
        "document_type": "PRIVATE_ENVELOPE",
        "visibility": "CIPHERTEXT_ONLY",
        "encrypted_on_ipfs": True,
        "guest": "CIPHERTEXT ONLY (No Key)",
        "lender": "CIPHERTEXT ONLY (No Key)",
        "borrower_owner": "CIPHERTEXT ONLY (Decrypt via Auth Backend)",
        "borrower_other": "CIPHERTEXT ONLY (No Key)",
        "admin": "CIPHERTEXT ONLY (Decrypt via Auth Backend)",
        "notes": "Khóa AES-256-GCM quản lý tại Backend; không bao giờ xuất hiện trong CID hay on-chain.",
    },
]


class AccessDeniedError(PermissionError):
    """Raised when an IPFS access request fails authentication (401) or authorization (403)."""

    def __init__(self, http_status: int, reason: str) -> None:
        super().__init__(f"HTTP {http_status}: {reason}")
        self.http_status = http_status
        self.reason = reason


@dataclass(frozen=True)
class AccessContext:
    """Server-verified session identity (produced by Q05 wallet-signature nonce verification)."""

    authenticated: bool
    wallet_address: Optional[str] = None
    roles: FrozenSet[Role] = frozenset({Role.GUEST})
    session_id: Optional[str] = None
    chain_id: Optional[int] = None

    @classmethod
    def guest(cls) -> "AccessContext":
        return cls(authenticated=False, wallet_address=None, roles=frozenset({Role.GUEST}))

    @classmethod
    def for_wallet(
        cls,
        wallet_address: str,
        roles: Iterable[Role],
        *,
        session_id: str = "verified-session",
        chain_id: int = 31337,
    ) -> "AccessContext":
        norm_addr = normalize_wallet_address(wallet_address)
        role_set = frozenset(roles)
        if not role_set or role_set == frozenset({Role.GUEST}):
            raise ValueError("Authenticated wallet context must include at least one non-GUEST role")
        return cls(
            authenticated=True,
            wallet_address=norm_addr,
            roles=role_set,
            session_id=session_id,
            chain_id=chain_id,
        )


@dataclass(frozen=True)
class DocumentAccessMetadata:
    """Backend ACL metadata binding a CID to its document type, visibility, owner, and hashes."""

    cid: str
    document_type: DocumentType
    visibility: DocumentVisibility
    owner_wallet: Optional[str]
    encrypted: bool
    content_type: str
    filename: str
    plaintext_sha256: str
    ciphertext_sha256: Optional[str] = None
    key_id: Optional[str] = None

    def normalized_owner(self) -> Optional[str]:
        if not self.owner_wallet:
            return None
        return normalize_wallet_address(self.owner_wallet)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cid": self.cid,
            "document_type": self.document_type.value,
            "visibility": self.visibility.value,
            "owner_wallet": self.normalized_owner(),
            "encrypted": self.encrypted,
            "content_type": self.content_type,
            "filename": self.filename,
            "plaintext_sha256": self.plaintext_sha256,
            "ciphertext_sha256": self.ciphertext_sha256,
            "key_id": self.key_id,
        }


@dataclass(frozen=True)
class AccessDecision:
    """Explicit RBAC evaluation result returned to Backend API (Q05)."""

    allowed: bool
    http_status: int
    reason: str
    can_release_key: bool = False
    can_decrypt_plaintext: bool = False


@dataclass(frozen=True)
class AuthorizedDocumentResult:
    """Verified (and decrypted if private) document payload returned after RBAC passes."""

    cid: str
    document_type: DocumentType
    visibility: DocumentVisibility
    content: bytes
    content_type: str
    filename: str
    plaintext_sha256: str
    decrypted: bool
    provider_used: str
    decision: AccessDecision


def authorize_document_access(
    context: AccessContext,
    metadata: DocumentAccessMetadata,
    action: AccessAction = AccessAction.RETRIEVE_PLAINTEXT,
) -> AccessDecision:
    """Evaluate RBAC & ownership rules for an IPFS document operation.

    - Public documents (e.g. ``AUDIT_LOGS``): readable by all roles (200), upload restricted to ADMIN.
    - Private documents (``CREDIT_REPORT``, ``LOAN_AGREEMENT``, ``COLLATERAL_PROOF``):
      - Unauthenticated caller -> 401 UNAUTHORIZED
      - Authenticated owner (wallet matches ``owner_wallet``) or ADMIN -> 200 ALLOWED
      - Any other authenticated role (LENDER, another BORROWER) -> 403 FORBIDDEN
    """
    is_admin = context.authenticated and Role.ADMIN in context.roles

    # Public read operations
    if metadata.visibility == DocumentVisibility.PUBLIC and action in (
        AccessAction.RETRIEVE_PLAINTEXT,
        AccessAction.RETRIEVE_CIPHERTEXT,
        AccessAction.LIST_METADATA,
    ):
        return AccessDecision(
            allowed=True,
            http_status=200,
            reason="PUBLIC_DOCUMENT_ALLOWED",
            can_release_key=False,
            can_decrypt_plaintext=True,
        )

    # Raw ciphertext access reflects IPFS network reality: ciphertext is readable, key is NEVER released
    if action == AccessAction.RETRIEVE_CIPHERTEXT and metadata.encrypted:
        return AccessDecision(
            allowed=True,
            http_status=200,
            reason="CIPHERTEXT_ONLY_NO_KEY_RELEASED",
            can_release_key=False,
            can_decrypt_plaintext=False,
        )

    # All private actions & uploads require an authenticated wallet-signed session
    if not context.authenticated or not context.wallet_address:
        return AccessDecision(
            allowed=False,
            http_status=401,
            reason="AUTHENTICATION_REQUIRED_SIGN_NONCE_WITH_METAMASK",
            can_release_key=False,
            can_decrypt_plaintext=False,
        )

    caller_wallet = normalize_wallet_address(context.wallet_address)
    owner_wallet = metadata.normalized_owner()

    if action == AccessAction.UPLOAD:
        if metadata.document_type == DocumentType.AUDIT_LOGS:
            if is_admin:
                return AccessDecision(True, 200, "ADMIN_AUDIT_LOG_UPLOAD_ALLOWED", False, False)
            return AccessDecision(False, 403, "ONLY_ADMIN_MAY_PUBLISH_AUDIT_LOGS", False, False)
        if is_admin or (owner_wallet is not None and caller_wallet == owner_wallet):
            return AccessDecision(True, 200, "OWNER_OR_ADMIN_UPLOAD_ALLOWED", False, False)
        return AccessDecision(False, 403, "FORBIDDEN_CANNOT_UPLOAD_FOR_ANOTHER_WALLET", False, False)

    # Private read / decryption key release / metadata listing
    if is_admin:
        return AccessDecision(
            allowed=True,
            http_status=200,
            reason="ADMIN_ROLE_AUTHORIZED",
            can_release_key=metadata.encrypted,
            can_decrypt_plaintext=True,
        )

    if owner_wallet is not None and caller_wallet == owner_wallet:
        return AccessDecision(
            allowed=True,
            http_status=200,
            reason="DOCUMENT_OWNER_AUTHORIZED",
            can_release_key=metadata.encrypted,
            can_decrypt_plaintext=True,
        )

    return AccessDecision(
        allowed=False,
        http_status=403,
        reason="FORBIDDEN_NOT_DOCUMENT_OWNER_OR_ADMIN",
        can_release_key=False,
        can_decrypt_plaintext=False,
    )


class AuthorizedIPFSGateway:
    """Combines ``IPFSClient``, ``DocumentEncryptor``, and RBAC policy enforcement.

    Ensures private documents are ALWAYS encrypted before touching IPFS and can only be decrypted
    when ``authorize_document_access`` returns ``allowed=True`` (200).
    """

    def __init__(
        self,
        ipfs_client: IPFSClient,
        encryptor: DocumentEncryptor,
    ) -> None:
        self.ipfs_client = ipfs_client
        self.encryptor = encryptor
        self._acl_registry: Dict[str, DocumentAccessMetadata] = {}

    def register_metadata(self, metadata: DocumentAccessMetadata) -> None:
        self._acl_registry[metadata.cid] = metadata

    def get_metadata(self, cid: str) -> Optional[DocumentAccessMetadata]:
        return self._acl_registry.get(cid.strip())

    def upload_document(
        self,
        plaintext: bytes,
        *,
        document_type: DocumentType,
        filename: str,
        content_type: str | None = None,
        owner_wallet: str | None = None,
        visibility: DocumentVisibility | None = None,
        extra_metadata: Dict[str, Any] | None = None,
    ) -> tuple[UploadResult, DocumentAccessMetadata, Optional[EncryptedEnvelope]]:
        """Classify, optionally encrypt (AES-256-GCM), pin to IPFS, and register ACL metadata."""
        policy = DOCUMENT_CLASSIFICATION[document_type]
        resolved_visibility = visibility or policy["visibility"]
        resolved_content_type = content_type or policy["default_content_type"]
        must_encrypt = bool(policy["encryption_required"] or resolved_visibility == DocumentVisibility.PRIVATE)

        if must_encrypt and not owner_wallet:
            raise ValueError(
                f"Private document {document_type.value} requires an explicit owner_wallet for encryption & RBAC"
            )

        plaintext_sha256 = self.ipfs_client.compute_sha256(plaintext)
        pin_meta: Dict[str, Any] = {
            "document_type": document_type.value,
            "visibility": resolved_visibility.value,
            "encrypted": str(must_encrypt).lower(),
        }
        if extra_metadata:
            pin_meta.update(extra_metadata)

        envelope: Optional[EncryptedEnvelope] = None
        if must_encrypt:
            assert owner_wallet is not None
            envelope = self.encryptor.encrypt_bytes(
                plaintext,
                document_type=document_type.value,
                owner_wallet=owner_wallet,
                original_filename=filename,
                content_type=resolved_content_type,
                visibility=resolved_visibility.value,
            )
            payload_bytes = envelope.to_json_bytes()
            upload_filename = f"{filename}.encrypted.json"
            upload_content_type = "application/json"
            upload_result = self.ipfs_client.upload_bytes(
                payload_bytes,
                filename=upload_filename,
                content_type=upload_content_type,
                metadata=pin_meta,
                is_encrypted=True,
            )
            acl = DocumentAccessMetadata(
                cid=upload_result.cid,
                document_type=document_type,
                visibility=resolved_visibility,
                owner_wallet=normalize_wallet_address(owner_wallet),
                encrypted=True,
                content_type=resolved_content_type,
                filename=filename,
                plaintext_sha256=plaintext_sha256,
                ciphertext_sha256=upload_result.sha256,
                key_id=self.encryptor.key_id,
            )
        else:
            upload_result = self.ipfs_client.upload_bytes(
                plaintext,
                filename=filename,
                content_type=resolved_content_type,
                metadata=pin_meta,
                is_encrypted=False,
            )
            acl = DocumentAccessMetadata(
                cid=upload_result.cid,
                document_type=document_type,
                visibility=resolved_visibility,
                owner_wallet=normalize_wallet_address(owner_wallet) if owner_wallet else None,
                encrypted=False,
                content_type=resolved_content_type,
                filename=filename,
                plaintext_sha256=plaintext_sha256,
                ciphertext_sha256=None,
                key_id=None,
            )

        self.register_metadata(acl)
        return upload_result, acl, envelope

    def retrieve_raw_by_cid(self, cid: str) -> RetrieveResult:
        """Fetch raw stored bytes directly from IPFS by CID (returns ciphertext for private docs)."""
        return self.ipfs_client.retrieve_bytes(cid, verify_cid=True)

    def retrieve_authorized_document(
        self,
        cid: str,
        context: AccessContext,
        *,
        metadata: DocumentAccessMetadata | None = None,
    ) -> AuthorizedDocumentResult:
        """Enforce RBAC before fetching and decrypting a document by CID."""
        acl = metadata or self.get_metadata(cid)
        if acl is None:
            raise AccessDeniedError(403, "UNKNOWN_DOCUMENT_ACL_DEFAULT_DENY")

        decision = authorize_document_access(context, acl, AccessAction.RETRIEVE_PLAINTEXT)
        if not decision.allowed:
            raise AccessDeniedError(decision.http_status, decision.reason)

        expected_ipfs_sha = acl.ciphertext_sha256 if acl.encrypted else acl.plaintext_sha256
        retrieved = self.ipfs_client.retrieve_bytes(
            acl.cid,
            expected_sha256=expected_ipfs_sha,
            verify_cid=True,
        )

        if acl.encrypted:
            plaintext = self.encryptor.decrypt_envelope(
                retrieved.content,
                expected_owner_wallet=acl.normalized_owner(),
                expected_document_type=acl.document_type.value,
            )
            decrypted = True
        else:
            plaintext = retrieved.content
            decrypted = False

        actual_plain_sha = self.ipfs_client.compute_sha256(plaintext)
        if actual_plain_sha != acl.plaintext_sha256:
            raise AccessDeniedError(500, "PLAINTEXT_HASH_MISMATCH")

        return AuthorizedDocumentResult(
            cid=acl.cid,
            document_type=acl.document_type,
            visibility=acl.visibility,
            content=plaintext,
            content_type=acl.content_type,
            filename=acl.filename,
            plaintext_sha256=actual_plain_sha,
            decrypted=decrypted,
            provider_used=retrieved.provider_used,
            decision=decision,
        )

