"""`imagegen-edit`: modify a single source image in place from an instruction.

Loads one source image, asserts the chosen provider supports in-place editing
(capability guard — no silent degrade), then renders an edited image with EDIT
framing: apply ONLY the user's delta, preserve everything else.

This is edit-via-regeneration (the backend redraws conditioned on the source),
so the preservation template — owned by the provider's payload builder — is what
keeps unmodified regions intact. Verified on the free Codex path.
"""

from pathlib import Path

from ..core import orchestrator
from ..core.errors import InputError
from ..providers.generate.base import GenIntent, ImageProvider


def run(
    provider: ImageProvider,
    delta: str,
    out_path: Path,
    *,
    source: tuple[str, str],
    size: str = "1024x1024",
    fmt: str = "png",
    total_timeout: float,
    stall_timeout: float,
    progress: bool = False,
) -> tuple[Path, dict]:
    """Edit `source` (base64, mime) per `delta`, writing the result to `out_path`.

    Returns (path, metadata). Raises InputError if the provider does not declare
    `GenIntent.EDIT` (so an edit-incapable backend fails loudly, not silently).
    """
    if GenIntent.EDIT not in provider.capabilities.intents:
        raise InputError(
            f"provider {provider.name!r} does not support in-place image editing "
            "(needs GenIntent.EDIT)"
        )
    return orchestrator.generate_to_file(
        provider,
        delta,
        out_path,
        refs=[source],
        intent=GenIntent.EDIT,
        size=size,
        fmt=fmt,
        total_timeout=total_timeout,
        stall_timeout=stall_timeout,
        progress=progress,
    )
