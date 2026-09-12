"""The ES level watch's damping rules and the GEX basis, pinned. [st-d7qe st-bpry]

Measured 2026-09-10: with a naive "price crossed the level" test the watch
fired 14 times in 90 seconds on 7603, and the GEX negative major toggled
7525/7540 <-> 7580/7600 on alternate polls. Measured 2026-09-11: GEX strikes
(SPX) were compared to ES prints with no basis, and every GEX clear was a
phantom — the day's live basis was +4.07 median (GexBot spot vs the ES print
at the same second), +8.25 at the 08:30 open, +49 in the Schwab premarket
row. These tests pin what replaced both.
"""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import es_level_watch as w  # noqa: E402

L = {"7603": (7603.0, "Mancini support"), "7595": (7595.0, "Mancini support")}


class TestLevelCrosser:
    def test_first_price_sets_state_without_reporting(self):
        c = w.LevelCrosser(1.0, 300)
        assert c.update(7598.0, L, t=0) == []
        assert c.state == {"7603": "below", "7595": "above"}

    def test_a_tick_on_the_level_is_not_a_cross_but_clearing_it_is(self):
        c = w.LevelCrosser(1.0, 300)
        c.update(7598.0, L, t=0)
        assert c.update(7603.0, L, t=1) == []           # on the level: inside the band
        assert c.update(7603.75, L, t=2) == []          # still inside +1
        assert c.update(7604.0, L, t=3) == [(7603.0, "Mancini support", "UP through")]

    def test_oscillation_on_the_level_does_not_report_again(self):
        c = w.LevelCrosser(1.0, 300)
        c.update(7598.0, L, t=0)
        c.update(7604.0, L, t=1)
        for px in (7603.0, 7602.75, 7603.25, 7603.0, 7602.75):
            assert c.update(px, L, t=2) == []
        assert c.chop == {}                              # nothing crossed: no state change

    def test_a_real_recross_inside_the_cooldown_is_counted_as_chop(self):
        c = w.LevelCrosser(1.0, 300)
        c.update(7598.0, L, t=0)
        assert c.update(7604.0, L, t=10) != []
        assert c.update(7602.0, L, t=20) == []           # crossed back, inside cooldown
        assert c.update(7604.0, L, t=30) == []
        assert c.take_chop() == {"7603": 2}
        assert c.take_chop() == {}
        assert c.update(7602.0, L, t=400) == [(7603.0, "Mancini support", "DOWN through")]

    def test_a_first_cross_after_a_quiet_spell_reports(self):
        c = w.LevelCrosser(1.0, 300)
        c.update(7598.0, L, t=0)
        assert c.update(7593.0, L, t=1000) == [(7595.0, "Mancini support", "DOWN through")]

    def test_a_gex_level_drifting_with_the_basis_is_still_one_level(self):
        """09-11 replay before the fix: long-gamma reported four times in four
        minutes because 7664/7665 SPX and basis +4.4/+4.2/+4.1 each made a new key."""
        c = w.LevelCrosser(1.0, 300)
        g = lambda es: {"GEX long-gamma": (es, "GEX long-gamma")}  # noqa: E731
        c.update(7672.0, g(7669.5), t=0)
        assert c.update(7668.0, g(7669.5), t=10) == [(7669.5, "GEX long-gamma", "DOWN through")]
        assert c.update(7671.0, g(7668.5), t=90) == []       # recross, level drifted a point: chop
        assert c.update(7667.5, g(7669.25), t=150) == []
        assert c.update(7671.0, g(7669.0), t=200) == []
        assert c.take_chop() == {"GEX long-gamma": 3}

    def test_a_level_that_jumps_across_price_is_reseeded_not_crossed(self):
        c = w.LevelCrosser(1.0, 300)
        g = lambda es: {"GEX major −": (es, "GEX major −")}  # noqa: E731
        c.update(7670.0, g(7649.0), t=0)                     # price above
        assert c.update(7670.0, g(7714.0), t=60) == []        # major moved 7645→7710 SPX: no cross
        assert c.state["GEX major −"] == "below"
        assert c.update(7715.5, g(7714.0), t=120) == [(7714.0, "GEX major −", "UP through")]


