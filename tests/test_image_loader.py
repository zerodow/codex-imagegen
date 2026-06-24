"""Reference image loading: mime sniff, missing/empty/unsupported, size budget."""

import base64

import pytest

from codex_imagegen import image_loader as il
from codex_imagegen.errors import InputError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff" + b"\x00" * 32
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def test_sniff_supported_types(tmp_path):
    assert il.load_reference(_write(tmp_path, "a.png", PNG))[1] == "image/png"
    assert il.load_reference(_write(tmp_path, "a.jpg", JPEG))[1] == "image/jpeg"
    assert il.load_reference(_write(tmp_path, "a.webp", WEBP))[1] == "image/webp"
    assert il.load_reference(_write(tmp_path, "a.gif", GIF))[1] == "image/gif"


def test_returns_decodable_base64(tmp_path):
    b64, mime = il.load_reference(_write(tmp_path, "a.png", PNG))
    assert base64.b64decode(b64) == PNG
    assert mime == "image/png"


def test_missing_file_raises(tmp_path):
    with pytest.raises(InputError):
        il.load_reference(str(tmp_path / "nope.png"))


def test_empty_file_raises(tmp_path):
    with pytest.raises(InputError):
        il.load_reference(_write(tmp_path, "e.png", b""))


def test_unsupported_type_raises(tmp_path):
    with pytest.raises(InputError):
        il.load_reference(_write(tmp_path, "a.bin", b"not an image at all"))


def test_total_budget_enforced(tmp_path, monkeypatch):
    monkeypatch.setattr(il, "_MAX_TOTAL_B64", 10)
    with pytest.raises(InputError):
        il.load_references([_write(tmp_path, "a.png", PNG)])
