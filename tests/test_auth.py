"""Auth.json loading, token extraction, and refresh error handling."""

import io
import json
import urllib.error

import pytest

from codex_imagegen import auth
from codex_imagegen.errors import AuthError, GatewayError


def test_extract_tokens_ok():
    data = {"tokens": {"access_token": "abc", "account_id": "acc", "refresh_token": "r"}}
    assert auth.extract_tokens(data) == ("abc", "acc", "r")


def test_extract_tokens_missing_access():
    with pytest.raises(AuthError):
        auth.extract_tokens({"tokens": {}})


def test_extract_tokens_api_key_only_rejected():
    # Authenticated with an API key (no OAuth bearer) -> this path can't be used.
    with pytest.raises(AuthError):
        auth.extract_tokens({"OPENAI_API_KEY": "sk-xxx", "tokens": {}})


def test_load_auth_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_PATH", tmp_path / "nope.json")
    with pytest.raises(AuthError):
        auth.load_auth()


def test_load_auth_ok(tmp_path, monkeypatch):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"tokens": {"access_token": "x"}}))
    monkeypatch.setattr(auth, "AUTH_PATH", path)
    assert auth.load_auth()["tokens"]["access_token"] == "x"


def test_refresh_invalid_grant_raises_autherror(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_PATH", tmp_path / "auth.json")

    def fake_urlopen(req, timeout=30):
        body = io.BytesIO(json.dumps({"error": "invalid_grant"}).encode())
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, body)

    monkeypatch.setattr(auth.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(AuthError):
        auth.refresh_and_persist({"tokens": {}}, "refreshtok")


def test_refresh_non_json_body_raises_gatewayerror(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_PATH", tmp_path / "auth.json")
    monkeypatch.setattr(
        auth.urllib.request, "urlopen",
        lambda req, timeout=30: io.BytesIO(b"<html>502 Bad Gateway</html>"),
    )
    with pytest.raises(GatewayError):
        auth.refresh_and_persist({"tokens": {}}, "r")


def test_refresh_missing_access_token_raises_gatewayerror(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_PATH", tmp_path / "auth.json")
    monkeypatch.setattr(
        auth.urllib.request, "urlopen",
        lambda req, timeout=30: io.BytesIO(json.dumps({"token_type": "bearer"}).encode()),
    )
    with pytest.raises(GatewayError):
        auth.refresh_and_persist({"tokens": {}}, "r")


def test_refresh_success_persists(tmp_path, monkeypatch):
    path = tmp_path / "auth.json"
    monkeypatch.setattr(auth, "AUTH_PATH", path)

    def fake_urlopen(req, timeout=30):
        payload = json.dumps({"access_token": "NEW", "refresh_token": "NEWR"}).encode()
        return io.BytesIO(payload)

    monkeypatch.setattr(auth.urllib.request, "urlopen", fake_urlopen)
    data = {"tokens": {"access_token": "OLD", "refresh_token": "OLDR"}}
    new_access = auth.refresh_and_persist(data, "OLDR")
    assert new_access == "NEW"
    persisted = json.loads(path.read_text())
    assert persisted["tokens"]["access_token"] == "NEW"
    assert persisted["tokens"]["refresh_token"] == "NEWR"
    assert "last_refresh" in persisted
    # In-place mutation: the SAME dict is updated, so a later extract_tokens on
    # the reused dict (e.g. the next image in a batch) sees the fresh token.
    assert data["tokens"]["access_token"] == "NEW"
    assert auth.extract_tokens(data)[0] == "NEW"
