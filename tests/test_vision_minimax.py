"""MiniMax vision: key resolution, request shape, defensive verdict parsing."""

import json

import pytest

from codex_imagegen.core.errors import AuthError
from codex_imagegen.providers.vision.base import CompositionVerdict, SubjectDescription
from codex_imagegen.providers.vision.minimax import client as mclient
from codex_imagegen.providers.vision.minimax import provider as prov_mod
from codex_imagegen.providers.vision.minimax.provider import MiniMaxVisionProvider, _parse_verdict


# ---- client: key + request shape ----

def test_resolve_api_key_present(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "abc")
    assert mclient.resolve_api_key() == "abc"


def test_resolve_api_key_absent_raises(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(AuthError):
        mclient.resolve_api_key()


def test_chat_with_image_sends_data_uri_and_bearer(monkeypatch):
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode()

    def fake_urlopen(req, timeout=0):
        captured["body"] = json.loads(req.data.decode())
        captured["auth"] = req.get_header("Authorization")
        return _Resp()

    monkeypatch.setattr(mclient.urllib.request, "urlopen", fake_urlopen)
    out = mclient.chat_with_image("KEY", system="s", user_text="u", image_b64="B64", mime="image/png")
    assert out == "hi"
    assert captured["auth"] == "Bearer KEY"
    assert captured["body"]["stream"] is False
    content = captured["body"]["messages"][1]["content"]
    assert content[1]["image_url"]["url"] == "data:image/png;base64,B64"


# ---- provider: describe + verify ----

def test_describe_subject_returns_trimmed_text(monkeypatch):
    monkeypatch.setattr(prov_mod.client, "resolve_api_key", lambda: "k")
    monkeypatch.setattr(prov_mod.client, "chat_with_image", lambda key, **kw: "  woman in red coat  ")
    d = MiniMaxVisionProvider().describe_subject("b64", "image/png")
    assert isinstance(d, SubjectDescription) and d.text == "woman in red coat"


def test_verify_parses_valid_json(monkeypatch):
    monkeypatch.setattr(prov_mod.client, "resolve_api_key", lambda: "k")
    monkeypatch.setattr(
        prov_mod.client, "chat_with_image",
        lambda key, **kw: '{"ok": true, "blended": false, "missing": [], "reasons": "both present"}',
    )
    v = MiniMaxVisionProvider().verify_composition("b", "image/png", expected=["a", "b"])
    assert v.ok is True and v.blended is False and v.missing == [] and "both" in v.reasons


def test_verify_extracts_json_from_chatty_reply(monkeypatch):
    monkeypatch.setattr(prov_mod.client, "resolve_api_key", lambda: "k")
    monkeypatch.setattr(
        prov_mod.client, "chat_with_image",
        lambda key, **kw: 'Sure!\n{"ok": false, "blended": true, "missing": ["bob"], "reasons": "merged"}\nHTH',
    )
    v = MiniMaxVisionProvider().verify_composition("b", "image/png", expected=["bob", "alice"])
    assert v.ok is False and v.blended is True and v.missing == ["bob"]


def test_verify_malformed_reply_is_not_ok(monkeypatch):
    monkeypatch.setattr(prov_mod.client, "resolve_api_key", lambda: "k")
    monkeypatch.setattr(prov_mod.client, "chat_with_image", lambda key, **kw: "totally not json")
    v = MiniMaxVisionProvider().verify_composition("b", "image/png", expected=["x"])
    assert v.ok is False and "totally not json" in v.reasons


def test_describe_strips_think_reasoning(monkeypatch):
    monkeypatch.setattr(prov_mod.client, "resolve_api_key", lambda: "k")
    monkeypatch.setattr(
        prov_mod.client, "chat_with_image",
        lambda key, **kw: "<think>\nThe user wants a compact line. Let me look...\n</think>\nwoman with a short black bob",
    )
    d = MiniMaxVisionProvider().describe_subject("b64", "image/png")
    assert d.text == "woman with a short black bob"  # reasoning stripped


def test_describe_unclosed_think_collapses_to_empty(monkeypatch):
    monkeypatch.setattr(prov_mod.client, "resolve_api_key", lambda: "k")
    monkeypatch.setattr(prov_mod.client, "chat_with_image", lambda key, **kw: "<think>still thinking, never answered")
    d = MiniMaxVisionProvider().describe_subject("b64", "image/png")
    assert d.text == ""  # better empty than reasoning garbage as a label


def test_verify_strips_think_before_json(monkeypatch):
    monkeypatch.setattr(prov_mod.client, "resolve_api_key", lambda: "k")
    # Reasoning contains a stray brace {maybe}; without stripping, the greedy JSON
    # extractor would span from it into the real object and break the parse.
    monkeypatch.setattr(
        prov_mod.client, "chat_with_image",
        lambda key, **kw: '<think>could be {maybe} ok</think>{"ok": true, "blended": false, "missing": [], "reasons": "fine"}',
    )
    v = MiniMaxVisionProvider().verify_composition("b", "image/png", expected=["a", "b"])
    assert v.ok is True and v.blended is False and v.missing == []


def test_parse_verdict_empty_is_not_ok():
    assert _parse_verdict("") == CompositionVerdict(ok=False, reasons="no response")


def test_missing_key_raises_before_network(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(AuthError):
        MiniMaxVisionProvider().describe_subject("b", "image/png")
