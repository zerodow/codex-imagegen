"""`imagegen` command: prompt -> image file via the Codex subscription.

Usage: imagegen "<prompt>" [-o out.png] [--size 1024x1024] [--format png]
"""

import argparse
import sys

from .core import env_file, image_loader, image_writer, orchestrator
from .core.errors import ImagegenError, InputError
from .providers import registry
from .providers.generate.base import GenIntent
from .providers.generate.codex.client import DEFAULT_STALL_TIMEOUT, DEFAULT_TOTAL_TIMEOUT

# gpt-image-2 treats size as a hint, not a hard constraint (it may return a
# different aspect). These are the accepted hint values; "auto" lets it choose.
SIZE_HINTS = {"auto", "1024x1024", "1536x1024", "1024x1536", "1792x1024", "1024x1792"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="imagegen",
        description="Generate an image from a prompt using your ChatGPT subscription "
        "(gpt-image-2 via Codex). Requires `codex login`.",
    )
    parser.add_argument("prompt", help="Text description of the image to generate")
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output file path (default: ./generated/<date>/<slug>-<time>.<ext>)",
    )
    parser.add_argument(
        "-i", "--reference", action="append", default=None, metavar="PATH",
        help="Reference image for character/subject consistency (repeatable). "
        "The result keeps the reference subject's appearance in the new scene.",
    )
    parser.add_argument(
        "--size", default="1024x1024",
        help=f"Size hint (not strictly honored by gpt-image-2). One of: {', '.join(sorted(SIZE_HINTS))}",
    )
    parser.add_argument(
        "--format", default="png", choices=["png", "jpeg", "webp"], dest="fmt",
        help="Output image format (default: png)",
    )
    parser.add_argument("--provider", default="codex", help="Image provider: codex | minimax (default: codex)")
    parser.add_argument("--model", default=None, help="Model override (default: the provider's own default)")
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TOTAL_TIMEOUT,
        help=f"Total wall-clock budget in seconds (default: {DEFAULT_TOTAL_TIMEOUT}); large images take 1-3 min",
    )
    parser.add_argument(
        "--stall-timeout", type=int, default=DEFAULT_STALL_TIMEOUT, dest="stall_timeout",
        help=f"Max seconds of stream silence before aborting (default: {DEFAULT_STALL_TIMEOUT})",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress progress; print only the saved path")
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if not args.prompt or not args.prompt.strip():
        raise InputError("prompt is empty")
    if args.size not in SIZE_HINTS:
        raise InputError(f"invalid --size {args.size!r}; expected one of: {', '.join(sorted(SIZE_HINTS))}")
    if args.timeout <= 0 or args.stall_timeout <= 0:
        raise InputError("--timeout and --stall-timeout must be positive")


def main(argv: list[str] | None = None) -> int:
    env_file.load_dotenv()  # pick up a project-local .env (real env vars still win)
    args = build_parser().parse_args(argv)
    progress = not args.quiet
    try:
        _validate_args(args)
        refs = image_loader.load_references(args.reference) if args.reference else None
        intent = GenIntent.CONSISTENCY if refs else GenIntent.PLAIN
        out_path = image_writer.resolve_output_path(args.output, args.prompt, args.fmt)
        provider = registry.get_image_provider(args.provider, model=args.model)
        orchestrator.generate_to_file(
            provider,
            args.prompt,
            out_path,
            refs=refs,
            intent=intent,
            size=args.size,
            fmt=args.fmt,
            total_timeout=args.timeout,
            stall_timeout=args.stall_timeout,
            progress=progress,
        )
    except ImagegenError as exc:
        print(f"imagegen: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001 - last resort: never leak a traceback
        print(f"imagegen: unexpected error: {exc}", file=sys.stderr)
        return 1
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
