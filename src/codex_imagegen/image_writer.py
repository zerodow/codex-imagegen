"""Resolve output paths and write validated image bytes to disk.

Validates the returned bytes against the requested format's magic number
(so a backend hiccup can't leave a corrupt file), then writes atomically
(temp file + os.replace) so a failure never leaves a partial file at the target.
"""

import os
import re
import tempfile
import time
from pathlib import Path

from .errors import GatewayError, InputError

# Magic-byte prefixes per format. WEBP needs a second check at offset 8.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_EXT = {"png": "png", "jpeg": "jpg", "webp": "webp"}


def slugify(text: str, maxlen: int = 40) -> str:
    """Turn a prompt into a filesystem-safe slug for default filenames."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = slug[:maxlen].strip("-")
    return slug or "image"


def resolve_output_path(out: str | None, prompt: str, fmt: str) -> Path:
    """Return the absolute target path, creating the parent directory.

    Default (no -o): ./generated/<YYYY-MM-DD>/<slug>-<HHMMSS>.<ext>.
    Raises InputError if the parent directory cannot be created/written.
    """
    ext = _EXT.get(fmt, "png")
    if out:
        path = Path(out).expanduser()
    else:
        day = time.strftime("%Y-%m-%d")
        stamp = time.strftime("%H%M%S")
        path = Path.cwd() / "generated" / day / f"{slugify(prompt)}-{stamp}.{ext}"
    path = path.resolve()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InputError(f"cannot create output directory {path.parent}: {exc}") from None
    if not os.access(path.parent, os.W_OK):
        raise InputError(f"output directory is not writable: {path.parent}")
    return path


def validate_magic(data: bytes, fmt: str) -> None:
    """Raise GatewayError if `data` is not a valid image of the expected format."""
    if not data:
        raise GatewayError("backend returned empty image data")
    if fmt == "png":
        ok = data[:8] == _PNG_MAGIC
    elif fmt == "jpeg":
        ok = data[:3] == _JPEG_MAGIC
    elif fmt == "webp":
        ok = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    else:
        ok = True  # unknown format: skip strict validation
    if not ok:
        raise GatewayError(f"backend returned data that is not a valid {fmt} image")


def write_image(data: bytes, path: Path, fmt: str) -> Path:
    """Validate then atomically write `data` to `path`. Returns the path."""
    validate_magic(data, fmt)
    fd, tmp_path = tempfile.mkstemp(prefix=".imagegen.", suffix=f".{fmt}", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        raise
    return path
