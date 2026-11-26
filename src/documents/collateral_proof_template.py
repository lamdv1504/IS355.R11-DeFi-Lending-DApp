"""Pure-Python PNG generator for optional Collateral Proof image evidence (H03).

Provides a zero-dependency third file format (PNG alongside PDF and JSON) demonstrating
multi-format IPFS storage, SHA-256 verification, and AES-256-GCM encryption for TC3.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Dict

from src.ipfs.cid_utils import compute_cid_v1, sha256_bytes


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def generate_collateral_proof_png(
    *,
    token_id: str = "1",
    valuation_display: str = "1000.000000 MyUSDT",
    data_kind: str = "SIMULATED",
    width: int = 320,
    height: int = 180,
) -> bytes:
    """Generate a valid RGB PNG visual badge representing a tokenized collateral proof image."""
    if width < 64 or height < 64:
        raise ValueError("width and height must be >= 64")

    # Build a crisp navy/teal card frame with a gold accent band and center emblem
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # PNG filter type 0 (None)
        for x in range(width):
            border = x < 6 or x >= width - 6 or y < 6 or y >= height - 6
            inner_border = 12 <= x < width - 12 and (12 <= y < 14 or height - 14 <= y < height - 12)
            header_band = 14 <= y < 48 and 12 <= x < width - 12
            emblem = (x - width // 2) ** 2 + (y - (height // 2 + 18)) ** 2 <= 28**2
            inner_emblem = (x - width // 2) ** 2 + (y - (height // 2 + 18)) ** 2 <= 16**2

            if border:
                r, g, b = 15, 41, 66      # Deep navy frame
            elif inner_border:
                r, g, b = 217, 119, 6     # Gold accent border
            elif header_band:
                r, g, b = 13, 148, 136    # Teal DeFi header
            elif inner_emblem:
                r, g, b = 245, 158, 11    # Gold inner seal
            elif emblem:
                r, g, b = 15, 41, 66      # Navy outer seal
            else:
                r, g, b = 248, 250, 252   # Clean slate background
            rows.extend((r, g, b))

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = _png_chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0),  # 8-bit RGB
    )
    meta_chunks = [
        _png_chunk(b"tEXt", f"Title\x00IS355 DeFi Collateral Proof #{token_id}".encode("latin-1")),
        _png_chunk(b"tEXt", f"Valuation\x00{valuation_display}".encode("latin-1")),
        _png_chunk(b"tEXt", f"DataKind\x00{data_kind}".encode("latin-1")),
    ]
    idat = _png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
    iend = _png_chunk(b"IEND", b"")

    return signature + ihdr + b"".join(meta_chunks) + idat + iend


def save_collateral_proof_png(
    output_path: str | Path,
    *,
    token_id: str = "1",
    valuation_display: str = "1000.000000 MyUSDT",
    data_kind: str = "SIMULATED",
) -> Dict[str, object]:
    """Generate and write a sample collateral proof PNG to ``output_path``."""
    png_bytes = generate_collateral_proof_png(
        token_id=token_id,
        valuation_display=valuation_display,
        data_kind=data_kind,
    )
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png_bytes)
    return {
        "path": str(target),
        "size_bytes": len(png_bytes),
        "sha256": sha256_bytes(png_bytes),
        "cid_v1_plaintext": compute_cid_v1(png_bytes),
    }

