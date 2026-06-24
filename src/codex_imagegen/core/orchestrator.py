"""Provider-agnostic generate-to-file core, used by the CLI and the pipeline.

Delegates image bytes to an `ImageProvider` (which owns credentials, the network
call, and any backend-specific prompt framing), then writes them to a target
path. Knows nothing about any specific backend.
"""

from pathlib import Path

from codex_imagegen.providers.generate.base import GenIntent, ImageProvider

from .image_writer import write_image


def generate_to_file(
    provider: ImageProvider,
    prompt: str,
    out_path: Path,
    *,
    refs: list[tuple[str, str]] | None = None,
    intent: GenIntent = GenIntent.PLAIN,
    size: str = "1024x1024",
    fmt: str = "png",
    total_timeout: float,
    stall_timeout: float,
    progress: bool = False,
    labels: list[str] | None = None,
    relation: str | None = None,
) -> tuple[Path, dict]:
    """Generate one image via `provider` and write it to `out_path`.

    Returns (path, metadata). Reuse the SAME `provider` instance across a batch so
    its credentials (and any mid-batch token refresh) persist between calls.
    `labels`/`relation` apply to COMPOSE intent (ignored otherwise).
    """
    image_bytes, meta = provider.generate(
        prompt,
        refs=refs,
        intent=intent,
        size=size,
        fmt=fmt,
        total_timeout=total_timeout,
        stall_timeout=stall_timeout,
        progress=progress,
        labels=labels,
        relation=relation,
    )
    return write_image(image_bytes, out_path, fmt), meta
