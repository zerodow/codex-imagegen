"""CodexImageProvider: capabilities + lazy/reused auth + delegation to the client."""

from codex_imagegen.providers.generate.base import GenIntent
from codex_imagegen.providers.generate.codex import provider as prov_mod
from codex_imagegen.providers.generate.codex.provider import CodexImageProvider


def test_capabilities_advertise_multi_subject():
    caps = CodexImageProvider().capabilities
    assert caps.multi_subject is True
    assert caps.max_refs == 4
    assert {GenIntent.PLAIN, GenIntent.CONSISTENCY, GenIntent.COMPOSE} <= caps.intents
    assert caps.metered == "subscription-quota"


def test_name():
    assert CodexImageProvider().name == "codex"


def test_generate_loads_auth_once_and_delegates(monkeypatch):
    load_calls = {"n": 0}
    gen_calls = []

    def fake_load_auth():
        load_calls["n"] += 1
        return {"tokens": {"access_token": "tok"}}

    def fake_generate_image_bytes(prompt, **kwargs):
        gen_calls.append((prompt, kwargs.get("intent"), kwargs.get("model")))
        return b"IMG", {"meta": 1}

    monkeypatch.setattr(prov_mod.auth, "load_auth", fake_load_auth)
    monkeypatch.setattr(prov_mod.client, "generate_image_bytes", fake_generate_image_bytes)

    p = CodexImageProvider(model="gpt-5.5")
    data, meta = p.generate(
        "hi", refs=None, intent=GenIntent.PLAIN, size="auto", fmt="png",
        total_timeout=10, stall_timeout=5, progress=False,
    )
    assert data == b"IMG" and meta == {"meta": 1}
    assert gen_calls[0] == ("hi", GenIntent.PLAIN, "gpt-5.5")

    # Second call must reuse the cached auth dict (load_auth not called again),
    # which is what lets a mid-batch token refresh persist.
    p.generate(
        "again", refs=None, intent=GenIntent.PLAIN, size="auto", fmt="png",
        total_timeout=10, stall_timeout=5, progress=False,
    )
    assert load_calls["n"] == 1
    assert len(gen_calls) == 2


def test_midbatch_refresh_persists_to_next_call(monkeypatch):
    # A 401 refresh mutates the shared auth dict in place (as the real client does);
    # because the provider reuses that dict, the NEXT call must observe the new token.
    auth_dict = {"tokens": {"access_token": "orig"}}
    seen_tokens = []

    def fake_generate_image_bytes(prompt, **kwargs):
        seen_tokens.append(kwargs["access_token"])
        kwargs["auth"]["tokens"]["access_token"] = "refreshed"  # simulate in-place 401 refresh
        return b"IMG", {}

    monkeypatch.setattr(prov_mod.auth, "load_auth", lambda: auth_dict)
    monkeypatch.setattr(prov_mod.client, "generate_image_bytes", fake_generate_image_bytes)

    p = CodexImageProvider()
    kw = dict(refs=None, intent=GenIntent.PLAIN, size="auto", fmt="png",
              total_timeout=10, stall_timeout=5, progress=False)
    p.generate("one", **kw)
    p.generate("two", **kw)
    assert seen_tokens == ["orig", "refreshed"]  # call two saw call one's refresh
