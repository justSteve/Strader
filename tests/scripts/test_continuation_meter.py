"""Continuation meter display + journal-scorer tests. [st-em4r]

The cold-context audit (`docs/audits/2026-08-04-auditor-report.md`) found the
live meter's number, wording and confidence wrong in three independent ways at
once. These tests are the tripwires for all three, plus the direction flag the
audit's §3.4 asked for:

* **the number** — every displayed probability must be a cell copied verbatim
  out of `data/measurement/decision_aligned_truth.json`, not computed here and
  not carried in the meter's source. Nothing may be rendered when that file is
  missing (§4.2, §1.3).
* **the wording** — the sentence next to a number must be the truth table's own
  question for the label that number was measured on. The retired sentence
  ("extends 2+ pts in the next 15 min") named a 91.9%-base-rate event next to a
  73 calibrated on a different label (§3.2); it must never reappear.
* **the interval** — the §4.1 bootstrap CIs must reach the pane (§4.1).
* **the direction** — a runner-up excursion within 20% of the primary means
  every oriented read is a coin flip away from sign-flipping, and the pane has
  to say so (§3.4).

The real truth table is used wherever a test asserts a specific measured value,
so a regenerated study that moves a number fails here rather than silently
changing what Steve reads.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scripts.desk import continuation_meter as cm
from scripts.measurement import score_meter_journal as smj

CT = ZoneInfo("America/Chicago")
ANSI = re.compile(r"\033\[[0-9;]*[A-Za-z]")


def plain(s: str) -> str:
    """Rendered pane text with the ANSI colour codes stripped."""
    return ANSI.sub("", s)


@pytest.fixture(scope="module")
def truth():
    t = cm.TruthTable()
    t.refresh()
    if t.error:
        pytest.skip(f"decision-aligned truth table unavailable: {t.error}")
    return t


@pytest.fixture(scope="module")
def truth_json():
    with cm.TRUTH_PATH.open() as fh:
        return json.load(fh)


def synth_closes(down_pts: float, up_pts: float, start=None) -> dict:
    """A minute-close series with a chosen drawdown then a chosen drawup.

    Walks in quarter-point ticks so the two excursions equal the arguments
    exactly — that is what makes the audit's sub-point direction margins
    (0.75 pts on 2026-07-30) assertable rather than approximate.
    """
    start = start or datetime(2026, 8, 4, 8, 30, tzinfo=CT)
    closes, p, i = {}, 7600.0, 0
    closes[start] = p
    for pts, sign in ((down_pts, -1.0), (up_pts, 1.0)):
        for _ in range(round(pts * 4)):
            i += 1
            p += sign * 0.25
            closes[start + timedelta(minutes=i)] = round(p, 2)
    return closes


def make_frame(truth, *, score=1, mode=2, move=None, age_min=45.0,
               clock=time(9, 30), label=cm.PRIMARY_LABEL, prev_dir=None):
    """A frame shaped exactly like build_frame's output, without a Schwab call."""
    mv = move or cm.primary_move(synth_closes(50, 10))
    age_bucket = cm.bucket_for_age(age_min)
    clock_bucket = cm.bucket_for_clock(clock)
    family, bucket, why = cm.choose_family(mv["size"], age_bucket, clock_bucket)
    frame = dict(
        ts=datetime(2026, 8, 4, clock.hour, clock.minute, 12,
                    tzinfo=CT).isoformat(),
        errors=[], last_candle=clock.strftime("%H:%M"), stale_min=0.4, move=mv,
        traces_raw=dict(tick=137.0, add10=None, vix5=0.12, vvix5=-0.01,
                        spx5=2.76),
        traces=dict(tick=137.0, add=None, vix=-0.12),
        score=score, score_mode=mode,
        buckets=dict(age_min=age_min, move_age=age_bucket,
                     session_clock=clock_bucket),
        levels=dict(spx=7646.7, vix=16.32, vvix=89.31, term=-1.73),
        truth_meta=truth.provenance())
    frame["primary"] = cm.primary_read(truth, label, family, bucket, reason=why)
    cc = cm.crosscheck_read(truth, label, clock_bucket)
    if cc and family != cm.CROSSCHECK_FAMILY:
        frame["primary"]["crosscheck"] = cc
    frame["secondary"] = cm.secondary_read(truth, score, mode, label)
    if prev_dir is not None and prev_dir != mv["dir"]:
        frame["dir_flip"] = dict(prev="dn" if prev_dir == -1 else "up",
                                 now="dn" if mv["dir"] == -1 else "up")
    return frame


