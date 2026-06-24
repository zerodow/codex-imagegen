"""output_report: human block, JSON, quiet/json precedence, batch aggregate."""

import json
import struct

from codex_imagegen.core import output_report


def _png(w: int, h: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0d" + b"IHDR" + struct.pack(">II", w, h) + b"\x00" * 4


META_FULL = {
    "action": "edit",
    "quality": "high",
    "models": {"orchestrator": "gpt-5.5", "image": "gpt-image-2-codex"},
    "image_usage": {
        "input_tokens": 15,
        "input_tokens_details": {"image_tokens": 0, "text_tokens": 15},
        "output_tokens": 229,
        "output_tokens_details": {"image_tokens": 229},
        "total_tokens": 244,
    },
    "usage": {"input_tokens": 2299, "output_tokens": 28, "total_tokens": 2327},
    "elapsed_s": 18.2,
}


def _img(tmp_path, name="o.png"):
    p = tmp_path / name
    p.write_bytes(_png(320, 200))
    return p


def test_human_report_has_models_dims_tokens_time(tmp_path):
    out = output_report.result_line(_img(tmp_path), META_FULL)
    assert "gpt-image-2-codex (via gpt-5.5)" in out
    assert "320×200" in out
    assert "total 244 tok" in out  # image-gen cost
    assert "2327 tok" in out       # orchestration
    assert "18.2s" in out


def test_missing_usage_shows_na(tmp_path):
    out = output_report.result_line(_img(tmp_path), {"elapsed_s": 5.0})
    assert out.count("n/a") >= 2  # both image + llm usage degrade to n/a, no crash


def test_json_report_stable_keys(tmp_path):
    p = _img(tmp_path)
    payload = json.loads(output_report.result_line(p, META_FULL, as_json=True))
    assert payload["path"] == str(p)
    assert payload["width"] == 320 and payload["height"] == 200
    assert payload["image_usage"]["total_tokens"] == 244
    assert payload["usage"]["total_tokens"] == 2327


def test_quiet_prints_path_only(tmp_path):
    p = _img(tmp_path)
    assert output_report.result_line(p, META_FULL, quiet=True) == str(p)


def test_json_takes_precedence_over_quiet(tmp_path):
    out = output_report.result_line(_img(tmp_path), META_FULL, as_json=True, quiet=True)
    json.loads(out)  # must be JSON, not a bare path


def test_format_batch_aggregates_totals(tmp_path):
    items = [(_img(tmp_path, "1.png"), META_FULL), (_img(tmp_path, "2.png"), META_FULL)]
    out = output_report.format_batch(items)
    assert "2 image(s)" in out
    assert "488 img tok" in out  # 244 * 2


def test_format_batch_quiet_paths_only(tmp_path):
    p1, p2 = _img(tmp_path, "1.png"), _img(tmp_path, "2.png")
    out = output_report.format_batch([(p1, META_FULL), (p2, META_FULL)], quiet=True)
    assert out == f"{p1}\n{p2}"
