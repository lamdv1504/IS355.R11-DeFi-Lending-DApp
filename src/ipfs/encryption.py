"""AES-256-GCM document encryption and authenticated envelope helpers for private IPFS records (H03).

Security invariants (Rubric TC2 & TC3):
1. Private IPFS records (Credit Report JSON, private Loan Agreement PDF, optional collateral proof)
   MUST be encrypted with AES-256-GCM before upload to IPFS.
2. Each encryption uses a fresh cryptographically random 96-bit (12-byte) IV/nonce and a per-document
   256-bit Data Encryption Key (DEK) derived via HKDF-SHA256 from the backend master key + random salt.
3. Additional Authenticated Data (AAD) binds document_type, owner_wallet, visibility, and schema_version
   so ciphertext cannot be transplanted across documents or owners.
4. Encryption keys and plaintext are NEVER stored in the IPFS CID payload or public pin metadata.
"""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.ipfs.cid_utils import sha256_bytes

AES_256_KEY_BYTES = 32
GCM_NONCE_BYTES = 12
HKDF_SALT_BYTES = 16
ENVELOPE_SCHEMA_VERSION = "1.0"
ENVELOPE_ALGORITHM = "AES-256-GCM"
ENVELOPE_KDF = "HKDF-SHA256"

_ETH_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_FORBIDDEN_ENVELOPE_KEYS = frozenset(
    {
        "key",
        "aes_key",
        "master_key",
        "dek",
        "decryption_key",
        "private_key",
        "secret",
        "plaintext",
    }
)


class EncryptionError(Exception):
    """Raised when document encryption input or key configuration is invalid."""


class DecryptionError(Exception):
    """Raised when decryption, authentication tag verification, or integrity verification fails."""


def normalize_wallet_address(wallet_address: str) -> str:
    """Validate and normalize an Ethereum wallet address to lowercase ``0x...`` format."""
    cleaned = wallet_address.strip()
    if not _ETH_ADDRESS_RE.match(cleaned):
        raise ValueError(f"Invalid Ethereum wallet address: {wallet_address!r}")
    return cleaned.lower()


def parse_hex_aes_key(hex_key: str) -> bytes:
    """Parse a 64-character hex string (optional ``0x`` prefix) into a 32-byte AES-256 key."""
    cleaned = hex_key.strip()
    if cleaned.lower().startswith("0x"):
        cleaned = cleaned[2:]
    try:
        key_bytes = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise EncryptionError("AES key must be valid hexadecimal") from exc
    if len(key_bytes) != AES_256_KEY_BYTES:
        raise EncryptionError(
            f"AES-256 key must be exactly {AES_256_KEY_BYTES} bytes (64 hex chars), "
            f"got {len(key_bytes)} bytes"
        )
    return key_bytes


@dataclass(frozen=True)
class EncryptedEnvelope:
    """Publicly safe JSON envelope stored on IPFS for private documents.

    Contains ONLY ciphertext, authentication parameters (nonce, salt, AAD), and safe metadata.
    Never embeds encryption keys or plaintext.
    """

    schema_version: str
    encrypted: bool
    algorithm: str
    kdf: str
    visibility: str
    document_type: str
    content_type: str
    original_filename: str
    owner_wallet: str
    key_id: str
    key_salt_b64: str
    nonce_b64: str
    aad_b64: str
    ciphertext_b64: str
    plaintext_size_bytes: int
    plaintext_sha256: str
    created_at_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "encrypted": self.encrypted,
            "algorithm": self.algorithm,
            "kdf": self.kdf,
            "visibility": self.visibility,
            "document_type": self.document_type,
            "content_type": self.content_type,
            "original_filename": self.original_filename,
            "owner_wallet": self.owner_wallet,
            "key_id": self.key_id,
            "key_salt_b64": self.key_salt_b64,
            "nonce_b64": self.nonce_b64,
            "aad_b64": self.aad_b64,
            "ciphertext_b64": self.ciphertext_b64,
            "plaintext_size_bytes": self.plaintext_size_bytes,
            "plaintext_sha256": self.plaintext_sha256,
            "created_at_utc": self.created_at_utc,
        }

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "EncryptedEnvelope":
        if not isinstance(raw, dict):
            raise DecryptionError("Encrypted envelope must be a JSON object")

        leaked_fields = _FORBIDDEN_ENVELOPE_KEYS.intersection(raw.keys())
        if leaked_fields:
            raise DecryptionError(
                f"Security violation: envelope contains forbidden secret fields: {sorted(leaked_fields)}"
            )

        required = {
            "schema_version",
            "encrypted",
            "algorithm",
            "kdf",
            "visibility",
            "document_type",
            "content_type",
            "original_filename",
            "owner_wallet",
            "key_id",
            "key_salt_b64",
            "nonce_b64",
            "aad_b64",
            "ciphertext_b64",
            "plaintext_size_bytes",
            "plaintext_sha256",
            "created_at_utc",
        }
        missing = required - set(raw.keys())
        if missing:
            raise DecryptionError(f"Encrypted envelope missing required fields: {sorted(missing)}")

        if raw["encrypted"] is not True or raw["algorithm"] != ENVELOPE_ALGORITHM:
            raise DecryptionError(
                f"Unsupported envelope encryption config: encrypted={raw['encrypted']!r}, "
                f"algorithm={raw['algorithm']!r}"
            )

        return cls(
            schema_version=str(raw["schema_version"]),
            encrypted=True,
            algorithm=str(raw["algorithm"]),
            kdf=str(raw["kdf"]),
            visibility=str(raw["visibility"]),
            document_type=str(raw["document_type"]),
            content_type=str(raw["content_type"]),
            original_filename=str(raw["original_filename"]),
            owner_wallet=normalize_wallet_address(str(raw["owner_wallet"])),
            key_id=str(raw["key_id"]),
            key_salt_b64=str(raw["key_salt_b64"]),
            nonce_b64=str(raw["nonce_b64"]),
            aad_b64=str(raw["aad_b64"]),
            ciphertext_b64=str(raw["ciphertext_b64"]),
            plaintext_size_bytes=int(raw["plaintext_size_bytes"]),
            plaintext_sha256=str(raw["plaintext_sha256"]).lower(),
            created_at_utc=str(raw["created_at_utc"]),
        )

    @classmethod
    def from_json_bytes(cls, payload: bytes) -> "EncryptedEnvelope":
        try:
            parsed = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise DecryptionError("Failed to parse encrypted IPFS envelope JSON") from exc
        return cls.from_dict(parsed)


