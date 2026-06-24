"""orchestrator.generate_to_file: delegate to the provider, then write validated bytes."""

import pytest

from codex_imagegen.core import orchestrator
from codex_imagegen.core.errors import GatewayError
from codex_imagegen.providers.generate.base import GenIntent

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class _FakeProvider:
    name = "fake"

    def __init__(self, data=PNG, meta=None):
        self._data = data
        self._meta = meta or {"revised_prompt": "rp"}
        self.calls = []

    def generate(self, prompt, *, refs, intent, size, fmt, total_timeout, stall_timeout,
                 progress, labels=None, relation=None):
        self.calls.append(
            {"prompt": prompt, "refs": refs, "intent": intent, "fmt": fmt,
             "labels": labels, "relation": relation}
        )
        return self._data, self._meta


def test_delegates_to_provider_and_writes(tmp_path):
    p = _FakeProvider()
    out = tmp_path / "o.png"
    path, meta = orchestrator.generate_to_file(
        p, "a cat", out, refs=[("b", "image/png")], intent=GenIntent.CONSISTENCY,
        size="auto", fmt="png", total_timeout=10, stall_timeout=5,
    )
    assert path == out and out.read_bytes() == PNG
    assert meta == {"revised_prompt": "rp"}
    assert p.calls[0]["prompt"] == "a cat"
    assert p.calls[0]["intent"] is GenIntent.CONSISTENCY
    assert p.calls[0]["refs"] == [("b", "image/png")]


def test_invalid_bytes_rejected_and_no_file_left(tmp_path):
    out = tmp_path / "o.png"
    with pytest.raises(GatewayError):
        orchestrator.generate_to_file(
            _FakeProvider(data=b"not-an-image"), "x", out,
            total_timeout=1, stall_timeout=1,
        )
    assert not out.exists()
