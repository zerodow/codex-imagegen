"""Header/payload construction, SSE result extraction, and 401 refresh retry."""

import base64
import json
import time

import pytest

from codex_imagegen.providers.generate.codex import client as rc
from codex_imagegen.providers.generate.base import GenIntent
from codex_imagegen.core.errors import GatewayError

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
    payload = rc.build_payload("a cat", "1024x1024", "png", "gpt-6.1-sol")
    assert payload["stream"] is True
    assert payload["model"] == "gpt-6.1-sol"
    assert payload["tool_choice"] == "auto"
    tool = payload["tools"][0]
    assert tool["type"] == "image_generation"
    assert tool["size"] == "1024x1024"
    assert tool["output_format"] == "png"


def test_build_payload_auto_size_omits_size():
    payload = rc.build_payload("x", "auto", "png", "m")
    assert "size" not in payload["tools"][0]


def test_build_payload_consistency_forces_tool_and_attaches_image():
    refs = [("BASE64DATA", "image/png")]
    payload = rc.build_payload(
        "a cat in space", "auto", "png", "gpt-6.1-sol", refs=refs, intent=GenIntent.CONSISTENCY
    )
    assert payload["tool_choice"] == "required"  # forced for consistency framing
    content = payload["input"][0]["content"]
    assert content[0]["type"] == "input_image"
    assert content[0]["image_url"] == "data:image/png;base64,BASE64DATA"
    assert content[-1]["type"] == "input_text"
    # Regression lock: the single-subject wording the character pipeline relies on.
    assert content[-1]["text"].startswith("Generate a NEW image of the SAME character/subject")


def test_build_payload_compose_attaches_all_refs_in_order_with_labels():
    refs = [("AAA", "image/png"), ("BBB", "image/jpeg")]
    payload = rc.build_payload(
        "in a cafe", "auto", "png", "gpt-6.1-sol",
        refs=refs, intent=GenIntent.COMPOSE,
        labels=["the woman in red", "the robot mascot"], relation="shaking hands",
    )
    assert payload["tool_choice"] == "required"
    content = payload["input"][0]["content"]
    # All references attached as input_image, in order, before the text part.
    assert content[0]["image_url"] == "data:image/png;base64,AAA"
    assert content[1]["image_url"] == "data:image/jpeg;base64,BBB"
    assert content[-1]["type"] == "input_text"
    text = content[-1]["text"]
    assert "2 DISTINCT characters" in text
    assert "FIRST reference" in text and "SECOND reference" in text
    assert "the woman in red" in text and "the robot mascot" in text
    assert "shaking hands" in text
    assert "DO NOT blend" in text
    assert "in a cafe" in text


def test_build_payload_compose_without_labels_uses_generic_subjects():
    refs = [("A", "image/png"), ("B", "image/png")]
    payload = rc.build_payload("scene", "auto", "png", "m", refs=refs, intent=GenIntent.COMPOSE)
    text = payload["input"][0]["content"][-1]["text"]
    assert "the subject in reference image 1" in text
    assert "the subject in reference image 2" in text
    assert "together in the scene" in text  # default relation


def test_build_payload_compose_blank_label_falls_back_to_generic():
    refs = [("A", "image/png"), ("B", "image/png")]
    payload = rc.build_payload(
        "scene", "auto", "png", "m", refs=refs, intent=GenIntent.COMPOSE, labels=["   ", "Bob"]
    )
    text = payload["input"][0]["content"][-1]["text"]
    assert "(   )" not in text  # whitespace-only label must not render verbatim
    assert "the subject in reference image 1" in text  # fell back
    assert "(Bob)" in text


def test_build_payload_edit_attaches_source_and_templates_preservation():
    refs = [("SRCDATA", "image/png")]
    payload = rc.build_payload(
        "make the cap red", "auto", "png", "gpt-6.1-sol", refs=refs, intent=GenIntent.EDIT
    )
    assert payload["tool_choice"] == "required"  # forced for edit framing
    content = payload["input"][0]["content"]
    assert content[0]["type"] == "input_image"
    assert content[0]["image_url"] == "data:image/png;base64,SRCDATA"
    assert content[-1]["type"] == "input_text"
    text = content[-1]["text"]
    assert "make the cap red" in text  # the user delta
    assert "Preserve everything else" in text  # the load-bearing preservation clause


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


