"""Provider lookup: map a name to a provider instance.

Keeps construction (and per-provider config like the parent model) in one place
so features/CLIs select a backend by name without importing concrete providers.
"""

from codex_imagegen.core.errors import InputError
from codex_imagegen.providers.generate.base import ImageProvider
from codex_imagegen.providers.generate.codex.provider import CodexImageProvider
from codex_imagegen.providers.vision.base import VisionProvider

_IMAGE_PROVIDERS = ("codex", "minimax")
_VISION_PROVIDERS = ("minimax",)


def get_image_provider(name: str = "codex", *, model: str | None = None) -> ImageProvider:
    """Return an image-generation provider by name. `model=None` uses that
    provider's own default. Raises InputError if the name is unknown."""
    if name == "codex":
        from codex_imagegen.providers.generate.codex.client import DEFAULT_MODEL

        return CodexImageProvider(model=model or DEFAULT_MODEL)
    if name == "minimax":
        from codex_imagegen.providers.generate.minimax.client import DEFAULT_MODEL as MINIMAX_MODEL
        from codex_imagegen.providers.generate.minimax.provider import MiniMaxImageProvider

        return MiniMaxImageProvider(model=model or MINIMAX_MODEL)
    raise InputError(
        f"unknown image provider {name!r}; expected one of: {', '.join(_IMAGE_PROVIDERS)}"
    )


def get_vision_provider(name: str) -> VisionProvider:
    """Return a vision provider by name. Raises InputError if unknown."""
    if name == "minimax":
        from codex_imagegen.providers.vision.minimax.provider import MiniMaxVisionProvider

        return MiniMaxVisionProvider()
    raise InputError(
        f"unknown vision provider {name!r}; expected one of: {', '.join(_VISION_PROVIDERS)}"
    )
