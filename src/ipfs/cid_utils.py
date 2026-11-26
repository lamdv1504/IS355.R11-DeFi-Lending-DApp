"""SHA-256 hashing and spec-compliant IPFS CIDv1 / CIDv0 verification utilities (H03).

Generates deterministic IPFS CIDv1 identifiers matching IPFS Kubo's
``ipfs add --cid-version=1 --raw-leaves --only-hash`` behavior:
- Files <= 256 KiB (262,144 bytes): single ``raw`` (0x55) leaf block -> ``bafkrei...``
- Files > 256 KiB: balanced UnixFS ``dag-pb`` (0x70) DAG with 256 KiB raw leaves -> ``bafybei...``
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple

# Multicodec / Multihash constants (IPFS CID specification)
CID_VERSION_1 = 0x01
RAW_CODEC = 0x55
DAG_PB_CODEC = 0x70
SHA2_256_CODE = 0x12
SHA2_256_LENGTH = 32

# Kubo defaults: 256 KiB fixed-size chunker, balanced DAG width 174
UNIXFS_CHUNK_SIZE = 262_144
UNIXFS_MAX_LINKS = 174
UNIXFS_DATA_TYPE_FILE = 2

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58_INDEX = {ch: idx for idx, ch in enumerate(_BASE58_ALPHABET)}
_SUPPORTED_CIDV1_CODECS = {RAW_CODEC, DAG_PB_CODEC, 0x71, 0x0129}  # raw, dag-pb, dag-cbor, dag-json


def sha256_bytes(data: bytes) -> str:
    """Return lowercase 64-character hex SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(file_path: str | Path, chunk_size: int = 65_536) -> str:
    """Compute SHA-256 hex digest of a file on disk using streaming reads."""
    hasher = hashlib.sha256()
    with Path(file_path).open("rb") as fp:
        while True:
            chunk = fp.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _encode_uvarint(value: int) -> bytes:
    """Encode a non-negative integer as unsigned LEB128 varint."""
    if value < 0:
        raise ValueError("uvarint value must be non-negative")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def _decode_uvarint(buf: bytes, offset: int = 0) -> Tuple[int, int]:
    """Decode an unsigned LEB128 varint from ``buf`` starting at ``offset``."""
    value = 0
    shift = 0
    pos = offset
    while pos < len(buf):
        byte = buf[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return value, pos
        shift += 7
        if shift > 63:
            raise ValueError("uvarint overflow")
    raise ValueError("unexpected end of buffer while decoding uvarint")


def _encode_base58(data: bytes) -> str:
    """Encode raw bytes to Bitcoin/IPFS base58btc string."""
    num = int.from_bytes(data, "big")
    chars: List[str] = []
    while num > 0:
        num, rem = divmod(num, 58)
        chars.append(_BASE58_ALPHABET[rem])
    leading_zeros = 0
    for byte in data:
        if byte == 0:
            leading_zeros += 1
        else:
            break
    return ("1" * leading_zeros) + "".join(reversed(chars))


def _decode_base58(text: str) -> bytes:
    """Decode base58btc string to raw bytes."""
    if not text:
        raise ValueError("empty base58 string")
    num = 0
    for ch in text:
        if ch not in _BASE58_INDEX:
            raise ValueError(f"invalid base58 character: {ch!r}")
        num = num * 58 + _BASE58_INDEX[ch]
    leading_zeros = 0
    for ch in text:
        if ch == "1":
            leading_zeros += 1
        else:
            break
    byte_len = (num.bit_length() + 7) // 8
    raw = num.to_bytes(byte_len, "big") if byte_len else b""
    return (b"\x00" * leading_zeros) + raw


def _pb_varint_field(field_number: int, value: int) -> bytes:
    tag = (field_number << 3) | 0
    return _encode_uvarint(tag) + _encode_uvarint(value)


def _pb_bytes_field(field_number: int, payload: bytes) -> bytes:
    tag = (field_number << 3) | 2
    return _encode_uvarint(tag) + _encode_uvarint(len(payload)) + payload


def _build_cid_v1_bytes(digest: bytes, codec: int = RAW_CODEC) -> bytes:
    if len(digest) != SHA2_256_LENGTH:
        raise ValueError(f"Expected 32-byte SHA-256 digest, got {len(digest)} bytes")
    return (
        _encode_uvarint(CID_VERSION_1)
        + _encode_uvarint(codec)
        + bytes([SHA2_256_CODE, SHA2_256_LENGTH])
        + digest
    )


def encode_cid_v1_from_bytes(cid_bytes: bytes) -> str:
    """Encode binary CIDv1 bytes using multibase base32lower ('b' prefix, no padding)."""
    b32 = base64.b32encode(cid_bytes).decode("ascii").lower().rstrip("=")
    return f"b{b32}"


def encode_cid_v1(digest: bytes, codec: int = RAW_CODEC) -> str:
    """Encode a 32-byte SHA-256 digest as a multibase base32lower CIDv1 string."""
    return encode_cid_v1_from_bytes(_build_cid_v1_bytes(digest, codec=codec))


def _encode_unixfs_file_node(
    file_size: int,
    block_sizes: List[int],
    inline_data: bytes | None = None,
) -> bytes:
    """Encode a UnixFS Data protobuf message (Type = File(2))."""
    parts = [_pb_varint_field(1, UNIXFS_DATA_TYPE_FILE)]
    if inline_data is not None and len(inline_data) > 0:
        parts.append(_pb_bytes_field(2, inline_data))
    parts.append(_pb_varint_field(3, file_size))
    for blk_size in block_sizes:
        parts.append(_pb_varint_field(4, blk_size))
    return b"".join(parts)


def _encode_dag_pb_node(links: List[Tuple[bytes, int]], unixfs_data: bytes) -> bytes:
    """Encode a dag-pb PBNode with canonical link order (field 2 Links, field 1 Data).

    Per the dag-pb spec, PBLinks are encoded with fields:
    1: Hash (bytes), 2: Name (bytes, empty for chunk links), 3: Tsize (uint64).
    """
    encoded_parts: List[bytes] = []
    for link_cid_bytes, cumulative_size in links:
        pb_link = (
            _pb_bytes_field(1, link_cid_bytes)
            + _pb_bytes_field(2, b"")
            + _pb_varint_field(3, cumulative_size)
        )
        encoded_parts.append(_pb_bytes_field(2, pb_link))
    if unixfs_data:
        encoded_parts.append(_pb_bytes_field(1, unixfs_data))
    return b"".join(encoded_parts)


def compute_cid_v1(data: bytes) -> str:
    """Compute spec-compliant IPFS CIDv1 matching ``ipfs add --cid-version=1 --raw-leaves``.

    - For payloads <= 256 KiB: returns ``raw`` codec CIDv1 (``bafkrei...``).
    - For payloads > 256 KiB: builds a balanced UnixFS ``dag-pb`` tree of 256 KiB raw leaves
      and returns the root ``dag-pb`` CIDv1 (``bafybei...``).
    """
    if len(data) <= UNIXFS_CHUNK_SIZE:
        digest = hashlib.sha256(data).digest()
        return encode_cid_v1(digest, codec=RAW_CODEC)

    # Chunk into 256 KiB raw leaves: (cid_bytes, cumulative_dag_size, raw_data_size)
    level: List[Tuple[bytes, int, int]] = []
    for start in range(0, len(data), UNIXFS_CHUNK_SIZE):
        chunk = data[start : start + UNIXFS_CHUNK_SIZE]
        chunk_digest = hashlib.sha256(chunk).digest()
        chunk_cid_bytes = _build_cid_v1_bytes(chunk_digest, codec=RAW_CODEC)
        level.append((chunk_cid_bytes, len(chunk), len(chunk)))

    while len(level) > 1:
        next_level: List[Tuple[bytes, int, int]] = []
        for idx in range(0, len(level), UNIXFS_MAX_LINKS):
            group = level[idx : idx + UNIXFS_MAX_LINKS]
            if len(group) == 1 and len(level) > UNIXFS_MAX_LINKS:
                next_level.append(group[0])
                continue
            links = [(item[0], item[1]) for item in group]
            block_sizes = [item[2] for item in group]
            total_data_size = sum(block_sizes)
            unixfs_data = _encode_unixfs_file_node(
                file_size=total_data_size,
                block_sizes=block_sizes,
            )
            pb_node = _encode_dag_pb_node(links=links, unixfs_data=unixfs_data)
            node_digest = hashlib.sha256(pb_node).digest()
            node_cid_bytes = _build_cid_v1_bytes(node_digest, codec=DAG_PB_CODEC)
            cumulative_size = len(pb_node) + sum(item[1] for item in group)
            next_level.append((node_cid_bytes, cumulative_size, total_data_size))
        level = next_level

    return encode_cid_v1_from_bytes(level[0][0])


def compute_unixfs_cid_v0(data: bytes) -> str:
    """Compute legacy UnixFS CIDv0 (``Qm...``) for single-chunk payloads <= 256 KiB.

    Used to verify integrity when an external gateway/Pinata endpoint pins using CIDv0
    (``--raw-leaves=false``).
    """
    if len(data) > UNIXFS_CHUNK_SIZE:
        raise ValueError("compute_unixfs_cid_v0 only supports single-chunk payloads <= 256 KiB")
    unixfs_data = _encode_unixfs_file_node(
        file_size=len(data),
        block_sizes=[],
        inline_data=data,
    )
    pb_node = _encode_dag_pb_node(links=[], unixfs_data=unixfs_data)
    digest = hashlib.sha256(pb_node).digest()
    multihash = bytes([SHA2_256_CODE, SHA2_256_LENGTH]) + digest
    return _encode_base58(multihash)


def compute_unixfs_dag_pb_cid_v1(data: bytes) -> str:
    """Compute UnixFS ``dag-pb`` CIDv1 (``bafybei...``) for single-chunk non-raw-leaf pins."""
    if len(data) > UNIXFS_CHUNK_SIZE:
        return compute_cid_v1(data)
    unixfs_data = _encode_unixfs_file_node(
        file_size=len(data),
        block_sizes=[],
        inline_data=data,
    )
    pb_node = _encode_dag_pb_node(links=[], unixfs_data=unixfs_data)
    digest = hashlib.sha256(pb_node).digest()
    return encode_cid_v1(digest, codec=DAG_PB_CODEC)


def detect_cid_version(cid: str) -> int:
    """Validate and return CID version (0 for ``Qm...``, 1 for ``b...`` base32lower)."""
    cleaned = cid.strip()
    if not cleaned:
        raise ValueError("CID cannot be empty")

    # CIDv0: base58btc-encoded sha2-256 multihash (34 bytes starting with 0x12 0x20)
    if cleaned.startswith("Qm") and len(cleaned) == 46:
        raw = _decode_base58(cleaned)
        if len(raw) == 34 and raw[0] == SHA2_256_CODE and raw[1] == SHA2_256_LENGTH:
            return 0
        raise ValueError(f"Malformed CIDv0 multihash: {cid}")

    # CIDv1: multibase base32lower ('b' prefix)
    if cleaned.startswith("b") and len(cleaned) >= 16:
        body = cleaned[1:]
        if body != body.lower():
            raise ValueError(f"CIDv1 base32lower must be lowercase: {cid}")
        padding = "=" * ((8 - len(body) % 8) % 8)
        try:
            raw = base64.b32decode((body + padding).upper(), casefold=False)
        except Exception as exc:
            raise ValueError(f"Invalid base32 encoding in CIDv1: {cid}") from exc

        version, pos = _decode_uvarint(raw, 0)
        if version != CID_VERSION_1:
            raise ValueError(f"Expected CID version 1, got {version}")
        codec, pos = _decode_uvarint(raw, pos)
        if codec not in _SUPPORTED_CIDV1_CODECS:
            raise ValueError(f"Unsupported CIDv1 multicodec: 0x{codec:x}")
        mh_code, pos = _decode_uvarint(raw, pos)
        mh_len, pos = _decode_uvarint(raw, pos)
        if mh_code != SHA2_256_CODE or mh_len != SHA2_256_LENGTH:
            raise ValueError(f"Unsupported multihash (code=0x{mh_code:x}, len={mh_len})")
        if len(raw) - pos != mh_len:
            raise ValueError("CIDv1 multihash digest length mismatch")
        return 1

    raise ValueError(f"Unrecognized or unsupported CID format: {cid}")


def is_valid_cid(cid: str) -> bool:
    """Return True if ``cid`` is a structurally valid CIDv0 or CIDv1 string."""
    try:
        detect_cid_version(cid)
        return True
    except ValueError:
        return False


def verify_content_integrity(
    data: bytes,
    *,
    expected_sha256: str | None = None,
    expected_cid: str | None = None,
) -> Dict[str, object]:
    """Verify retrieved IPFS bytes against expected SHA-256 and/or CID.

    Returns a dictionary containing computed digests and boolean verification flags.
    """
    actual_sha256 = sha256_bytes(data)
    actual_cid_v1 = compute_cid_v1(data)

    sha256_ok = True
    if expected_sha256 is not None:
        sha256_ok = actual_sha256 == expected_sha256.strip().lower()

    cid_ok = True
    if expected_cid is not None:
        target = expected_cid.strip()
        if not is_valid_cid(target):
            cid_ok = False
        elif target == actual_cid_v1:
            cid_ok = True
        elif len(data) <= UNIXFS_CHUNK_SIZE and target in (
            compute_unixfs_cid_v0(data),
            compute_unixfs_dag_pb_cid_v1(data),
        ):
            cid_ok = True
        else:
            cid_ok = False

    return {
        "actual_sha256": actual_sha256,
        "actual_cid_v1": actual_cid_v1,
        "sha256_verified": sha256_ok,
        "cid_verified": cid_ok,
        "integrity_verified": bool(sha256_ok and cid_ok),
    }

