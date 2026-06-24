"""Project `.env` loader: parsing, precedence (real env wins), and safety."""

import os

import pytest

from codex_imagegen.core.env_file import load_dotenv


@pytest.fixture(autouse=True)
def _restore_environ():
    """Snapshot os.environ around each test — load_dotenv mutates it for real."""
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


def _write(tmp_path, body):
    p = tmp_path / ".env"
    p.write_text(body, encoding="utf-8")
    return p


def test_loads_simple_pairs(tmp_path, monkeypatch):
    monkeypatch.delenv("FOO_KEY", raising=False)
    env = _write(tmp_path, "FOO_KEY=bar\n")
    loaded = load_dotenv(env)
    assert loaded == ["FOO_KEY"] and os.environ["FOO_KEY"] == "bar"


def test_real_env_wins_and_is_not_in_loaded(tmp_path, monkeypatch):
    monkeypatch.setenv("EXISTING_KEY", "real")
    env = _write(tmp_path, "EXISTING_KEY=from-file\n")
    loaded = load_dotenv(env)
    assert os.environ["EXISTING_KEY"] == "real" and "EXISTING_KEY" not in loaded


def test_skips_comments_blanks_and_malformed(tmp_path, monkeypatch):
    for k in ("A_KEY", "B_KEY", "BAD"):
        monkeypatch.delenv(k, raising=False)
    env = _write(tmp_path, "# comment\n\n   \nA_KEY=1\nno_equals_line\nBAD KEY=2\nB_KEY=2\n")
    loaded = load_dotenv(env)
    assert set(loaded) == {"A_KEY", "B_KEY"}  # malformed/space-key lines skipped


def test_strips_quotes_and_export_prefix(tmp_path, monkeypatch):
    for k in ("Q1", "Q2", "EXP"):
        monkeypatch.delenv(k, raising=False)
    env = _write(tmp_path, 'Q1="double quoted"\nQ2=\'single\'\nexport EXP=value\n')
    load_dotenv(env)
    assert os.environ["Q1"] == "double quoted"
    assert os.environ["Q2"] == "single"
    assert os.environ["EXP"] == "value"


def test_missing_file_is_noop(tmp_path):
    assert load_dotenv(tmp_path / "does-not-exist.env") == []


def test_default_path_reads_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("CWD_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "CWD_KEY=here\n")
    loaded = load_dotenv()  # no path -> cwd/.env
    assert loaded == ["CWD_KEY"] and os.environ["CWD_KEY"] == "here"


def test_utf8_bom_does_not_drop_first_key(tmp_path, monkeypatch):
    monkeypatch.delenv("BOM_KEY", raising=False)
    # write_text with utf-8-sig prepends a BOM, as some editors do on save
    p = tmp_path / ".env"
    p.write_text("BOM_KEY=value\n", encoding="utf-8-sig")
    loaded = load_dotenv(p)
    assert loaded == ["BOM_KEY"] and os.environ["BOM_KEY"] == "value"


def test_empty_value_allowed(tmp_path, monkeypatch):
    monkeypatch.delenv("EMPTY_KEY", raising=False)
    env = _write(tmp_path, "EMPTY_KEY=\n")
    load_dotenv(env)
    assert os.environ["EMPTY_KEY"] == ""
