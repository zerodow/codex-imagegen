"""CLI argument validation, success path, reference flag, and error-to-exit-code mapping."""

from pathlib import Path

from codex_imagegen import cli
from codex_imagegen.core.errors import AuthError
from codex_imagegen.providers.generate.base import GenIntent

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_empty_prompt_exit2():
    assert cli.main([""]) == 2


def test_bad_size_exit2():
    assert cli.main(["a cat", "--size", "999x999"]) == 2


def test_nonpositive_timeout_exit2():
    assert cli.main(["a cat", "--timeout", "0"]) == 2


def test_success_writes_file(monkeypatch, tmp_path):
    out = tmp_path / "o.png"

    def fake_gen(provider, prompt, out_path, **kwargs):
        Path(out_path).write_bytes(_PNG)
        return out_path, {}

    monkeypatch.setattr(cli.orchestrator, "generate_to_file", fake_gen)
    assert cli.main(["a watercolor cat", "-o", str(out)]) == 0
    assert out.read_bytes() == _PNG


def test_no_reference_uses_plain_intent(monkeypatch, tmp_path):
    out = tmp_path / "o.png"
    captured = {}

    def fake_gen(provider, prompt, out_path, **kwargs):
        captured["intent"] = kwargs.get("intent")
        Path(out_path).write_bytes(_PNG)
        return out_path, {}

    monkeypatch.setattr(cli.orchestrator, "generate_to_file", fake_gen)
    assert cli.main(["a watercolor cat", "-o", str(out)]) == 0
    assert captured["intent"] is GenIntent.PLAIN


def test_reference_flag_loads_refs_and_consistency_intent(monkeypatch, tmp_path):
    ref = tmp_path / "ref.png"
    ref.write_bytes(_PNG)
    out = tmp_path / "o.png"
    captured = {}

    def fake_gen(provider, prompt, out_path, **kwargs):
        captured["refs"] = kwargs.get("refs")
        captured["intent"] = kwargs.get("intent")
        Path(out_path).write_bytes(_PNG)
        return out_path, {}

    monkeypatch.setattr(cli.orchestrator, "generate_to_file", fake_gen)
    assert cli.main(["a cat in space", "-o", str(out), "-i", str(ref)]) == 0
    assert captured["refs"] and captured["refs"][0][1] == "image/png"
    assert captured["intent"] is GenIntent.CONSISTENCY


def test_missing_reference_exit2(tmp_path):
    out = tmp_path / "o.png"
    assert cli.main(["a cat", "-o", str(out), "-i", str(tmp_path / "nope.png")]) == 2


def test_auth_error_exit3(monkeypatch, tmp_path):
    def boom(*args, **kwargs):
        raise AuthError("not logged in")

    monkeypatch.setattr(cli.orchestrator, "generate_to_file", boom)
    assert cli.main(["a cat", "-o", str(tmp_path / "x.png")]) == 3


def test_provider_flag_routes_to_minimax(monkeypatch, tmp_path):
    out = tmp_path / "o.png"
    captured = {}

    def fake_gen(provider, prompt, out_path, **kwargs):
        captured["provider"] = provider.name
        Path(out_path).write_bytes(_PNG)
        return out_path, {}

    monkeypatch.setattr(cli.orchestrator, "generate_to_file", fake_gen)
    assert cli.main(["a portrait", "-o", str(out), "--provider", "minimax"]) == 0
    assert captured["provider"] == "minimax"


def test_unknown_provider_exit2(tmp_path):
    assert cli.main(["a cat", "-o", str(tmp_path / "x.png"), "--provider", "nope"]) == 2
