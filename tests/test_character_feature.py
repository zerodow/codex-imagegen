"""Character batch: scene parsing + baseline/scene orchestration (generation mocked)."""

import json
from pathlib import Path

import pytest

from codex_imagegen.features import character as pipeline
from codex_imagegen.core.errors import InputError
from codex_imagegen.providers.generate.base import GenIntent

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_read_scenes_skips_blank_and_comments(tmp_path):
    f = tmp_path / "s.txt"
    f.write_text("# comment\n\nscene one\n  scene two  \n# another\n")
    assert pipeline._read_scenes(str(f)) == ["scene one", "scene two"]


def test_read_scenes_missing_file(tmp_path):
    with pytest.raises(InputError):
        pipeline._read_scenes(str(tmp_path / "nope.txt"))


def test_read_scenes_all_comments_raises(tmp_path):
    f = tmp_path / "s.txt"
    f.write_text("# only comments\n\n")
    with pytest.raises(InputError):
        pipeline._read_scenes(str(f))


def _mock_provider_and_gen(monkeypatch, sink):
    """Stub the provider (no auth/network) and capture each generate call."""

    def fake_gen(provider, prompt, out_path, **kwargs):
        sink.append((prompt, Path(out_path).name, kwargs.get("refs") is not None, kwargs.get("intent")))
        Path(out_path).write_bytes(PNG)
        return Path(out_path), {}

    monkeypatch.setattr(pipeline.registry, "get_image_provider", lambda *a, **k: object())
    monkeypatch.setattr(pipeline.orchestrator, "generate_to_file", fake_gen)


def test_generates_baseline_then_scenes_with_refs(tmp_path, monkeypatch):
    scenes = tmp_path / "s.txt"
    scenes.write_text("scene A\nscene B\n")
    calls = []
    _mock_provider_and_gen(monkeypatch, calls)
    code = pipeline.main([
        "--name", "Robo", "--baseline-prompt", "a robot mascot",
        "--scenes", str(scenes), "--outdir", str(tmp_path / "out"), "--quiet",
    ])
    assert code == 0
    # baseline: no refs, PLAIN framing
    assert calls[0] == ("a robot mascot", "00-baseline.png", False, GenIntent.PLAIN)
    # scenes: use the baseline as a CONSISTENCY reference
    assert calls[1][2] is True and calls[1][3] is GenIntent.CONSISTENCY
    assert calls[2][2] is True and calls[2][3] is GenIntent.CONSISTENCY
    assert len(calls) == 3


def test_existing_baseline_skips_baseline_gen(tmp_path, monkeypatch):
    base = tmp_path / "base.png"
    base.write_bytes(PNG)
    scenes = tmp_path / "s.txt"
    scenes.write_text("scene A\n")
    calls = []
    _mock_provider_and_gen(monkeypatch, calls)
    code = pipeline.main([
        "--name", "Robo", "--baseline-image", str(base),
        "--scenes", str(scenes), "--outdir", str(tmp_path / "out"), "--quiet",
    ])
    assert code == 0
    assert len(calls) == 1 and calls[0][2] is True  # only the scene, with refs


def test_batch_reuses_same_provider_across_scenes(tmp_path, monkeypatch):
    # The batch builds ONE provider and reuses it for every scene, so credentials
    # (and any mid-batch token refresh held inside the provider) carry forward.
    scenes = tmp_path / "s.txt"
    scenes.write_text("scene A\nscene B\n")
    base = tmp_path / "base.png"
    base.write_bytes(PNG)
    sentinel = object()
    construct_count = {"n": 0}
    providers_seen = []

    def fake_get(*a, **k):
        construct_count["n"] += 1
        return sentinel

    def fake_gen(provider, prompt, out_path, **kwargs):
        providers_seen.append(provider)
        Path(out_path).write_bytes(PNG)
        return Path(out_path), {}

    monkeypatch.setattr(pipeline.registry, "get_image_provider", fake_get)
    monkeypatch.setattr(pipeline.orchestrator, "generate_to_file", fake_gen)
    code = pipeline.main([
        "--name", "X", "--baseline-image", str(base),
        "--scenes", str(scenes), "--outdir", str(tmp_path / "o"), "--quiet",
    ])
    assert code == 0
    assert construct_count["n"] == 1               # provider built exactly once
    assert providers_seen == [sentinel, sentinel]  # same instance reused per scene


def test_nonpositive_timeout_exit2(tmp_path):
    scenes = tmp_path / "s.txt"
    scenes.write_text("scene A\n")
    base = tmp_path / "base.png"
    base.write_bytes(PNG)
    assert pipeline.main([
        "--name", "X", "--baseline-image", str(base),
        "--scenes", str(scenes), "--timeout", "0",
    ]) == 2


def test_scene_failure_reported_as_exit4(tmp_path, monkeypatch):
    scenes = tmp_path / "s.txt"
    scenes.write_text("scene A\n")
    base = tmp_path / "base.png"
    base.write_bytes(PNG)

    def boom(*args, **kwargs):
        raise InputError("simulated scene failure")

    monkeypatch.setattr(pipeline.registry, "get_image_provider", lambda *a, **k: object())
    monkeypatch.setattr(pipeline.orchestrator, "generate_to_file", boom)
    code = pipeline.main([
        "--name", "Robo", "--baseline-image", str(base),
        "--scenes", str(scenes), "--outdir", str(tmp_path / "out"), "--quiet",
    ])
    assert code == 4  # batch completes, failures surfaced via exit code


def test_all_fail_batch_json_still_emits_parseable_report(tmp_path, monkeypatch, capsys):
    # --json must always print a parseable report, even when every scene failed.
    scenes = tmp_path / "s.txt"
    scenes.write_text("scene A\n")
    base = tmp_path / "base.png"
    base.write_bytes(PNG)

    def boom(*args, **kwargs):
        raise InputError("simulated scene failure")

    monkeypatch.setattr(pipeline.registry, "get_image_provider", lambda *a, **k: object())
    monkeypatch.setattr(pipeline.orchestrator, "generate_to_file", boom)
    code = pipeline.main([
        "--name", "Robo", "--baseline-image", str(base),
        "--scenes", str(scenes), "--outdir", str(tmp_path / "out"), "--json",
    ])
    assert code == 4
    payload = json.loads(capsys.readouterr().out)  # stdout is valid JSON, not empty
    assert payload["images"] == [] and payload["totals"]["count"] == 0