# ---------------------------------------------------------------------------
# mapping: truth-table JSON -> display values
# ---------------------------------------------------------------------------

def test_bucket_names_cover_exactly_the_truth_tables_buckets(truth_json):
    """The meter's pinned edges and the study's must not drift apart.

    The bucket names are the join key between the two; a rename on either side
    would otherwise show up live as a silently missing headline.
    """
    base = truth_json["base_rates"][cm.PRIMARY_LABEL]
    assert set(b[0] for b in cm.AGE_BUCKETS) == set(base["move_age"])
    assert set(b[0] for b in cm.SESSION_BUCKETS) == set(base["session_clock"])


@pytest.mark.parametrize("age,expected", [
    (0.0, "0-10"), (9.9, "0-10"), (10.0, "10-20"), (19.9, "10-20"),
    (20.0, "20-40"), (39.9, "20-40"), (40.0, "40+"), (600.0, "40+"),
    (None, None), (-1.0, None),
])
def test_bucket_for_age_edges(age, expected):
    assert cm.bucket_for_age(age) == expected


@pytest.mark.parametrize("t,expected", [
    (time(8, 30), "pre-0900"), (time(8, 59), "pre-0900"),
    (time(9, 0), "0900-1000"), (time(9, 59), "0900-1000"),
    (time(10, 0), "post-1000"), (time(14, 59), "post-1000"),
    (None, None),
])
def test_bucket_for_clock_edges(t, expected):
    assert cm.bucket_for_clock(t) == expected


def test_primary_read_copies_the_cell_verbatim(truth, truth_json):
    """Nothing is recomputed: p, both CI bounds, n and n_days come from disk."""
    cell = truth_json["base_rates"][cm.PRIMARY_LABEL]["move_age"]["40+"]
    read = cm.primary_read(truth, cm.PRIMARY_LABEL, "move_age", "40+")
    assert read["p"] == cell["p"]
    assert (read["ci_lo"], read["ci_hi"]) == (cell["ci_lo"], cell["ci_hi"])
    assert (read["n"], read["n_days"]) == (cell["n"], cell["n_days"])
    assert read["question"] == truth_json["labels"][cm.PRIMARY_LABEL]["question"]


def test_primary_read_carries_the_stop_and_the_cost_of_being_wrong(truth,
                                                                   truth_json):
    """The split and P(adverse) come from the study, not from the meter."""
    read = cm.primary_read(truth, cm.PRIMARY_LABEL, "move_age", "40+")
    split = truth_json["outcome_split"][cm.PRIMARY_LABEL]["move_age"]["40+"]
    assert read["split"]["target_first"] == split["p_target_first"]
    assert read["split"]["stop_first"] == split["p_stop_first"]
    assert read["p_adverse_8"] == truth_json["excursions"]["p_mae_ge_8"]


def test_headline_is_clock_conditioned_not_pooled(truth, truth_json):
    """§1.3/§4.2: the fix is that the cell moves with the clock.

    A young move and a mature one must not read the same number, and neither
    may read the pooled average the retired pane showed.
    """
    young = cm.primary_read(truth, cm.PRIMARY_LABEL, "move_age", "0-10")["p"]
    old = cm.primary_read(truth, cm.PRIMARY_LABEL, "move_age", "40+")["p"]
    pooled = truth_json["base_rates"][cm.PRIMARY_LABEL]["all"]["all"]["p"]
    assert young > old
    assert young != pooled and old != pooled


