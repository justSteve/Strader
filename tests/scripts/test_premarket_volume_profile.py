"""Premarket anchored VP page — rendering and the last-good contract. [st-eo0]

No Schwab here: fetch_bars is the only live-API surface and it is stubbed, so
the whole render/publish path is exercised under the API gate.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from market.orderflow.anchored_profile import (
    CENTRAL, anchor_utc, build_profile_from_bars, value_area,
)
from scripts import premarket_volume_profile as pvp


def _bars(n=24, base=7750.0):
    """A rising staircase with a heavy shelf at base+5 (so the POC is knowable)."""
    start = int(datetime(2026, 8, 10, 13, 30, tzinfo=timezone.utc).timestamp() * 1000)
    out = []
    for i in range(n):
        lo = base + (i % 10)
        out.append({"datetime": start + i * 300_000, "open": lo, "high": lo + 1,
                    "low": lo, "close": lo + 0.5,
                    "volume": 500 if (i % 10) == 5 else 40})
    return out


@pytest.fixture
def rendered():
    bars = _bars()
    profile = build_profile_from_bars(bars, symbol="/ES")
    va = value_area(profile)
    anchor = anchor_utc(date(2026, 8, 10)).astimezone(CENTRAL)
    gen = datetime(2026, 8, 11, 8, 15, tzinfo=CENTRAL)
    return pvp.render_page(profile, va, bars, anchor, gen), profile, va


class TestRender:
    def test_page_is_self_contained_no_external_assets(self, rendered):
        page, _, _ = rendered
        for bad in ("http://", "https://", "<script"):
            assert bad not in page

    def test_header_states_the_anchor_and_generation_time(self, rendered):
        page, _, _ = rendered
        assert "prior RTH open" in page
        assert "08:30 CT" in page
        assert "2026-08-11 08:15 CT" in page

    def test_every_bucket_gets_a_row(self, rendered):
        page, profile, _ = rendered
        assert page.count("<tr") == len(profile.prices)

    def test_poc_row_is_marked_once(self, rendered):
        page, _, _ = rendered
        assert page.count('class="poc"') == 1

    def test_highest_price_renders_first(self, rendered):
        page, profile, _ = rendered
        top = f'<td class="px">{max(profile.prices):g}</td>'
        bottom = f'<td class="px">{min(profile.prices):g}</td>'
        assert page.index(top) < page.index(bottom)

    def test_last_price_row_is_marked(self, rendered):
        page, _, _ = rendered
        assert 'class="here"' in page or 'here"' in page

    def test_states_the_bar_resolution_caveat(self, rendered):
        page, _, _ = rendered
        assert "approximation" in page
        assert "02:50" in page  # the corpus gap is disclosed, not hidden


class TestFailureContract:
    def test_fetch_failure_returns_nonzero_and_publishes_nothing(self, monkeypatch):
        published = []
        monkeypatch.setattr(pvp, "fetch_bars",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("token dead")))
        monkeypatch.setattr(pvp, "publish", lambda *a, **k: published.append(a))
        assert pvp.main(["--date", "2026-08-10"]) == 2
        assert published == []

    def test_success_publishes_and_returns_zero(self, monkeypatch):
        published = []
        monkeypatch.setattr(pvp, "fetch_bars", lambda *a, **k: _bars())
        monkeypatch.setattr(pvp, "publish", lambda page, dry: published.append(page))
        assert pvp.main(["--date", "2026-08-10"]) == 0
        assert published and "Premarket Volume Profile" in published[0]

    def test_dry_run_writes_no_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pvp, "fetch_bars", lambda *a, **k: _bars())
        monkeypatch.setattr(pvp, "PAGE", tmp_path / "premarket-volume-profile.html")
        assert pvp.main(["--date", "2026-08-10", "--dry-run"]) == 0
        assert not (tmp_path / "premarket-volume-profile.html").exists()
