"""Read and refresh the ChatGPT OAuth credentials Codex stores in auth.json.

The Codex subscription path authenticates with the OAuth *access_token* under
`tokens` (NOT the `OPENAI_API_KEY` field — that is an API key the codex/responses
backend rejects). When the access token is expired the backend returns 401; we
refresh via the published Codex client id and persist the new tokens atomically.

An account-POOL proxy is the second credential path (see `pool_config`): one
opaque bearer key in front of many ChatGPT accounts, with no auth.json and no
refresh token, because the proxy owns rotation and per-account refresh.
"""

import base64
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from codex_imagegen.core.errors import AuthError, GatewayError


def _codex_home() -> Path:
    """Resolve the Codex home directory the way the Codex CLI does.

    `CODEX_HOME` wins when set and non-empty — Orca points it at a per-account
    home, so `codex login` inside Orca writes credentials there, not to
    `~/.codex`. Reading only `~/.codex` silently authenticates as a different
    (possibly stale) account, or fails with "auth.json not found".
    """
    override = (os.environ.get("CODEX_HOME") or "").strip()
    return Path(override).expanduser() if override else Path.home() / ".codex"


AUTH_PATH = _codex_home() / "auth.json"
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"  # Codex CLI's published client id
_REFRESH_UA = "codex_cli_rs (Mac OS; arm64) codex-imagegen"

POOL_URL_ENV = "CODEX_IMAGEGEN_BASE_URL"
POOL_KEY_ENV = "CODEX_IMAGEGEN_API_KEY"


def pool_config() -> tuple[str, str] | None:
    """Return (responses_url, api_key) when an account-pool proxy is configured.

    A pool (CLIProxyAPI and friends) fronts many ChatGPT accounts behind ONE
    opaque bearer key: there is no auth.json, no refresh_token and no
    account_id, because the proxy owns rotation and per-account token refresh.
    Returns None when unconfigured, which keeps the personal OAuth path the
    default. Read lazily (never at import) so the CLIs' `.env` load still counts.

    Both vars are required together: honouring a half-configured pair would
    silently fall back to the personal `auth.json` and bill the wrong account's
    quota -- exactly the confusion `describe_account` exists to prevent.
    """
    url = (os.environ.get(POOL_URL_ENV) or "").strip()
    key = (os.environ.get(POOL_KEY_ENV) or "").strip()
    if not url and not key:
        return None
    if not url or not key:
        present, missing = (POOL_KEY_ENV, POOL_URL_ENV) if key else (POOL_URL_ENV, POOL_KEY_ENV)
        raise AuthError(
            f"{present} is set but {missing} is not. Set both to render through an "
            f"account pool, or unset both to use your own ChatGPT login."
        )
    return _responses_url(url), key


def _responses_url(base: str) -> str:
    """Normalize a pool base URL to its `responses` endpoint.

    Accepts the three spellings people paste: the host root, `.../v1`, or the
    full `.../v1/responses`. The scheme is checked because urllib would
    otherwise happily open a `file://` "endpoint".
    """
    url = base.rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise AuthError(f"{POOL_URL_ENV} must start with http:// or https:// (got {base!r}).")
    if url.endswith("/responses"):
        return url
    if url.endswith("/v1"):
        return f"{url}/responses"
    return f"{url}/v1/responses"


def load_auth() -> dict:
    """Load and parse the Codex `auth.json`, or raise AuthError."""
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


def _jwt_claims(token: str) -> dict:
    """Decode a JWT payload WITHOUT verifying it. Diagnostics only, never access."""
    try:
        segment = token.split(".")[1]
        segment += "=" * (-len(segment) % 4)
        claims = json.loads(base64.urlsafe_b64decode(segment))
    except Exception:  # noqa: BLE001 - an unreadable token just means a vaguer message
        return {}
    return claims if isinstance(claims, dict) else {}


def describe_account(auth: dict) -> str:
    """Return "who am I": which ChatGPT account/plan, from which auth.json.

    A 401/429 is about WHICH account the request used, and that is picked by
    `$CODEX_HOME` rather than by any CLI flag — so the raw status alone sends
    the user hunting in the wrong account. Falls back to the account id, then
    to the path alone, when the token is not a readable JWT.
    """
    tokens = auth.get("tokens") if isinstance(auth.get("tokens"), dict) else {}
    claims = _jwt_claims(tokens.get("access_token") or "")
    api_auth = claims.get("https://api.openai.com/auth")
    plan = api_auth.get("chatgpt_plan_type") if isinstance(api_auth, dict) else None
    # The email sits under the profile claim; only some tokens also mirror it
    # top-level, so check both before falling back to the opaque account id.
    profile = claims.get("https://api.openai.com/profile")
    email = claims.get("email") or (profile.get("email") if isinstance(profile, dict) else None)
    who = email or tokens.get("account_id") or "unknown account"
    return f"{who}{f', plan {plan}' if plan else ''} (from {AUTH_PATH})"


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
