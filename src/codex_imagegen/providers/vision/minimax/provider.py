"""MiniMax M3 vision provider: caption reference subjects + verify compositions.

Wraps the MiniMax chat client behind the `VisionProvider` contract. The API key
is resolved lazily (first call) so constructing the provider never touches the
environment — keeps it testable and lets features build it before deciding to use it.
"""

import json
import re

from codex_imagegen.providers.vision.base import CompositionVerdict, SubjectDescription

from . import client

_DESCRIBE_SYSTEM = "You are a precise visual identity describer. Reply with one compact line, no preamble."
_DESCRIBE_USER = (
    "Describe ONLY this subject's visual identity for re-rendering: face, hair, "
    "outfit, dominant colors, and art style. One short sentence."
)
_VERIFY_SYSTEM = "You are a strict image-composition checker. Reply with ONLY a JSON object, no prose."

# Pull the first {...} block out of a possibly chatty reply.
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

# MiniMax M3 is a reasoning model: it may wrap chain-of-thought in <think>...</think>
# before the real answer. Strip those so captions/verdicts use the answer, not the
# reasoning (and so a stray brace inside the reasoning can't fool the JSON extractor).
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_OPEN_THINK_RE = re.compile(r"<think>.*", re.DOTALL | re.IGNORECASE)


def _strip_reasoning(text: str) -> str:
    """Remove <think> blocks. An unclosed <think> (no answer emitted) collapses to ''."""
    cleaned = _THINK_RE.sub("", text or "")
    cleaned = _OPEN_THINK_RE.sub("", cleaned)  # drop a dangling, never-closed <think>
    return cleaned.strip()


class MiniMaxVisionProvider:
    name = "minimax"

    def __init__(self, *, timeout: float = client.DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout
        self._key: str | None = None

    def _api_key(self) -> str:
        if self._key is None:
            self._key = client.resolve_api_key()
        return self._key

    def describe_subject(self, image_b64: str, mime: str) -> SubjectDescription:
        text = client.chat_with_image(
            self._api_key(),
            system=_DESCRIBE_SYSTEM,
            user_text=_DESCRIBE_USER,
            image_b64=image_b64,
            mime=mime,
            timeout=self._timeout,
        )
        return SubjectDescription(text=_strip_reasoning(text))

    def verify_composition(
        self, image_b64: str, mime: str, *, expected: list[str]
    ) -> CompositionVerdict:
        subjects = "; ".join(expected) if expected else "the intended subjects"
        user_text = (
            f"This image must contain these DISTINCT subjects, each as a separate person: {subjects}. "
            'Reply with ONLY this JSON: {"ok": <bool>, "blended": <bool>, '
            '"missing": [<subject strings>], "reasons": "<short>"}. '
            "ok=true only if every subject is present AND no two faces are blended into one."
        )
        raw = client.chat_with_image(
            self._api_key(),
            system=_VERIFY_SYSTEM,
            user_text=user_text,
            image_b64=image_b64,
            mime=mime,
            json_object=True,
            timeout=self._timeout,
        )
        return _parse_verdict(raw)


def _parse_verdict(raw: str) -> CompositionVerdict:
    """Defensively parse the verifier reply; never raise — a bad reply means 'not ok'."""
    raw = _strip_reasoning(raw)
    match = _JSON_RE.search(raw)
    if not match:
        return CompositionVerdict(ok=False, reasons=(raw or "").strip()[:200] or "no response")
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return CompositionVerdict(ok=False, reasons=(raw or "").strip()[:200])
    missing = data.get("missing")
    return CompositionVerdict(
        ok=bool(data.get("ok")),
        blended=bool(data.get("blended")),
        missing=[str(m) for m in missing] if isinstance(missing, list) else [],
        reasons=str(data.get("reasons", "")),
    )
