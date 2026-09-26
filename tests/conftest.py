"""Shared test setup: keep the pool credentials out of every test's environment.

The CLI entry points call `env_file.load_dotenv()`, so a developer with a real
`.env` (or an exported `CODEX_IMAGEGEN_*` pair) would otherwise silently flip
the Codex provider into pool mode mid-suite and fail unrelated tests. Tests that
want pool mode set the vars themselves.
"""

import pytest

from codex_imagegen.providers.generate.codex import auth


@pytest.fixture(autouse=True)
def _no_pool_env(monkeypatch):
    monkeypatch.delenv(auth.POOL_URL_ENV, raising=False)
    monkeypatch.delenv(auth.POOL_KEY_ENV, raising=False)