def test_under_the_floor_the_headline_switches_to_the_wall_clock():
    """No qualifying move means no meaningful move age — say so, don't guess."""
    family, bucket, why = cm.choose_family(4.0, "0-10", "0900-1000")
    assert (family, bucket) == (cm.CROSSCHECK_FAMILY, "0900-1000")
    assert "floor" in why
    family, bucket, why = cm.choose_family(cm.MOVE_FLOOR, "0-10", "0900-1000")
    assert (family, bucket, why) == (cm.PRIMARY_FAMILY, "0-10", None)


def test_missing_bucket_or_label_is_reported_not_raised(truth):
    assert "no move_age bucket" in cm.primary_read(
        truth, cm.PRIMARY_LABEL, "move_age", None)["unavailable"]
    assert "no label" in cm.primary_read(
        truth, "not_a_label", "move_age", "40+")["unavailable"]
    assert "no cell" in cm.primary_read(
        truth, cm.PRIMARY_LABEL, "move_age", "99-100")["unavailable"]


# ---------------------------------------------------------------------------
# the truth table as a live dependency
# ---------------------------------------------------------------------------

def test_absent_truth_table_degrades_loudly_and_never_falls_back(tmp_path):
    """The whole point of st-em4r: no table, no number. Not the old constants.

    The retired pooled percentages (25/49/65/73 and 33/57/74) must not appear
    anywhere in the rendered pane, because appearing is exactly the failure the
    audit found — a confident integer describing an event nobody measured.
    """
    t = cm.TruthTable(tmp_path / "nope.json")
    t.refresh()
    assert t.error and "truth table absent" in t.error
    read = cm.primary_read(t, cm.PRIMARY_LABEL, "move_age", "40+")
    assert "truth table absent" in read["unavailable"]

    frame = dict(ts=datetime(2026, 8, 4, 9, 30, tzinfo=CT).isoformat(),
                 errors=[], last_candle="09:30", stale_min=0.4,
                 move=cm.primary_move(synth_closes(50, 10)),
                 traces_raw=dict(tick=137.0, add10=None, vix5=0.12),
                 traces=dict(tick=137.0, add=None, vix=-0.12),
                 score=2, score_mode=2, primary=read,
                 secondary=cm.secondary_read(t, 2, 2),
                 levels=dict(spx=7646.7, vix=16.3, vvix=89.3, term=-1.7))
    text = plain(cm.render(frame))
    assert "No measured probability" in text
    for retired in ("25%", "49%", "65%", "73%", "33%", "57%", "74%"):
        assert retired not in text


def test_truth_table_reloads_when_the_file_changes(tmp_path):
    """A study re-run mid-session must reach the pane without a restart."""
    p = tmp_path / "truth.json"
    doc = dict(labels={"L": {"question": "Q?"}},
               base_rates={"L": {"all": {"all": dict(p=0.5, ci_lo=0.4,
                                                     ci_hi=0.6, n=10,
                                                     n_days=2)}}},
               auc={}, score_conditional=[])
    p.write_text(json.dumps(doc))
    t = cm.TruthTable(p)
    t.refresh()
    assert t.cell("L", "all", "all")["p"] == 0.5
    doc["base_rates"]["L"]["all"]["all"]["p"] = 0.7
    p.write_text(json.dumps(doc) + " ")     # size differs -> stamp differs
    t.refresh()
    assert t.cell("L", "all", "all")["p"] == 0.7


def test_malformed_truth_table_never_raises(tmp_path):
    p = tmp_path / "truth.json"
    p.write_text("{not json")
    t = cm.TruthTable(p)
    t.refresh()
    assert t.data is None and "unreadable" in t.error
    p.write_text(json.dumps({"labels": {}}))    # valid JSON, wrong shape
    t.refresh()
    assert t.data is None and "unreadable" in t.error


# ---------------------------------------------------------------------------
# wording: every sentence names the label its number was measured on
# ---------------------------------------------------------------------------

