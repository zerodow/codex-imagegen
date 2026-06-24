"""`imagegen-merge`: combine subjects from 2+ reference images into one new image.

Loads the references, asserts the chosen provider can actually composite multiple
DISTINCT subjects (capability guard — no silent degrade), then renders one image
with COMPOSE framing so each subject's identity is preserved and not blended.

Optionally uses a `VisionProvider` as the "eyes + judge": caption each reference
BEFORE generation (richer identity binding) and verify the result AFTER, retrying
with a correction note up to `max_retries` times. Vision is off unless a provider
is passed.
"""

import base64
import sys
from pathlib import Path

from ..core import orchestrator
from ..core.errors import InputError
from ..providers.generate.base import GenIntent, ImageProvider
from ..providers.vision.base import VisionProvider

_MIN_REFS = 2  # "merge" is meaningless with fewer than two subjects
_FMT_MIME = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}


def run(
    provider: ImageProvider,
    scene: str,
    out_path: Path,
    *,
    refs: list[tuple[str, str]],
    labels: list[str] | None = None,
    relation: str | None = None,
    size: str = "1024x1024",
    fmt: str = "png",
    total_timeout: float,
    stall_timeout: float,
    progress: bool = False,
    vision: VisionProvider | None = None,
    verify: bool = False,
    max_retries: int = 1,
) -> Path:
    """Merge the subjects in `refs` into one image at `out_path`. Returns the path.

    Raises InputError if the provider cannot do multi-subject composition or the
    reference count is outside what it supports. When `vision` is given, references
    are captioned into labels; when `verify` is also set, the result is checked and
    regenerated with a correction up to `max_retries` times (best effort kept).
    """
    if len(refs) < _MIN_REFS:
        raise InputError(f"merge needs at least {_MIN_REFS} reference images, got {len(refs)}")

    caps = provider.capabilities
    if not caps.multi_subject or GenIntent.COMPOSE not in caps.intents:
        raise InputError(
            f"provider {provider.name!r} cannot merge multiple distinct subjects "
            "(needs multi-subject composition support)"
        )
    if len(refs) > caps.max_refs:
        raise InputError(
            f"{len(refs)} reference images exceed provider {provider.name!r} "
            f"maximum of {caps.max_refs}"
        )

    if vision is not None:
        labels = _caption_subjects(vision, refs, progress)  # richer binding; overrides user labels
    elif labels and len(labels) != len(refs):
        raise InputError(
            f"got {len(labels)} labels for {len(refs)} references; "
            "provide one label per reference, or none"
        )

    expected = [text for text in (labels or []) if text and text.strip()] or [
        f"subject {i + 1}" for i in range(len(refs))
    ]
    mime = _FMT_MIME.get(fmt, "image/png")
    attempts = max_retries + 1 if (vision is not None and verify) else 1
    correction = ""
    path = out_path
    for attempt in range(attempts):
        scene_text = scene if not correction else f"{scene}. {correction}"
        path, _meta = orchestrator.generate_to_file(
            provider,
            scene_text,
            out_path,
            refs=refs,
            intent=GenIntent.COMPOSE,
            labels=labels,
            relation=relation,
            size=size,
            fmt=fmt,
            total_timeout=total_timeout,
            stall_timeout=stall_timeout,
            progress=progress,
        )
        if vision is None or not verify:
            return path
        verdict = vision.verify_composition(_encode(path), mime, expected=expected)
        if verdict.ok:
            return path
        if attempt < attempts - 1:
            correction = (
                f"A previous attempt was wrong ({verdict.reasons}). Ensure these appear as "
                f"separate people with distinct, unblended faces: "
                f"{', '.join(verdict.missing or expected)}."
            )
            if progress:
                print(f"[verify] attempt {attempt + 1} failed; retrying", file=sys.stderr)
        elif progress:
            print(
                f"[verify] still not verified after {attempts} attempt(s); "
                f"keeping best effort ({verdict.reasons})",
                file=sys.stderr,
            )
    return path


def _caption_subjects(vision: VisionProvider, refs: list[tuple[str, str]], progress: bool) -> list[str]:
    """Caption each reference subject into a one-line identity label."""
    labels = []
    for idx, (b64, mime) in enumerate(refs, start=1):
        desc = vision.describe_subject(b64, mime)
        labels.append(desc.text)
        if progress:
            print(f"[caption] subject {idx}: {desc.text[:70]}", file=sys.stderr)
    return labels


def _encode(path: Path) -> str:
    """Base64-encode the written image so the vision provider can read it back."""
    return base64.b64encode(path.read_bytes()).decode("ascii")
