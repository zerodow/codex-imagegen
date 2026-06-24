"""`imagegen-merge` command: combine subjects from 2+ images into one new image.

Usage: imagegen-merge "<scene>" -i a.png -i b.png [--label "..." --label "..."]
       [--relation "..."] [-o out.png] [--size ...] [--format ...] [--provider codex]
"""

import argparse
import sys

from .cli import SIZE_HINTS  # reuse the same size-hint whitelist
from .core import env_file, image_loader, image_writer
from .core.errors import ImagegenError, InputError
from .features import merge
from .providers import registry
from .providers.generate.codex.client import DEFAULT_STALL_TIMEOUT, DEFAULT_TOTAL_TIMEOUT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="imagegen-merge",
        description="Merge the subjects from two or more reference images into one new "
        "image, preserving each subject's identity. Requires `codex login`.",
    )
    parser.add_argument("prompt", help="Scene description for the merged image")
    parser.add_argument(
        "-i", "--reference", action="append", default=None, metavar="PATH",
        help="Reference image holding a subject to include (repeat for each subject; need >=2)",
    )
    parser.add_argument(
        "--label", action="append", default=None, metavar="TEXT",
        help="Short label for each -i, in the SAME order (repeatable). "
        "Either omit entirely or provide one per reference.",
    )
    parser.add_argument(
        "--relation", default=None, metavar="TEXT",
        help='How the subjects are arranged/interact (e.g. "shaking hands", "side by side")',
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output file path (default: ./generated/<date>/<slug>-<time>.<ext>)",
    )
    parser.add_argument(
        "--size", default="1024x1024",
        help=f"Size hint (not strictly honored by gpt-image-2). One of: {', '.join(sorted(SIZE_HINTS))}",
    )
    parser.add_argument("--format", default="png", choices=["png", "jpeg", "webp"], dest="fmt")
    parser.add_argument("--provider", default="codex", help="Image provider (default: codex)")
    parser.add_argument(
        "--vision", default="off", choices=["off", "minimax"],
        help="Vision step: caption references before generation, and (with --verify) "
        "check the result. 'minimax' needs MINIMAX_API_KEY (token plan). Default: off.",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="With --vision, verify the result and retry on failure (needs --vision != off)",
    )
    parser.add_argument(
        "--max-retries", type=int, default=1, dest="max_retries",
        help="Max regeneration retries when --verify fails a check (default: 1)",
    )
    parser.add_argument("--model", default=None, help="Model override (default: the provider's own default)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TOTAL_TIMEOUT)
    parser.add_argument("--stall-timeout", type=int, default=DEFAULT_STALL_TIMEOUT, dest="stall_timeout")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress; print only the saved path")
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if not args.prompt or not args.prompt.strip():
        raise InputError("prompt is empty")
    refs = args.reference or []
    if len(refs) < 2:
        raise InputError("merge needs at least 2 reference images (repeat -i/--reference)")
    if args.label and len(args.label) != len(refs):
        raise InputError(
            f"got {len(args.label)} --label(s) for {len(refs)} reference(s); "
            "provide one label per reference, or none"
        )
    if args.size not in SIZE_HINTS:
        raise InputError(f"invalid --size {args.size!r}; expected one of: {', '.join(sorted(SIZE_HINTS))}")
    if args.timeout <= 0 or args.stall_timeout <= 0:
        raise InputError("--timeout and --stall-timeout must be positive")
    if args.verify and args.vision == "off":
        raise InputError("--verify requires --vision (e.g. --vision minimax)")
    if args.max_retries < 0:
        raise InputError("--max-retries must be >= 0")


def main(argv: list[str] | None = None) -> int:
    env_file.load_dotenv()  # pick up a project-local .env (real env vars still win)
    args = build_parser().parse_args(argv)
    progress = not args.quiet
    try:
        _validate_args(args)
        refs = image_loader.load_references(args.reference)
        out_path = image_writer.resolve_output_path(args.output, args.prompt, args.fmt)
        provider = registry.get_image_provider(args.provider, model=args.model)
        vision = registry.get_vision_provider(args.vision) if args.vision != "off" else None
        merge.run(
            provider,
            args.prompt,
            out_path,
            refs=refs,
            labels=args.label,
            relation=args.relation,
            size=args.size,
            fmt=args.fmt,
            total_timeout=args.timeout,
            stall_timeout=args.stall_timeout,
            progress=progress,
            vision=vision,
            verify=args.verify,
            max_retries=args.max_retries,
        )
    except ImagegenError as exc:
        print(f"imagegen-merge: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001 - last resort: never leak a traceback
        print(f"imagegen-merge: unexpected error: {exc}", file=sys.stderr)
        return 1
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
