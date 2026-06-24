"""Entry shim for the `imagegen-character` command.

The batch logic lives in `features/character.py`; this module only re-exports its
`main` so the `codex_imagegen.pipeline:main` console-script entry point resolves.
"""

from .features.character import main

__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
