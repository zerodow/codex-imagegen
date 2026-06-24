"""Output-path resolution, magic-byte validation, and atomic write."""

import pytest

from codex_imagegen.core import image_writer as iw
from codex_imagegen.core.errors import GatewayError, InputError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff" + b"\x00" * 32
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 16


def test_slugify():
    assert iw.slugify("A Cat, Astronaut! 2026") == "a-cat-astronaut-2026"
    assert iw.slugify("") == "image"
    assert iw.slugify("!!!") == "image"


def test_validate_magic_accepts():
    iw.validate_magic(PNG, "png")
    iw.validate_magic(JPEG, "jpeg")
    iw.validate_magic(WEBP, "webp")


def test_validate_magic_rejects_wrong_and_empty():
    with pytest.raises(GatewayError):
        iw.validate_magic(b"not an image", "png")
    with pytest.raises(GatewayError):
        iw.validate_magic(b"", "png")


def test_resolve_explicit_path(tmp_path):
    target = tmp_path / "sub" / "out.png"
    resolved = iw.resolve_output_path(str(target), "x", "png")
    assert resolved == target.resolve()
    assert resolved.parent.is_dir()


def test_resolve_default_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resolved = iw.resolve_output_path(None, "My Prompt Here", "png")
    assert resolved.suffix == ".png"
    assert "generated" in str(resolved)
    assert resolved.parent.is_dir()


def test_write_image_atomic_no_leftover_temp(tmp_path):
    target = tmp_path / "a.png"
    out = iw.write_image(PNG, target, "png")
    assert out.read_bytes() == PNG
    assert list(tmp_path.glob(".imagegen.*")) == []


def test_write_image_rejects_corrupt_leaves_no_file(tmp_path):
    target = tmp_path / "a.png"
    with pytest.raises(GatewayError):
        iw.write_image(b"junk", target, "png")
    assert not target.exists()