def test_secondary_names_the_standing_extreme_label(truth, truth_json):
    """§3.2: the convergence score's sentence is its OWN label, verbatim."""
    read = cm.secondary_read(truth, 2, 2)
    assert read["label"] == "orig_ext2_beyond_standing_extreme"
    assert read["question"] == (
        truth_json["labels"]["orig_ext2_beyond_standing_extreme"]["question"])
    assert "standing extreme" in read["question"] or "high-water" in read["question"]


def test_retired_sentence_never_reaches_the_pane(truth):
    """The exact string audit §3.2 quotes must not survive anywhere."""
    for score in (0, 1, 2):
        text = plain(cm.render(make_frame(truth, score=score, mode=2)))
        assert "extends 2+ pts in the next 15 min" not in text
        assert "extends 2+" not in text


def test_pane_says_the_score_does_not_grade_the_decision(truth):
    """The score stays on the pane only with its own AUC on the decision label."""
    read = cm.secondary_read(truth, 3, 3)
    assert read["primary_label"] == cm.PRIMARY_LABEL
    assert 0.40 < read["auc_on_primary"] < 0.60      # a coin flip, and shown as one
    text = plain(cm.render(make_frame(truth, score=3, mode=3)))
    assert "coin flip" in text
    assert "breakout re-entry trigger" in text


def test_headline_sentence_is_the_labels_question(truth, truth_json):
    text = plain(cm.render(make_frame(truth)))
    assert truth_json["labels"][cm.PRIMARY_LABEL]["question"] in text


def test_every_displayed_probability_carries_an_interval(truth):
    """§4.1: a bare integer hides a 15-30 point wide cell."""
    text = plain(cm.render(make_frame(truth, score=2, mode=2)))
    pct_lines = [ln for ln in text.splitlines()
                 if re.search(r"\d+\.\d%", ln)]
    assert pct_lines, "no probability rendered at all"
    for ln in pct_lines:
        if "CI [" in ln or "no measured interval" in ln:
            continue
        # split / cost-of-being-wrong lines are conditional decompositions of a
        # cell that already showed its interval on the line above
        assert ("ends:" in ln or "what being wrong costs" in ln
                or "cross-check" in ln), f"unbounded probability: {ln!r}"


def test_vol_quadrants_render_as_tags_not_probabilities(truth):
    """§2.4: those percentages are pooled, interval-free and mostly the ES sign."""
    frame = make_frame(truth)
    frame["esvix"] = cm.ESVIX_P[(1, "es+", "vix+")]
    frame["volcx"] = cm.VOLCX_P[(1, "vix+", "vvix-")]
    text = plain(cm.render(frame))
    assert "rally with vol bid — suspicious" in text
    assert "53% state" not in text and "49% state" not in text
    assert "Tags only" in text


# ---------------------------------------------------------------------------
# the §4.1 numbers actually reaching the pane
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode,score,p,lo,hi", [
    (3, 0, 0.2527, 0.1465, 0.4106),
    (3, 3, 0.7291, 0.6287, 0.8178),
    (2, 0, 0.3294, 0.2212, 0.4704),
    (2, 2, 0.7412, 0.6588, 0.8119),
])
def test_score_cells_match_the_audit_4_1_table(truth, mode, score, p, lo, hi):
    """Audit §4.1 point estimates reproduce exactly; the CIs to bootstrap noise.

    The report's own draw gives [.147, .397] / [.628, .815] / [.221, .461] /
    [.656, .810]; this table's draw (seed 20260804, 4,000 day-block resamples)
    lands within a point and a half on every bound. The point estimates are
    identical, so the difference is RNG and not a different computation.
    """
    read = cm.secondary_read(truth, score, mode)
    assert read["p"] == pytest.approx(p, abs=1e-4)
    assert read["ci_lo"] == pytest.approx(lo, abs=1e-4)
    assert read["ci_hi"] == pytest.approx(hi, abs=1e-4)


