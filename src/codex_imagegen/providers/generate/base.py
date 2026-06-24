"""Image-generation provider contract.

An `ImageProvider` turns a prompt (+ optional reference images) into image bytes.
Providers stay thin and **declare their capabilities** so the feature layer can
route each job to the strongest backend instead of flattening every provider to
the lowest common denominator (e.g. Codex handles multiple distinct subjects;
MiniMax Image-01 handles a single face). The caller picks the framing via
`GenIntent`; the provider owns how to express that intent in its own request.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class GenIntent(Enum):
    """How the references (if any) relate to the requested image."""

    PLAIN = "plain"             # prompt only, no subject to preserve
    CONSISTENCY = "consistency"  # refs = the SAME single subject, render a new scene
    COMPOSE = "compose"         # refs = multiple DISTINCT subjects, merge them (Phase 2)
    EDIT = "edit"               # refs = the SINGLE source image to modify in place


@dataclass(frozen=True)
class GenCapabilities:
    """What a provider can do — read by features to route/guard, never to flatten."""

    max_refs: int                  # max reference images honored in one call
    multi_subject: bool            # can preserve >1 distinct subject at once
    intents: frozenset[GenIntent]  # framings the provider supports
    metered: str                   # billing meter, e.g. "subscription-quota" | "pay-per-image"


@runtime_checkable
class ImageProvider(Protocol):
    """Minimal generate contract. `refs` is always a list so a provider can honor
    as many as its `max_refs` allows rather than being capped to one upstream."""

    name: str
    capabilities: GenCapabilities

    def generate(
        self,
        prompt: str,
        *,
        refs: list[tuple[str, str]] | None,
        intent: GenIntent,
        size: str,
        fmt: str,
        total_timeout: float,
        stall_timeout: float,
        progress: bool,
        labels: list[str] | None = None,
        relation: str | None = None,
    ) -> tuple[bytes, dict]:
        """Return (image_bytes, metadata). Raises ImagegenError subclasses on failure.

        `labels` (paired to `refs`, in order) and `relation` apply to COMPOSE
        intent; providers that don't support multi-subject composition ignore them.
        """
        ...
