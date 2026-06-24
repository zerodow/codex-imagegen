"""Provider registry: name lookup + unknown-name error."""

import pytest

from codex_imagegen.core.errors import InputError
from codex_imagegen.providers import registry


def test_returns_codex_provider():
    p = registry.get_image_provider("codex")
    assert p.name == "codex"


def test_default_is_codex():
    assert registry.get_image_provider().name == "codex"


def test_model_override_is_applied():
    p = registry.get_image_provider("codex", model="custom-model")
    assert p._model == "custom-model"


def test_returns_minimax_image_provider_with_default_model():
    p = registry.get_image_provider("minimax")
    assert p.name == "minimax" and p._model == "image-01"  # provider default when model=None


def test_codex_default_model_when_none():
    assert registry.get_image_provider("codex")._model == "gpt-5.5"


def test_unknown_provider_raises_input_error():
    with pytest.raises(InputError):
        registry.get_image_provider("does-not-exist")


def test_returns_minimax_vision_provider():
    assert registry.get_vision_provider("minimax").name == "minimax"


def test_unknown_vision_provider_raises_input_error():
    with pytest.raises(InputError):
        registry.get_vision_provider("does-not-exist")
