"""IPFS Client with Pinata Cloud, IPFS Kubo Local Node, and Local Content-Addressed Fallback (H03).

Handoff library from Hùng (H03) to Quân (Q03, Q04, Q05) and Lâm (L04).
Supports:
- SHA-256 hashing + spec-compliant IPFS CIDv1 computation
- Uploading files, bytes, and JSON payloads to Pinata Cloud or IPFS Kubo local node
- Automatic fallback to Kubo local node or local pinned block store when offline
- Retrieving files/bytes by CID via IPFS gateways or local fallback with mandatory SHA-256 verification
"""

from __future__ import annotations

import json
import mimetypes
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.ipfs.cid_utils import (
    compute_cid_v1,
    detect_cid_version,
    is_valid_cid,
    sha256_bytes,
    verify_content_integrity,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCAL_STORE_DIR = PROJECT_ROOT / "ipfs_storage" / "local_repo"
DEFAULT_PINATA_API_URL = "https://api.pinata.cloud"
DEFAULT_PINATA_GATEWAY_URL = "https://gateway.pinata.cloud/ipfs"
DEFAULT_KUBO_API_URL = "http://127.0.0.1:5001"
DEFAULT_KUBO_GATEWAY_URL = "http://127.0.0.1:8080/ipfs"

_FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "pinata_jwt",
        "pinata_api_key",
        "pinata_secret_api_key",
        "aes_key",
        "document_aes_key_hex",
        "decryption_key",
        "private_key",
        "master_key",
        "dek",
        "secret",
    }
)


class IPFSError(Exception):
    """Base exception for IPFS client operations."""


class IPFSUploadError(IPFSError):
    """Raised when all configured IPFS upload backends fail."""


class IPFSRetrieveError(IPFSError):
    """Raised when content cannot be retrieved from any gateway or fallback store."""


class IPFSNotFoundError(IPFSRetrieveError):
    """Raised when a requested CID does not exist in any reachable store/gateway."""


class IPFSIntegrityError(IPFSError):
    """Raised when downloaded bytes fail SHA-256 or CID integrity verification."""


def _sanitize_pin_metadata(metadata: Dict[str, Any] | None) -> Dict[str, str]:
    """Validate and stringify metadata safe to attach to IPFS/Pinata pin records."""
    if not metadata:
        return {}
    cleaned: Dict[str, str] = {}
    for key, val in metadata.items():
        lowered = str(key).strip().lower()
        if lowered in _FORBIDDEN_METADATA_KEYS or "secret" in lowered or "private_key" in lowered:
            raise ValueError(f"Refusing to attach sensitive key {key!r} to public IPFS pin metadata")
        if val is not None:
            cleaned[str(key)] = str(val)
    return cleaned


