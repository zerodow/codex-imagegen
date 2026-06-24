"""Header/payload construction, SSE result extraction, and 401 refresh retry."""

import base64
import json
import time

import pytest

from codex_imagegen import responses_client as rc
from codex_imagegen.errors import GatewayError

_REAL_PNG = b"\x89PNG\r\n\x1a\nDATA"


class _FakeResp:
    """Minimal stand-in for an SSE HTTP response: iterates raw byte-lines."""

    def __init__(self, lines: list[bytes]):
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)

    def close(self):
        pass


def test_stream_frames_events_and_flushes_unterminated_final(monkeypatch):
    # The final `output_item.done` deliberately has NO trailing blank line —
    # regression guard for the dropped-final-event bug.
    b64 = base64.b64encode(_REAL_PNG).decode()
    done = json.dumps(
        {"type": "response.output_item.done",
         "item": {"type": "image_generation_call", "result": b64}}
    )
    lines = [
        b"event: x\n",
        b'data: {"type": "response.created"}\n',
        b"\n",
        b": keepalive comment\n",
        ("data: " + done + "\n").encode(),
    ]
    monkeypatch.setattr(rc.urllib.request, "urlopen", lambda req, timeout=0: _FakeResp(lines))
    events = list(rc._stream({}, {}, time.monotonic() + 100, 100))
    assert events[0]["type"] == "response.created"
    assert events[-1]["item"]["result"] == b64


def test_stream_done_sentinel_terminates(monkeypatch):
    lines = [b'data: {"type": "response.created"}\n', b"\n", b"data: [DONE]\n", b"\n"]
    monkeypatch.setattr(rc.urllib.request, "urlopen", lambda req, timeout=0: _FakeResp(lines))
    events = list(rc._stream({}, {}, time.monotonic() + 100, 100))
    assert [e["type"] for e in events] == ["response.created"]


def test_build_payload_shape():
    payload = rc.build_payload("a cat", "1024x1024", "png", "gpt-5.5")
    assert payload["stream"] is True
    assert payload["model"] == "gpt-5.5"
    assert payload["tool_choice"] == "auto"
    tool = payload["tools"][0]
    assert tool["type"] == "image_generation"
    assert tool["size"] == "1024x1024"
    assert tool["output_format"] == "png"


def test_build_payload_auto_size_omits_size():
    payload = rc.build_payload("x", "auto", "png", "m")
    assert "size" not in payload["tools"][0]


def test_build_payload_with_refs_forces_tool_and_attaches_image():
    refs = [("BASE64DATA", "image/png")]
    payload = rc.build_payload("a cat in space", "auto", "png", "gpt-5.5", refs=refs)
    assert payload["tool_choice"] == "required"  # forced when references present
    content = payload["input"][0]["content"]
    assert content[0]["type"] == "input_image"
    assert content[0]["image_url"] == "data:image/png;base64,BASE64DATA"
    assert content[-1]["type"] == "input_text"


def test_build_headers_includes_required_fields():
    headers = rc.build_headers("tok", "acc", "0.141.0")
    assert headers["Authorization"] == "Bearer tok"
    assert headers["chatgpt-account-id"] == "acc"
    assert headers["originator"] == "codex_cli_rs"
    assert headers["Accept"] == "text/event-stream"
    assert headers["session_id"] == headers["x-client-request-id"]


def test_build_headers_omits_account_when_none():
    headers = rc.build_headers("tok", None, "v")
    assert "chatgpt-account-id" not in headers


def _success_events():
    b64 = base64.b64encode(_REAL_PNG).decode()
    return [
        {"type": "response.image_generation_call.in_progress"},
        {"type": "response.image_generation_call.generating"},
        {
            "type": "response.output_item.done",
            "item": {"type": "image_generation_call", "result": b64, "revised_prompt": "rp"},
        },
    ]


def test_post_once_extracts_image(monkeypatch):
    monkeypatch.setattr(rc, "_stream", lambda *a, **k: iter(_success_events()))
    data, meta = rc._post_once({}, {}, 10, 5, False)
    assert data == _REAL_PNG
    assert "result" not in meta
    assert meta.get("revised_prompt") == "rp"


def test_post_once_surfaces_backend_error(monkeypatch):
    events = [{"type": "response.failed", "response": {"error": {"message": "quota exceeded"}}}]
    monkeypatch.setattr(rc, "_stream", lambda *a, **k: iter(events))
    with pytest.raises(GatewayError) as exc:
        rc._post_once({}, {}, 10, 5, False)
    assert "quota exceeded" in str(exc.value)


def test_post_once_no_image_raises(monkeypatch):
    monkeypatch.setattr(rc, "_stream", lambda *a, **k: iter([{"type": "response.created"}]))
    with pytest.raises(GatewayError):
        rc._post_once({}, {}, 10, 5, False)


def test_generate_refreshes_on_401_and_retries_with_new_token(monkeypatch):
    seen_headers: list[dict] = []

    def fake_post(headers, payload, total, stall, progress):
        seen_headers.append(headers)
        if len(seen_headers) == 1:
            raise GatewayError("HTTP 401: expired", status=401)
        return _REAL_PNG, {}

    monkeypatch.setattr(rc, "_post_once", fake_post)
    monkeypatch.setattr(rc, "codex_version", lambda: "0.141.0")
    monkeypatch.setattr(rc._auth, "refresh_and_persist", lambda auth, rt: "newtok")
    data, _ = rc.generate_image_bytes(
        "p", size="auto", output_format="png",
        access_token="old", account_id="a", refresh_token="r", auth={}, progress=False,
    )
    assert data == _REAL_PNG
    assert len(seen_headers) == 2
    # The retry MUST use the refreshed token, not the expired one.
    assert seen_headers[0]["Authorization"] == "Bearer old"
    assert seen_headers[1]["Authorization"] == "Bearer newtok"


def test_generate_raises_401_when_no_refresh_token(monkeypatch):
    def fake_post(*a, **k):
        raise GatewayError("HTTP 401", status=401)

    monkeypatch.setattr(rc, "_post_once", fake_post)
    monkeypatch.setattr(rc, "codex_version", lambda: "v")
    with pytest.raises(GatewayError):
        rc.generate_image_bytes(
            "p", size="auto", output_format="png",
            access_token="old", account_id=None, refresh_token=None, auth={}, progress=False,
        )