def test_post_once_captures_usage_and_models_from_completed(monkeypatch):
    b64 = base64.b64encode(_REAL_PNG).decode()
    events = [
        {"type": "response.output_item.done",
         "item": {"type": "image_generation_call", "result": b64}},
        {"type": "response.completed", "response": {
            "model": "gpt-6.1-sol",
            "usage": {"input_tokens": 2299, "output_tokens": 28, "total_tokens": 2327},
            "tool_usage": {"image_gen": {"input_tokens": 15, "output_tokens": 229, "total_tokens": 244}},
            "tools": [{"type": "image_generation", "model": "gpt-image-2-codex"}],
        }},
    ]
    monkeypatch.setattr(rc, "_stream", lambda *a, **k: iter(events))
    data, meta = rc._post_once({}, {}, 10, 5, False)
    assert data == _REAL_PNG
    assert meta["usage"]["total_tokens"] == 2327
    assert meta["image_usage"]["total_tokens"] == 244
    assert meta["models"] == {"orchestrator": "gpt-6.1-sol", "image": "gpt-image-2-codex"}
    assert "elapsed_s" in meta


def test_post_once_usage_absent_is_safe(monkeypatch):
    # No response.completed -> no usage keys, but elapsed_s is always present.
    monkeypatch.setattr(rc, "_stream", lambda *a, **k: iter(_success_events()))
    _data, meta = rc._post_once({}, {}, 10, 5, False)
    assert "usage" not in meta and "image_usage" not in meta
    assert "elapsed_s" in meta


def test_generate_refreshes_on_401_and_retries_with_new_token(monkeypatch):
    seen_headers: list[dict] = []

    def fake_post(headers, payload, total, stall, progress, **kwargs):
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


# --- account-pool endpoint ----------------------------------------------------


def test_stream_posts_to_default_backend(monkeypatch):
    seen = []
    monkeypatch.setattr(
        rc.urllib.request, "urlopen",
        lambda req, timeout=0: (seen.append(req.full_url), _FakeResp([]))[1],
    )
    list(rc._stream({}, {}, time.monotonic() + 5, 5))
    assert seen == [rc.CODEX_BACKEND]


def test_stream_posts_to_endpoint_override(monkeypatch):
    seen = []
    monkeypatch.setattr(
        rc.urllib.request, "urlopen",
        lambda req, timeout=0: (seen.append(req.full_url), _FakeResp([]))[1],
    )
    list(rc._stream({}, {}, time.monotonic() + 5, 5, url="https://pool.example.com/v1/responses"))
    assert seen == ["https://pool.example.com/v1/responses"]


def test_generate_forwards_endpoint_to_post_once(monkeypatch):
    seen = {}

    def fake_post(headers, payload, total, stall, progress, *, url=None):
        seen["url"] = url
        seen["auth_header"] = headers["Authorization"]
        seen["has_account_header"] = "chatgpt-account-id" in headers
        return _REAL_PNG, {}

    monkeypatch.setattr(rc, "_post_once", fake_post)
    monkeypatch.setattr(rc, "codex_version", lambda: "v")
    rc.generate_image_bytes(
        "p", size="auto", output_format="png", access_token="sk-cpa-x",
        account_id=None, refresh_token=None, auth={},
        endpoint="https://pool.example.com/v1/responses",
    )
    assert seen["url"] == "https://pool.example.com/v1/responses"
    assert seen["auth_header"] == "Bearer sk-cpa-x"
    # The proxy picks which pooled account renders; we must not pin one.
    assert seen["has_account_header"] is False


def test_pool_429_names_the_pool_not_codex_home(monkeypatch):
    def fake_post(*a, **k):
        raise GatewayError("usage limit reached", status=429)

    monkeypatch.setattr(rc, "_post_once", fake_post)
    monkeypatch.setattr(rc, "codex_version", lambda: "v")
    with pytest.raises(GatewayError) as exc:
        rc.generate_image_bytes(
            "p", size="auto", output_format="png", access_token="sk-cpa-x",
            account_id=None, refresh_token=None, auth={},
            endpoint="https://pool.example.com/v1/responses",
        )
    msg = str(exc.value)
    assert "pool.example.com" in msg and "pool" in msg
    # CODEX_HOME is meaningless in pool mode — pointing there sends the user astray.
    assert "CODEX_HOME" not in msg


