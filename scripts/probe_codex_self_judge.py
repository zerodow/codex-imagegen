"""Probe: can the Codex backend return a TEXT verdict about an image?

If yes, the edit-eval harness can judge for FREE (no paid MiniMax VLM). We send a
source image + a yes/no question with NO image_generation tool and check whether
the stream yields usable text. Read-only; reuses the package auth + SSE parser.

Usage:
  python3 scripts/probe_codex_self_judge.py [--source IMG] [--question "..."]
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codex_imagegen.core import image_loader  # noqa: E402
from codex_imagegen.core.errors import GatewayError, ImagegenError  # noqa: E402
from codex_imagegen.providers.generate.codex import auth, client  # noqa: E402

DEFAULT_SOURCE = "generated/2026-06-24/fox.png"
DEFAULT_QUESTION = (
    "Look at this image. Does it contain a speech bubble with text? "
    "Answer 'yes' or 'no' and give a one-sentence reason."
)


def _judge_payload(b64: str, mime: str, question: str) -> dict:
    return {
        "model": client.DEFAULT_MODEL,
        "stream": True,
        "instructions": "You are a precise visual checker. Answer briefly in plain text.",
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_image", "image_url": f"data:{mime};base64,{b64}"},
            {"type": "input_text", "text": question},
        ]}],
        "tools": [],            # no image_generation -> we want a TEXT answer
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "store": False,
        "reasoning": {"effort": "low", "summary": "auto"},
        "include": ["reasoning.encrypted_content"],
        "text": {"verbosity": "low"},
    }


def _read_text(headers: dict, payload: dict, total: float = 120, stall: float = 60):
    # The same answer arrives three ways (streamed deltas, a final output_text.done,
    # and the message item). Capture each source separately and return ONE, by
    # priority, so the verdict text isn't triplicated.
    seen: dict[str, int] = {}
    deltas: list[str] = []
    done_text = ""
    msg_text: list[str] = []
    deadline = time.monotonic() + total
    for evt in client._stream(headers, payload, deadline, stall):
        et = evt.get("type", "?")
        seen[et] = seen.get(et, 0) + 1
        if et == "response.output_text.delta" and isinstance(evt.get("delta"), str):
            deltas.append(evt["delta"])
        elif et == "response.output_text.done" and isinstance(evt.get("text"), str):
            done_text = evt["text"]
        elif et == "response.output_item.done":
            item = evt.get("item")
            if isinstance(item, dict) and item.get("type") == "message":
                for part in item.get("content") or []:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        msg_text.append(part["text"])
    text = done_text or "".join(deltas) or "".join(msg_text)
    return text.strip(), seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--question", default=DEFAULT_QUESTION)
    args = ap.parse_args()

    if not Path(args.source).is_file():
        print(f"source not found: {args.source} (pass --source)", file=sys.stderr)
        return 2

    b64, mime = image_loader.load_reference(args.source)
    a = auth.load_auth()
    access, account_id, refresh = auth.extract_tokens(a)
    version = client.codex_version()
    headers = client.build_headers(access, account_id, version)
    payload = _judge_payload(b64, mime, args.question)

    print(f"POST {client.CODEX_BACKEND}  (self-judge probe: image + question, no image tool)",
          file=sys.stderr)
    try:
        text, seen = _read_text(headers, payload)
    except GatewayError as exc:
        if getattr(exc, "status", None) == 401 and refresh:
            print("  401 -> refresh + retry", file=sys.stderr)
            headers = client.build_headers(auth.refresh_and_persist(a, refresh), account_id, version)
            text, seen = _read_text(headers, payload)
        else:
            print(f"FAILED: {exc}", file=sys.stderr)
            return 1
    except ImagegenError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"\nEVENT TYPES: {seen}", file=sys.stderr)
    print("\n=== VERDICT ===", file=sys.stderr)
    if text:
        print("FEASIBLE: backend returned text -> free automated judging is possible.", file=sys.stderr)
        print(f"TEXT: {text[:500]}", file=sys.stderr)
        return 0
    print("NOT FEASIBLE: no text returned -> fall back to human (or paid MiniMax) judge.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