class TestBasis:
    def _b(self):
        b = w.Basis(None)
        for i in range(60):
            b.add_print(1000.0 + i, 7670.0)                     # a print a second at 7670
        return b

    def test_refuses_until_three_polls_have_paired(self):
        b = self._b()
        assert b.value(1100) is None
        assert b.sample_gex(7666.0, 1010.0, t=1010) == 4.0
        assert b.sample_gex(7661.5, 1020.0, t=1020) == 8.5      # the open artifact
        assert b.value(1100) is None                            # two samples: not yet
        assert b.sample_gex(7666.25, 1030.0, t=1030) == 3.75
        assert b.value(1100) == (4.0, "gexbot×3")               # median, the artifact outvoted

    def test_rolling_median_of_the_last_five(self):
        b = self._b()
        for i, spot in enumerate((7661.5, 7666.0, 7666.0, 7666.25, 7666.0, 7666.0, 7666.0)):
            b.sample_gex(spot, 1010.0 + i, t=1010 + i)
        assert len(b.samples) == 5
        assert b.value(1100)[0] == 4.0

    def test_same_vendor_timestamp_is_not_sampled_twice(self):
        b = self._b()
        assert b.sample_gex(7666.0, 1010.0, t=1010) == 4.0
        assert b.sample_gex(7666.0, 1010.0, t=1070) is None     # live poll re-read the same row
        assert len(b.samples) == 1

    def test_no_print_near_the_spot_time_means_no_sample(self):
        b = self._b()
        assert b.sample_gex(7666.0, 1500.0, t=1500) is None     # nearest print 440 s away
        assert b.samples == w.deque()

    def test_samples_age_out(self):
        b = self._b()
        for i in range(3):
            b.sample_gex(7666.0, 1010.0 + i, t=1010 + i)
        assert b.value(1100) is not None
        assert b.value(1010 + w.BASIS_MAX_AGE_S + 5) is None

    def test_schwab_fallback_skips_premarket_and_open_rows(self, tmp_path):
        p = tmp_path / "schwab.jsonl"
        rows = [
            {"ts_pull_utc": "2026-09-11T12:00:05Z", "stage": "premarket", "data": {"es_minus_spx_basis": 49.3}},
            {"ts_pull_utc": "2026-09-11T13:30:01Z", "stage": "open", "data": {"es_minus_spx_basis": 7.8}},
            {"ts_pull_utc": "2026-09-11T18:00:01Z", "stage": "afternoon", "data": {"es_minus_spx_basis": 4.16}},
            {"ts_pull_utc": "2026-09-11T19:45:01Z", "stage": "close-watch", "data": {"es_minus_spx_basis": 4.1}},
        ]
        p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        b = w.Basis(p)
        t_open = w.parse_utc("2026-09-11T14:00:00Z")
        assert b.value(t_open) is None                          # only premarket/open pulled so far
        t_pm = w.parse_utc("2026-09-11T18:30:00Z")
        assert b.value(t_pm) == (4.16, "schwab afternoon 13:00")
        t_late = w.parse_utc("2026-09-11T20:30:00Z")
        assert b.value(t_late) == (4.1, "schwab close-watch 14:45")

    def test_gexbot_median_outranks_schwab(self, tmp_path):
        p = tmp_path / "schwab.jsonl"
        p.write_text(json.dumps({"ts_pull_utc": "2026-09-11T18:00:01Z", "stage": "afternoon",
                                 "data": {"es_minus_spx_basis": 4.16}}) + "\n")
        b = w.Basis(p)
        for i in range(60):
            b.add_print(1000.0 + i, 7670.0)
        for i in range(3):
            b.sample_gex(7666.5, 1010.0 + i, t=1010 + i)
        assert b.value(1100) == (3.5, "gexbot×3")


