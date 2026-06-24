"""MiniMax Image-01: capabilities, single-subject intents, request/response shape."""

import base64
import json

import pytest

from codex_imagegen.core.errors import AuthError, GatewayError, InputError
from codex_imagegen.providers.generate.base import GenIntent
from codex_imagegen.providers.generate.minimax import client as mclient
from codex_imagegen.providers.generate.minimax import provider as prov_mod
from codex_imagegen.providers.generate.minimax.provider import MiniMaxImageProvider

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


# ---- capabilities ----

def test_capabilities_are_single_subject():
    caps = MiniMaxImageProvider().capabilities
    assert caps.multi_subject is False
    assert caps.max_refs == 1
    assert GenIntent.COMPOSE not in caps.intents
    assert caps.intents == frozenset({GenIntent.PLAIN, GenIntent.CONSISTENCY})
    assert caps.metered == "pay-per-image"


def test_name():
    assert MiniMaxImageProvider().name == "minimax"


# ---- provider.generate intent handling ----

def _gen(p, **kw):
    return p.generate("a portrait", total_timeout=10, stall_timeout=5, **kw)


def test_plain_generate_sends_no_ref(monkeypatch):
    captured = {}
    monkeypatch.setattr(prov_mod.client, "resolve_api_key", lambda: "k")

    def fake(key, *, prompt, size, ref, model, timeout):
        captured["ref"] = ref
        return PNG

    monkeypatch.setattr(prov_mod.client, "generate_image", fake)
    data, meta = _gen(MiniMaxImageProvider(), intent=GenIntent.PLAIN)
    assert data == PNG and captured["ref"] is None and meta["provider"] == "minimax"


def test_consistency_passes_single_ref(monkeypatch):
    captured = {}
    monkeypatch.setattr(prov_mod.client, "resolve_api_key", lambda: "k")
    monkeypatch.setattr(prov_mod.client, "generate_image",
                        lambda key, **kw: (captured.update(kw) or PNG))
    _gen(MiniMaxImageProvider(), intent=GenIntent.CONSISTENCY, refs=[("B", "image/png")])
    assert captured["ref"] == ("B", "image/png")


def test_consistency_without_ref_raises(monkeypatch):
    monkeypatch.setattr(prov_mod.client, "resolve_api_key", lambda: "k")
    with pytest.raises(InputError):
        _gen(MiniMaxImageProvider(), intent=GenIntent.CONSISTENCY, refs=[])


def test_consistency_multiple_refs_rejected(monkeypatch):
    monkeypatch.setattr(prov_mod.client, "resolve_api_key", lambda: "k")
    with pytest.raises(InputError, match="single subject"):
        _gen(MiniMaxImageProvider(), intent=GenIntent.CONSISTENCY,
             refs=[("A", "image/png"), ("B", "image/png")])


def test_compose_intent_rejected():
    # Defense in depth: even if something bypassed the merge guard, the provider refuses.
    with pytest.raises(InputError, match="does not support"):
        _gen(MiniMaxImageProvider(), intent=GenIntent.COMPOSE, refs=[("A", "image/png")])


def test_missing_key_raises_autherror(monkeypatch):
    monkeypatch.delenv("MINIMAX_IMAGE_API_KEY", raising=False)
    with pytest.raises(AuthError):
        _gen(MiniMaxImageProvider(), intent=GenIntent.PLAIN)


# ---- client: key (distinct from vision), size, request/response ----

def test_resolve_image_key_uses_distinct_env(monkeypatch):
    monkeypatch.setenv("MINIMAX_IMAGE_API_KEY", "payg")
    monkeypatch.setenv("MINIMAX_API_KEY", "token-plan")  # must NOT be used here
    assert mclient.resolve_api_key() == "payg"


def test_resolve_image_key_absent_raises(monkeypatch):
    monkeypatch.delenv("MINIMAX_IMAGE_API_KEY", raising=False)
    with pytest.raises(AuthError):
        mclient.resolve_api_key()


def test_parse_size():
    assert mclient._parse_size("1024x1024") == (1024, 1024)
    assert mclient._parse_size("1536x1024") == (1536, 1024)
    assert mclient._parse_size("auto") is None
    assert mclient._parse_size(None) is None


def test_generate_image_decodes_base64_and_sends_subject_ref(monkeypatch):
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"data": {"image_base64": [base64.b64encode(PNG).decode()]}}).encode()

    def fake_urlopen(req, timeout=0):
        captured["body"] = json.loads(req.data.decode())
        return _Resp()

    monkeypatch.setattr(mclient.urllib.request, "urlopen", fake_urlopen)
    out = mclient.generate_image("K", prompt="p", size="1024x1024", ref=("B64", "image/png"))
    assert out == PNG
    assert captured["body"]["subject_reference"][0]["image_file"] == "data:image/png;base64,B64"
    assert captured["body"]["width"] == 1024 and captured["body"]["height"] == 1024


def test_generate_image_without_base64_raises(monkeypatch):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"data": {"image_urls": ["http://x"]}}).encode()

    monkeypatch.setattr(mclient.urllib.request, "urlopen", lambda req, timeout=0: _Resp())
    with pytest.raises(GatewayError):
        mclient.generate_image("K", prompt="p")
