"""Commentary store tests. [co-7lyf]"""
from runbook.mancini.schema import Commentary, Trigger
from runbook.mancini import store


def _item(text: str, anchors) -> Commentary:
    return Commentary(
        text=text,
        trigger=Trigger(type="price_zone", anchor_prices=anchors, condition_text=text),
        tags=["mancini"],
        source_quote=text,
    )


def test_append_and_load_roundtrip(tmp_path):
    items = [_item("hold 5800 -> 5840", [5800, 5840]), _item("lose 5785 -> 5760", [5785, 5760])]
    path = store.append(items, "2026-06-29", instrument="ES",
                        ingested_at="2026-06-29T18:00:00Z", store_root=tmp_path)
    assert path.exists()

    records = store.load("2026-06-29", store_root=tmp_path)
    assert len(records) == 2
    assert records[0]["date"] == "2026-06-29"
    assert records[0]["instrument"] == "ES"
    assert records[0]["trigger"]["anchor_prices"] == [5800, 5840]
    assert records[0]["ingested_at"] == "2026-06-29T18:00:00Z"


def test_append_is_additive(tmp_path):
    store.append([_item("a", [1])], "2026-06-29", store_root=tmp_path)
    store.append([_item("b", [2])], "2026-06-29", store_root=tmp_path)
    records = store.load("2026-06-29", store_root=tmp_path)
    assert [r["text"] for r in records] == ["a", "b"]


def test_load_missing_day_returns_empty(tmp_path):
    assert store.load("2020-01-01", store_root=tmp_path) == []


def test_append_empty_is_noop_but_safe(tmp_path):
    path = store.append([], "2026-06-29", store_root=tmp_path)
    # No file content required; load should be empty either way.
    assert store.load("2026-06-29", store_root=tmp_path) == []
    assert path.name == "2026-06-29.jsonl"


def test_reappending_the_same_items_is_idempotent(tmp_path):
    """A re-parse of a day the store already holds must not double it. [st-psoj]

    This is the real defect shape: /mancini-parse run twice for one plan-day.
    Three days in the live store were doubled and one tripled before the blind
    append was noticed, because parsed/<day>.json replaced correctly and only
    the store drifted.
    """
    items = [_item("a", [1]), _item("b", [2])]
    store.append(items, "2026-06-29", store_root=tmp_path)
    store.append(items, "2026-06-29", store_root=tmp_path)
    records = store.load("2026-06-29", store_root=tmp_path)
    assert [r["text"] for r in records] == ["a", "b"]


def test_a_fresh_ingested_at_does_not_defeat_the_dedupe(tmp_path):
    """Identity is (text, trigger) — never the envelope.

    A re-parse always stamps a new ingested_at. Were that part of identity,
    every item would look new and the dedupe would be decorative.
    """
    items = [_item("a", [1])]
    store.append(items, "2026-06-29", ingested_at="2026-06-29T08:00:00Z",
                 store_root=tmp_path)
    store.append(items, "2026-06-29", ingested_at="2026-06-29T09:30:00Z",
                 store_root=tmp_path)
    records = store.load("2026-06-29", store_root=tmp_path)
    assert len(records) == 1
    assert records[0]["ingested_at"] == "2026-06-29T08:00:00Z"


def test_same_text_different_trigger_is_a_different_note(tmp_path):
    """Dedupe must not swallow a genuinely distinct note. Text alone is not
    identity: the same sentence anchored on different prices is a real second
    note, and collapsing the two would lose plan content."""
    store.append([_item("a", [1])], "2026-06-29", store_root=tmp_path)
    store.append([_item("a", [2])], "2026-06-29", store_root=tmp_path)
    assert len(store.load("2026-06-29", store_root=tmp_path)) == 2


def test_a_changed_field_updates_the_note_in_place(tmp_path):
    """Identity says it is the same note; the newest parse says what it holds.

    Closing the tag vocabulary re-tagged notes already in the store [st-9r51].
    Under skip-if-present the store kept the old spellings while the parse file
    held the canonical ones — the same divergence the dedupe was added to stop.
    """
    first = _item("a", [1]); first.tags = ["bull-case"]
    store.append([first], "2026-06-29", ingested_at="T1", store_root=tmp_path)
    second = _item("a", [1]); second.tags = ["bull_case", "long_entry"]
    store.append([second], "2026-06-29", ingested_at="T2", store_root=tmp_path)
    records = store.load("2026-06-29", store_root=tmp_path)
    assert len(records) == 1, "an update must not append a near-duplicate"
    assert records[0]["tags"] == ["bull_case", "long_entry"]


def test_an_update_keeps_the_original_ingested_at(tmp_path):
    """When the note entered the store is not the re-parse's to rewrite."""
    first = _item("a", [1]); first.tags = ["bull-case"]
    store.append([first], "2026-06-29", ingested_at="T1", store_root=tmp_path)
    second = _item("a", [1]); second.tags = ["bull_case"]
    store.append([second], "2026-06-29", ingested_at="T2", store_root=tmp_path)
    assert store.load("2026-06-29", store_root=tmp_path)[0]["ingested_at"] == "T1"


def test_an_update_preserves_the_other_notes_and_their_order(tmp_path):
    items = [_item("a", [1]), _item("b", [2]), _item("c", [3])]
    store.append(items, "2026-06-29", ingested_at="T1", store_root=tmp_path)
    changed = _item("b", [2]); changed.tags = ["risk"]
    store.append([changed], "2026-06-29", ingested_at="T2", store_root=tmp_path)
    records = store.load("2026-06-29", store_root=tmp_path)
    assert [r["text"] for r in records] == ["a", "b", "c"]
    assert records[1]["tags"] == ["risk"]