def test_original_label_clock_collapse_reproduces(truth):
    """Audit §1.3: 91.4% in the first 10 minutes, 42.2% after 40."""
    assert cm.primary_read(truth, cm.SECONDARY_LABEL, "move_age",
                           "0-10")["p"] == pytest.approx(0.9136, abs=1e-4)
    assert cm.primary_read(truth, cm.SECONDARY_LABEL, "move_age",
                           "40+")["p"] == pytest.approx(0.4222, abs=1e-4)


def test_the_sentence_the_old_pane_displayed_is_a_919_base_rate(truth):
    """Audit §3.2: 'gain 2 pts from here in 15 min' is near-certain anyway."""
    assert cm.primary_read(truth, "reach2_any_adverse", "all",
                           "all")["p"] == pytest.approx(0.9187, abs=1e-4)


# ---------------------------------------------------------------------------
# contested direction (§3.4)
# ---------------------------------------------------------------------------

def test_contested_flags_the_2026_07_30_margin():
    """The audit's worst case: dn 47.50 vs up 46.75, a 0.75-pt margin."""
    mv = cm.primary_move(synth_closes(47.5, 46.75))
    assert mv["dir"] == -1
    assert mv["drawdown"] == 47.5 and mv["drawup"] == 46.75
    assert mv["margin"] == 0.75
    assert mv["runner_ratio"] == pytest.approx(0.984, abs=1e-3)
    assert mv["contested"] is True


def test_a_clear_day_is_not_contested():
    """2026-07-27: dd 91.00 vs du 38.75 — nothing ambiguous about it."""
    mv = cm.primary_move(synth_closes(91, 38.75))
    assert mv["dir"] == -1 and mv["contested"] is False
    assert mv["runner_ratio"] == pytest.approx(0.426, abs=1e-3)


def test_contested_threshold_is_inclusive_at_20_percent():
    """Exactly 20% counts as contested — the flag errs toward warning.

    Audit §3.4 reports 5 of 22 days inside 20%; recomputing from the corpus
    gives 6, the extra being 2026-07-03 at a ratio of exactly 0.800. A warning
    that fires on the tie is the safe side of that boundary.
    """
    assert cm.CONTESTED_RATIO == 0.80
    assert cm.primary_move(synth_closes(10, 8))["contested"] is True
    assert cm.primary_move(synth_closes(10, 7))["contested"] is False


def test_contested_banner_and_its_consequence_render(truth):
    mv = cm.primary_move(synth_closes(47.5, 46.75))
    text = plain(cm.render(make_frame(truth, move=mv)))
    assert "CONTESTED DIRECTION" in text
    assert "47.50" in text and "46.75" in text
    assert "unstable" in text and "sign-flip" in text


def test_direction_flip_is_marked(truth):
    mv = cm.primary_move(synth_closes(47.5, 46.75))
    text = plain(cm.render(make_frame(truth, move=mv, prev_dir=1)))
    assert "DIRECTION FLIPPED" in text and "up → dn" in text


def test_primary_move_keeps_every_legacy_journal_field():
    """The journal schema may gain fields; it may never lose one."""
    mv = cm.primary_move(synth_closes(30, 10))
    for k in ("size", "start_t", "end_t", "start_p", "end_p", "dir"):
        assert k in mv
    for k in ("drawdown", "drawup", "runner_up", "margin", "runner_ratio",
              "contested"):
        assert k in mv


def test_preopen_and_stale_banners_survive_the_rework(truth):
    """Both guards predate st-em4r and are load-bearing (st-t7cf, st-byrg)."""
    pre = plain(cm.render(dict(ts=datetime(2026, 8, 4, 7, 0, tzinfo=CT).isoformat(),
                               preopen=True, opens_in_min=90)))
    assert "Pre-open" in pre and "in 90 min" in pre
    frame = make_frame(truth)
    frame["stale_min"] = 143.1
    frame["last_candle"] = "14:59"
    assert "*** STALE" in plain(cm.render(frame))


