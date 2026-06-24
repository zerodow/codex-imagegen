"""Load a project-local `.env` into os.environ — stdlib-only (no python-dotenv).

Reads simple `KEY=VALUE` lines from a `.env` (the current working directory by
default) and sets them in the process environment. Two rules keep it predictable
and safe:

- **Real env wins.** A variable already present in `os.environ` is never
  overridden, so an explicit `export FOO=...` always beats the file.
- **Never crashes.** A missing/unreadable file or a malformed line is skipped,
  not raised — a stray `.env` must not take the CLI down.

Credentials therefore live in a gitignored `.env` (or a real export), never in
source. Codex auth stays in `~/.codex/auth.json`; this is only for env-var keys
such as the MiniMax token-plan / image keys.
"""

import os
from pathlib import Path

__all__ = ["load_dotenv"]


def _strip_quotes(value: str) -> str:
    """Drop one layer of matching surrounding single/double quotes, if present."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _is_valid_key(key: str) -> bool:
    """A shell-style identifier: non-empty, alphanumerics + underscore only."""
    return bool(key) and key.replace("_", "").isalnum()


def load_dotenv(path: "str | os.PathLike[str] | None" = None) -> list[str]:
    """Load `.env` (cwd by default) into os.environ; return the keys newly set.

    Existing environment entries are left untouched. The returned list lets a
    caller report what was loaded; it is empty when the file is absent.
    """
    env_path = Path(path) if path is not None else Path.cwd() / ".env"
    try:
        # utf-8-sig so a UTF-8 BOM doesn't get glued onto the first key name
        # (which would silently drop that variable).
        text = env_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return []  # no file / unreadable -> no-op

    loaded: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue  # not a KEY=VALUE line
        key = key.strip()
        if not _is_valid_key(key) or key in os.environ:
            continue  # skip junk keys; never override a real env var
        os.environ[key] = _strip_quotes(value.strip())
        loaded.append(key)
    return loaded
