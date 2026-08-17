#!/usr/bin/env python3
"""Build a catalog-style `review.html` for one OracleMessage deck session.

Sibling of `build_deck_session_index.py`, but for *review* rounds rather than
contact sheets: one full-width section per image (art left, annotations right)
in the same gold-on-dark serif look as the 30-card catalog
(`sessions/260814-1047-30cards-brd-catalog/catalog.html`), which is the layout
the deck owner reviews in.

session.json schema (superset of the index builder's — extra keys are ignored
by that script, so one session.json can drive both pages):
  {
    "title":   "Lá 01 The Spark — phương án thay đom đóm",
    "created": "2026-08-14 23:05",
    "provider": "codex (gpt-image-2)",
    "notes":   "intro paragraph shown under the page title",
    "images": [
      {
        "file":    "card-a1-sunbeam-blind.png",   # relative to the session dir
        "label":   "A1 · Tia nắng qua mành tre",
        "nav":     "A1 · Mành tre",               # sticky-nav label (default: label)
        "numline": "PHƯƠNG ÁN A / biến thể 1",
        "badge":   {"text": "RENDER MỚI", "kind": "new"},   # kind: new | reuse
        "fields":  [{"k": "Ý nghĩa", "v": "...", "warn": false}],
        "prompt":  "the full prompt used",
        "size":    "1024x1536",
        "notes":   "shown in the File line after size"
      }
    ]
  }

Usage:
  python3 scripts/build_deck_review_page.py oraclemessage-deck/sessions/<dir>
"""

import html
import json
import sys
from pathlib import Path

SESSION_FILE = "session.json"
OUT_FILE = "review.html"

CSS = """
  :root { --silk:#e9dfc8; --gold:#b08d3e; --dim:#9d94b8; --bg1:#241f33; --bg2:#171320; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:linear-gradient(180deg,var(--bg1),var(--bg2)); color:var(--silk);
         font-family:Georgia,"Times New Roman",serif; }
  header { padding:36px 5vw 12px; }
  h1 { font-size:1.4rem; font-weight:normal; letter-spacing:0.12em; }
  .sub { color:var(--dim); font-size:0.85rem; margin-top:4px; max-width:85ch; line-height:1.6; }
  nav { position:sticky; top:0; background:rgba(23,19,32,0.95); backdrop-filter:blur(6px);
        padding:10px 5vw; display:flex; flex-wrap:wrap; gap:6px; z-index:10;
        border-bottom:1px solid rgba(176,141,62,0.25); }
  nav a { color:var(--dim); text-decoration:none; font-size:0.72rem; padding:3px 9px;
          border:1px solid rgba(176,141,62,0.3); border-radius:999px; white-space:nowrap; }
  nav a:hover { color:var(--silk); border-color:var(--gold); }
  .page { display:grid; grid-template-columns:minmax(280px,420px) 1fr; gap:36px;
          padding:48px 5vw; border-bottom:1px solid rgba(176,141,62,0.18);
          scroll-margin-top:70px; align-items:start; }
  @media (max-width:800px) { .page { grid-template-columns:1fr; } }
  .art img { width:100%; border-radius:12px;
             box-shadow:0 10px 30px rgba(0,0,0,0.55), 0 0 0 1px rgba(176,141,62,0.35); }
  .numline { color:var(--dim); font-size:0.78rem; letter-spacing:0.15em; margin-bottom:8px; }
  .badge { padding:2px 10px; border-radius:999px; font-size:0.72rem; letter-spacing:0.05em; }
  .badge.reuse { background:rgba(107,142,110,0.25); color:#a8c5ab; border:1px solid #6b8e6e; }
  .badge.new { background:rgba(176,141,62,0.2); color:#d9b96a; border:1px solid var(--gold); }
  h2 { font-size:1.5rem; font-weight:normal; letter-spacing:0.06em; margin-bottom:18px; }
  .field { margin-bottom:14px; }
  .field .k { color:var(--gold); font-size:0.72rem; letter-spacing:0.14em; text-transform:uppercase;
              margin-bottom:3px; }
  .field .v { font-size:0.95rem; line-height:1.55; }
  .field.warn .v { color:#e3c37a; }
  .prompt { font-family:ui-monospace,Menlo,monospace; font-size:0.72rem; line-height:1.5;
            background:rgba(0,0,0,0.3); padding:12px 14px; border-radius:8px;
            border:1px solid rgba(176,141,62,0.2); max-height:180px; overflow-y:auto; }
  .mono { font-family:ui-monospace,Menlo,monospace; font-size:0.78rem; color:var(--dim); }
  .strip { padding:40px 5vw 8px; }
  .strip h2 { margin-bottom:6px; }
  .strip p.desc { color:var(--dim); font-size:0.85rem; margin-bottom:22px; }
  .stripgrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr)); gap:20px; }
  .strip .item img { width:100%; border-radius:8px; box-shadow:0 6px 16px rgba(0,0,0,0.4); }
  .strip .item p { font-size:0.75rem; color:var(--dim); margin-top:6px; line-height:1.4; }
  .missing { color:#e08a7a; font-size:0.8rem; margin-top:6px; }
"""


