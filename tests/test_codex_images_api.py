"""Pool Images API path: URL mapping, payload, response parsing, error wording."""

import base64
import io
import json
import urllib.error

import pytest

from codex_imagegen.core.errors import GatewayError
from codex_imagegen.providers.generate.base import GenIntent
from codex_imagegen.providers.generate.codex import images_api

_POOL = "https://pool.example.com/v1/responses"
_PNG = b"\x89PNG\r\n\x1a\nDATA"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(monkeypatch, body: dict, seen: dict):
    def fake(req, timeout):
        seen.update(url=req.full_url, body=json.loads(req.data), headers=dict(req.headers))
        return _Resp(json.dumps(body).encode())

    monkeypatch.setattr(images_api.urllib.request, "urlopen", fake)


def _call(**kw):
    args = dict(size="1024x1024", output_format="png", api_key="sk-pool", endpoint=_POOL)
    args.update(kw)
    return images_api.generate_image_bytes("an apple", **args)


def test_images_url_maps_responses_endpoint():
    assert images_api.images_url(_POOL) == "https://pool.example.com/v1/images/generations"
    assert images_api.images_url(_POOL, edits=True) == "https://pool.example.com/v1/images/edits"


def test_payload_omits_auto_size():
    assert "size" not in images_api.build_payload("p", "auto", "png", "m")
    assert images_api.build_payload("p", "1024x1024", "png", "m")["size"] == "1024x1024"


def test_success_decodes_image_and_maps_metadata(monkeypatch):
    seen: dict = {}
    usage = {"total_tokens": 356, "output_tokens": 343}
    _fake_urlopen(monkeypatch, {
        "data": [{"b64_json": base64.b64encode(_PNG).decode()}],
        "quality": "low", "size": "1536x1024", "usage": usage,
    }, seen)

    data, meta = _call()

    assert data == _PNG
    assert seen["url"] == "https://pool.example.com/v1/images/generations"
    assert seen["headers"]["Authorization"] == "Bearer sk-pool"
    assert seen["body"]["model"] == images_api.DEFAULT_IMAGE_MODEL
    assert seen["body"]["prompt"] == "an apple"
    assert meta["models"] == {"image": images_api.DEFAULT_IMAGE_MODEL}
    assert meta["quality"] == "low"
    assert meta["image_usage"] == usage  # the Images API usage IS the image cost
    assert "usage" not in meta  # no orchestrator LLM on this path
    assert "elapsed_s" in meta


def test_missing_image_surfaces_backend_error(monkeypatch):
    _fake_urlopen(monkeypatch, {"error": {"message": "content policy"}}, {})
    with pytest.raises(GatewayError, match="no image returned \\(content policy\\)"):
        _call()


def test_http_429_names_the_pool(monkeypatch):
    def fake(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(images_api.urllib.request, "urlopen", fake)
    with pytest.raises(GatewayError) as ei:
        _call()
    assert ei.value.status == 429
    assert "account pool" in str(ei.value)


def test_plain_sends_prompt_verbatim_without_images():
    body = images_api.build_payload("an apple", "auto", "png", "m")
    assert body["prompt"] == "an apple"
    assert "images" not in body


def test_refs_go_to_edits_with_data_uris_and_intent_wording(monkeypatch):
    seen: dict = {}
    _fake_urlopen(monkeypatch, {"data": [{"b64_json": base64.b64encode(_PNG).decode()}]}, seen)

    _, meta = _call(
        refs=[("QUFB", "image/png"), ("QkJC", "image/jpeg")],
        intent=GenIntent.COMPOSE, labels=["cat", "dog"], relation="side by side",
    )

    assert seen["url"] == "https://pool.example.com/v1/images/edits"
    assert seen["body"]["images"] == [
        {"image_url": "data:image/png;base64,QUFB"},
        {"image_url": "data:image/jpeg;base64,QkJC"},
    ]
    prompt = seen["body"]["prompt"]
    assert "2 DISTINCT characters" in prompt and "(cat)" in prompt and "side by side" in prompt
    assert "an apple" in prompt
    assert meta["action"] == "generate"  # only EDIT intent is labelled "edit"


def test_edit_intent_wraps_delta_in_preservation_template():
    body = images_api.build_payload(
        "make it red", "auto", "png", "m", refs=[("QUFB", "image/png")], intent=GenIntent.EDIT
    )
    assert "Apply ONLY this change: make it red" in body["prompt"]
    assert "Preserve everything else" in body["prompt"]