@dataclass(frozen=True)
class IPFSConfig:
    """Configuration for IPFS Kubo local node, Pinata Cloud API, and offline fallback store.

    Secrets (``pinata_jwt``, ``pinata_api_key``, ``pinata_secret_api_key``) are loaded from
    ``.env`` / environment variables only and NEVER written to logs or GitHub.
    """

    provider: str = "local_fallback"  # "pinata" | "kubo" | "local_fallback" | "local_store"
    kubo_api_url: str = DEFAULT_KUBO_API_URL
    kubo_gateway_url: str = DEFAULT_KUBO_GATEWAY_URL
    pinata_api_url: str = DEFAULT_PINATA_API_URL
    pinata_gateway_url: str = DEFAULT_PINATA_GATEWAY_URL
    pinata_jwt: str = ""
    pinata_api_key: str = ""
    pinata_secret_api_key: str = ""
    local_store_dir: Path = DEFAULT_LOCAL_STORE_DIR
    request_timeout_seconds: float = 15.0
    enable_local_fallback: bool = True
    mirror_pins_to_local_store: bool = True

    @property
    def has_pinata_credentials(self) -> bool:
        return bool(self.pinata_jwt or (self.pinata_api_key and self.pinata_secret_api_key))

    @classmethod
    def from_env(cls, local_store_dir: Path | None = None) -> "IPFSConfig":
        """Build ``IPFSConfig`` from environment variables / ``backend.config.settings``."""
        try:
            from dotenv import load_dotenv

            load_dotenv(PROJECT_ROOT / ".env")
        except Exception:
            pass

        provider = os.getenv("IPFS_PROVIDER", "local_fallback").strip().lower() or "local_fallback"
        store_dir_env = os.getenv("IPFS_LOCAL_STORE_DIR", "").strip()
        resolved_store = (
            local_store_dir
            if local_store_dir is not None
            else (Path(store_dir_env) if store_dir_env else DEFAULT_LOCAL_STORE_DIR)
        )
        return cls(
            provider=provider,
            kubo_api_url=os.getenv("IPFS_LOCAL_API_URL", DEFAULT_KUBO_API_URL).strip().rstrip("/"),
            kubo_gateway_url=os.getenv("IPFS_LOCAL_GATEWAY_URL", DEFAULT_KUBO_GATEWAY_URL).strip().rstrip("/"),
            pinata_api_url=os.getenv("PINATA_API_URL", DEFAULT_PINATA_API_URL).strip().rstrip("/"),
            pinata_gateway_url=os.getenv("PINATA_GATEWAY_URL", DEFAULT_PINATA_GATEWAY_URL).strip().rstrip("/"),
            pinata_jwt=os.getenv("PINATA_JWT", "").strip(),
            pinata_api_key=os.getenv("PINATA_API_KEY", "").strip(),
            pinata_secret_api_key=os.getenv("PINATA_SECRET_API_KEY", "").strip(),
            local_store_dir=resolved_store,
            request_timeout_seconds=float(os.getenv("IPFS_TIMEOUT_SECONDS", "15")),
            enable_local_fallback=os.getenv("IPFS_ENABLE_LOCAL_FALLBACK", "true").strip().lower() != "false",
            mirror_pins_to_local_store=os.getenv("IPFS_MIRROR_LOCAL_PINS", "true").strip().lower() != "false",
        )


@dataclass(frozen=True)
class UploadResult:
    """Result returned after pinning a file or payload on IPFS."""

    cid: str
    cid_version: int
    sha256: str
    size_bytes: int
    filename: str
    content_type: str
    provider_used: str  # "pinata" | "kubo" | "local_store"
    gateway_url: str
    fallback_gateway_urls: List[str]
    pinned: bool
    is_encrypted: bool = False
    uploaded_at_utc: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cid": self.cid,
            "cid_version": self.cid_version,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "filename": self.filename,
            "content_type": self.content_type,
            "provider_used": self.provider_used,
            "gateway_url": self.gateway_url,
            "fallback_gateway_urls": list(self.fallback_gateway_urls),
            "pinned": self.pinned,
            "is_encrypted": self.is_encrypted,
            "uploaded_at_utc": self.uploaded_at_utc,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RetrieveResult:
    """Result returned after retrieving and verifying content by CID."""

    cid: str
    content: bytes
    sha256: str
    size_bytes: int
    provider_used: str
    source_url: str
    integrity_verified: bool
    cid_verified: bool


class LocalPinnedStore:
    """Deterministic content-addressed local fallback store keyed by IPFS CIDv1.

    Used when neither Pinata Cloud nor a running IPFS Kubo daemon is reachable, and as a local
    pinned cache mirror so offline demo retrievals keep working for previously pinned CIDs.
    """

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = Path(root_dir)
        self.blocks_dir = self.root_dir / "blocks"
        self.index_path = self.root_dir / "pins.json"

    def _ensure_dirs(self) -> None:
        self.blocks_dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> Dict[str, Dict[str, Any]]:
        if not self.index_path.exists():
            return {}
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_index(self, index: Dict[str, Dict[str, Any]]) -> None:
        self._ensure_dirs()
        self.index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def put(
        self,
        data: bytes,
        *,
        cid: str | None = None,
        filename: str = "object.bin",
        content_type: str = "application/octet-stream",
        metadata: Dict[str, str] | None = None,
    ) -> str:
        self._ensure_dirs()
        resolved_cid = cid.strip() if cid else compute_cid_v1(data)
        if not is_valid_cid(resolved_cid):
            raise IPFSUploadError(f"Cannot store invalid CID in local fallback store: {resolved_cid}")

        block_path = self.blocks_dir / resolved_cid
        block_path.write_bytes(data)

        index = self._load_index()
        index[resolved_cid] = {
            "cid": resolved_cid,
            "sha256": sha256_bytes(data),
            "size_bytes": len(data),
            "filename": filename,
            "content_type": content_type,
            "pinned_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "metadata": dict(metadata or {}),
        }
        self._save_index(index)
        return resolved_cid

    def get(self, cid: str) -> Optional[bytes]:
        cleaned = cid.strip()
        if not is_valid_cid(cleaned):
            return None
        block_path = self.blocks_dir / cleaned
        if not block_path.exists():
            return None
        return block_path.read_bytes()

    def list_pins(self) -> Dict[str, Dict[str, Any]]:
        return self._load_index()


