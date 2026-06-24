"""imagegen-merge CLI: argument validation, success path, error-to-exit-code mapping."""

from pathlib import Path

from codex_imagegen import merge_cli
from codex_imagegen.providers.generate.base import GenIntent

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _ref(tmp_path, name):
    p = tmp_path / name
    p.write_bytes(_PNG)
    return str(p)


def test_empty_prompt_exit2(tmp_path):
    a, b = _ref(tmp_path, "a.png"), _ref(tmp_path, "b.png")
    assert merge_cli.main(["", "-i", a, "-i", b]) == 2


def test_single_reference_exit2(tmp_path):
    assert merge_cli.main(["scene", "-i", _ref(tmp_path, "a.png")]) == 2


def test_no_references_exit2():
    assert merge_cli.main(["scene"]) == 2


def test_label_count_mismatch_exit2(tmp_path):
    a, b = _ref(tmp_path, "a.png"), _ref(tmp_path, "b.png")
    assert merge_cli.main(["scene", "-i", a, "-i", b, "--label", "only one"]) == 2


def test_bad_size_exit2(tmp_path):
    a, b = _ref(tmp_path, "a.png"), _ref(tmp_path, "b.png")
    assert merge_cli.main(["scene", "-i", a, "-i", b, "--size", "3x3"]) == 2


def test_missing_reference_file_exit2(tmp_path):
    a = _ref(tmp_path, "a.png")
    assert merge_cli.main(["scene", "-i", a, "-i", str(tmp_path / "nope.png")]) == 2


def test_success_writes_file_and_passes_compose_args(monkeypatch, tmp_path):
    a, b = _ref(tmp_path, "a.png"), _ref(tmp_path, "b.png")
    out = tmp_path / "o.png"
    captured = {}

    def fake_run(provider, scene, out_path, **kwargs):
        captured["scene"] = scene
        captured["refs"] = kwargs.get("refs")
        captured["labels"] = kwargs.get("labels")
        captured["relation"] = kwargs.get("relation")
        Path(out_path).write_bytes(_PNG)
        return Path(out_path)

    monkeypatch.setattr(merge_cli.merge, "run", fake_run)
    code = merge_cli.main([
        "two friends", "-i", a, "-i", b,
        "--label", "friend one", "--label", "friend two",
        "--relation", "hugging", "-o", str(out),
    ])
    assert code == 0
    assert out.read_bytes() == _PNG
    assert captured["scene"] == "two friends"
    assert len(captured["refs"]) == 2 and captured["refs"][0][1] == "image/png"
    assert captured["labels"] == ["friend one", "friend two"]
    assert captured["relation"] == "hugging"


def test_unknown_provider_exit2(tmp_path):
    a, b = _ref(tmp_path, "a.png"), _ref(tmp_path, "b.png")
    out = str(tmp_path / "o.png")  # -o so the default ./generated path isn't created in cwd
    # registry raises InputError (exit 2) for an unknown provider name.
    assert merge_cli.main(["scene", "-i", a, "-i", b, "--provider", "nope", "-o", out]) == 2


def test_merge_provider_minimax_rejected_by_capability_guard(tmp_path):
    # Real minimax provider is single-subject -> merge.run's capability guard rejects
    # it (exit 2) instead of silently dropping a subject. No key needed (fails before generate).
    a, b = _ref(tmp_path, "a.png"), _ref(tmp_path, "b.png")
    out = str(tmp_path / "o.png")
    assert merge_cli.main(["scene", "-i", a, "-i", b, "--provider", "minimax", "-o", out]) == 2


def test_verify_without_vision_exit2(tmp_path):
    a, b = _ref(tmp_path, "a.png"), _ref(tmp_path, "b.png")
    assert merge_cli.main(["scene", "-i", a, "-i", b, "--verify", "-o", str(tmp_path / "o.png")]) == 2


def test_negative_max_retries_exit2(tmp_path):
    a, b = _ref(tmp_path, "a.png"), _ref(tmp_path, "b.png")
    assert merge_cli.main([
        "scene", "-i", a, "-i", b, "--vision", "minimax", "--verify",
        "--max-retries", "-1", "-o", str(tmp_path / "o.png"),
    ]) == 2


def test_vision_flag_wires_vision_provider(monkeypatch, tmp_path):
    a, b = _ref(tmp_path, "a.png"), _ref(tmp_path, "b.png")
    out = tmp_path / "o.png"
    captured = {}
    sentinel = object()

    def fake_run(provider, scene, out_path, **kwargs):
        captured["vision"] = kwargs.get("vision")
        captured["verify"] = kwargs.get("verify")
        captured["max_retries"] = kwargs.get("max_retries")
        Path(out_path).write_bytes(_PNG)
        return Path(out_path)

    monkeypatch.setattr(merge_cli.merge, "run", fake_run)
    monkeypatch.setattr(merge_cli.registry, "get_vision_provider", lambda name: sentinel)
    code = merge_cli.main([
        "scene", "-i", a, "-i", b, "--vision", "minimax", "--verify",
        "--max-retries", "2", "-o", str(out),
    ])
    assert code == 0
    assert captured["vision"] is sentinel
    assert captured["verify"] is True and captured["max_retries"] == 2


def test_vision_missing_key_exit3(monkeypatch, tmp_path):
    # Real providers: caption-before resolves the MiniMax key -> AuthError -> exit 3.
    # (Codex provider is built lazily and never reached; no network.)
    # chdir to an empty dir so the CLI's .env autoloader can't re-supply the key
    # from a developer's real project-root .env after we delete it here.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    a, b = _ref(tmp_path, "a.png"), _ref(tmp_path, "b.png")
    out = str(tmp_path / "o.png")
    assert merge_cli.main(["scene", "-i", a, "-i", b, "--vision", "minimax", "-o", out]) == 3


def test_default_no_vision_passes_none(monkeypatch, tmp_path):
    a, b = _ref(tmp_path, "a.png"), _ref(tmp_path, "b.png")
    out = tmp_path / "o.png"
    captured = {}

    def fake_run(provider, scene, out_path, **kwargs):
        captured["vision"] = kwargs.get("vision")
        Path(out_path).write_bytes(_PNG)
        return Path(out_path)

    monkeypatch.setattr(merge_cli.merge, "run", fake_run)
    assert merge_cli.main(["scene", "-i", a, "-i", b, "-o", str(out)]) == 0
    assert captured["vision"] is None
