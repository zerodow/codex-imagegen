"""`imagegen-edit` command: modify one source image from a text instruction.

Usage: imagegen-edit "<change to apply>" -i source.png [-o out.png]
       [--size ...] [--format ...] [--provider codex] [--quiet]

Edit is instruction-only in v1 (recolor / add / remove). It applies ONLY the
change and preserves the rest. Note: gpt-image-2 edits by regeneration, so a
non-standard input size is rescaled to the backend's own resolution.
"""

import argparse
import sys

from .cli import SIZE_HINTS  # reuse the same size-hint whitelist
from .core import env_file, image_loader, image_writer, output_report
from .core.errors import ImagegenError, InputError
from .features import edit
from .providers import registry
from .providers.generate.codex.client import DEFAULT_STALL_TIMEOUT, DEFAULT_TOTAL_TIMEOUT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="imagegen-edit",
        description="Edit one source image in place from a text instruction "
        "(apply only the change, preserve the rest). Requires `codex login`.",
    )
    parser.add_argument("prompt", help="The change to apply (e.g. \"make the cap red\")")
    parser.add_argument(
        "-i", "--reference", action="append", default=None, metavar="PATH",
        help="The source image to edit (exactly one).",
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
    parser.add_argument("--model", default=None, help="Model override (default: the provider's own default)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TOTAL_TIMEOUT)
    parser.add_argument("--stall-timeout", type=int, default=DEFAULT_STALL_TIMEOUT, dest="stall_timeout")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress; print only the saved path")
    parser.add_argument("--json", action="store_true", help="Print a JSON report (path, dims, token usage) instead of the human block")
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if not args.prompt or not args.prompt.strip():
        raise InputError("edit instruction is empty")
    refs = args.reference or []
    if len(refs) != 1:
        raise InputError("edit needs exactly one source image (one -i/--reference)")
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
        # load_references (plural) enforces the ~8 MB base64 budget; a single
        # source still goes through it so an oversized image fails fast here.
        source = image_loader.load_references([args.reference[0]])[0]
        out_path = image_writer.resolve_output_path(args.output, args.prompt, args.fmt)
        provider = registry.get_image_provider(args.provider, model=args.model)
        _path, meta = edit.run(
            provider,
            args.prompt,
            out_path,
            source=source,
            size=args.size,
            fmt=args.fmt,
            total_timeout=args.timeout,
            stall_timeout=args.stall_timeout,
            progress=progress,
        )
    except ImagegenError as exc:
        print(f"imagegen-edit: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001 - last resort: never leak a traceback
        print(f"imagegen-edit: unexpected error: {exc}", file=sys.stderr)
        return 1
    print(output_report.result_line(out_path, meta, as_json=args.json, quiet=args.quiet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