# ---------------------------------------------------------------------------
# journal scorer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label,expected", [
    ("reach5_before_adverse4", (5.0, 4.0)),
    ("reach2_before_adverse8", (2.0, 8.0)),
    ("reach8_any_adverse", (8.0, None)),
    ("orig_ext2_beyond_standing_extreme", None),
    ("", None), (None, None),
])
def test_parse_label(label, expected):
    assert smj.parse_label(label) == expected


def tape_of(prices, start=None, step_s=10):
    start = start or datetime(2026, 8, 4, 9, 0, tzinfo=CT)
    ts = [start + timedelta(seconds=step_s * i) for i in range(len(prices))]
    return smj.Tape(ts, list(prices), "es-ticks", "synthetic")


def test_resolve_barrier_target_before_stop():
    """Path order is the whole point: +5 arrives before -4, so it is a win."""
    t = tape_of([100, 102, 105, 96])
    out, detail = smj.resolve_barrier(t, t.ts[0], 100.0, 1, 5.0, 4.0)
    assert out is True and detail["hit_stop_at"] is None


def test_resolve_barrier_stop_before_target():
    t = tape_of([100, 98, 95, 110])
    out, detail = smj.resolve_barrier(t, t.ts[0], 100.0, 1, 5.0, 4.0)
    assert out is False and detail["hit_target_at"] is None


def test_resolve_barrier_respects_direction():
    """A down move pays when price falls; the sign must not be assumed."""
    t = tape_of([100, 94])
    assert smj.resolve_barrier(t, t.ts[0], 100.0, -1, 5.0, 4.0)[0] is True
    assert smj.resolve_barrier(t, t.ts[0], 100.0, 1, 5.0, 4.0)[0] is False


def test_truncated_window_is_unresolved_not_a_miss():
    """A window running past the end of the tape cannot say FALSE."""
    t = tape_of([100, 100, 100], step_s=10)        # 20 s of tape, 15 min needed
    out, detail = smj.resolve_barrier(t, t.ts[0], 100.0, 1, 5.0, 4.0)
    assert out is None and detail["truncated"] is True


def test_truncated_window_still_resolves_a_hit():
    t = tape_of([100, 106])
    assert smj.resolve_barrier(t, t.ts[0], 100.0, 1, 5.0, 4.0)[0] is True


def test_full_window_with_no_touch_is_a_miss():
    start = datetime(2026, 8, 4, 9, 0, tzinfo=CT)
    t = tape_of([100.0] * 200, start=start, step_s=10)   # ~33 min of flat tape
    out, detail = smj.resolve_barrier(t, start, 100.0, 1, 5.0, 4.0)
    assert out is False and detail["truncated"] is False


def test_legacy_frame_is_graded_against_both_of_its_meanings():
    """Audit §3.2, live: one integer, two events, both scored."""
    claims = smj.claims_of(dict(score=0, score_mode=2))
    names = {c["name"]: c for c in claims}
    assert set(names) == {"legacy_sentence", "legacy_number"}
    assert names["legacy_sentence"]["p"] == names["legacy_number"]["p"] == 0.33
    assert names["legacy_sentence"]["label"] == "reach2_any_adverse"
    assert names["legacy_number"]["label"] == "orig_ext2_beyond_standing_extreme"


def test_new_schema_frame_grades_the_displayed_headline():
    frame = dict(primary=dict(label="reach5_before_adverse4", p=0.478,
                              family="move_age", bucket="40+"),
                 secondary=dict(label="orig_ext2_beyond_standing_extreme",
                                p=0.5721, score=1, mode=2),
                 score=1, score_mode=2)
    claims = {c["name"]: c for c in smj.claims_of(frame)}
    assert set(claims) == {"primary", "secondary"}     # no legacy double-count
    assert (claims["primary"]["target"], claims["primary"]["stop"]) == (5.0, 4.0)
    assert claims["primary"]["bucket"] == "move_age:40+"


