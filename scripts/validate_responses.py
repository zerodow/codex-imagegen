#!/usr/bin/env python3
"""One-shot validation of the Codex Responses image path (consumes 1 quota image).

Exercises the full chain: read ~/.codex/auth.json -> build headers+payload ->
POST codex/responses -> parse SSE -> decode base64 -> write PNG -> verify magic.
Run: python3 scripts/validate_responses.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codex_imagegen.providers.generate.codex import auth as A  # noqa: E402
from codex_imagegen.providers.generate.codex.client import generate_image_bytes  # noqa: E402

OUT = Path("/tmp/validate-cat.png")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def main() -> int:
    auth = A.load_auth()
    access, account_id, refresh = A.extract_tokens(auth)
    print(f"auth ok: account_id={'set' if account_id else 'none'}, refresh={'set' if refresh else 'none'}",
          file=sys.stderr)
    img, meta = generate_image_bytes(
        "a watercolor cat sitting on a sunny windowsill",
        size="1024x1024",
        output_format="png",
        access_token=access,
        account_id=account_id,
        refresh_token=refresh,
        auth=auth,
        progress=True,
    )
    OUT.write_bytes(img)
    ok = img[:8] == PNG_MAGIC
    print(f"WROTE {OUT} ({len(img)} bytes) png_magic={ok} meta_keys={sorted(meta)[:6]}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
