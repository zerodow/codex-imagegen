"""`imagegen-character`: generate many images of ONE consistent character.

Takes a baseline (an existing image, or a prompt to generate one), then renders
each scene with the baseline attached as a reference image so the character's
appearance carries across the set. Runs sequentially (image gen is slow and
quota-limited); a failed scene is reported but does not abort the batch.
"""

import argparse
import sys
from pathlib import Path

from ..core import env_file, image_loader, image_writer, orchestrator
from ..core.errors import ImagegenError, InputError
from ..providers import registry
from ..providers.generate.base import GenIntent
from ..providers.generate.codex.client import (
    DEFAULT_MODEL,
    DEFAULT_STALL_TIMEOUT,
    DEFAULT_TOTAL_TIMEOUT,
)

from ..cli import SIZE_HINTS  # reuse the same size-hint whitelist


def _read_scenes(path: str) -> list[str]:
    """Read scene prompts, one per line; skip blanks and `#` comments."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise InputError(f"scenes file not found: {p}")
    scenes = [
        line.strip()
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not scenes:
        raise InputError(f"no scenes found in {p} (one prompt per non-comment line)")
    return scenes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="imagegen-character",
        description="Generate a set of images of the same character, using a baseline "
        "image as a consistency reference for every scene.",
    )
    parser.add_argument("--name", required=True, help="Character name (used for output folder/filenames)")
    baseline = parser.add_mutually_exclusive_group(required=True)
    baseline.add_argument("--baseline-image", metavar="PATH", help="Existing baseline image to use as the reference")
    baseline.add_argument("--baseline-prompt", metavar="TEXT", help="Prompt to generate the baseline character first")
    parser.add_argument("--scenes", required=True, metavar="FILE", help="Text file: one scene prompt per line")
    parser.add_argument("--outdir", default=None, help="Output dir (default: ./characters/<name>/)")
    parser.add_argument("--size", default="1024x1024", help=f"Size hint: {', '.join(sorted(SIZE_HINTS))}")
    parser.add_argument("--format", default="png", choices=["png", "jpeg", "webp"], dest="fmt")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TOTAL_TIMEOUT)
    parser.add_argument("--stall-timeout", type=int, default=DEFAULT_STALL_TIMEOUT, dest="stall_timeout")
    parser.add_argument("--quiet", action="store_true", help="Print only saved paths")
    return parser


def main(argv: list[str] | None = None) -> int:
    env_file.load_dotenv()  # pick up a project-local .env (real env vars still win)
    args = build_parser().parse_args(argv)
    progress = not args.quiet
    if args.size not in SIZE_HINTS:
        print(f"imagegen-character: invalid --size {args.size!r}", file=sys.stderr)
        return 2
    if args.timeout <= 0 or args.stall_timeout <= 0:
        print("imagegen-character: --timeout and --stall-timeout must be positive", file=sys.stderr)
        return 2

    try:
        scenes = _read_scenes(args.scenes)
        slug = image_writer.slugify(args.name)
        outdir = Path(args.outdir).expanduser() if args.outdir else Path.cwd() / "characters" / slug
        outdir.mkdir(parents=True, exist_ok=True)
        # One provider instance, reused for the whole batch so a mid-batch token
        # refresh persists across scenes.
        provider = registry.get_image_provider("codex", model=args.model)

        # 1) Resolve the baseline image (use given, or generate from a prompt).
        if args.baseline_image:
            baseline = Path(args.baseline_image).expanduser()
            if not baseline.is_file():
                raise InputError(f"baseline image not found: {baseline}")
        else:
            baseline = outdir / f"00-baseline.{args.fmt}"
            print(f"[baseline] generating -> {baseline}", file=sys.stderr)
            orchestrator.generate_to_file(
                provider, args.baseline_prompt, baseline, refs=None, intent=GenIntent.PLAIN,
                size=args.size, fmt=args.fmt, total_timeout=args.timeout,
                stall_timeout=args.stall_timeout, progress=progress,
            )

        # Validate the baseline (existing or just-generated) before the batch.
        refs = image_loader.load_references([str(baseline)])
        print(f"[baseline] ready: {baseline}", file=sys.stderr)

        # 2) Render each scene with the baseline as a consistency reference.
        saved: list[Path] = []
        failures: list[tuple[str, str]] = []
        for idx, scene in enumerate(scenes, start=1):
            out = outdir / f"{idx:02d}-{image_writer.slugify(scene)}.{args.fmt}"
            print(f"[{idx}/{len(scenes)}] {scene[:60]}", file=sys.stderr)
            try:
                orchestrator.generate_to_file(
                    provider, scene, out, refs=refs, intent=GenIntent.CONSISTENCY,
                    size=args.size, fmt=args.fmt, total_timeout=args.timeout,
                    stall_timeout=args.stall_timeout, progress=progress,
                )
                saved.append(out)
            except ImagegenError as exc:
                print(f"  ! scene {idx} failed: {exc}", file=sys.stderr)
                failures.append((scene, str(exc)))
    except ImagegenError as exc:
        print(f"imagegen-character: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001 - last resort: never leak a traceback
        print(f"imagegen-character: unexpected error: {exc}", file=sys.stderr)
        return 1

    for path in saved:
        print(path)
    print(f"[done] {len(saved)} saved, {len(failures)} failed -> {outdir}", file=sys.stderr)
    return 4 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
