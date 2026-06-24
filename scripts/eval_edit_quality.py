"""Edit-quality eval: TEMPLATE arm vs RAW arm, per fixed case.

For each case it builds two payloads against the SAME source:
  - template arm: the package `GenIntent.EDIT` framing (preservation scaffold)
  - raw arm: the SAME payload with only the final instruction replaced by the
    delta verbatim (no scaffold) — so the arms differ by construction in exactly
    one field, nothing else
runs both on the free Codex path, records the per-image token usage (Phase 03),
and writes a side-by-side HTML for human judgment (default judge).

Cost: cases x 2 arms x --samples free Codex image calls (~70s each). Use --dry-run
to validate wiring with zero quota. Reuses the package; no scratchpad dependency.

Usage:
  python3 scripts/eval_edit_quality.py --dry-run
  python3 scripts/eval_edit_quality.py --samples 1 --outdir eval-out
"""

import argparse
import base64
import html
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codex_imagegen.core import image_loader, image_writer  # noqa: E402
from codex_imagegen.core.errors import GatewayError, ImagegenError  # noqa: E402
from codex_imagegen.providers.generate.base import GenIntent  # noqa: E402
from codex_imagegen.providers.generate.codex import auth, client  # noqa: E402

DEFAULT_CASES = Path(__file__).resolve().parent / "edit_eval_cases.json"


def _arms(b64: str, mime: str, delta: str, size: str) -> dict[str, dict]:
    """Both arms from the SAME builder; the raw arm only swaps the final text to
    the verbatim delta, so the preservation scaffold is the sole difference."""
    template = client.build_payload(
        delta, size, "png", client.DEFAULT_MODEL, refs=[(b64, mime)], intent=GenIntent.EDIT
    )
    raw = client.build_payload(
        delta, size, "png", client.DEFAULT_MODEL, refs=[(b64, mime)], intent=GenIntent.EDIT
    )
    raw["input"][0]["content"][-1]["text"] = delta  # drop the scaffold; keep wiring identical
    return {"template": template, "raw": raw}


def _call(payload: dict, *, total: float, stall: float) -> tuple[bytes, dict]:
    a = auth.load_auth()
    access, account_id, refresh = auth.extract_tokens(a)
    version = client.codex_version()
    headers = client.build_headers(access, account_id, version)
    try:
        return client._post_once(headers, payload, total, stall, True)
    except GatewayError as exc:
        if getattr(exc, "status", None) == 401 and refresh:
            headers = client.build_headers(auth.refresh_and_persist(a, refresh), account_id, version)
            return client._post_once(headers, payload, total, stall, True)
        raise


def _img_total(meta: dict) -> object:
    return (meta.get("image_usage") or {}).get("total_tokens", "n/a")


def _html(records: list[dict], outdir: Path) -> Path:
    rows = []
    for r in records:
        cells = []
        for arm in ("template", "raw"):
            a = r["arms"].get(arm, {})
            if a.get("file"):
                data = base64.b64encode((outdir / a["file"]).read_bytes()).decode("ascii")
                img = f'<img src="data:image/png;base64,{data}" style="max-width:100%;height:auto">'
            else:
                img = f"<em>{html.escape(str(a.get('error', 'not run')))}</em>"
            cells.append(
                f"<td style='vertical-align:top;width:50%'><b>{arm}</b> "
                f"&mdash; {a.get('image_tokens', 'n/a')} img tok, {a.get('elapsed_s', '?')}s"
                f"<br>{img}</td>"
            )
        rows.append(
            f"<tr><td colspan=2 style='padding-top:24px'><h3>{html.escape(r['id'])}: "
            f"{html.escape(r['delta'])}</h3></td></tr><tr>{''.join(cells)}</tr>"
        )
    page = (
        "<!doctype html><meta charset=utf-8><title>Edit eval: template vs raw</title>"
        "<body style='font-family:system-ui;max-width:1100px;margin:2rem auto'>"
        "<h1>Edit eval &mdash; template vs raw</h1>"
        "<p>Judge: which arm applied the delta AND preserved the rest better?</p>"
        f"<table style='width:100%;border-collapse:collapse'>{''.join(rows)}</table></body>"
    )
    path = outdir / "side-by-side.html"
    path.write_text(page, encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(DEFAULT_CASES))
    ap.add_argument("--source", default=None, help="override the source image in the cases file")
    ap.add_argument("--outdir", default="eval-out")
    ap.add_argument("--samples", type=int, default=1, help="runs per arm (gpt-image-2 has no seed)")
    ap.add_argument("--judge", default="human", choices=["human", "codex", "minimax"])
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--stall-timeout", type=int, default=120, dest="stall_timeout")
    ap.add_argument("--dry-run", action="store_true", help="build payloads, make NO network calls")
    args = ap.parse_args()

    spec = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    source = args.source or spec["source"]
    cases = spec["cases"]
    if not Path(source).is_file():
        print(f"source not found: {source} (edit the cases file or pass --source)", file=sys.stderr)
        return 2
    if args.judge != "human":
        print(f"[note] judge={args.judge!r} not wired in v1; run probe_codex_self_judge.py first. "
              "Producing the human side-by-side instead.", file=sys.stderr)

    total_calls = len(cases) * 2 * args.samples
    print(f"{len(cases)} case(s) x 2 arms x {args.samples} sample(s) = {total_calls} Codex calls"
          f"{' (DRY RUN: none)' if args.dry_run else ''}", file=sys.stderr)

    b64, mime = image_loader.load_reference(source)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []

    try:
        for case in cases:
            cid, delta = case["id"], case["delta"]
            arms_payloads = _arms(b64, mime, delta, "auto")
            rec: dict = {"id": cid, "delta": delta, "arms": {}}
            for arm, payload in arms_payloads.items():
                for s in range(args.samples):
                    suffix = f"-{s + 1}" if args.samples > 1 else ""
                    tag = f"{image_writer.slugify(cid)}-{arm}{suffix}"
                    if args.dry_run:
                        text = payload["input"][0]["content"][-1]["text"]
                        print(f"[dry] {tag}: tool_choice={payload['tool_choice']} text={text[:60]!r}",
                              file=sys.stderr)
                        rec["arms"][arm] = {"dry_run": True}
                        continue
                    print(f"[run] {tag} ...", file=sys.stderr)
                    try:
                        img, meta = _call(payload, total=args.timeout, stall=args.stall_timeout)
                    except ImagegenError as exc:  # GatewayError/AuthError/InputError all subclass this
                        print(f"  ! {tag} failed: {exc}", file=sys.stderr)
                        rec["arms"][arm] = {"error": str(exc)}
                        continue
                    fname = f"{tag}.png"
                    (outdir / fname).write_bytes(img)
                    rec["arms"][arm] = {
                        "file": fname,
                        "image_tokens": _img_total(meta),
                        "elapsed_s": meta.get("elapsed_s"),
                        "action": meta.get("action"),
                    }
            records.append(rec)
    finally:
        # Always persist whatever completed, even if an unexpected error aborts the run.
        (outdir / "manifest.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(f"\nmanifest -> {outdir / 'manifest.json'}", file=sys.stderr)

    if not args.dry_run and records:
        html_path = _html(records, outdir)
        print(f"side-by-side -> {html_path}  (open in a browser to judge)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
