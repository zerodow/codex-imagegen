#!/usr/bin/env python3
"""Build a self-contained index.html gallery for one OracleMessage deck session.

A "session" is one generation batch living under
`oraclemessage-deck/sessions/<YYMMDD-HHMM>-<slug>/`. It holds the rendered PNGs
plus a `session.json` describing them. This script reads that JSON and writes a
portable `index.html` (no external assets, dark "selection screen" felt theme)
so each session is self-documenting: image + prompt + params + notes + tokens.

session.json schema (all fields optional except images[].file):
  {
    "title":    "Card back — candidates",
    "slug":     "back-candidates",
    "created":  "2026-07-13 10:07",
    "provider": "codex",
    "notes":    "free-text markdown-ish notes about the whole session",
    "images": [
      {
        "file":   "candidate-a-celestial.png",   # relative to the session dir
        "label":  "A — Celestial",
        "prompt": "the full prompt used",
        "size":   "1024x1536",
        "format": "png",
        "notes":  "per-image observations",
        "tokens": {"input": 123, "output": 456, "total": 579}  # optional
      }
    ]
  }

Usage:
  python3 scripts/build_deck_session_index.py oraclemessage-deck/sessions/260713-1007-back-candidates
"""

import html
import json
import sys
from pathlib import Path

SESSION_FILE = "session.json"
OUT_FILE = "index.html"


def _esc(value: object) -> str:
    return html.escape(str(value)) if value is not None else ""


def _tokens_line(tokens: dict | None) -> str:
    if not tokens:
        return ""
    parts = [f"{k}: {v}" for k, v in tokens.items()]
    return f'<div class="meta tokens">tokens · {_esc(" · ".join(parts))}</div>'


def _image_card(img: dict, session_dir: Path) -> str:
    file = img.get("file", "")
    if not file:
        return ""
    exists = (session_dir / file).exists()
    label = img.get("label") or file
    size = img.get("size", "")
    fmt = img.get("format", "")
    dims = " · ".join(p for p in (size, fmt) if p)

    prompt = img.get("prompt", "")
    prompt_block = (
        f'<details class="prompt"><summary>prompt</summary>'
        f"<p>{_esc(prompt)}</p></details>"
        if prompt
        else ""
    )
    notes = img.get("notes", "")
    notes_block = f'<div class="note">{_esc(notes)}</div>' if notes else ""
    missing = "" if exists else '<div class="missing">⚠ file not found</div>'

    return f"""
      <figure class="card">
        <div class="thumb"><img src="{_esc(file)}" alt="{_esc(label)}" loading="lazy"></div>
        <figcaption>
          <div class="label">{_esc(label)}</div>
          {f'<div class="meta">{_esc(dims)}</div>' if dims else ''}
          {_tokens_line(img.get("tokens"))}
          {notes_block}
          {prompt_block}
          {missing}
        </figcaption>
      </figure>"""


def build_html(session: dict, session_dir: Path) -> str:
    title = session.get("title") or session_dir.name
    created = session.get("created", "")
    provider = session.get("provider", "")
    notes = session.get("notes", "")
    images = session.get("images", [])

    header_meta = " · ".join(p for p in (created, provider and f"provider: {provider}") if p)
    cards = "\n".join(_image_card(img, session_dir) for img in images)
    notes_html = f'<p class="session-notes">{_esc(notes)}</p>' if notes else ""

    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} — OracleMessage</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 2.5rem 1.5rem 4rem;
    font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #e7e3d8;
    background:
      radial-gradient(1200px 800px at 50% -10%, #1b2436 0%, transparent 60%),
      #0d1017;
  }}
  header {{ max-width: 1100px; margin: 0 auto 2rem; }}
  h1 {{ margin: 0 0 .35rem; font-size: 1.5rem; letter-spacing: .01em; }}
  .brand {{ color: #c8a44d; font-weight: 600; letter-spacing: .18em; text-transform: uppercase; font-size: .72rem; }}
  .header-meta {{ color: #8a8f9c; font-size: .82rem; margin-top: .25rem; }}
  .session-notes {{ color: #b9bccb; max-width: 70ch; margin: .9rem 0 0; }}
  .grid {{
    max-width: 1100px; margin: 0 auto;
    display: grid; gap: 1.6rem;
    grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  }}
  .card {{ margin: 0; }}
  .thumb {{
    background: #06080d;
    border: 1px solid #232a3a; border-radius: 14px;
    padding: 1.1rem; display: flex; justify-content: center;
    box-shadow: 0 10px 30px rgba(0,0,0,.45);
  }}
  .thumb img {{ width: 100%; max-width: 260px; height: auto; border-radius: 10px; display: block; }}
  figcaption {{ padding: .7rem .2rem 0; }}
  .label {{ font-weight: 600; }}
  .meta {{ color: #8a8f9c; font-size: .78rem; margin-top: .15rem; }}
  .tokens {{ color: #6f7788; }}
  .note {{ color: #b9bccb; font-size: .86rem; margin-top: .4rem; }}
  .missing {{ color: #e08a7a; font-size: .8rem; margin-top: .4rem; }}
  details.prompt {{ margin-top: .5rem; }}
  details.prompt summary {{ cursor: pointer; color: #c8a44d; font-size: .78rem; }}
  details.prompt p {{ color: #9aa0b0; font-size: .8rem; margin: .4rem 0 0; }}
</style>
</head>
<body>
  <header>
    <div class="brand">OracleMessage · thông điệp cuộc sống</div>
    <h1>{_esc(title)}</h1>
    {f'<div class="header-meta">{_esc(header_meta)}</div>' if header_meta else ''}
    {notes_html}
  </header>
  <main class="grid">{cards}
  </main>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <session-dir>", file=sys.stderr)
        return 2
    session_dir = Path(argv[1]).resolve()
    session_path = session_dir / SESSION_FILE
    if not session_path.exists():
        print(f"error: {session_path} not found", file=sys.stderr)
        return 2
    try:
        session = json.loads(session_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON in {session_path}: {exc}", file=sys.stderr)
        return 2

    out_path = session_dir / OUT_FILE
    out_path.write_text(build_html(session, session_dir), encoding="utf-8")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
