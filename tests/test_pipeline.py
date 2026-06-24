"""Pipeline: scene parsing + baseline/scene orchestration (generation mocked)."""

from pathlib import Path

import pytest

from codex_imagegen import pipeline
from codex_imagegen.errors import InputError

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


def _mock_creds_and_gen(monkeypatch, sink):
    def fake_gen(prompt, out_path, **kwargs):
        sink.append((prompt, Path(out_path).name, kwargs.get("refs") is not None))
        Path(out_path).write_bytes(PNG)
        return Path(out_path), {}

    monkeypatch.setattr(pipeline.generator, "load_credentials", lambda: {"tokens": {"access_token": "x"}})
    monkeypatch.setattr(pipeline.generator, "generate_to_file", fake_gen)


def test_generates_baseline_then_scenes_with_refs(tmp_path, monkeypatch):
    scenes = tmp_path / "s.txt"
    scenes.write_text("scene A\nscene B\n")
    calls = []
    _mock_creds_and_gen(monkeypatch, calls)
    code = pipeline.main([
        "--name", "Robo", "--baseline-prompt", "a robot mascot",
        "--scenes", str(scenes), "--outdir", str(tmp_path / "out"), "--quiet",
    ])
    assert code == 0
    assert calls[0] == ("a robot mascot", "00-baseline.png", False)  # baseline: no refs
    assert calls[1][2] is True and calls[2][2] is True  # scenes use the baseline as ref
    assert len(calls) == 3


def test_existing_baseline_skips_baseline_gen(tmp_path, monkeypatch):
    base = tmp_path / "base.png"
    base.write_bytes(PNG)
    scenes = tmp_path / "s.txt"
    scenes.write_text("scene A\n")
    calls = []
    _mock_creds_and_gen(monkeypatch, calls)
    code = pipeline.main([
        "--name", "Robo", "--baseline-image", str(base),
        "--scenes", str(scenes), "--outdir", str(tmp_path / "out"), "--quiet",
    ])
    assert code == 0
    assert len(calls) == 1 and calls[0][2] is True  # only the scene, with refs


def test_batch_reuses_same_auth_dict_across_scenes(tmp_path, monkeypatch):
    # Proves the shared auth dict is reused (not reloaded) per scene, so a token
    # refreshed mid-batch carries forward. Each call mutates the dict like a real
    # 401 refresh would; the next call must observe that mutation.
    scenes = tmp_path / "s.txt"
    scenes.write_text("scene A\nscene B\n")
    base = tmp_path / "base.png"
    base.write_bytes(PNG)
    seen_tokens = []

    def fake_gen(prompt, out_path, **kwargs):
        auth_data = kwargs.get("auth_data")
        seen_tokens.append(auth_data["tokens"]["access_token"])
        auth_data["tokens"]["access_token"] = f"refreshed-{len(seen_tokens)}"
        Path(out_path).write_bytes(PNG)
        return Path(out_path), {}

    monkeypatch.setattr(pipeline.generator, "load_credentials", lambda: {"tokens": {"access_token": "orig"}})
    monkeypatch.setattr(pipeline.generator, "generate_to_file", fake_gen)
    code = pipeline.main([
        "--name", "X", "--baseline-image", str(base),
        "--scenes", str(scenes), "--outdir", str(tmp_path / "o"), "--quiet",
    ])
    assert code == 0
    assert seen_tokens == ["orig", "refreshed-1"]  # scene B saw scene A's mutation


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

    def boom(prompt, out_path, **kwargs):
        raise InputError("simulated scene failure")

    monkeypatch.setattr(pipeline.generator, "load_credentials", lambda: {"tokens": {"access_token": "x"}})
    monkeypatch.setattr(pipeline.generator, "generate_to_file", boom)
    code = pipeline.main([
        "--name", "Robo", "--baseline-image", str(base),
        "--scenes", str(scenes), "--outdir", str(tmp_path / "out"), "--quiet",
    ])
    assert code == 4  # batch completes, failures surfaced via exit code
