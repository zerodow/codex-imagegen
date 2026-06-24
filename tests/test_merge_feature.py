"""merge.run: capability guard (no silent degrade) + COMPOSE delegation."""

import pytest

from codex_imagegen.core.errors import InputError
from codex_imagegen.features import merge
from codex_imagegen.providers.generate.base import GenCapabilities, GenIntent

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
REFS2 = [("AAA", "image/png"), ("BBB", "image/png")]


class _StubProvider:
    def __init__(self, *, multi_subject=True, max_refs=4, intents=None):
        self.name = "stub"
        self.capabilities = GenCapabilities(
            max_refs=max_refs,
            multi_subject=multi_subject,
            intents=intents if intents is not None
            else frozenset({GenIntent.PLAIN, GenIntent.CONSISTENCY, GenIntent.COMPOSE}),
            metered="test",
        )
        self.calls = []

    def generate(self, prompt, *, refs, intent, size, fmt, total_timeout,
                 stall_timeout, progress, labels=None, relation=None):
        self.calls.append(
            {"prompt": prompt, "intent": intent, "refs": refs, "labels": labels, "relation": relation}
        )
        return PNG, {}


def _run(provider, tmp_path, refs=REFS2, **kw):
    return merge.run(
        provider, "two friends in a cafe", tmp_path / "out.png",
        refs=refs, total_timeout=10, stall_timeout=5, **kw,
    )


def test_happy_path_writes_file_with_compose_intent(tmp_path):
    p = _StubProvider()
    out, meta = _run(p, tmp_path, labels=["A", "B"], relation="side by side")
    assert out.read_bytes() == PNG
    call = p.calls[0]
    assert call["intent"] is GenIntent.COMPOSE
    assert call["refs"] == REFS2
    assert call["labels"] == ["A", "B"] and call["relation"] == "side by side"


def test_rejects_single_subject_provider(tmp_path):
    # A MiniMax-Image-like provider: single face only -> must fail, not degrade.
    p = _StubProvider(multi_subject=False, max_refs=1)
    with pytest.raises(InputError, match="cannot merge"):
        _run(p, tmp_path)
    assert p.calls == []  # never reached generate


def test_rejects_provider_without_compose_intent(tmp_path):
    p = _StubProvider(intents=frozenset({GenIntent.PLAIN, GenIntent.CONSISTENCY}))
    with pytest.raises(InputError, match="cannot merge"):
        _run(p, tmp_path)


def test_rejects_more_refs_than_provider_max(tmp_path):
    p = _StubProvider(max_refs=2)
    three = REFS2 + [("CCC", "image/png")]
    with pytest.raises(InputError, match="exceed"):
        _run(p, tmp_path, refs=three)


def test_rejects_fewer_than_two_refs(tmp_path):
    p = _StubProvider()
    with pytest.raises(InputError, match="at least 2"):
        _run(p, tmp_path, refs=[("AAA", "image/png")])


def test_rejects_label_count_mismatch(tmp_path):
    p = _StubProvider()
    with pytest.raises(InputError, match="one label per reference"):
        _run(p, tmp_path, labels=["only one"])  # 1 label for 2 refs
    assert p.calls == []  # rejected before generate
