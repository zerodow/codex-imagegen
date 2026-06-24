"""MiniMax Image-01 generation provider (pay-as-you-go fallback).

Single-subject only: `subject_reference` supports one face, so this provider
advertises `multi_subject=False` and supports only PLAIN and CONSISTENCY intents.
The merge feature's capability guard therefore refuses to route a COMPOSE job here
(it would silently drop a subject) — that rejection is the whole point of the
capability model. API key is resolved lazily (no env/network at construction).
"""

from codex_imagegen.core.errors import InputError
from codex_imagegen.providers.generate.base import GenCapabilities, GenIntent

from . import client

_MINIMAX_CAPABILITIES = GenCapabilities(
    max_refs=1,
    multi_subject=False,
    intents=frozenset({GenIntent.PLAIN, GenIntent.CONSISTENCY}),
    metered="pay-per-image",
)


class MiniMaxImageProvider:
    """ImageProvider backed by MiniMax Image-01 (text-to-image + single-face ref)."""

    name = "minimax"
    capabilities = _MINIMAX_CAPABILITIES

    def __init__(self, model: str = client.DEFAULT_MODEL) -> None:
        self._model = model
        self._key: str | None = None

    def _api_key(self) -> str:
        if self._key is None:
            self._key = client.resolve_api_key()
        return self._key

    def generate(
        self,
        prompt: str,
        *,
        refs: list[tuple[str, str]] | None = None,
        intent: GenIntent = GenIntent.PLAIN,
        size: str = "1024x1024",
        fmt: str = "png",  # MiniMax decides the encoding; write-side validates the bytes
        total_timeout: float,
        stall_timeout: float,
        progress: bool = False,
        labels: list[str] | None = None,
        relation: str | None = None,
    ) -> tuple[bytes, dict]:
        if intent not in self.capabilities.intents:
            raise InputError(
                f"minimax does not support {intent.value} generation "
                "(single subject only — use 'codex' for multi-subject merge)"
            )
        ref = None
        if intent is GenIntent.CONSISTENCY:
            refs = refs or []
            if not refs:
                raise InputError("consistency intent needs one reference image")
            if len(refs) > self.capabilities.max_refs:
                raise InputError(
                    f"minimax supports a single subject reference, got {len(refs)}"
                )
            ref = refs[0]
        data = client.generate_image(
            self._api_key(), prompt=prompt, size=size, ref=ref,
            model=self._model, timeout=total_timeout,
        )
        return data, {"provider": "minimax", "model": self._model}
