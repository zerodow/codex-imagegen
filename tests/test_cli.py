"""CLI argument validation, success path, reference flag, and error-to-exit-code mapping."""

from pathlib import Path

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
    out = tmp_path / "o.png"

    def fake_gen(prompt, out_path, **kwargs):
        Path(out_path).write_bytes(_PNG)
        return out_path, {}

    monkeypatch.setattr(cli.generator, "generate_to_file", fake_gen)
    assert cli.main(["a watercolor cat", "-o", str(out)]) == 0
    assert out.read_bytes() == _PNG


def test_reference_flag_loads_and_passes_refs(monkeypatch, tmp_path):
    ref = tmp_path / "ref.png"
    ref.write_bytes(_PNG)
    out = tmp_path / "o.png"
    captured = {}

    def fake_gen(prompt, out_path, **kwargs):
        captured["refs"] = kwargs.get("refs")
        Path(out_path).write_bytes(_PNG)
        return out_path, {}

    monkeypatch.setattr(cli.generator, "generate_to_file", fake_gen)
    assert cli.main(["a cat in space", "-o", str(out), "-i", str(ref)]) == 0
    assert captured["refs"] and captured["refs"][0][1] == "image/png"


def test_missing_reference_exit2(tmp_path):
    out = tmp_path / "o.png"
    assert cli.main(["a cat", "-o", str(out), "-i", str(tmp_path / "nope.png")]) == 2


def test_auth_error_exit3(monkeypatch, tmp_path):
    def boom(*args, **kwargs):
        raise AuthError("not logged in")

    monkeypatch.setattr(cli.generator, "generate_to_file", boom)
    assert cli.main(["a cat", "-o", str(tmp_path / "x.png")]) == 3
