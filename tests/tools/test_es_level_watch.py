"""The ES level watch's two damping rules, pinned. [st-d7qe]

Measured 2026-09-10: with a naive "price crossed the level" test the watch
fired 14 times in 90 seconds on 7603, and the GEX negative major toggled
7525/7540 <-> 7580/7600 on alternate polls. These tests pin what replaced that.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import es_level_watch as w  # noqa: E402

L = {7603.0: "Mancini support", 7595.0: "Mancini support"}


class TestLevelCrosser:
    def test_first_price_sets_state_without_reporting(self):
        c = w.LevelCrosser(1.0, 300)
        assert c.update(7598.0, L, t=0) == []
        assert c.state == {7603.0: "below", 7595.0: "above"}

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
        assert c.take_chop() == {7603.0: 2}
        assert c.take_chop() == {}
        assert c.update(7602.0, L, t=400) == [(7603.0, "Mancini support", "DOWN through")]

    def test_a_first_cross_after_a_quiet_spell_reports(self):
        c = w.LevelCrosser(1.0, 300)
        c.update(7598.0, L, t=0)
        assert c.update(7593.0, L, t=1000) == [(7595.0, "Mancini support", "DOWN through")]


class TestGexMajors:
    def _g(self, pos, neg, gz=7600):
        return {"gamma-zero": gz, "major +": pos, "major −": neg, "long-gamma": 7600, "short-gamma": 7640}

    def test_first_poll_announces_everything(self):
        g = w.GexMajors(Path("/nonexistent"))
        assert g.apply(self._g(7630, 7525), t=0)[0].startswith("GEX: gamma-zero 7600, major + 7630, major − 7525")

    def test_a_major_reports_only_when_held_two_polls(self):
        g = w.GexMajors(Path("/nonexistent"))
        g.apply(self._g(7630, 7525), t=0)
        assert g.apply(self._g(7630, 7600), t=60) == []                 # first sighting
        assert g.apply(self._g(7630, 7525), t=120) == []                # went back: pending cleared
        assert g.apply(self._g(7630, 7540), t=180) == []
        assert g.apply(self._g(7630, 7540), t=240) == ["GEX major − moved 7525 → 7540 (held two polls)"]
        assert g.levels["major −"] == 7540

    def test_toggling_between_two_clusters_is_silent_after_the_first_time(self):
        g = w.GexMajors(Path("/nonexistent"))
        g.apply(self._g(7630, 7540), t=0)
        g.apply(self._g(7630, 7580), t=60)
        assert g.apply(self._g(7630, 7580), t=120) == ["GEX major − moved 7540 → 7580 (held two polls)"]
        g.apply(self._g(7630, 7540), t=180)
        assert g.apply(self._g(7630, 7540), t=240) == []                # 7540 seen 4 min ago
        g.apply(self._g(7630, 7580), t=300)
        assert g.apply(self._g(7630, 7580), t=360) == []
        g.apply(self._g(7630, 7540), t=2500)
        assert g.apply(self._g(7630, 7540), t=2560) == ["GEX major − moved 7580 → 7540 (held two polls)"]

    def test_undamped_keys_follow_every_poll_and_feed_the_level_map(self):
        g = w.GexMajors(Path("/nonexistent"))
        g.apply(self._g(7630, 7525, gz=7600), t=0)
        g.apply(self._g(7630, 7525, gz=7583), t=60)
        assert g.levels["gamma-zero"] == 7583
        assert g.as_levels() == {7630.0: "GEX major +", 7525.0: "GEX major −",
                                 7600.0: "GEX long-gamma", 7640.0: "GEX short-gamma"}
