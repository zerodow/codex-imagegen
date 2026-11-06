"""Render images through an account pool's OpenAI-style Images API.

Why a second wire format: on the Responses path the backend forces the tool's
image model to `gpt-image-2-codex`, injects a `complexity` it then rejects for
every value ("Complexity 'low' is not supported for this image model"), and so
returns no image at all (observed 2026-11-06 through the pool, for every
orchestrator/quality/version tried). The pool also exposes the image models
directly behind the OpenAI Images API, which renders fine.

Scope: every request in pool mode. Prompt-only (PLAIN) goes to
`/images/generations`; anything with reference images (CONSISTENCY / COMPOSE /
EDIT) goes to `/images/edits` as JSON `images: [{image_url: data-URI}]`, worded
by the same `client.ref_intent_text` the Responses path uses. Both verified live
2026-11-06 (edit kept the composition, merge kept both subjects). Not streamed:
one JSON response carrying `b64_json`.
"""

import base64
import json
import sys
import time
import urllib.error
import urllib.request

from codex_imagegen.core.errors import GatewayError
from codex_imagegen.providers.generate.base import GenIntent
from . import client as _client

DEFAULT_IMAGE_MODEL = "gpt-image-2.5"


def images_url(responses_url: str, *, edits: bool = False) -> str:
    """Map the pool's normalized `.../v1/responses` URL to its Images API route."""
    base = responses_url.rstrip("/")
    if base.endswith("/responses"):
        base = base[: -len("/responses")]
    return f"{base}/images/{'edits' if edits else 'generations'}"


def build_payload(
    prompt: str,
    size: str,
    output_format: str,
    model: str,
    *,
    refs: list[tuple[str, str]] | None = None,
    intent: GenIntent = GenIntent.PLAIN,
    labels: list[str] | None = None,
    relation: str | None = None,
) -> dict:
    """Images API body; `size` is omitted for "auto" so the model picks it.

    With `refs` the body targets `/images/edits`: refs ride as data-URI
    `images` entries (order preserved, so COMPOSE labels still pair up) and the
    prompt is wrapped in the intent's wording. PLAIN sends the prompt verbatim —
    there is no orchestrator LLM to instruct on this path.
    """
    text = prompt if intent is GenIntent.PLAIN else _client.ref_intent_text(
        prompt, intent, len(refs or []), labels, relation
    )
    body: dict = {"model": model, "prompt": text, "n": 1, "output_format": output_format}
    if refs:
        body["images"] = [{"image_url": f"data:{mime};base64,{b64}"} for (b64, mime) in refs]
    if size and size != "auto":
        body["size"] = size
    return body


def _meta(resp: dict, model: str, action: str) -> dict:
    """Map the Images API response onto the keys `output_report` reads.

    `usage` here IS the image cost (no orchestrator LLM on this path), so it
    lands in `image_usage`; absent fields stay absent rather than fabricated.
    """
    meta: dict = {"models": {"image": model}, "action": action}
    for key in ("quality", "size", "output_format", "background"):
        if resp.get(key):
            meta[key] = resp[key]
    if isinstance(resp.get("usage"), dict):
        meta["image_usage"] = resp["usage"]
    return meta


def generate_image_bytes(
    prompt: str,
    *,
    size: str,
    output_format: str,
    api_key: str,
    endpoint: str,
    model: str = DEFAULT_IMAGE_MODEL,
    total_timeout: float = _client.DEFAULT_TOTAL_TIMEOUT,
    progress: bool = False,
    refs: list[tuple[str, str]] | None = None,
    intent: GenIntent = GenIntent.PLAIN,
    labels: list[str] | None = None,
    relation: str | None = None,
) -> tuple[bytes, dict]:
    """Generate one image via the pool's Images API; return (bytes, metadata).

    `refs` (list of (base64, mime)) switches to `/images/edits`; `intent`,
    `labels` and `relation` frame the prompt exactly as on the Responses path.

    `endpoint` is the pool's responses URL (from `auth.pool_config`); 401/429
    are annotated with the pool via the same `_with_account` the Responses path
    uses, so a pool-wide quota error reads identically on both paths.
    """
    start = time.monotonic()
    url = images_url(endpoint, edits=bool(refs))
    payload = build_payload(
        prompt, size, output_format, model,
        refs=refs, intent=intent, labels=labels, relation=relation,
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    if progress:
        route = "images/edits" if refs else "images/generations"
        print(f"[{0.0:6.1f}s] generating ({model} via {route})", file=sys.stderr)
    try:
        with urllib.request.urlopen(req, timeout=total_timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        err = GatewayError(_client._http_failure(exc.code, body), status=exc.code)
        raise _client._with_account(err, {}, endpoint) from None
    except (TimeoutError, ConnectionError):
        elapsed = time.monotonic() - start
        raise GatewayError(f"images API timed out ({elapsed:.0f}s elapsed)") from None
    except urllib.error.URLError as exc:
        raise GatewayError(f"network error contacting the image pool: {exc.reason}") from None

    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        raise GatewayError(f"images API returned non-JSON: {raw[:200]}") from None
    items = data.get("data") if isinstance(data, dict) else None
    b64 = items[0].get("b64_json") if isinstance(items, list) and items and isinstance(items[0], dict) else None
    if not isinstance(b64, str):
        detail = _client._extract_failure(data) if isinstance(data, dict) else None
        raise GatewayError(f"no image returned ({detail or 'response had no data[0].b64_json'})")
    try:
        decoded = base64.b64decode(b64, validate=True)
    except Exception:  # noqa: BLE001
        raise GatewayError("images API returned invalid base64") from None
    return decoded, {**_meta(data, model, "edit" if intent is GenIntent.EDIT else "generate"), "elapsed_s": round(time.monotonic() - start, 1)}