def test_pool_401_blames_the_pool_key(monkeypatch):
    def fake_post(*a, **k):
        raise GatewayError("HTTP 401", status=401)

    monkeypatch.setattr(rc, "_post_once", fake_post)
    monkeypatch.setattr(rc, "codex_version", lambda: "v")
    with pytest.raises(GatewayError) as exc:
        rc.generate_image_bytes(
            "p", size="auto", output_format="png", access_token="sk-cpa-x",
            account_id=None, refresh_token=None, auth={},
            endpoint="https://pool.example.com/v1/responses",
        )
    assert rc._auth.POOL_KEY_ENV in str(exc.value)


def test_direct_429_still_names_codex_home(monkeypatch):
    # The pool branch must not have weakened the direct-mode diagnosis.
    def fake_post(*a, **k):
        raise GatewayError("usage limit reached", status=429)

    monkeypatch.setattr(rc, "_post_once", fake_post)
    monkeypatch.setattr(rc, "codex_version", lambda: "v")
    with pytest.raises(GatewayError) as exc:
        rc.generate_image_bytes(
            "p", size="auto", output_format="png", access_token="tok",
            account_id="acc", refresh_token=None, auth={"tokens": {"account_id": "acc"}},
        )
    assert "CODEX_HOME" in str(exc.value)


def test_non_auth_failure_is_untouched_in_pool_mode(monkeypatch):
    def fake_post(*a, **k):
        raise GatewayError("no image returned (events seen: response.created)")

    monkeypatch.setattr(rc, "_post_once", fake_post)
    monkeypatch.setattr(rc, "codex_version", lambda: "v")
    with pytest.raises(GatewayError) as exc:
        rc.generate_image_bytes(
            "p", size="auto", output_format="png", access_token="sk-cpa-x",
            account_id=None, refresh_token=None, auth={},
            endpoint="https://pool.example.com/v1/responses",
        )
    assert str(exc.value) == "no image returned (events seen: response.created)"


# --- image_generation tool stripped by the backend (plan without image gen) ---

_TOOLS_REJECTED_BODY = (
    '{"error":{"message":"Tool choice \'required\' must be specified with \'tools\' '
    'parameter.","type":"invalid_request_error","param":"tool_choice","code":null}}'
)


def _free_plan_auth() -> dict:
    claims = {"https://api.openai.com/auth": {"chatgpt_plan_type": "free"}}
    segment = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return {"tokens": {"access_token": f"h.{segment}.s", "account_id": "acc"}}


def _raise_http(code: int, body: str):
    import io
    import urllib.error

    def fake_stream(*a, **k):
        raise urllib.error.HTTPError("u", code, "bad", {}, io.BytesIO(body.encode()))
        yield  # pragma: no cover - makes this a generator like the real _stream

    return fake_stream


def test_post_once_flags_required_tool_choice_rejected_as_tool_unavailable(monkeypatch):
    monkeypatch.setattr(rc, "_stream", _raise_http(400, _TOOLS_REJECTED_BODY))
    with pytest.raises(rc.ImageToolUnavailable) as exc:
        rc._post_once({}, {}, 10, 5, False)
    assert exc.value.status == 400


def test_post_once_flags_text_only_answer_as_tool_unavailable(monkeypatch):
    events = [
        {"type": "response.created"},
        {"type": "response.output_text.delta", "delta": "Here is an apple"},
        {"type": "response.completed", "response": {}},
    ]
    monkeypatch.setattr(rc, "_stream", lambda *a, **k: iter(events))
    with pytest.raises(rc.ImageToolUnavailable) as exc:
        rc._post_once({}, {}, 10, 5, False)
    assert "never called the image_generation tool" in str(exc.value)


