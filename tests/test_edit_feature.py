"""edit.run: capability guard (no silent degrade) + EDIT delegation."""

import pytest

from codex_imagegen.core.errors import InputError
from codex_imagegen.features import edit
from codex_imagegen.providers.generate.base import GenCapabilities, GenIntent

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
SOURCE = ("SRCB64", "image/png")


class _StubProvider:
    def __init__(self, *, intents=None):
        self.name = "stub"
        self.capabilities = GenCapabilities(
            max_refs=4, multi_subject=True,
            intents=intents if intents is not None
            else frozenset({GenIntent.PLAIN, GenIntent.EDIT}),
            metered="test",
        )
        self.calls = []

    def generate(self, prompt, *, refs, intent, size, fmt, total_timeout,
                 stall_timeout, progress, labels=None, relation=None):
        self.calls.append({"prompt": prompt, "intent": intent, "refs": refs})
        return PNG, {"action": "edit"}


def _run(provider, tmp_path, **kw):
    return edit.run(
        provider, "make the cap red", tmp_path / "out.png",
        source=SOURCE, total_timeout=10, stall_timeout=5, **kw,
    )


def test_happy_path_writes_file_with_edit_intent(tmp_path):
    p = _StubProvider()
    out, meta = _run(p, tmp_path)
    assert out.read_bytes() == PNG
    assert meta.get("action") == "edit"
    call = p.calls[0]
    assert call["intent"] is GenIntent.EDIT
    assert call["refs"] == [SOURCE]
    assert call["prompt"] == "make the cap red"


def test_rejects_provider_without_edit_intent(tmp_path):
    p = _StubProvider(intents=frozenset({GenIntent.PLAIN, GenIntent.CONSISTENCY}))
    with pytest.raises(InputError, match="does not support"):
        _run(p, tmp_path)
    assert p.calls == []  # never reached generate
