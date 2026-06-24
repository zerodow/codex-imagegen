"""Load local reference images into (base64, mime) pairs for subject consistency.

Sniffs the MIME from magic bytes (the data URI the backend expects needs an
explicit type) and enforces a total base64 budget so a large reference can't
balloon the request body.
"""

import base64
from pathlib import Path

from .errors import InputError

# (magic prefix, mime). WEBP needs a second check at offset 8.
_SNIFF: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
]
# Total base64 budget across all references (~6 MB raw). Keeps the POST body sane.
_MAX_TOTAL_B64 = 8 * 1024 * 1024


def _sniff_mime(data: bytes, path: Path) -> str:
    for sig, mime in _SNIFF:
        if data.startswith(sig):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise InputError(f"unsupported reference image type: {path} (use png/jpeg/webp/gif)")


def load_reference(path: str) -> tuple[str, str]:
    """Return (base64, mime) for one local image file. Raises InputError."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise InputError(f"reference image not found: {p}")
    raw = p.read_bytes()
    if not raw:
        raise InputError(f"reference image is empty: {p}")
    mime = _sniff_mime(raw, p)
    return base64.b64encode(raw).decode("ascii"), mime


def load_references(paths: list[str]) -> list[tuple[str, str]]:
    """Load several references, enforcing the combined base64 budget."""
    refs = [load_reference(p) for p in paths]
    total = sum(len(b64) for b64, _ in refs)
    if total > _MAX_TOTAL_B64:
        raise InputError(
            f"reference image(s) too large ({total // (1024 * 1024)} MB base64); "
            "use fewer/smaller images (≲6 MB total)."
        )
    return refs
