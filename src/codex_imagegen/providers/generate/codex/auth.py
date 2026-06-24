"""Read and refresh the ChatGPT OAuth credentials Codex stores in auth.json.

The Codex subscription path authenticates with the OAuth *access_token* under
`tokens` (NOT the `OPENAI_API_KEY` field — that is an API key the codex/responses
backend rejects). When the access token is expired the backend returns 401; we
refresh via the published Codex client id and persist the new tokens atomically.
"""

import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from codex_imagegen.core.errors import AuthError, GatewayError

AUTH_PATH = Path.home() / ".codex" / "auth.json"
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"  # Codex CLI's published client id
_REFRESH_UA = "codex_cli_rs (Mac OS; arm64) codex-imagegen"


def load_auth() -> dict:
    """Load and parse ~/.codex/auth.json, or raise AuthError."""
    if not AUTH_PATH.exists():
        raise AuthError(f"{AUTH_PATH} not found. Run `codex login` first.")
    try:
        data = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surface a clean message
        raise AuthError(f"failed to read {AUTH_PATH}: {exc}") from None
    if not isinstance(data, dict):
        raise AuthError(f"{AUTH_PATH} is malformed (expected a JSON object).")
    return data


def extract_tokens(auth: dict) -> tuple[str, str | None, str | None]:
    """Return (access_token, account_id, refresh_token) from a loaded auth dict.

    Raises AuthError when no usable OAuth access token is present (e.g. the
    machine is authenticated with an API key only, which this path cannot use).
    """
    tokens = auth.get("tokens") if isinstance(auth.get("tokens"), dict) else {}
    access = tokens.get("access_token")
    if not isinstance(access, str) or not access:
        raise AuthError(
            "no ChatGPT OAuth access_token in auth.json. "
            "Run `codex login` (sign in with your ChatGPT account, not an API key)."
        )
    account_id = tokens.get("account_id")
    refresh = tokens.get("refresh_token")
    return (
        access,
        account_id if isinstance(account_id, str) else None,
        refresh if isinstance(refresh, str) else None,
    )


def refresh_and_persist(auth: dict, refresh_token: str, *, timeout: int = 30) -> str:
    """Exchange the refresh token for a fresh access token and persist it.

    Returns the new access token. Raises AuthError on invalid_grant (user must
    re-run `codex login`) or GatewayError on other HTTP failures.
    """
    data = urllib.parse.urlencode(
        {
            "client_id": OAUTH_CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "openid profile email",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        OAUTH_TOKEN_URL,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": _REFRESH_UA,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_body = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        oauth_err = ""
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict) and isinstance(parsed.get("error"), str):
                oauth_err = parsed["error"]
        except Exception:  # noqa: BLE001
            pass
        if oauth_err == "invalid_grant":
            raise AuthError("refresh_token is no longer valid — run `codex login` again.") from None
        msg = f"token refresh failed: HTTP {exc.code}" + (f" ({oauth_err})" if oauth_err else "")
        raise GatewayError(msg, status=exc.code) from None
    except urllib.error.URLError as exc:
        raise GatewayError(f"network error during token refresh: {exc.reason}") from None

    try:
        refreshed = json.loads(raw_body)
    except (ValueError, json.JSONDecodeError):
        raise GatewayError("token refresh returned a non-JSON response.") from None
    if not isinstance(refreshed, dict):
        raise GatewayError("token refresh returned an unexpected response shape.")

    new_access = refreshed.get("access_token")
    if not isinstance(new_access, str) or not new_access:
        raise GatewayError("token refresh returned no access_token.")

    tokens = auth.get("tokens")
    if not isinstance(tokens, dict):
        tokens = {}
        auth["tokens"] = tokens
    for key in ("access_token", "refresh_token", "id_token"):
        if isinstance(refreshed.get(key), str):
            tokens[key] = refreshed[key]
    auth["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _atomic_write_json(AUTH_PATH, auth)
    return new_access


def _atomic_write_json(path: Path, obj: dict) -> None:
    """Write JSON to `path` atomically with 0600 perms (temp + fsync + replace)."""
    serialized = json.dumps(obj, indent=2).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".auth.", suffix=".tmp", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        raise
