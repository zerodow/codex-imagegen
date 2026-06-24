"""Read image pixel dimensions from raw bytes — stdlib only, no Pillow.

The output report shows the ACTUAL output size: gpt-image-2 returns its own
resolution regardless of the requested size hint, so the hint is not the truth.
`read_dimensions` returns None on anything it can't parse and never raises into
the image path.
"""

import struct

_SOF_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)


def read_dimensions(data: bytes) -> tuple[int, int] | None:
    """Return (width, height) for PNG/JPEG/WebP/GIF bytes, or None if unknown."""
    if len(data) < 24:
        return None
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return _png(data)
        if data[:3] == b"\xff\xd8\xff":
            return _jpeg(data)
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return _webp(data)
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return _gif(data)
    except Exception:  # noqa: BLE001 - malformed header -> unknown, not a crash
        return None
    return None


def _png(data: bytes) -> tuple[int, int] | None:
    # IHDR is the first chunk: 8-byte sig + 4-byte length + "IHDR" + W,H as uint32 BE.
    if data[12:16] != b"IHDR":
        return None
    w, h = struct.unpack(">II", data[16:24])
    return (w, h) if w and h else None


def _gif(data: bytes) -> tuple[int, int] | None:
    w, h = struct.unpack("<HH", data[6:10])  # logical screen descriptor, LE uint16
    return (w, h) if w and h else None


def _jpeg(data: bytes) -> tuple[int, int] | None:
    # Walk segments to the first Start-Of-Frame marker, which carries the size.
    i, n = 2, len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in _SOF_MARKERS:
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return (w, h) if w and h else None
        if marker == 0xD8 or marker == 0xD9 or 0xD0 <= marker <= 0xD7:
            i += 2  # standalone markers carry no length
            continue
        seg_len = struct.unpack(">H", data[i + 2 : i + 4])[0]
        i += 2 + seg_len
    return None


def _webp(data: bytes) -> tuple[int, int] | None:
    codec = data[12:16]
    if codec == b"VP8 ":  # lossy: 14-bit dims after the 3-byte start code
        w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return (w, h) if w and h else None
    if codec == b"VP8L":  # lossless: 14-bit dims packed after the 0x2F signature byte
        bits = int.from_bytes(data[21:25], "little")
        w = (bits & 0x3FFF) + 1
        h = ((bits >> 14) & 0x3FFF) + 1
        return (w, h)
    if codec == b"VP8X":  # extended: 24-bit canvas dims (minus one) at offset 24
        w = int.from_bytes(data[24:27], "little") + 1
        h = int.from_bytes(data[27:30], "little") + 1
        return (w, h)
    return None
