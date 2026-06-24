"""Shared generate-to-file core used by both the single-shot CLI and the pipeline.

Loads credentials once (reusable across many calls so a token refresh persists
for the rest of a batch), generates one image, and writes it to a target path.
"""

from pathlib import Path

from . import auth as _auth
from .image_writer import write_image
from .responses_client import (
    DEFAULT_MODEL,
    DEFAULT_STALL_TIMEOUT,
    DEFAULT_TOTAL_TIMEOUT,
    generate_image_bytes,
)


def load_credentials() -> dict:
    """Load + validate ~/.codex/auth.json once; return the mutable auth dict.

    The dict is reused across calls: a 401 refresh updates it in place so later
    calls in a batch pick up the fresh token instead of re-refreshing each time.
    """
    auth_data = _auth.load_auth()
    _auth.extract_tokens(auth_data)  # validate an OAuth access token exists
    return auth_data


def generate_to_file(
    prompt: str,
    out_path: Path,
    *,
    refs: list[tuple[str, str]] | None = None,
    size: str = "1024x1024",
    fmt: str = "png",
    model: str = DEFAULT_MODEL,
    total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
    stall_timeout: float = DEFAULT_STALL_TIMEOUT,
    progress: bool = False,
    auth_data: dict | None = None,
) -> tuple[Path, dict]:
    """Generate one image and write it to `out_path`. Returns (path, metadata)."""
    if auth_data is None:
        auth_data = load_credentials()
    access, account_id, refresh = _auth.extract_tokens(auth_data)
    image_bytes, meta = generate_image_bytes(
        prompt,
        size=size,
        output_format=fmt,
        access_token=access,
        account_id=account_id,
        refresh_token=refresh,
        auth=auth_data,
        model=model,
        total_timeout=total_timeout,
        stall_timeout=stall_timeout,
        progress=progress,
        refs=refs,
    )
    return write_image(image_bytes, out_path, fmt), meta
