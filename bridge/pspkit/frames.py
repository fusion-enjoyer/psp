"""PSP framebuffer dumps to PNG (stdlib only)."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path


def to_rgb(pixels: bytes, fmt: int) -> bytes:
    """PSP framebuffer (little endian, red in the low bits) to packed RGB."""
    if fmt == 3:  # 8888: bytes are R, G, B, A
        out = bytearray(len(pixels) // 4 * 3)
        out[0::3], out[1::3], out[2::3] = pixels[0::4], pixels[1::4], pixels[2::4]
        return bytes(out)
    out = bytearray()
    for (v,) in struct.iter_unpack("<H", pixels):
        if fmt == 0:    # 565
            r, g, b = v & 0x1F, (v >> 5) & 0x3F, (v >> 11) & 0x1F
            out += bytes((r * 255 // 31, g * 255 // 63, b * 255 // 31))
        elif fmt == 1:  # 5551
            r, g, b = v & 0x1F, (v >> 5) & 0x1F, (v >> 10) & 0x1F
            out += bytes((r * 255 // 31, g * 255 // 31, b * 255 // 31))
        else:           # 4444
            r, g, b = v & 0xF, (v >> 4) & 0xF, (v >> 8) & 0xF
            out += bytes((r * 17, g * 17, b * 17))
    return bytes(out)


def save_png(path: Path, w: int, h: int, fmt: int, pixels: bytes) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rgb = to_rgb(pixels, fmt)
    raw = b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9))
                     + chunk(b"IEND", b""))
