"""Tests for the Playbook entity + catalog (strader/entities/playbook.py)."""

from __future__ import annotations

import pytest

from strader.entities.playbook import (
    CONDITIONS_PATH,
    PLAYBOOKS_DIR,
    Playbook,
    PlaybookCatalog,
    PlaybookError,
    Vocabulary,
)


@pytest.fixture(scope="module")
def vocab() -> Vocabulary:
    return Vocabulary.load(CONDITIONS_PATH)


# ─── vocabulary ──────────────────────────────────────────────────────────────

def test_vocabulary_has_expected_tags(vocab):
    assert "trend-up" in vocab.day_context
    assert "range-chop" in vocab.day_context
    assert "orderflow-confirm" in vocab.entry_confirmation
    # weighted confluence outranks a plain tag
    assert vocab.weight("mancini-carmine-confluence") == 2.0
    assert vocab.weight("trend-up") == 1.0


# ─── the seed playbook ───────────────────────────────────────────────────────

def test_momentum_breakout_loads(vocab):
    pb = Playbook.load(PLAYBOOKS_DIR / "momentum-breakout.md", vocab)
    assert pb.code == "MB"
    assert pb.name == "Momentum Breakout"
    assert pb.source == "InvestiTrade"
    assert pb.status == "worthy"
    assert pb.is_worthy
    assert "SPX" in pb.instruments
    assert "trend-up" in pb.favored_conditions
    assert "range-chop" in pb.avoid_conditions
    assert pb.adopted.isoformat() == "2026-07-02"
    assert "## Thesis" in pb.body
    assert "## Management checklist" in pb.body


# ─── validation (via temp fixtures) ──────────────────────────────────────────

def _write_playbook(
    tmp_path,
    *,
    favored="[trend-up]",
    avoid="[range-chop]",
    status="candidate",
    drop=None,
):
    fields = {
        "code": "TT",
        "name": "Temp",
        "status": status,
        "source": "own",
        "instruments": "[ES]",
        "favored_conditions": favored,
        "avoid_conditions": avoid,
        "indicators": "[vwap]",
        "rationale": '"placeholder"',
        "adopted": "2026-07-02",
        "updated": "2026-07-02",
    }
    if drop:
        fields.pop(drop)
    frontmatter = "\n".join(f"{k}: {v}" for k, v in fields.items())
    path = tmp_path / "temp.md"
    path.write_text(f"---\n{frontmatter}\n---\n## Thesis\nbody\n")
    return path


def test_unknown_tag_is_load_error(tmp_path, vocab):
    path = _write_playbook(tmp_path, favored="[not-a-real-tag]")
    with pytest.raises(PlaybookError) as exc:
        Playbook.load(path, vocab)
    assert "not-a-real-tag" in str(exc.value)


def test_missing_field_is_load_error(tmp_path, vocab):
    path = _write_playbook(tmp_path, drop="rationale")
    with pytest.raises(PlaybookError) as exc:
        Playbook.load(path, vocab)
    assert "rationale" in str(exc.value)


def test_favored_avoid_overlap_rejected(tmp_path, vocab):
    path = _write_playbook(tmp_path, favored="[trend-up]", avoid="[trend-up]")
    with pytest.raises(PlaybookError):
        Playbook.load(path, vocab)


def test_bad_status_rejected(tmp_path, vocab):
    path = _write_playbook(tmp_path, status="brilliant")
    with pytest.raises(PlaybookError):
        Playbook.load(path, vocab)


def test_missing_frontmatter_fence_rejected(tmp_path, vocab):
    path = tmp_path / "nofence.md"
    path.write_text("## Thesis\nno frontmatter here\n")
    with pytest.raises(PlaybookError):
        Playbook.load(path, vocab)


# ─── the catalog ─────────────────────────────────────────────────────────────

def test_catalog_loads_and_filters():
    catalog = PlaybookCatalog()
    assert len(catalog) >= 1
    mb = catalog.by_code("MB")
    assert mb.name == "Momentum Breakout"
    assert mb in catalog.by_instrument("SPX")
    # the catalog mixes curated-worthy records with Steve's own candidates
    # (st-1g3: SGL/LDF enter as candidate until Steve validates them)
    assert mb in catalog.worthy()
    assert set(catalog.worthy()) == {pb for pb in catalog if pb.status in ("worthy", "active")}
    assert len(catalog.worthy()) >= 6  # the six InvestiTrade records stay eligible
    assert {"SGL", "LDF"} <= {pb.code for pb in catalog}


def test_catalog_integrity_all_tags_known():
    """Every favored/avoid tag on every playbook must exist in the vocabulary."""
    catalog = PlaybookCatalog()
    for pb in catalog:
        for tag in (*pb.favored_conditions, *pb.avoid_conditions):
            assert tag in catalog.vocab.day_context, f"{pb.code}: unknown tag {tag!r}"
