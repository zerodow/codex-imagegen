"""HTTP client for MiniMax Image-01 text-to-image, stdlib-only (urllib).

Supports a single subject reference (one human face) for consistency. Uses the
**pay-as-you-go image key** (`MINIMAX_IMAGE_API_KEY`) — a DIFFERENT key/meter from
the vision token-plan key (`MINIMAX_API_KEY`). Endpoint, model id, and the base64
response shape are isolated here; confirm against platform.minimax.io when a key
is available (tests mock the HTTP).
"""

import base64
import json
import os
import urllib.error
import urllib.request

from codex_imagegen.core.errors import AuthError, GatewayError

API_KEY_ENV = "MINIMAX_IMAGE_API_KEY"
IMAGE_ENDPOINT = "https://api.minimax.io/v1/image_generation"
DEFAULT_MODEL = "image-01"
DEFAULT_TIMEOUT = 120


def resolve_api_key() -> str:
    """Read the MiniMax pay-as-you-go image key, or raise AuthError.

    Distinct from the vision token-plan key — image generation bills per image on a
    separate balance, so it uses its own env var.
    """
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise AuthError(
            f"{API_KEY_ENV} is not set. Export your MiniMax pay-as-you-go image key "
            "(separate from the MINIMAX_API_KEY token-plan key used for vision)."
        )
    return key


def _parse_size(size: str | None) -> tuple[int, int] | None:
    """Turn a 'WxH' hint into (width, height); 'auto'/unknown -> None (model decides)."""
    if not size or size == "auto" or "x" not in size:
        return None
    w, h = size.split("x", 1)
    if w.isdigit() and h.isdigit():
        return int(w), int(h)
    return None


def generate_image(
    api_key: str,
    *,
    prompt: str,
    size: str = "1024x1024",
    ref: tuple[str, str] | None = None,
    model: str = DEFAULT_MODEL,
    timeout: float = DEFAULT_TIMEOUT,
) -> bytes:
    """Generate one image and return its bytes. `ref` is an optional (base64, mime)
    single subject reference for character consistency."""
    body: dict = {"model": model, "prompt": prompt, "response_format": "base64", "n": 1}
    wh = _parse_size(size)
    if wh:
        body["width"], body["height"] = wh
    if ref:
        b64, mime = ref
        body["subject_reference"] = [
            {"type": "character", "image_file": f"data:{mime};base64,{b64}"}
        ]

    req = urllib.request.Request(
        IMAGE_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:200]
        raise GatewayError(f"MiniMax image HTTP {exc.code}: {detail}", status=exc.code) from None
    except urllib.error.URLError as exc:
        raise GatewayError(f"MiniMax image network error: {exc.reason}") from None

    return _decode_image(raw)


def _decode_image(raw: str) -> bytes:
    """Extract + decode the first base64 image from the response, or GatewayError."""
    try:
        data = json.loads(raw)
    except ValueError:
        raise GatewayError("MiniMax image returned a non-JSON response") from None
    payload = data.get("data") if isinstance(data, dict) else None
    images = payload.get("image_base64") if isinstance(payload, dict) else None
    if not (isinstance(images, list) and images and isinstance(images[0], str)):
        raise GatewayError("MiniMax image response had no base64 image data")
    try:
        return base64.b64decode(images[0], validate=True)  # binascii.Error subclasses ValueError
    except ValueError:
        raise GatewayError("MiniMax image returned undecodable base64") from None