class IPFSClient:
    """Unified IPFS client supporting Pinata Cloud, IPFS Kubo Local Node, and Local Fallback."""

    def __init__(
        self,
        config: IPFSConfig | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config or IPFSConfig.from_env()
        self.session = session or requests.Session()
        self.local_store = LocalPinnedStore(self.config.local_store_dir)

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        return sha256_bytes(data)

    @staticmethod
    def compute_cid_v1(data: bytes) -> str:
        return compute_cid_v1(data)

    def get_gateway_urls(self, cid: str) -> List[str]:
        """Return ordered HTTP gateway URLs for ``cid`` (local Kubo + Pinata)."""
        cleaned = cid.strip()
        if not is_valid_cid(cleaned):
            raise ValueError(f"Invalid IPFS CID: {cid!r}")
        kubo_url = f"{self.config.kubo_gateway_url.rstrip('/')}/{cleaned}"
        pinata_url = f"{self.config.pinata_gateway_url.rstrip('/')}/{cleaned}"
        if self.config.provider == "pinata":
            return [pinata_url, kubo_url]
        return [kubo_url, pinata_url]

    def _pinata_headers(self) -> Dict[str, str]:
        if self.config.pinata_jwt:
            return {"Authorization": f"Bearer {self.config.pinata_jwt}"}
        if self.config.pinata_api_key and self.config.pinata_secret_api_key:
            return {
                "pinata_api_key": self.config.pinata_api_key,
                "pinata_secret_api_key": self.config.pinata_secret_api_key,
            }
        raise IPFSUploadError("Pinata credentials are not configured in environment variables")

    def _upload_via_kubo(
        self,
        data: bytes,
        *,
        filename: str,
        content_type: str,
        pin: bool = True,
    ) -> Tuple[str, str]:
        url = f"{self.config.kubo_api_url.rstrip('/')}/api/v0/add"
        params = {
            "cid-version": "1",
            "raw-leaves": "true",
            "pin": "true" if pin else "false",
        }
        files = {"file": (filename, data, content_type)}
        resp = self.session.post(
            url,
            params=params,
            files=files,
            timeout=self.config.request_timeout_seconds,
        )
        resp.raise_for_status()
        # Kubo returns newline-delimited JSON objects; last non-empty line is the target object
        lines = [line for line in resp.text.splitlines() if line.strip()]
        if not lines:
            raise IPFSUploadError("Empty response from IPFS Kubo /api/v0/add")
        payload = json.loads(lines[-1])
        cid = str(payload.get("Hash", "")).strip()
        if not is_valid_cid(cid):
            raise IPFSUploadError(f"Kubo returned invalid CID: {cid!r}")
        gateway_url = f"{self.config.kubo_gateway_url.rstrip('/')}/{cid}"
        return cid, gateway_url

    def _upload_via_pinata(
        self,
        data: bytes,
        *,
        filename: str,
        content_type: str,
        metadata: Dict[str, str],
    ) -> Tuple[str, str]:
        url = f"{self.config.pinata_api_url.rstrip('/')}/pinning/pinFileToIPFS"
        headers = self._pinata_headers()
        pinata_options = json.dumps({"cidVersion": 1})
        pinata_metadata = json.dumps({"name": filename, "keyvalues": metadata})
        files = {"file": (filename, data, content_type)}
        form_data = {
            "pinataOptions": pinata_options,
            "pinataMetadata": pinata_metadata,
        }
        resp = self.session.post(
            url,
            headers=headers,
            files=files,
            data=form_data,
            timeout=self.config.request_timeout_seconds,
        )
        resp.raise_for_status()
        payload = resp.json()
        cid = str(payload.get("IpfsHash", "")).strip()
        if not is_valid_cid(cid):
            raise IPFSUploadError(f"Pinata returned invalid IpfsHash: {cid!r}")
        gateway_url = f"{self.config.pinata_gateway_url.rstrip('/')}/{cid}"
        return cid, gateway_url

    def _provider_upload_order(self) -> List[str]:
        mode = self.config.provider.lower()
        order: List[str] = []
        if mode == "pinata":
            order = ["pinata", "kubo"]
        elif mode == "kubo":
            order = ["kubo"]
        elif mode == "local_store":
            order = ["local_store"]
        else:  # "local_fallback" (default)
            order = ["kubo"]
            if self.config.has_pinata_credentials:
                order.append("pinata")

        if self.config.enable_local_fallback and "local_store" not in order:
            order.append("local_store")
        return order

    def upload_bytes(
        self,
        data: bytes,
        *,
        filename: str,
        content_type: str = "application/octet-stream",
        metadata: Dict[str, Any] | None = None,
        pin: bool = True,
        is_encrypted: bool = False,
    ) -> UploadResult:
        """Hash ``data`` (SHA-256 + CIDv1), upload via configured provider chain, and return ``UploadResult``."""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("data must be bytes")
        raw = bytes(data)
        safe_metadata = _sanitize_pin_metadata(metadata)
        digest_sha256 = sha256_bytes(raw)
        errors: List[str] = []

        for backend in self._provider_upload_order():
            try:
                if backend == "pinata":
                    if not self.config.has_pinata_credentials:
                        errors.append("pinata: credentials not configured")
                        continue
                    cid, primary_gw = self._upload_via_pinata(
                        raw,
                        filename=filename,
                        content_type=content_type,
                        metadata=safe_metadata,
                    )
                    if self.config.mirror_pins_to_local_store:
                        self.local_store.put(
                            raw,
                            cid=cid,
                            filename=filename,
                            content_type=content_type,
                            metadata=safe_metadata,
                        )
                    return UploadResult(
                        cid=cid,
                        cid_version=detect_cid_version(cid),
                        sha256=digest_sha256,
                        size_bytes=len(raw),
                        filename=filename,
                        content_type=content_type,
                        provider_used="pinata",
                        gateway_url=primary_gw,
                        fallback_gateway_urls=self.get_gateway_urls(cid),
                        pinned=pin,
                        is_encrypted=is_encrypted,
                        uploaded_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        metadata=safe_metadata,
                    )

                if backend == "kubo":
                    cid, primary_gw = self._upload_via_kubo(
                        raw,
                        filename=filename,
                        content_type=content_type,
                        pin=pin,
                    )
                    if self.config.mirror_pins_to_local_store:
                        self.local_store.put(
                            raw,
                            cid=cid,
                            filename=filename,
                            content_type=content_type,
                            metadata=safe_metadata,
                        )
                    return UploadResult(
                        cid=cid,
                        cid_version=detect_cid_version(cid),
                        sha256=digest_sha256,
                        size_bytes=len(raw),
                        filename=filename,
                        content_type=content_type,
                        provider_used="kubo",
                        gateway_url=primary_gw,
                        fallback_gateway_urls=self.get_gateway_urls(cid),
                        pinned=pin,
                        is_encrypted=is_encrypted,
                        uploaded_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        metadata=safe_metadata,
                    )

                if backend == "local_store":
                    cid = self.local_store.put(
                        raw,
                        filename=filename,
                        content_type=content_type,
                        metadata=safe_metadata,
                    )
                    gw_urls = self.get_gateway_urls(cid)
                    return UploadResult(
                        cid=cid,
                        cid_version=detect_cid_version(cid),
                        sha256=digest_sha256,
                        size_bytes=len(raw),
                        filename=filename,
                        content_type=content_type,
                        provider_used="local_store",
                        gateway_url=gw_urls[0],
                        fallback_gateway_urls=gw_urls,
                        pinned=True,
                        is_encrypted=is_encrypted,
                        uploaded_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        metadata=safe_metadata,
                    )
            except Exception as exc:
                errors.append(f"{backend}: {exc}")

        raise IPFSUploadError(
            "Failed to upload to all configured IPFS backends: " + "; ".join(errors)
        )

    def upload_file(
        self,
        file_path: str | Path,
        *,
        content_type: str | None = None,
        metadata: Dict[str, Any] | None = None,
        pin: bool = True,
        is_encrypted: bool = False,
    ) -> UploadResult:
        """Read a file from disk and upload it to IPFS."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found for IPFS upload: {path}")
        guessed_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return self.upload_bytes(
            path.read_bytes(),
            filename=path.name,
            content_type=guessed_type,
            metadata=metadata,
            pin=pin,
            is_encrypted=is_encrypted,
        )

    def upload_json(
        self,
        payload: Dict[str, Any],
        *,
        filename: str = "document.json",
        metadata: Dict[str, Any] | None = None,
        pin: bool = True,
        is_encrypted: bool = False,
    ) -> UploadResult:
        """Serialize ``payload`` deterministically as UTF-8 JSON and upload to IPFS."""
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        return self.upload_bytes(
            raw,
            filename=filename,
            content_type="application/json",
            metadata=metadata,
            pin=pin,
            is_encrypted=is_encrypted,
        )

    def _retrieve_via_kubo_rpc(self, cid: str) -> Tuple[bytes, str]:
        url = f"{self.config.kubo_api_url.rstrip('/')}/api/v0/cat"
        resp = self.session.post(
            url,
            params={"arg": cid},
            timeout=self.config.request_timeout_seconds,
        )
        resp.raise_for_status()
        return resp.content, f"{url}?arg={cid}"

    def _retrieve_via_gateway(self, gateway_base: str, cid: str) -> Tuple[bytes, str]:
        url = f"{gateway_base.rstrip('/')}/{cid}"
        resp = self.session.get(url, timeout=self.config.request_timeout_seconds)
        resp.raise_for_status()
        return resp.content, url

    def _provider_retrieve_order(self) -> List[str]:
        mode = self.config.provider.lower()
        if mode == "local_store":
            return ["local_store"]
        if mode == "pinata":
            order = ["pinata_gateway", "kubo_gateway", "kubo_rpc"]
        elif mode == "kubo":
            order = ["kubo_gateway", "kubo_rpc"]
        else:  # "local_fallback"
            order = ["kubo_gateway", "kubo_rpc"]
            if self.config.has_pinata_credentials or self.config.pinata_gateway_url:
                order.append("pinata_gateway")
        if self.config.enable_local_fallback:
            order.append("local_store")
        return order

    def retrieve_bytes(
        self,
        cid: str,
        *,
        expected_sha256: str | None = None,
        verify_cid: bool = True,
    ) -> RetrieveResult:
        """Retrieve content by ``cid`` with gateway fallback and mandatory integrity checks."""
        cleaned = cid.strip()
        if not is_valid_cid(cleaned):
            raise ValueError(f"Invalid IPFS CID: {cid!r}")

        errors: List[str] = []
        content: Optional[bytes] = None
        provider_used = ""
        source_url = ""

        for source in self._provider_retrieve_order():
            try:
                if source == "pinata_gateway":
                    content, source_url = self._retrieve_via_gateway(
                        self.config.pinata_gateway_url, cleaned
                    )
                    provider_used = "pinata_gateway"
                    break
                if source == "kubo_gateway":
                    content, source_url = self._retrieve_via_gateway(
                        self.config.kubo_gateway_url, cleaned
                    )
                    provider_used = "kubo_gateway"
                    break
                if source == "kubo_rpc":
                    content, source_url = self._retrieve_via_kubo_rpc(cleaned)
                    provider_used = "kubo_rpc"
                    break
                if source == "local_store":
                    local_data = self.local_store.get(cleaned)
                    if local_data is None:
                        errors.append("local_store: CID not pinned locally")
                        continue
                    content = local_data
                    provider_used = "local_store"
                    source_url = str((self.local_store.blocks_dir / cleaned).resolve())
                    break
            except Exception as exc:
                errors.append(f"{source}: {exc}")

        if content is None:
            raise IPFSNotFoundError(
                f"Unable to retrieve CID {cleaned} from any configured source: " + "; ".join(errors)
            )

        verification = verify_content_integrity(
            content,
            expected_sha256=expected_sha256,
            expected_cid=cleaned if verify_cid else None,
        )
        if not verification["sha256_verified"]:
            raise IPFSIntegrityError(
                f"SHA-256 mismatch for CID {cleaned}: "
                f"expected={expected_sha256}, actual={verification['actual_sha256']}"
            )
        if verify_cid and not verification["cid_verified"]:
            raise IPFSIntegrityError(
                f"Content does not match requested CID {cleaned} "
                f"(computed CIDv1={verification['actual_cid_v1']})"
            )

        return RetrieveResult(
            cid=cleaned,
            content=content,
            sha256=str(verification["actual_sha256"]),
            size_bytes=len(content),
            provider_used=provider_used,
            source_url=source_url,
            integrity_verified=bool(verification["integrity_verified"]),
            cid_verified=bool(verification["cid_verified"]),
        )

    def retrieve_file(
        self,
        cid: str,
        output_path: str | Path,
        *,
        expected_sha256: str | None = None,
        verify_cid: bool = True,
    ) -> RetrieveResult:
        """Retrieve a CID from IPFS and write verified bytes to ``output_path``."""
        result = self.retrieve_bytes(cid, expected_sha256=expected_sha256, verify_cid=verify_cid)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(result.content)
        return result

    def retrieve_json(
        self,
        cid: str,
        *,
        expected_sha256: str | None = None,
        verify_cid: bool = True,
    ) -> Tuple[Dict[str, Any], RetrieveResult]:
        """Retrieve and parse a JSON object from IPFS by CID."""
        result = self.retrieve_bytes(cid, expected_sha256=expected_sha256, verify_cid=verify_cid)
        parsed = json.loads(result.content.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise IPFSRetrieveError(f"CID {cid} did not resolve to a JSON object")
        return parsed, result

    def check_health(self) -> Dict[str, Any]:
        """Inspect availability of Kubo local node, Pinata Cloud auth, and local fallback store.

        Never exposes JWTs, API keys, or secrets in the returned diagnostic payload.
        """
        kubo_status: Dict[str, Any] = {"reachable": False, "api_url": self.config.kubo_api_url}
        try:
            resp = self.session.post(
                f"{self.config.kubo_api_url.rstrip('/')}/api/v0/version",
                timeout=min(self.config.request_timeout_seconds, 3.0),
            )
            if resp.ok:
                kubo_status["reachable"] = True
                kubo_status["version"] = resp.json().get("Version")
            else:
                kubo_status["status_code"] = resp.status_code
        except Exception as exc:
            kubo_status["error"] = str(exc)

        pinata_status: Dict[str, Any] = {
            "configured": self.config.has_pinata_credentials,
            "authenticated": False,
            "gateway_url": self.config.pinata_gateway_url,
        }
        if self.config.has_pinata_credentials:
            try:
                resp = self.session.get(
                    f"{self.config.pinata_api_url.rstrip('/')}/data/testAuthentication",
                    headers=self._pinata_headers(),
                    timeout=min(self.config.request_timeout_seconds, 5.0),
                )
                pinata_status["authenticated"] = resp.ok
                pinata_status["status_code"] = resp.status_code
            except Exception as exc:
                pinata_status["error"] = str(exc)

        local_pins = self.local_store.list_pins()
        return {
            "provider_mode": self.config.provider,
            "kubo_local": kubo_status,
            "pinata_cloud": pinata_status,
            "local_fallback_store": {
                "enabled": self.config.enable_local_fallback,
                "path": str(self.config.local_store_dir),
                "pinned_count": len(local_pins),
            },
        }

