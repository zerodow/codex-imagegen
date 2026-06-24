"""Call the Codex Responses backend with the image_generation tool.

Builds the headers + payload the Codex CLI uses, POSTs to the codex/responses
endpoint, parses the SSE stream, and returns the decoded image bytes from the
`image_generation_call` result. Refreshes the access token once on HTTP 401.
"""

import base64
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Iterator

from . import auth as _auth
from codex_imagegen.core.errors import GatewayError
from codex_imagegen.providers.generate.base import GenIntent

CODEX_BACKEND = "https://chatgpt.com/backend-api/codex/responses"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_TOTAL_TIMEOUT = 300
DEFAULT_STALL_TIMEOUT = 120
_VERSION_FLOOR = "0.141.0"


def codex_version() -> str:
    """Best-effort Codex version string for the `version` header.

    The backend rejects newer image models when sent a stale version, so we
    read the installed CLI version and fall back to a known-good floor.
    """
    try:
        out = subprocess.run(
            ["codex", "--version"], capture_output=True, text=True, timeout=10
        ).stdout
        match = re.search(r"(\d+\.\d+\.\d+)", out)
        if match:
            return match.group(1)
    except Exception:  # noqa: BLE001
        pass
    return _VERSION_FLOOR


def _user_agent(version: str) -> str:
    return f"codex_cli_rs/{version} (Mac OS; arm64) codex-imagegen"


def build_headers(token: str, account_id: str | None, version: str) -> dict[str, str]:
    """Construct the request headers the codex/responses backend expects."""
    sid = str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
        "Connection": "Keep-Alive",
        "version": version,
        "session_id": sid,
        "x-client-request-id": sid,
        "User-Agent": _user_agent(version),
        "originator": "codex_cli_rs",
    }
    if account_id:
        headers["chatgpt-account-id"] = account_id
    return headers


# Ordinal words for the first few references; beyond this we fall back to "#N".
_ORDINALS = ("FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH")


def _compose_user_text(prompt: str, n_refs: int, labels: list[str], relation: str | None) -> str:
    """Build the multi-subject merge instruction: each reference is a DISTINCT
    character that must appear, with faces kept separate (no identity blending)."""
    lines = []
    for i in range(n_refs):
        ordinal = _ORDINALS[i] if i < len(_ORDINALS) else f"#{i + 1}"
        raw_label = labels[i].strip() if i < len(labels) and labels[i] else ""
        label = raw_label or f"the subject in reference image {i + 1}"
        lines.append(f" - Character {i + 1} = the subject in the {ordinal} reference image ({label})")
    relation_text = relation.strip() if relation and relation.strip() else "together in the scene"
    return (
        f"Create ONE new image containing {n_refs} DISTINCT characters, all clearly visible:\n"
        + "\n".join(lines)
        + "\nEach character MUST appear. Preserve each one's OWN face, hair, outfit, colors, "
        "and art style. DO NOT blend or merge their faces into a single person. "
        f"Arrange them: {relation_text}. Scene: {prompt}. "
        "Do not copy any reference background. Return only the image."
    )


def _edit_user_text(delta: str) -> str:
    """Frame an in-place edit: apply ONLY the delta, preserve everything else.

    The preservation clause is the load-bearing part — the backend edits via
    regeneration, so without an explicit "keep the rest" instruction it drifts
    unmodified regions (text, line work, colors). Verified by probe.
    """
    return (
        "Edit the provided image. Apply ONLY this change: "
        f"{delta}. "
        "Preserve everything else exactly as in the original — overall composition, "
        "the position and pose of every subject, all other colors, any text rendered "
        "in the image, line work, art style, and the background. Do not restyle or "
        "regenerate unmodified regions. Return only the edited image, no commentary."
    )


