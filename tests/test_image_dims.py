"""read_dimensions: correct (w,h) per format; None on short/garbage input."""

import struct

from codex_imagegen.core import image_dims


def _png(w: int, h: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0d" + b"IHDR" + struct.pack(">II", w, h) + b"\x00" * 4


def _gif(w: int, h: int) -> bytes:
    return b"GIF89a" + struct.pack("<HH", w, h) + b"\x00" * 20


def _jpeg(w: int, h: int) -> bytes:
    # SOI + SOF0(marker, len, precision, height, width) + padding
    return b"\xff\xd8" + b"\xff\xc0\x00\x11\x08" + struct.pack(">HH", h, w) + b"\x00" * 30


def _webp_vp8x(w: int, h: int) -> bytes:
    return (
        b"RIFF" + b"\x00" * 4 + b"WEBP" + b"VP8X" + b"\x00" * 8
        + (w - 1).to_bytes(3, "little") + (h - 1).to_bytes(3, "little") + b"\x00" * 4
    )


def _webp_vp8(w: int, h: int) -> bytes:
    # lossy: 3-byte frame tag + start code 0x9d012a + 14-bit width/height (LE)
    return (
        b"RIFF" + b"\x00" * 4 + b"WEBP" + b"VP8 " + b"\x00" * 4
        + b"\x00\x00\x00" + b"\x9d\x01\x2a"
        + struct.pack("<H", w) + struct.pack("<H", h) + b"\x00" * 4
    )


def _webp_vp8l(w: int, h: int) -> bytes:
    # lossless: 0x2f signature + 4 bytes packing (width-1) | (height-1)<<14
    bits = (w - 1) | ((h - 1) << 14)
    return (
        b"RIFF" + b"\x00" * 4 + b"WEBP" + b"VP8L" + b"\x00" * 4
        + b"\x2f" + struct.pack("<I", bits) + b"\x00" * 4
    )


def test_png_dims():
    assert image_dims.read_dimensions(_png(320, 200)) == (320, 200)


def test_gif_dims():
    assert image_dims.read_dimensions(_gif(640, 480)) == (640, 480)


def test_jpeg_dims():
    assert image_dims.read_dimensions(_jpeg(320, 200)) == (320, 200)


def test_webp_vp8x_dims():
    assert image_dims.read_dimensions(_webp_vp8x(320, 200)) == (320, 200)


def test_webp_vp8_lossy_dims():
    assert image_dims.read_dimensions(_webp_vp8(320, 200)) == (320, 200)


def test_webp_vp8l_lossless_dims():
    assert image_dims.read_dimensions(_webp_vp8l(320, 200)) == (320, 200)


def test_too_short_returns_none():
    assert image_dims.read_dimensions(b"\x89PNG") is None


def test_unknown_format_returns_none():
    assert image_dims.read_dimensions(b"not really an image at all, nope") is None


def test_png_zero_dims_returns_none():
    assert image_dims.read_dimensions(_png(0, 0)) is None
