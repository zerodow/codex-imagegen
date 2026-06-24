"""Codex / gpt-image-2 image provider (ChatGPT subscription, no API key).

Wraps the codex/responses client behind the `ImageProvider` contract. The
provider instance holds the loaded auth dict and reuses it across calls, so a
token refreshed mid-batch (in place, on HTTP 401) carries forward to later
images instead of being re-loaded each time.
"""

from . import auth, client
from codex_imagegen.providers.generate.base import GenCapabilities, GenIntent

# gpt-image-2 composites multiple distinct subjects natively; the count cap is a
# conservative semantic ceiling (quality degrades with too many subjects) and is
# enforced alongside the byte budget in image_loader.
_CODEX_CAPABILITIES = GenCapabilities(
    max_refs=4,
    multi_subject=True,
    intents=frozenset({GenIntent.PLAIN, GenIntent.CONSISTENCY, GenIntent.COMPOSE}),
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
        if self._auth is None:
            self._auth = auth.load_auth()
        access, account_id, refresh = auth.extract_tokens(self._auth)
        return client.generate_image_bytes(
            prompt,
            size=size,
            output_format=fmt,
            access_token=access,
            account_id=account_id,
            refresh_token=refresh,
            auth=self._auth,
            model=self._model,
            total_timeout=total_timeout,
            stall_timeout=stall_timeout,
            progress=progress,
            refs=refs,
            intent=intent,
            labels=labels,
            relation=relation,
        )