class DocumentEncryptor:
    """Backend AES-256-GCM + HKDF-SHA256 encryptor for private IPFS documents."""

    def __init__(self, master_key: bytes, key_id: str = "backend-master-v1") -> None:
        if len(master_key) != AES_256_KEY_BYTES:
            raise EncryptionError(
                f"Master key must be {AES_256_KEY_BYTES} bytes, got {len(master_key)} bytes"
            )
        if not key_id.strip():
            raise EncryptionError("key_id must be non-empty")
        self._master_key = master_key
        self._key_id = key_id.strip()

    @property
    def key_id(self) -> str:
        return self._key_id

    @classmethod
    def from_hex_key(cls, hex_key: str, key_id: str = "backend-master-v1") -> "DocumentEncryptor":
        return cls(parse_hex_aes_key(hex_key), key_id=key_id)

    @classmethod
    def from_env(
        cls,
        env_var: str = "DOCUMENT_AES_KEY_HEX",
        key_id: str = "backend-master-v1",
    ) -> "DocumentEncryptor":
        raw_hex = os.getenv(env_var, "").strip()
        if not raw_hex:
            raise EncryptionError(
                f"Environment variable {env_var} is not set. Configure a 64-hex-char "
                f"AES-256 key in `.env` (never commit `.env` to GitHub)."
            )
        return cls.from_hex_key(raw_hex, key_id=key_id)

    def derive_document_key(
        self,
        *,
        salt: bytes,
        document_type: str,
        owner_wallet: str,
    ) -> bytes:
        """Derive a unique 256-bit Data Encryption Key (DEK) bound to salt, doc type & owner."""
        if len(salt) != HKDF_SALT_BYTES:
            raise EncryptionError(f"HKDF salt must be {HKDF_SALT_BYTES} bytes")
        normalized_owner = normalize_wallet_address(owner_wallet)
        info = f"is355-defi-lending:ipfs-dek:v1:{document_type}:{normalized_owner}".encode("utf-8")
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=AES_256_KEY_BYTES,
            salt=salt,
            info=info,
        )
        return hkdf.derive(self._master_key)

    def encrypt_bytes(
        self,
        plaintext: bytes,
        *,
        document_type: str,
        owner_wallet: str,
        original_filename: str,
        content_type: str = "application/octet-stream",
        visibility: str = "PRIVATE",
        extra_aad: Dict[str, Any] | None = None,
    ) -> EncryptedEnvelope:
        """Encrypt ``plaintext`` into an authenticated AES-256-GCM ``EncryptedEnvelope``."""
        if not isinstance(plaintext, (bytes, bytearray)):
            raise EncryptionError("plaintext must be bytes")
        raw_bytes = bytes(plaintext)
        normalized_owner = normalize_wallet_address(owner_wallet)

        salt = os.urandom(HKDF_SALT_BYTES)
        nonce = os.urandom(GCM_NONCE_BYTES)
        dek = self.derive_document_key(
            salt=salt,
            document_type=document_type,
            owner_wallet=normalized_owner,
        )

        aad_obj: Dict[str, Any] = {
            "schema_version": ENVELOPE_SCHEMA_VERSION,
            "document_type": document_type,
            "owner_wallet": normalized_owner,
            "visibility": visibility,
            "key_id": self._key_id,
        }
        if extra_aad:
            aad_obj["extra"] = extra_aad
        aad_bytes = json.dumps(aad_obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

        aesgcm = AESGCM(dek)
        ciphertext = aesgcm.encrypt(nonce, raw_bytes, aad_bytes)

        return EncryptedEnvelope(
            schema_version=ENVELOPE_SCHEMA_VERSION,
            encrypted=True,
            algorithm=ENVELOPE_ALGORITHM,
            kdf=ENVELOPE_KDF,
            visibility=visibility,
            document_type=document_type,
            content_type=content_type,
            original_filename=original_filename,
            owner_wallet=normalized_owner,
            key_id=self._key_id,
            key_salt_b64=base64.b64encode(salt).decode("ascii"),
            nonce_b64=base64.b64encode(nonce).decode("ascii"),
            aad_b64=base64.b64encode(aad_bytes).decode("ascii"),
            ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"),
            plaintext_size_bytes=len(raw_bytes),
            plaintext_sha256=sha256_bytes(raw_bytes),
            created_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    def decrypt_envelope(
        self,
        envelope: EncryptedEnvelope | Dict[str, Any] | bytes,
        *,
        expected_owner_wallet: str | None = None,
        expected_document_type: str | None = None,
    ) -> bytes:
        """Verify AAD, decrypt ciphertext with AES-256-GCM, and check SHA-256 of plaintext."""
        if isinstance(envelope, bytes):
            env = EncryptedEnvelope.from_json_bytes(envelope)
        elif isinstance(envelope, dict):
            env = EncryptedEnvelope.from_dict(envelope)
        elif isinstance(envelope, EncryptedEnvelope):
            env = envelope
        else:
            raise DecryptionError("Unsupported envelope type")

        if env.kdf != ENVELOPE_KDF:
            raise DecryptionError(f"Unsupported KDF: {env.kdf!r}")

        if expected_owner_wallet is not None:
            norm_expected = normalize_wallet_address(expected_owner_wallet)
            if env.owner_wallet != norm_expected:
                raise DecryptionError("Envelope owner_wallet does not match expected owner")

        if expected_document_type is not None and env.document_type != expected_document_type:
            raise DecryptionError("Envelope document_type does not match expected type")

        try:
            salt = base64.b64decode(env.key_salt_b64, validate=True)
            nonce = base64.b64decode(env.nonce_b64, validate=True)
            aad_bytes = base64.b64decode(env.aad_b64, validate=True)
            ciphertext = base64.b64decode(env.ciphertext_b64, validate=True)
        except Exception as exc:
            raise DecryptionError("Malformed base64 cryptographic fields in envelope") from exc

        if len(nonce) != GCM_NONCE_BYTES:
            raise DecryptionError(f"Invalid GCM nonce length: expected {GCM_NONCE_BYTES}, got {len(nonce)}")

        # Cross-check authenticated AAD fields against outer metadata before decryption
        try:
            aad_parsed = json.loads(aad_bytes.decode("utf-8"))
        except Exception as exc:
            raise DecryptionError("Malformed AAD JSON in envelope") from exc

        if (
            aad_parsed.get("owner_wallet") != env.owner_wallet
            or aad_parsed.get("document_type") != env.document_type
            or aad_parsed.get("visibility") != env.visibility
        ):
            raise DecryptionError("Envelope metadata does not match authenticated AAD")

        dek = self.derive_document_key(
            salt=salt,
            document_type=env.document_type,
            owner_wallet=env.owner_wallet,
        )

        try:
            plaintext = AESGCM(dek).decrypt(nonce, ciphertext, aad_bytes)
        except InvalidTag as exc:
            raise DecryptionError(
                "AES-256-GCM authentication failed (wrong key, tampered ciphertext, or altered AAD)"
            ) from exc

        actual_sha256 = sha256_bytes(plaintext)
        if actual_sha256 != env.plaintext_sha256:
            raise DecryptionError(
                f"Plaintext SHA-256 mismatch after decryption: "
                f"expected={env.plaintext_sha256}, actual={actual_sha256}"
            )
        if len(plaintext) != env.plaintext_size_bytes:
            raise DecryptionError("Plaintext byte length mismatch after decryption")

        return plaintext

