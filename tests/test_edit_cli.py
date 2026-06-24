"""imagegen-edit: arg validation, single-source rule, and EDIT success path."""

from pathlib import Path

from codex_imagegen import edit_cli
from codex_imagegen.core import orchestrator
from codex_imagegen.providers.generate.base import GenIntent

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _src(tmp_path) -> str:
    p = tmp_path / "s.png"
    p.write_bytes(_PNG)
    return str(p)


def test_empty_instruction_exit2(tmp_path):
    assert edit_cli.main(["", "-i", _src(tmp_path)]) == 2


def test_requires_a_source_exit2():
    assert edit_cli.main(["make it red"]) == 2


def test_rejects_two_sources_exit2(tmp_path):
    a, b = _src(tmp_path), _src(tmp_path)
    assert edit_cli.main(["make it red", "-i", a, "-i", b]) == 2


def test_bad_size_exit2(tmp_path):
    assert edit_cli.main(["make it red", "-i", _src(tmp_path), "--size", "999x999"]) == 2


def test_missing_source_exit2(tmp_path):
    assert edit_cli.main(["make it red", "-i", str(tmp_path / "nope.png")]) == 2


def test_success_uses_edit_intent_and_single_source(monkeypatch, tmp_path):
    out = tmp_path / "o.png"
    captured = {}

    def fake_gen(provider, prompt, out_path, **kwargs):
        captured["intent"] = kwargs.get("intent")
        captured["refs"] = kwargs.get("refs")
        Path(out_path).write_bytes(_PNG)
        return out_path, {"action": "edit"}

    monkeypatch.setattr(orchestrator, "generate_to_file", fake_gen)
    assert edit_cli.main(["make the cap red", "-i", _src(tmp_path), "-o", str(out)]) == 0
    assert out.read_bytes() == _PNG
    assert captured["intent"] is GenIntent.EDIT
    assert captured["refs"] and captured["refs"][0][1] == "image/png"
