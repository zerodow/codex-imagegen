"""Codex / gpt-image-2 image provider (ChatGPT subscription, no API key).

Wraps the codex/responses client behind the `ImageProvider` contract. The
provider instance holds the loaded auth dict and reuses it across calls, so a
token refreshed mid-batch (in place, on HTTP 401) carries forward to later
images instead of being re-loaded each time.

Two credential paths, chosen per call by `auth.pool_config()`: the personal
ChatGPT login in `auth.json` (default), or an account-pool proxy fronting many
accounts behind one bearer key. Capabilities are identical either way. Pool
mode does NOT use the Responses wire format: every intent goes through the
pool's Images API (`images_api`: PLAIN -> `/images/generations`, refs ->
`/images/edits`), because the Responses image tool fails backend-side there.
"""

from . import auth, client, images_api
from codex_imagegen.providers.generate.base import GenCapabilities, GenIntent

# gpt-image-2 composites multiple distinct subjects natively; the count cap is a
# conservative semantic ceiling (quality degrades with too many subjects) and is
# enforced alongside the byte budget in image_loader.
_CODEX_CAPABILITIES = GenCapabilities(
    max_refs=4,
    multi_subject=True,
    intents=frozenset(
        {GenIntent.PLAIN, GenIntent.CONSISTENCY, GenIntent.COMPOSE, GenIntent.EDIT}
    ),
    metered="subscription-quota",
)


class CodexImageProvider:
    """ImageProvider backed by the Codex Responses backend."""

    name = "codex"
    capabilities = _CODEX_CAPABILITIES

    def __init__(self, model: str = client.DEFAULT_MODEL) -> None:
        self._model = model
        self._auth: dict | None = None  # lazy; reused across calls in a batch

    def generate(
        self,
        prompt: str,
        *,
        refs: list[tuple[str, str]] | None = None,
        intent: GenIntent = GenIntent.PLAIN,
        size: str = "1024x1024",
        fmt: str = "png",
        total_timeout: float,
        stall_timeout: float,
        progress: bool = False,
        labels: list[str] | None = None,
        relation: str | None = None,
    ) -> tuple[bytes, dict]:
        pool = auth.pool_config()
        if pool is not None:
            # Pool mode: one opaque bearer key, no auth.json to read and no
            # refresh_token (the proxy refreshes each pooled account itself), so
            # nothing is cached on the instance — the proxy picks the account.
            # Images API for every intent (see images_api docstring for why).
            endpoint, access = pool
            return images_api.generate_image_bytes(
                prompt,
                size=size,
                output_format=fmt,
                api_key=access,
                endpoint=endpoint,
                total_timeout=total_timeout,
                progress=progress,
                refs=refs,
                intent=intent,
                labels=labels,
                relation=relation,
            )
        if self._auth is None:
            self._auth = auth.load_auth()
        auth_store = self._auth
        access, account_id, refresh = auth.extract_tokens(auth_store)
        return client.generate_image_bytes(
            prompt,
            size=size,
            output_format=fmt,
            access_token=access,
            account_id=account_id,
            refresh_token=refresh,
            auth=auth_store,
            endpoint=None,  # direct mode: OpenAI backend; pools use images_api
            model=self._model,
            total_timeout=total_timeout,
            stall_timeout=stall_timeout,
            progress=progress,
            refs=refs,
            intent=intent,
            labels=labels,
            relation=relation,
        )
