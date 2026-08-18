"""Premarket anchored VP page — profile paths, rendering, source contract. [st-6gs3]

No Schwab here: fetch_bars is the only live-API surface and it is stubbed, so
the whole build/render/publish path runs under the API gate.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from market.entities.trade import Trade
from market.orderflow.anchored_profile import (
    CENTRAL, anchor_utc, build_profile_from_bars, build_split_profile, value_area,
)
from scripts import premarket_volume_profile as pvp

TS = datetime(2026, 8, 10, 8, 30, tzinfo=CENTRAL)


def _bars(n=24, base=7750.0):
    """Rising staircase with a heavy shelf at base+5, so the POC is knowable."""
    start = int(datetime(2026, 8, 10, 13, 30, tzinfo=timezone.utc).timestamp() * 1000)
    out = []
    for i in range(n):
        lo = base + (i % 10)
        out.append({"datetime": start + i * 300_000, "open": lo, "high": lo + 1,
                    "low": lo, "close": lo + 0.5,
                    "volume": 500 if (i % 10) == 5 else 40})
    return out


def _trades():
    """Prints with a known aggressor split and a known POC at 7755."""
    out = []
    for price, buy, sell in [(7750.0, 10, 5), (7755.0, 300, 200), (7760.0, 8, 12)]:
        out.append(Trade(ts=TS, symbol="ESU6", instrument_id=1, price=price,
                         size=buy, side="B"))
        out.append(Trade(ts=TS, symbol="ESU6", instrument_id=1, price=price,
                         size=sell, side="A"))
    return out


@pytest.fixture
def tick_page():
    prof = build_split_profile(_trades(), bucket_ticks=1)
    va = value_area(prof.as_volume_profile())
    # A window whose tape has an 11 h silence (the pre-2026-08-18 capture shape).
    hole = (datetime(2026, 8, 10, 20, 5, tzinfo=timezone.utc),
            datetime(2026, 8, 11, 7, 50, tzinfo=timezone.utc), 11.75 * 3600)
    page = pvp.render_page(prof, va, 7755.0, len(_trades()), TS,
                           anchor_utc(date(2026, 8, 10)).astimezone(CENTRAL),
                           datetime(2026, 8, 11, 8, 15, tzinfo=CENTRAL),
                           source="ticks", aggressor=True, hole=hole)
    return page, prof, va


@pytest.fixture
def bar_page():
    bars = _bars()
    prof = build_profile_from_bars(bars, symbol="/ES")
    va = value_area(prof)
    page = pvp.render_page(prof, va, float(bars[-1]["close"]), len(bars), TS,
                           anchor_utc(date(2026, 8, 10)).astimezone(CENTRAL),
                           datetime(2026, 8, 11, 8, 15, tzinfo=CENTRAL),
                           source="schwab", aggressor=False)
    return page, prof, va


class TestSplitProfile:
    def test_aggressor_sides_are_kept_apart(self):
        prof = build_split_profile(_trades(), bucket_ticks=1)
        i = prof.prices.index(7755.0)
        assert (prof.buy_volumes[i], prof.sell_volumes[i]) == (300, 200)

    def test_totals_and_net_delta(self):
        prof = build_split_profile(_trades(), bucket_ticks=1)
        assert prof.total == 535
        assert prof.delta == (10 + 300 + 8) - (5 + 200 + 12)

    def test_native_bucket_is_one_tick(self):
        assert build_split_profile(_trades(), bucket_ticks=1).bucket_pts == 0.25

    def test_unknown_aggressor_is_not_invented_into_a_side(self):
        """Aggressor None Policy (Watcher V2 Phase 4, 2026-08-16): the estate's
        one policy is ``separate`` — an N print is neither buyer nor seller in
        the histogram; ``halve`` is opt-in for a caller that needs total ==
        traded. On ES the two agree exactly (Databento classifies every print).
        Before this ruling the default halved and this test asserted total 7."""
        odd = [Trade(ts=TS, symbol="ESU6", instrument_id=1, price=7750.0,
                     size=7, side="N")]
        prof = build_split_profile(odd, bucket_ticks=1)
        assert prof.buy_volumes == (0,) and prof.sell_volumes == (0,) and prof.total == 0
        hal = build_split_profile(odd, bucket_ticks=1, none_policy="halve")
        assert hal.total == 7 and hal.buy_volumes[0] + hal.sell_volumes[0] == 7

    def test_as_volume_profile_round_trips_into_the_value_area(self):
        prof = build_split_profile(_trades(), bucket_ticks=1)
        assert value_area(prof.as_volume_profile()).poc == 7755.0

    def test_zero_trades_raises(self):
        with pytest.raises(ValueError):
            build_split_profile([], bucket_ticks=1)


class TestRender:
    def test_page_is_self_contained_no_external_assets(self, tick_page):
        page, _, _ = tick_page
        for bad in ("http://", "https://", "<script src", "<link "):
            assert bad not in page

    def test_header_states_anchor_and_generation_time(self, tick_page):
        page, _, _ = tick_page
        assert "prior RTH open" in page and "08:30 CT" in page
        assert "2026-08-11 08:15 CT" in page

    def test_every_bucket_gets_a_row(self, tick_page):
        page, prof, _ = tick_page
        assert page.count('<div class="r ') == len(prof.prices)

    def test_poc_row_is_marked_once(self, tick_page):
        page, _, _ = tick_page
        assert page.count("r poc") == 1

    def test_highest_price_renders_first(self, tick_page):
        page, prof, _ = tick_page
        assert page.index(f'>{max(prof.prices):g}<') < page.index(f'>{min(prof.prices):g}<')

    def test_bars_are_right_justified(self, tick_page):
        page, _, _ = tick_page
        assert "justify-content:flex-end" in page

    def test_buy_and_sell_segments_both_render(self, tick_page):
        page, _, _ = tick_page
        assert 'class="sell"' in page and 'class="buy"' in page

    def test_rows_carry_exact_volumes_for_hover(self, tick_page):
        page, _, _ = tick_page
        assert "buy 300" in page and "sell 200" in page and "delta +100" in page

    def test_net_delta_stat_is_shown_for_tick_source(self, tick_page):
        page, _, _ = tick_page
        assert "Net delta" in page

    def test_price_labels_thin_out_at_tick_resolution(self, tick_page):
        """Every row labelled at 0.25pt would be unreadable — whole points only."""
        page, prof, _ = tick_page
        assert page.count('class="px">7') < len(prof.prices)


class TestBarSourceRendering:
    def test_bar_source_renders_single_tone_and_no_delta(self, bar_page):
        page, _, _ = bar_page
        assert 'class="flat"' in page
        assert "Net delta" not in page

    def test_schwab_page_has_no_incomplete_window_banner(self, bar_page):
        page, _, _ = bar_page
        assert "Incomplete window" not in page

    def test_tick_page_with_a_hole_carries_the_banner(self, tick_page):
        page, _, _ = tick_page
        assert "Incomplete window" in page and "15:05" in page and "02:50" in page

    def test_tick_page_without_a_hole_has_no_banner(self):
        """Since 2026-08-18 the Globex day is captured [st-9olq]: a window whose
        tape is continuous must not banner a hole it does not have."""
        prof = build_split_profile(_trades(), bucket_ticks=1)
        va = value_area(prof.as_volume_profile())
        page = pvp.render_page(prof, va, 7755.0, len(_trades()), TS,
                               anchor_utc(date(2026, 8, 10)).astimezone(CENTRAL),
                               datetime(2026, 8, 11, 8, 15, tzinfo=CENTRAL),
                               source="ticks", aggressor=True, hole=None)
        assert "Incomplete window" not in page and "INCOMPLETE" not in page

    def test_tally_measures_the_widest_silence(self):
        t0 = datetime(2026, 8, 17, 20, 5, tzinfo=timezone.utc)
        mk = lambda secs: Trade(ts=t0 + timedelta(seconds=secs), symbol="ESU6", instrument_id=1,
                                price=7750.0, size=1, side="B")
        tally = pvp._Tally()
        list(tally([mk(0), mk(10), mk(10 + 3 * 3600), mk(10 + 3 * 3600 + 5)]))
        assert tally.n == 4 and tally.gap[2] == 3 * 3600
        assert tally.gap[0] == t0 + timedelta(seconds=10)


def _dead(*a, **k):
    raise RuntimeError("token dead")


class TestSourceContract:
    def test_default_source_is_ticks(self, monkeypatch):
        pages = []
        monkeypatch.setattr(pvp, "trades_from_corpus", lambda *a, **k: iter(_trades()))
        monkeypatch.setattr(pvp, "publish", lambda page, dry: pages.append(page))
        assert pvp.main(["--date", "2026-08-10"]) == 0
        assert "Net delta" in pages[0]          # aggressor split, i.e. the tick path

    def test_schwab_source_uses_bars_and_publishes(self, monkeypatch):
        pages = []
        monkeypatch.setattr(pvp, "fetch_bars", lambda *a, **k: _bars())
        monkeypatch.setattr(pvp, "publish", lambda page, dry: pages.append(page))
        assert pvp.main(["--date", "2026-08-10", "--source", "schwab"]) == 0
        assert "Incomplete window" not in pages[0]

    def test_unusable_source_returns_nonzero_and_publishes_nothing(self, monkeypatch):
        published = []
        monkeypatch.setattr(pvp, "fetch_bars", _dead)
        monkeypatch.setattr(pvp, "publish", lambda *a, **k: published.append(a))
        assert pvp.main(["--date", "2026-08-10", "--source", "schwab"]) == 2
        assert published == []

    def test_dry_run_writes_no_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pvp, "trades_from_corpus", lambda *a, **k: iter(_trades()))
        monkeypatch.setattr(pvp, "PAGE", tmp_path / "premarket-volume-profile.html")
        assert pvp.main(["--date", "2026-08-10", "--dry-run"]) == 0
        assert not (tmp_path / "premarket-volume-profile.html").exists()

    def test_bucket_ticks_flag_changes_resolution(self, monkeypatch):
        pages = []
        monkeypatch.setattr(pvp, "trades_from_corpus", lambda *a, **k: iter(_trades()))
        monkeypatch.setattr(pvp, "publish", lambda page, dry: pages.append(page))
        assert pvp.main(["--date", "2026-08-10", "--bucket-ticks", "4"]) == 0
        assert "1-pt buckets" in pages[0]


class TestPackedCorpusDays:
    """A T+1-packed day is .jsonl.gz. Testing the raw path skipped it in silence
    and the 2026-08-18 noon run drew Monday as empty (248k prints instead of
    470k) minutes after 08-17 was packed. [st-9olq]"""

    def _rec(self, ts_utc: datetime, price: float, size: int, side: str) -> str:
        import json
        return json.dumps({"provenance": {"ts_event": ts_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")},
                           "data": {"symbol": "ESU6", "instrument_id": 1, "price": price,
                                    "size": size, "side": side}}) + "\n"

    def test_trades_from_corpus_reads_a_packed_day(self, tmp_path, monkeypatch):
        import gzip
        import market.corpus.paths as paths
        monkeypatch.setattr(paths, "CORPUS_ROOT", tmp_path)
        day = tmp_path / "2026-08-17"; day.mkdir()
        t = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
        with gzip.open(day / "databento_glbx_es.jsonl.gz", "wt", encoding="utf-8") as f:
            f.write(self._rec(t, 7750.0, 3, "B"))
            f.write(self._rec(t + timedelta(seconds=1), 7750.25, 2, "A"))
        # `today` inside the reader is the real today; the walk starts at the anchor day
        got = list(pvp.trades_from_corpus(datetime(2026, 8, 17, 13, 30, tzinfo=timezone.utc)))
        assert [(x.price, x.size, x.side) for x in got] == [(7750.0, 3, "B"), (7750.25, 2, "A")]

    def test_bars_from_corpus_reads_a_packed_day(self, tmp_path, monkeypatch):
        import gzip
        import market.corpus.paths as paths
        monkeypatch.setattr(paths, "CORPUS_ROOT", tmp_path)
        day = tmp_path / "2026-08-17"; day.mkdir()
        t = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
        with gzip.open(day / "databento_glbx_es.jsonl.gz", "wt", encoding="utf-8") as f:
            f.write(self._rec(t, 7750.0, 3, "B"))
        bars = pvp.bars_from_corpus(datetime(2026, 8, 17, 13, 30, tzinfo=timezone.utc))
        assert len(bars) == 1 and bars[0]["volume"] == 3
