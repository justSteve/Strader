"""Every GexBot reader must take its key through strader.settings.load_gexbot.

Sibling of test_corpus_env_routing.py (st-cir). Until 2026-09-05 five files
parsed the repo .env by hand for ``GEXBOT_API_KEY=`` — market/ingest/gexbot.py,
market/corpus/gexbot_stream.py and three scripts. When the value moved to the
vault (credential estate convention 2026-08-25, co-4q6cg) each was routed
through the shared fail-fast loader, which is the only code that knows where
secrets live. These tests keep a private parser from coming back.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import market.corpus.gexbot_stream as gexbot_stream
import market.ingest.gexbot as gexbot

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# The hand-parse signature: a string test for the key's name followed by '='.
PRIVATE_PARSE = re.compile(r"""GEXBOT_API_KEY=['"]?\)|startswith\(\s*['"]GEXBOT_API_KEY=""")


def _py_files(*roots: str):
    for root in roots:
        for p in (REPO_ROOT / root).rglob("*.py"):
            if "tests" in p.parts or ".venv" in p.parts:
                continue
            yield p


def test_ingest_load_api_key_delegates_to_the_loader(monkeypatch, tmp_path):
    seen = {}

    def fake(env_path):
        seen["env_path"] = env_path
        return {"GEXBOT_API_KEY": "gexbot_custom_test"}

    monkeypatch.setattr(gexbot, "load_gexbot", fake)
    assert gexbot.load_api_key(tmp_path / ".env") == "gexbot_custom_test"
    assert seen["env_path"] == tmp_path / ".env"


def test_stream_load_api_key_delegates_to_the_loader(monkeypatch):
    import strader.settings as settings

    monkeypatch.setattr(settings, "load_gexbot", lambda env_path=None: {"GEXBOT_API_KEY": "k"})
    assert gexbot_stream._load_api_key() == "k"


def test_ingest_load_api_key_refuses_a_key_in_the_tree(tmp_path):
    """A GEXBOT_API_KEY sitting in .env is a ConfigError, not a working key."""
    from strader.config import ConfigError

    env = tmp_path / ".env"
    env.write_text("GEXBOT_API_KEY=abc\n")
    with pytest.raises(ConfigError) as ei:
        gexbot.load_api_key(env)
    assert "secret value found in .env" in str(ei.value)


@pytest.mark.parametrize("path", sorted(_py_files("market", "scripts", "strader", "broker_schwab")),
                         ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_private_gexbot_env_parser(path: Path):
    text = path.read_text(errors="replace")
    hits = [ln for ln in text.splitlines() if PRIVATE_PARSE.search(ln)]
    assert not hits, f"{path.relative_to(REPO_ROOT)} parses GEXBOT_API_KEY by hand: {hits[:2]}"