class TestGexMajors:
    def _g(self, pos, neg, gz=7600):
        return {"gamma-zero": gz, "major +": pos, "major −": neg, "long-gamma": 7600, "short-gamma": 7640}

    def test_first_poll_announces_everything_as_spx(self):
        g = w.GexMajors(lambda t: None)
        assert g.apply(self._g(7630, 7525), t=0)[0].startswith("GEX (SPX): gamma-zero 7600, major + 7630, major − 7525")

    def test_a_major_reports_only_when_held_two_polls(self):
        g = w.GexMajors(lambda t: None)
        g.apply(self._g(7630, 7525), t=0)
        assert g.apply(self._g(7630, 7600), t=60) == []                 # first sighting
        assert g.apply(self._g(7630, 7525), t=120) == []                # went back: pending cleared
        assert g.apply(self._g(7630, 7540), t=180) == []
        assert g.apply(self._g(7630, 7540), t=240) == ["GEX major − moved 7525 → 7540 SPX (held two polls)"]
        assert g.levels["major −"] == 7540

    def test_toggling_between_two_clusters_is_silent_after_the_first_time(self):
        g = w.GexMajors(lambda t: None)
        g.apply(self._g(7630, 7540), t=0)
        g.apply(self._g(7630, 7580), t=60)
        assert g.apply(self._g(7630, 7580), t=120) == ["GEX major − moved 7540 → 7580 SPX (held two polls)"]
        g.apply(self._g(7630, 7540), t=180)
        assert g.apply(self._g(7630, 7540), t=240) == []                # 7540 seen 4 min ago
        g.apply(self._g(7630, 7580), t=300)
        assert g.apply(self._g(7630, 7580), t=360) == []
        g.apply(self._g(7630, 7540), t=2500)
        assert g.apply(self._g(7630, 7540), t=2560) == ["GEX major − moved 7580 → 7540 SPX (held two polls)"]

    def test_undamped_keys_follow_every_poll(self):
        g = w.GexMajors(lambda t: None)
        g.apply(self._g(7630, 7525, gz=7600), t=0)
        g.apply(self._g(7630, 7525, gz=7583), t=60)
        assert g.levels["gamma-zero"] == 7583

    def test_levels_are_moved_to_es_by_the_basis_and_say_so(self):
        g = w.GexMajors(lambda t: None)
        g.apply(self._g(7630, 7525), t=0)
        assert g.as_levels(4.1) == {
            "GEX major +": (7634.0, "GEX major + 7630 SPX, basis +4.1"),
            "GEX major −": (7529.0, "GEX major − 7525 SPX, basis +4.1"),
            "GEX long-gamma": (7604.0, "GEX long-gamma 7600 SPX, basis +4.1"),
            "GEX short-gamma": (7644.0, "GEX short-gamma 7640 SPX, basis +4.1"),
        }
        assert g.as_levels(4.37)["GEX major +"][0] == 7634.25          # to the ES tick

    def test_no_basis_means_no_gex_levels_at_all(self):
        """The 09-11 failure: raw SPX strikes against ES prints. Refuse, never assume zero."""
        g = w.GexMajors(lambda t: None)
        g.apply(self._g(7630, 7525), t=0)
        assert g.as_levels(None) == {}

    def test_poll_takes_spot_and_the_vendor_time_from_the_row(self):
        row = {"ts_pull_utc": "2026-09-11T14:00:05Z",
               "data": {"summary": {"spot_at_gamma_zero": 7656.13, "major_positive": 7654.92,
                                    "major_negative": 7660, "major_long_gamma": 7660.3,
                                    "major_short_gamma": 7644.4},
                        "responses": {"/SPX/state/gamma_zero": {"timestamp": 1789156800}}}}
        g = w.GexMajors(lambda t: row)
        assert g.poll(0)[0].startswith("GEX (SPX): gamma-zero 7656, major + 7655, major − 7660")
        assert g.spot == 7656.13
        assert g.spot_ts == 1789156800.0


class TestGexReplay:
    def test_last_row_pulled_at_or_before_t(self, tmp_path):
        p = tmp_path / "gexbot.jsonl"
        rows = [{"ts_pull_utc": f"2026-09-11T13:3{i}:00Z", "data": {"summary": {"spot_at_gamma_zero": 7650 + i}}}
                for i in range(3)]
        p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        src = w.GexReplay(p)
        assert src(w.parse_utc("2026-09-11T13:29:00Z")) is None
        assert src(w.parse_utc("2026-09-11T13:31:30Z"))["data"]["summary"]["spot_at_gamma_zero"] == 7651
        assert src(w.parse_utc("2026-09-11T20:00:00Z"))["data"]["summary"]["spot_at_gamma_zero"] == 7652