def _esc(value: object) -> str:
    return html.escape(str(value)) if value is not None else ""


def _field(k: str, v: str, warn: bool = False) -> str:
    cls = "field warn" if warn else "field"
    return f'<div class="{cls}"><div class="k">{_esc(k)}</div><div class="v">{_esc(v)}</div></div>'


def _section(idx: int, img: dict, session_dir: Path) -> str:
    file = img.get("file", "")
    label = img.get("label") or file
    badge = img.get("badge") or {}
    badge_html = (
        f'<span class="badge {_esc(badge.get("kind", "new"))}">{_esc(badge.get("text", ""))}</span>'
        if badge.get("text")
        else ""
    )
    numline = img.get("numline", "")
    head = " · ".join(p for p in (_esc(numline), badge_html) if p)

    fields = "\n      ".join(
        _field(f.get("k", ""), f.get("v", ""), bool(f.get("warn"))) for f in img.get("fields", [])
    )
    prompt = img.get("prompt", "")
    prompt_html = (
        f'<div class="field"><div class="k">Prompt gen (EN, đầy đủ)</div>'
        f'<div class="v prompt">{_esc(prompt)}</div></div>'
        if prompt
        else ""
    )
    file_line = " · ".join(p for p in (file, img.get("size", ""), img.get("notes", "")) if p)
    missing = "" if (session_dir / file).exists() else '<div class="missing">⚠ file not found</div>'

    return f"""
  <section class="page" id="c{idx}">
    <div class="art"><img src="{_esc(file)}" alt="{_esc(label)}" loading="lazy">{missing}</div>
    <div class="meta">
      <div class="numline">{head}</div>
      <h2>{_esc(label)}</h2>
      {fields}
      {prompt_html}
      <div class="field"><div class="k">File</div><div class="v mono">{_esc(file_line)}</div></div>
    </div>
  </section>"""


def _strip(images: list[dict]) -> str:
    if len(images) < 2:
        return ""
    items = "\n".join(
        f'    <div class="item"><a href="#c{i + 1}">'
        f'<img src="{_esc(img.get("file", ""))}" alt="{_esc(img.get("label", ""))}" loading="lazy"></a>'
        f'<p>{_esc(img.get("label", ""))}</p></div>'
        for i, img in enumerate(images)
    )
    return f"""
  <section class="strip">
    <h2>So sánh nhanh</h2>
    <p class="desc">Bấm một ảnh để nhảy xuống phần chi tiết.</p>
    <div class="stripgrid">
{items}
    </div>
  </section>"""


def build_html(session: dict, session_dir: Path) -> str:
    title = session.get("title") or session_dir.name
    created = session.get("created", "")
    provider = session.get("provider", "")
    notes = session.get("notes", "")
    images = session.get("images", [])

    sub = " · ".join(p for p in (created, provider) if p)
    sub_html = f'<div class="sub">{_esc(sub)}</div>' if sub else ""
    notes_html = f'<div class="sub">{_esc(notes)}</div>' if notes else ""
    nav = "".join(
        f'<a href="#c{i + 1}">{_esc(img.get("nav") or img.get("label", ""))}</a>'
        for i, img in enumerate(images)
    )
    sections = "\n".join(_section(i + 1, img, session_dir) for i, img in enumerate(images))

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>{_esc(title).upper()}</h1>
  {sub_html}
  {notes_html}
</header>
<nav>{nav}</nav>
{_strip(images)}
{sections}
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
