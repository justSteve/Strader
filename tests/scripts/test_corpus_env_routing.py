"""The live-feed corpus scripts must route DATABENTO_API_KEY through the shared
fail-fast loader (strader.settings.load_databento), not an ad-hoc .env parse.

Regression guard for st-cir: the three corpus scripts used to hydrate the key
with an inline `os.environ.setdefault(...)` parse — the polluted-env-wins
pattern that produced the 2026-06-30 invalid_client incident (a stale/malformed
process value silently beat the clean .env). The loader's override + fail-fast
semantics are covered by strader/tests/test_settings.py; here we prove each
script actually *delegates* to it, so nobody reintroduces a private parser.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS_SCRIPTS = [
    "corpus_pull_databento.py",
    "corpus_pull_databento_es.py",
    "corpus_stream_databento.py",
]


def _load_script(name: str):
    """Import a bare script (no package) from scripts/ as a throwaway module.

    Registered in sys.modules before exec so module-level @dataclass fields
    (e.g. corpus_stream_databento.StreamSpec) resolve their annotations — the
    dataclasses machinery looks the defining module up by name.
    """
    path = REPO_ROOT / "scripts" / name
    mod_name = f"_routing_{name[:-3]}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    return mod


@pytest.mark.parametrize("script", CORPUS_SCRIPTS)
def test_load_env_delegates_to_shared_loader(script, monkeypatch):
    import strader.settings as settings

    calls: list[tuple] = []

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))
        return {"DATABENTO_API_KEY": "db-test-key"}

    # Each script does a lazy `from strader.settings import load_databento`
    # inside _load_env, so patching the module attribute is picked up at call time.
    monkeypatch.setattr(settings, "load_databento", _spy)

    mod = _load_script(script)
    assert hasattr(mod, "_load_env"), f"{script} lost its _load_env entry point"
    mod._load_env()

    assert calls == [((), {})], (
        f"{script}._load_env did not delegate to load_databento() exactly once "
        f"with no args (calls={calls}) — it may have reintroduced a private "
        f".env parser"
    )
