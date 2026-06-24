"""HTTP client for MiniMax multimodal chat (vision), stdlib-only (urllib).

Talks to MiniMax's OpenAI-compatible chat completions with an image content part
(text + image_url data-URI), non-streaming. Returns the assistant text. The exact
endpoint/model id are isolated here — confirm against platform.minimax.io when a
key is available; everything else (provider, feature) is independent of them.

Vision uses the MiniMax **token plan** key (`MINIMAX_API_KEY`), NOT the separate
pay-as-you-go image-generation key.
"""

import json
import os
import urllib.error
import urllib.request

from codex_imagegen.core.errors import AuthError, GatewayError

API_KEY_ENV = "MINIMAX_API_KEY"
CHAT_ENDPOINT = "https://api.minimax.io/v1/chat/completions"
DEFAULT_MODEL = "MiniMax-M3"  # natively multimodal (text + image input)
DEFAULT_TIMEOUT = 60


def resolve_api_key() -> str:
    """Read the MiniMax token-plan key from the environment, or raise AuthError."""
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise AuthError(
            f"{API_KEY_ENV} is not set. Export your MiniMax token-plan key to use "
            "the vision step (this is the token-plan key, not the image PAYG key)."
        )
    return key


def chat_with_image(
    api_key: str,
    *,
    system: str,
    user_text: str,
    image_b64: str,
    mime: str,
    model: str = DEFAULT_MODEL,
    json_object: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Send one vision turn (text + image) and return the assistant's text content.

    `json_object=True` sets `response_format` best-effort (not all models honor it);
    callers must still parse defensively. Non-streaming (response_format ⊥ stream).
    """
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
            ],
        },
    ]
    body: dict = {"model": model, "messages": messages, "stream": False}
    if json_object:
        body["response_format"] = {"type": "json_object"}

    req = urllib.request.Request(
        CHAT_ENDPOINT,
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
        raise GatewayError(f"MiniMax vision HTTP {exc.code}: {detail}", status=exc.code) from None
    except urllib.error.URLError as exc:
        raise GatewayError(f"MiniMax vision network error: {exc.reason}") from None

    try:
        data = json.loads(raw)
        return data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise GatewayError(f"MiniMax vision returned an unexpected response shape: {exc}") from None
