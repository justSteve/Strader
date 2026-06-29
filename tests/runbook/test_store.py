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