def test_independent_windows_counts_non_overlapping_looks():
    base = datetime(2026, 8, 4, 9, 0, tzinfo=CT)
    rows = [dict(ts=(base + timedelta(seconds=30 * i)).isoformat())
            for i in range(60)]                       # 30 min of 30 s frames
    assert smj.independent_windows(rows) == 2
    assert smj.independent_windows([]) == 0


def test_dedup_by_minute_keeps_the_first_of_each_minute():
    base = datetime(2026, 8, 4, 9, 0, tzinfo=CT)
    rows = [dict(ts=(base + timedelta(seconds=30 * i)).isoformat(), i=i)
            for i in range(6)]
    kept = smj.dedup_by_minute(rows)
    assert [r["i"] for r in kept] == [0, 2, 4]


def test_grade_frame_end_to_end_and_calibrates():
    """A frame that displayed 47.8% and then paid, graded on a real path."""
    start = datetime(2026, 8, 4, 9, 0, tzinfo=CT)
    # up move: 100 -> 108 inside the window, never 4 pts back
    tape = tape_of([100 + 0.1 * i for i in range(120)], start=start, step_s=5)
    frame = dict(ts=start.isoformat(),
                 move=dict(dir=1, size=40.0, start_t=(
                     start - timedelta(minutes=45)).isoformat()),
                 primary=dict(label="reach5_before_adverse4", p=0.478,
                              family="move_age", bucket="40+"),
                 score=1, score_mode=2, stale_min=0.3,
                 buckets=dict(age_min=45.0, move_age="40+"))
    g = smj.grade_frame(frame, tape)
    assert g["anchor"] == 100.0 and g["dir"] == 1
    claim = next(c for c in g["claims"] if c["name"] == "primary")
    assert claim["outcome"] is True
    cal = smj.calibration([g])
    assert cal["primary"]["overall"]["realized"] == 1.0
    assert cal["primary"]["overall"]["predicted"] == 0.478
    assert cal["primary"]["by_bucket"]["move_age:40+"]["n"] == 1


def test_grade_frame_skips_preopen_and_moveless_frames():
    tape = tape_of([100, 101])
    assert smj.grade_frame(dict(ts="x", preopen=True), tape) is None
    assert smj.grade_frame(dict(ts="x", no_data=True), tape) is None
    assert smj.grade_frame(dict(ts="x"), tape) is None


def test_frames_past_the_end_of_the_tape_are_skipped_not_scored():
    """The 2026-08-03 shape: 729 after-hours frames, nothing forward."""
    start = datetime(2026, 8, 4, 9, 0, tzinfo=CT)
    tape = tape_of([100, 101], start=start)
    frame = dict(ts=(start + timedelta(hours=6)).isoformat(),
                 move=dict(dir=1, size=40.0, start_t=start.isoformat()),
                 score=1, score_mode=2)
    assert smj.grade_frame(frame, tape)["skipped"]


def test_journal_tape_fallback_is_marked_as_not_path_ordered():
    rows = [dict(ts=datetime(2026, 8, 4, 9, 0, tzinfo=CT).isoformat(),
                 levels=dict(spx=7600.0)),
            dict(ts=datetime(2026, 8, 4, 9, 0, 30, tzinfo=CT).isoformat(),
                 levels=dict(spx=7605.0)),
            dict(ts="not-a-timestamp", levels=dict(spx=1.0))]
    t = smj.load_journal_tape(rows)
    assert len(t) == 2 and t.path_ordered is False
    assert "NOT recoverable" in t.note


def test_retired_constants_live_only_in_the_scorer():
    """They are gradeable history, not a display fallback.

    If these reappear in continuation_meter.py the audit's §3.2 defect is back.
    """
    assert smj.RETIRED_SCORE_P == {0: 0.25, 1: 0.49, 2: 0.65, 3: 0.73}
    assert smj.RETIRED_SCORE2_P == {0: 0.33, 1: 0.57, 2: 0.74}
    src = Path(cm.__file__).read_text()
    assert "SCORE_P" not in src and "SCORE2_P" not in src
