"""Render a structured (or JSON) report for a generated/edited image.

Surfaces the per-image token cost the Codex backend reports on
`response.completed`: `image_usage` (the image-generation tokens — the real
per-image cost) prominently, plus a one-line orchestration (gpt-5.5) summary.
Missing usage degrades to `n/a` / `null` — numbers are never fabricated.
"""

import json
from pathlib import Path

from . import image_dims


def result_line(path: Path, meta: dict, *, as_json: bool = False, quiet: bool = False) -> str:
    """Render one image's report. Precedence: json > quiet > structured block."""
    if as_json:
        return _json_report(path, meta, _dims(path))
    if quiet:
        return str(path)
    return _human_report(path, meta, _dims(path))


def format_batch(items: list[tuple[Path, dict]], *, as_json: bool = False, quiet: bool = False) -> str:
    """Render a batch (path, meta) report with per-image lines + aggregate totals."""
    if quiet:
        return "\n".join(str(p) for p, _ in items)
    if as_json:
        return json.dumps(
            {
                "images": [
                    {
                        "path": str(p),
                        "image_usage": m.get("image_usage"),
                        "usage": m.get("usage"),
                        "elapsed_s": m.get("elapsed_s"),
                    }
                    for p, m in items
                ],
                "totals": _batch_totals(items),
            },
            indent=2,
        )
    lines = [f"✓ {len(items)} image(s)"]
    for p, m in items:
        total = (m.get("image_usage") or {}).get("total_tokens")
        elapsed = m.get("elapsed_s")
        lines.append(
            f"  {Path(p).name}   "
            f"{total if total is not None else 'n/a'} img tok · "
            f"{elapsed if elapsed is not None else '?'}s"
        )
    t = _batch_totals(items)
    lines.append(
        f"  ─ total: {t['image_tokens']} img tok · "
        f"{t['llm_tokens']} llm tok · {round(t['elapsed_s'], 1)}s"
    )
    return "\n".join(lines)


def _dims(path: Path) -> tuple[int, int] | None:
    try:
        return image_dims.read_dimensions(Path(path).read_bytes())
    except OSError:
        return None


def _human_report(path: Path, meta: dict, dims: tuple[int, int] | None) -> str:
    models = meta.get("models") or {}
    image_model = models.get("image") or "image model"
    orch = models.get("orchestrator")
    model_line = f"{image_model} (via {orch})" if orch else image_model
    action = meta.get("action") or "generate"
    quality = meta.get("quality") or "auto"
    dim_str = f"{dims[0]}×{dims[1]}" if dims else "?"
    lines = [
        f"✓ saved   {path}",
        f"  model   {model_line}",
        f"  result  {action} · quality {quality} · {dim_str}",
        f"  image   {_fmt_image_usage(meta.get('image_usage'))}",
        f"  llm     {_fmt_llm_usage(meta.get('usage'))}",
    ]
    elapsed = meta.get("elapsed_s")
    if elapsed is not None:
        lines.append(f"  time    {elapsed}s")
    return "\n".join(lines)


def _json_report(path: Path, meta: dict, dims: tuple[int, int] | None) -> str:
    return json.dumps(
        {
            "path": str(path),
            "models": meta.get("models"),
            "action": meta.get("action"),
            "quality": meta.get("quality"),
            "width": dims[0] if dims else None,
            "height": dims[1] if dims else None,
            "image_usage": meta.get("image_usage"),
            "usage": meta.get("usage"),
            "elapsed_s": meta.get("elapsed_s"),
        },
        indent=2,
    )


def _fmt_image_usage(iu: dict | None) -> str:
    if not iu:
        return "n/a"
    ind = iu.get("input_tokens_details") or {}
    outd = iu.get("output_tokens_details") or {}
    return (
        f"in {iu.get('input_tokens')} (img {ind.get('image_tokens', 0)} / "
        f"txt {ind.get('text_tokens', 0)}) · "
        f"out {iu.get('output_tokens')} (img {outd.get('image_tokens', 0)}) · "
        f"total {iu.get('total_tokens')} tok"
    )


def _fmt_llm_usage(u: dict | None) -> str:
    if not u:
        return "n/a"
    return f"{u.get('total_tokens')} tok (in {u.get('input_tokens')} / out {u.get('output_tokens')})"


def _batch_totals(items: list[tuple[Path, dict]]) -> dict:
    image_tokens = sum((m.get("image_usage") or {}).get("total_tokens") or 0 for _, m in items)
    llm_tokens = sum((m.get("usage") or {}).get("total_tokens") or 0 for _, m in items)
    elapsed = sum(m.get("elapsed_s") or 0 for _, m in items)
    return {
        "image_tokens": image_tokens,
        "llm_tokens": llm_tokens,
        "elapsed_s": round(elapsed, 1),  # avoid float-sum noise in the JSON totals
        "count": len(items),
    }