def build_payload(
    prompt: str,
    size: str,
    output_format: str,
    model: str,
    refs: list[tuple[str, str]] | None = None,
    intent: GenIntent = GenIntent.PLAIN,
    labels: list[str] | None = None,
    relation: str | None = None,
) -> dict:
    """Build the codex/responses body that wires a single image_generation tool.

    `intent` chooses the prompt framing (the caller decides; this function owns
    the wording). CONSISTENCY/COMPOSE/EDIT attach each `refs` entry (base64, mime)
    as an `input_image` content part and force the tool (`tool_choice: "required"`);
    PLAIN sends prompt-only with `tool_choice: "auto"`. COMPOSE also uses `labels`
    (paired to refs, in order) and `relation` to disambiguate subjects. EDIT takes
    a single source ref and wraps `prompt` in a preservation template (apply only
    the delta, keep everything else).
    """
    refs = refs or []
    if intent is GenIntent.COMPOSE:
        user_text = _compose_user_text(prompt, len(refs), labels or [], relation)
        content: list[dict] = [
            {"type": "input_image", "image_url": f"data:{mime};base64,{b64}"}
            for (b64, mime) in refs
        ]
        content.append({"type": "input_text", "text": user_text})
        tool_choice = "required"
    elif intent is GenIntent.CONSISTENCY:
        user_text = (
            "Generate a NEW image of the SAME character/subject shown in the reference "
            "image(s). Keep their appearance consistent — face, hair, body, outfit, "
            "colors, and art style — but place them in the scene described below. "
            "Do not copy the reference background. Return only the image. "
            f"Scene: {prompt}"
        )
        content: list[dict] = [
            {"type": "input_image", "image_url": f"data:{mime};base64,{b64}"}
            for (b64, mime) in refs
        ]
        content.append({"type": "input_text", "text": user_text})
        tool_choice = "required"
    elif intent is GenIntent.EDIT:
        user_text = _edit_user_text(prompt)
        content = [
            {"type": "input_image", "image_url": f"data:{mime};base64,{b64}"}
            for (b64, mime) in refs
        ]
        content.append({"type": "input_text", "text": user_text})
        tool_choice = "required"
    else:  # GenIntent.PLAIN
        user_text = (
            "Use the image_generation tool to render the following image. "
            f"Return only the image, no commentary. Prompt: {prompt}"
        )
        content = [{"type": "input_text", "text": user_text}]
        tool_choice = "auto"

    image_tool: dict = {"type": "image_generation", "output_format": output_format}
    if size and size != "auto":
        image_tool["size"] = size
    return {
        "model": model,
        "stream": True,
        "instructions": "You are an image generation assistant.",
        "input": [{"type": "message", "role": "user", "content": content}],
        "tools": [image_tool],
        "tool_choice": tool_choice,
        "parallel_tool_calls": False,
        "store": False,
        "reasoning": {"effort": "low", "summary": "auto"},
        "include": ["reasoning.encrypted_content"],
        "text": {"verbosity": "low"},
    }