def test_post_once_other_400_is_plain_gateway_error(monkeypatch):
    monkeypatch.setattr(rc, "_stream", _raise_http(400, '{"error":{"message":"bad size"}}'))
    with pytest.raises(GatewayError) as exc:
        rc._post_once({}, {}, 10, 5, False)
    assert not isinstance(exc.value, rc.ImageToolUnavailable)


def test_direct_tool_unavailable_names_plan_and_remedies(monkeypatch):
    def fake_post(*a, **k):
        raise rc.ImageToolUnavailable(f"HTTP 400: {_TOOLS_REJECTED_BODY}", status=400)

    monkeypatch.setattr(rc, "_post_once", fake_post)
    monkeypatch.setattr(rc, "codex_version", lambda: "v")
    auth = _free_plan_auth()
    with pytest.raises(GatewayError) as exc:
        rc.generate_image_bytes(
            "p", size="auto", output_format="png", access_token=auth["tokens"]["access_token"],
            account_id="acc", refresh_token=None, auth=auth,
        )
    msg = str(exc.value)
    assert "plan free" in msg
    assert "codex login" in msg and "CODEX_HOME" in msg and rc._auth.POOL_URL_ENV in msg
    assert exc.value.exit_code == 4


def test_pool_tool_unavailable_blames_a_pooled_account(monkeypatch):
    def fake_post(*a, **k):
        raise rc.ImageToolUnavailable("no image returned: text only")

    monkeypatch.setattr(rc, "_post_once", fake_post)
    monkeypatch.setattr(rc, "codex_version", lambda: "v")
    with pytest.raises(GatewayError) as exc:
        rc.generate_image_bytes(
            "p", size="auto", output_format="png", access_token="sk-cpa-x",
            account_id=None, refresh_token=None, auth={},
            endpoint="https://pool.example.com/v1/responses",
        )
    msg = str(exc.value)
    assert "pool.example.com" in msg and "CODEX_HOME" not in msg


def _pool_generate():
    return rc.generate_image_bytes(
        "p", size="auto", output_format="png", access_token="sk-cpa-x",
        account_id=None, refresh_token=None, auth={},
        endpoint="https://pool.example.com/v1/responses",
    )


def test_pool_retries_when_a_free_pooled_account_strips_the_tool(monkeypatch):
    # The pool rotates accounts per request; a free one strips the tool, a paid
    # one renders. A stripped-tool failure renders nothing, so retrying is free.
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        if len(calls) < 3:
            raise rc.ImageToolUnavailable("HTTP 400: tools", status=400)
        return _REAL_PNG, {}

    monkeypatch.setattr(rc, "_post_once", fake_post)
    monkeypatch.setattr(rc, "codex_version", lambda: "v")
    data, _ = _pool_generate()
    assert data == _REAL_PNG and len(calls) == 3


def test_pool_gives_up_after_bounded_attempts(monkeypatch):
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        raise rc.ImageToolUnavailable("HTTP 400: tools", status=400)

    monkeypatch.setattr(rc, "_post_once", fake_post)
    monkeypatch.setattr(rc, "codex_version", lambda: "v")
    with pytest.raises(rc.ImageToolUnavailable) as exc:
        _pool_generate()
    assert len(calls) == rc.POOL_TOOL_ATTEMPTS
    assert "pool.example.com" in str(exc.value)


def test_pool_does_not_retry_other_failures(monkeypatch):
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        raise GatewayError("usage limit reached", status=429)

    monkeypatch.setattr(rc, "_post_once", fake_post)
    monkeypatch.setattr(rc, "codex_version", lambda: "v")
    with pytest.raises(GatewayError):
        _pool_generate()
    assert len(calls) == 1


def test_direct_does_not_retry_stripped_tool(monkeypatch):
    # One account in direct mode: retrying would hit the same free plan again.
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        raise rc.ImageToolUnavailable("HTTP 400: tools", status=400)

    monkeypatch.setattr(rc, "_post_once", fake_post)
    monkeypatch.setattr(rc, "codex_version", lambda: "v")
    with pytest.raises(rc.ImageToolUnavailable):
        rc.generate_image_bytes(
            "p", size="auto", output_format="png", access_token="tok",
            account_id="acc", refresh_token=None, auth={"tokens": {"account_id": "acc"}},
        )
    assert len(calls) == 1
