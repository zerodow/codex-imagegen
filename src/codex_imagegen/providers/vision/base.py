"""Vision provider contract: the "eyes + judge" in a generation pipeline.

A `VisionProvider` reads an image and returns structured text — used to caption
reference subjects BEFORE generation (identity binding) and to verify a generated
image AFTER (did every subject appear, are faces blended?). It never generates
pixels; that is an `ImageProvider`'s job.
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SubjectDescription:
    """A compact identity description for one reference subject."""

    text: str


@dataclass(frozen=True)
class CompositionVerdict:
    """Whether a generated image correctly contains all expected distinct subjects."""

    ok: bool
    blended: bool = False
    missing: list[str] = field(default_factory=list)
    reasons: str = ""


@runtime_checkable
class VisionProvider(Protocol):
    name: str

    def describe_subject(self, image_b64: str, mime: str) -> SubjectDescription:
        """Return a one-line identity description (face, hair, outfit, colors, style)."""
        ...

    def verify_composition(
        self, image_b64: str, mime: str, *, expected: list[str]
    ) -> CompositionVerdict:
        """Judge whether each `expected` subject appears as a distinct, unblended person."""
        ...