def _loosen_read_timeout(resp, seconds: float) -> None:
    """Bound the per-read idle window on the streaming socket.

    The default connect timeout is too short for the quiet gaps between SSE
    chunks while an image renders; the overall budget is enforced separately.
    Best-effort: silently no-op if the socket isn't reachable on this platform.
    """
    try:
        resp.fp.raw._sock.settimeout(seconds)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def _stream(headers: dict, body: dict, deadline: float, stall: float) -> Iterator[dict]:
    """Yield parsed JSON event dicts from the SSE response."""
    req = urllib.request.Request(
        CODEX_BACKEND, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    initial = max(1.0, min(30.0, deadline - time.monotonic()))
    resp = urllib.request.urlopen(req, timeout=initial)
    _loosen_read_timeout(resp, min(stall, max(1.0, deadline - time.monotonic())))
    try:
        buf: list[str] = []
        for raw in resp:
            if time.monotonic() >= deadline:
                raise GatewayError("stream exceeded total timeout budget")
            line = raw.decode("utf-8", errors="ignore").rstrip("\r\n")
            if line == "":
                if not buf:
                    continue
                payload = "\n".join(buf)
                buf = []
                if payload == "[DONE]":
                    return
                try:
                    yield json.loads(payload)
                except Exception:  # noqa: BLE001 - skip malformed event, keep streaming
                    continue
                continue
            if line.startswith(":") or line.startswith("event:"):
                continue
            if line.startswith("data:"):
                chunk = line[len("data:") :]
                if chunk.startswith(" "):
                    chunk = chunk[1:]
                buf.append(chunk)
        # Flush a final event the server closed without a trailing blank line.
        # That last event is `response.output_item.done` carrying the image, so
        # dropping it would turn a success into a false "no image returned".
        if buf:
            payload = "\n".join(buf)
            if payload != "[DONE]":
                try:
                    yield json.loads(payload)
                except Exception:  # noqa: BLE001
                    pass
    finally:
        resp.close()


def _post_once(
    headers: dict, payload: dict, total: float, stall: float, progress: bool
) -> tuple[bytes, dict]:
    start = time.monotonic()
    deadline = start + total
    seen: dict[str, int] = {}
    image_b64: str | None = None
    meta: dict = {}
    usage_meta: dict = {}
    failure: str | None = None
    last_phase = "connecting"

    def emit(msg: str) -> None:
        if progress:
            print(f"[{time.monotonic() - start:6.1f}s] {msg}", file=sys.stderr)

    try:
        for evt in _stream(headers, payload, deadline, stall):
            etype = evt.get("type", "?")
            seen[etype] = seen.get(etype, 0) + 1
            first = seen[etype] == 1
            if etype == "response.image_generation_call.in_progress" and first:
                last_phase = "queued"
                emit("queued")
            elif etype == "response.image_generation_call.generating" and first:
                last_phase = "generating"
                emit("generating")
            elif etype == "response.image_generation_call.partial_image":
                last_phase = "receiving image"
                emit(f"receiving image (partial {seen[etype]})")
            if etype in ("error", "response.failed"):
                failure = _extract_failure(evt) or failure
            if etype == "response.output_item.done":
                item = evt.get("item")
                if (
                    isinstance(item, dict)
                    and item.get("type") == "image_generation_call"
                    and isinstance(item.get("result"), str)
                ):
                    image_b64 = item["result"]
                    meta = {k: v for k, v in item.items() if k != "result"}
            if etype == "response.completed":
                usage_meta = _extract_usage(evt)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise GatewayError(f"HTTP {exc.code}: {body[:400]}", status=exc.code) from None
    except (TimeoutError, ConnectionError):
        elapsed = time.monotonic() - start
        raise GatewayError(
            f"stalled/timed out (last phase: {last_phase}, {elapsed:.0f}s elapsed)"
        ) from None
    except urllib.error.URLError as exc:
        raise GatewayError(f"network error contacting the image backend: {exc.reason}") from None

    if not image_b64:
        types = ", ".join(sorted(seen)) or "(none)"
        detail = failure or f"events seen: {types}"
        raise GatewayError(f"no image returned ({detail})")
    try:
        decoded = base64.b64decode(image_b64, validate=True)
    except Exception:  # noqa: BLE001
        raise GatewayError("backend returned invalid base64 in image result") from None
    return decoded, {**meta, **usage_meta, "elapsed_s": round(time.monotonic() - start, 1)}


def _extract_failure(evt: dict) -> str | None:
    response = evt.get("response")
    if isinstance(response, dict) and isinstance(response.get("error"), dict):
        err = response["error"]
        return err.get("message") or err.get("code")
    if isinstance(evt.get("error"), dict):
        return evt["error"].get("message")
    return evt.get("message") or evt.get("code") or (
        evt.get("error") if isinstance(evt.get("error"), str) else None
    )


def _extract_usage(evt: dict) -> dict:
    """Pull token usage + model names from a `response.completed` event.

    Returns {} when the fields are absent (older/other backends) — callers must
    treat usage as optional and never fabricate it. `tool_usage.image_gen` is the
    real per-image cost; top-level `usage` is the orchestration (gpt-5.5) cost.
    """
    resp = evt.get("response")
    if not isinstance(resp, dict):
        return {}
    out: dict = {}
    if isinstance(resp.get("usage"), dict):
        out["usage"] = resp["usage"]
    tool_usage = resp.get("tool_usage")
    if isinstance(tool_usage, dict) and isinstance(tool_usage.get("image_gen"), dict):
        out["image_usage"] = tool_usage["image_gen"]
    models: dict = {}
    if resp.get("model"):
        models["orchestrator"] = resp["model"]
    tools = resp.get("tools")
    if isinstance(tools, list) and tools and isinstance(tools[0], dict) and tools[0].get("model"):
        models["image"] = tools[0]["model"]
    if models:
        out["models"] = models
    return out


def generate_image_bytes(
    prompt: str,
    *,
    size: str,
    output_format: str,
    access_token: str,
    account_id: str | None,
    refresh_token: str | None,
    auth: dict,
    model: str = DEFAULT_MODEL,
    total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
    stall_timeout: float = DEFAULT_STALL_TIMEOUT,
    progress: bool = False,
    refs: list[tuple[str, str]] | None = None,
    intent: GenIntent = GenIntent.PLAIN,
    labels: list[str] | None = None,
    relation: str | None = None,
) -> tuple[bytes, dict]:
    """Generate one image; return (image_bytes, item_metadata).

    `refs` (list of (base64, mime)) attaches reference images; `intent` frames
    the prompt (`labels`/`relation` apply to COMPOSE). Refreshes the access token
    once and retries on HTTP 401.
    """
    version = codex_version()
    payload = build_payload(
        prompt, size, output_format, model,
        refs=refs, intent=intent, labels=labels, relation=relation,
    )
    headers = build_headers(access_token, account_id, version)
    try:
        return _post_once(headers, payload, total_timeout, stall_timeout, progress)
    except GatewayError as exc:
        if exc.status == 401 and refresh_token:
            if progress:
                print("[auth] access token expired; refreshing", file=sys.stderr)
            new_token = _auth.refresh_and_persist(auth, refresh_token)
            headers = build_headers(new_token, account_id, version)
            return _post_once(headers, payload, total_timeout, stall_timeout, progress)
        raise
