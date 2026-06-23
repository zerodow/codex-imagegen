"""CLI argument validation, success path, and error-to-exit-code mapping."""

import pytest

from codex_imagegen import cli
from codex_imagegen.errors import AuthError

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_empty_prompt_exit2():
    assert cli.main([""]) == 2


def test_bad_size_exit2():
    assert cli.main(["a cat", "--size", "999x999"]) == 2


def test_nonpositive_timeout_exit2():
    assert cli.main(["a cat", "--timeout", "0"]) == 2


def test_success_writes_file(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.auth, "load_auth", lambda: {"tokens": {"access_token": "x"}})
    monkeypatch.setattr(cli.auth, "extract_tokens", lambda a: ("x", "acc", "r"))
    monkeypatch.setattr(cli, "generate_image_bytes", lambda *a, **k: (_PNG, {}))
    out = tmp_path / "o.png"
    code = cli.main(["a watercolor cat", "-o", str(out)])
    assert code == 0
    assert out.read_bytes() == _PNG


def test_auth_error_exit3(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    def boom():
        raise AuthError("not logged in")

    monkeypatch.setattr(cli.auth, "load_auth", boom)
    assert cli.main(["a cat", "-o", str(tmp_path / "x.png")]) == 3
