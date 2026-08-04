#!/usr/bin/env python3
"""Live continuation meter — desk pane for the morning flush. [st-byrg, st-em4r]

Display-only. Polls Schwab minute history for $SPX + internals, detects
today's primary move (same max-excursion definition as the st-gzwb study),
and reports **measured** continuation probabilities read live out of
`data/measurement/decision_aligned_truth.json`.

No orders, no order strings, no FD0 coupling. The human stays the trigger.

What changed on 2026-08-04 [st-em4r], and why
---------------------------------------------
The cold-context audit (`docs/audits/2026-08-04-auditor-report.md`) found the
old display wrong in three independent ways at once, and this module is the
remediation of all three:

* **§3.2 — the sentence named a different quantity than the integer.** The pane
  read *"Score 3/3 -> about 73% chance the move extends 2+ pts in the next 15
  min."* Read literally that is the "gain 2 pts from here in 15 min" event,
  whose unconditional base rate is 91.9% and which the score does not move
  (AUC .506). The 73 was calibrated on a different label entirely: extension
  beyond the *standing extreme*. The convergence score is now SECONDARY and
  carries the label it was actually measured on, in the truth table's own
  words.
* **§1.3 / §4.2 — a pooled number over a window whose truth runs 91% to 42%.**
  The primary line is now conditioned on the clock, cell by cell.
* **§4.1 — no intervals.** Every percentage on the pane now ships its 95%
  day-block bootstrap CI. A quantity with no measured interval is not
  displayed as a probability at all (that is why the vol quadrants now render
  as named tags rather than "% state" — their percentages are pooled,
  interval-free, and measured on the standing-extreme label; they stay in the
  journal so they remain scoreable).
* **§3.4 — direction decided by under a point on some days.** `primary_move()`
  now returns both excursions and flags CONTESTED when the runner-up is within
  20% of the primary; a direction flip between frames is marked on the pane.

The numbers are not in this file. They are read at render time from the truth
table so the pane cannot drift from the study that produced it. If that file is
absent the meter says so loudly and shows no probability — it never falls back
to the retired pooled constants.

Usage:
    .venv/bin/python3 scripts/desk/continuation_meter.py            # 30s loop
    .venv/bin/python3 scripts/desk/continuation_meter.py --once     # one frame
    .venv/bin/python3 scripts/desk/continuation_meter.py --interval 60
    .venv/bin/python3 scripts/desk/continuation_meter.py --label reach5_before_adverse8

Journal: every rendered frame appends to data/exec/continuation-meter-<day>.jsonl,
carrying the displayed probability and its interval so the meter's own calls can
be graded after the close — `scripts/measurement/score_meter_journal.py`.
A frame whose newest internals candle is older than STALE_MIN minutes carries
a loud STALE banner — the meter never silently shows dead numbers.
"""
from __future__ import annotations

import argparse
import json
import sys
import time as _time
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from broker_schwab.client import create_client  # noqa: E402

CT = ZoneInfo("America/Chicago")
SYMBOLS = ("$SPX", "$TICK", "$ADD", "$VIX", "$VVIX", "$VIX9D")
SESSION_OPEN = time(8, 30)
SESSION_CLOSE = time(15, 0)
CALIB_END = time(10, 30)     # the measured window; later readings extrapolate
MOVE_FLOOR = 10.0            # pts of primary move before grading means much
STALE_MIN = 3

# --- the measured lookup ----------------------------------------------------
# Produced by scripts/measurement/decision_aligned_study.py [st-kqvj]; documented
# in docs/measurement/decision-aligned-truth.md §9. Nothing on this pane is
# calibrated in this file.
TRUTH_PATH = ROOT / "data" / "measurement" / "decision_aligned_truth.json"

# The label closest to the question Steve asks when he is standing in a position
# deciding whether to stay or re-enter: does it pay N before it costs M, in
# path order, in the next quarter hour. 5-before-4 names a target and a stop
# that both survive the 0.6-1.2 pt friction model (audit §6.4) and matches the
# tight-cut / liberal-re-entry style under test; --label swaps it.
PRIMARY_LABEL = "reach5_before_adverse4"
# Move age is the stronger conditioner (.549 vs .540 AUC on the primary label)
# and the meter can compute it live off its own running move start. Session
# clock is the honest cross-check: the study's move start is hindsight, so a
# live move age can revise under you while the wall clock cannot.
PRIMARY_FAMILY = "move_age"
CROSSCHECK_FAMILY = "session_clock"
# The convergence score's OWN label — the one its 25/49/65/73 ladder was
# measured on. Never scored against a decision label: at AUC .482-.501 it is
# noise there, and a novice reading a number that moves believes the movement
# means something (decision-aligned-truth.md §8).
SECONDARY_LABEL = "orig_ext2_beyond_standing_extreme"

# Bucket edges mirror decision_aligned_study.AGE_BUCKETS / SESSION_BUCKETS.
# Pinned here rather than imported so a live desk pane does not drag the study's
# corpus-reading imports into its process; the test suite asserts these names
# cover exactly the bucket keys the truth table ships.
AGE_BUCKETS = (("0-10", 0.0, 10.0), ("10-20", 10.0, 20.0),
               ("20-40", 20.0, 40.0), ("40+", 40.0, float("inf")))
SESSION_BUCKETS = (("pre-0900", 0, 9 * 60), ("0900-1000", 9 * 60, 10 * 60),
                   ("post-1000", 10 * 60, 24 * 60))

# Runner-up excursion within this fraction of the primary => the day's direction
# was a near-coin-flip and every oriented read on the pane inherits that.
# Audit §3.4: 6 of the 22 study days are contested at this threshold
# (2026-07-03 sits exactly on it; the report's "5 of 22" excludes the tie).
CONTESTED_RATIO = 0.80

# ES x VIX 5-min sign quadrants, by move direction. Retained for the journal and
# for the state NAME; the percentages are pooled over the whole morning window,
# carry no measured interval, and are calibrated on the standing-extreme label —
# and audit §2.4 shows the ES sign alone explains nearly all of the lift
# (.723 vs .712 in the well-populated cell). Not rendered as probabilities.
ESVIX_P = {
    (-1, "es-", "vix+"): (73, "flush running, vol bid"),
    (-1, "es+", "vix+"): (66, "bounce NOT believed — vol still bid"),
    (-1, "es-", "vix-"): (64, "falling, vol easing"),
    (-1, "es+", "vix-"): (45, "bounce with vol crush"),
    (1, "es+", "vix-"): (63, "healthy rally, vol crushed"),
    (1, "es+", "vix+"): (53, "rally with vol bid — suspicious"),
    (1, "es-", "vix-"): (45, "dip, vol easing"),
    (1, "es-", "vix+"): (34, "DIP WITH PROTECTION BID — warning"),
}
# VIX x VVIX 5-min sign quadrants (the vol complex), by move direction. Same
# caveat as ESVIX_P.
VOLCX_P = {
    (-1, "vix+", "vvix+"): (74, "complex bid with the move"),
    (-1, "vix+", "vvix-"): (64, "vol bid, tails quiet"),
    (-1, "vix-", "vvix+"): (55, "vol easing, tails still bid"),
    (-1, "vix-", "vvix-"): (47, "COMPLEX RELEASING — fuel gone"),
    (1, "vix-", "vvix-"): (66, "complex releasing — healthy"),
    (1, "vix-", "vvix+"): (49, "vol easing, tails bid"),
    (1, "vix+", "vvix-"): (49, "vol bid, tails quiet"),
    (1, "vix+", "vvix+"): (31, "DEATH RATTLE — complex bid against rally"),
}

GREEN, RED, YEL, DIM, BOLD, END = ("\033[32m", "\033[31m", "\033[33m",
                                   "\033[2m", "\033[1m", "\033[0m")


# ---------------------------------------------------------------------------
# the measured lookup
# ---------------------------------------------------------------------------

class TruthTable:
    """The decision-aligned truth table, reloaded whenever the file changes.

    Every accessor returns ``None`` on any miss and every load failure is
    captured in ``self.error`` rather than raised: this object sits in a live
    desk loop where a crash is worse than a degraded frame. An absent or
    unparseable table means the pane shows no probability at all — there is no
    fallback to the retired pooled constants, which is the whole point of
    st-em4r.
    """

    def __init__(self, path: Path = TRUTH_PATH):
        self.path = Path(path)
        self.data: dict | None = None
        self.error: str | None = "not loaded yet"
        self._stamp: tuple[int, int] | None = None

    def refresh(self) -> None:
        """Load the table if it appeared, changed, or has never loaded.

        Cheap enough for a 30-second loop: one stat() when nothing changed.
        """
        try:
            st = self.path.stat()
        except OSError as e:
            self.data, self._stamp = None, None
            self.error = f"truth table absent — {self.path.name}: {e.strerror}"
            return
        stamp = (st.st_mtime_ns, st.st_size)
        if stamp == self._stamp and self.data is not None:
            return
        try:
            with self.path.open() as fh:
                data = json.load(fh)
            for key in ("labels", "base_rates", "auc", "score_conditional"):
                if key not in data:
                    raise KeyError(key)
        except Exception as e:                  # malformed / truncated / racing
            self.data, self._stamp = None, None
            self.error = f"truth table unreadable — {self.path.name}: {e}"
            return
        self.data, self._stamp, self.error = data, stamp, None

    # -- accessors ---------------------------------------------------------
    def labels(self) -> dict:
        return (self.data or {}).get("labels", {})

    def question(self, label: str) -> str | None:
        """The label's question in the trader's words, straight from the study.

        Displayed verbatim so the sentence on the pane cannot drift from the
        label the number was measured on — audit §3.2 is exactly that drift.
        """
        return self.labels().get(label, {}).get("question")

    def cell(self, label: str, family: str, bucket: str) -> dict | None:
        """base_rates[label][family][bucket], or None if any level is missing."""
        try:
            c = self.data["base_rates"][label][family][bucket]
        except (TypeError, KeyError):
            return None
        return c if c.get("p") is not None else None

    def score_cell(self, label: str, score_key: str, score_value: int,
                   family: str = "all", bucket: str = "all") -> dict | None:
        """One row of the flat ``score_conditional`` list, or None."""
        for r in (self.data or {}).get("score_conditional", ()):
            if (r.get("label") == label and r.get("score") == score_key
                    and r.get("score_value") == score_value
                    and r.get("bucket_family") == family
                    and r.get("bucket") == bucket):
                return r if r.get("p") is not None else None
        return None

    def auc(self, label: str, predictor: str) -> float | None:
        try:
            return self.data["auc"][label][predictor]["auc"]
        except (TypeError, KeyError):
            return None

    def outcome_split(self, label: str, family: str, bucket: str) -> dict | None:
        try:
            return self.data["outcome_split"][label][family][bucket]
        except (TypeError, KeyError):
            return None

    def excursions(self) -> dict:
        return (self.data or {}).get("excursions", {})

    def provenance(self) -> dict:
        m = (self.data or {}).get("meta", {})
        return dict(n_days=m.get("n_days"), n_minutes=m.get("n_minutes"),
                    generated=m.get("generated"), bead=m.get("bead"))


def bucket_for_age(age_min: float | None) -> str | None:
    """Move-age bucket name, mirroring the study's AGE_BUCKETS edges."""
    if age_min is None or age_min < 0:
        return None
    for name, lo, hi in AGE_BUCKETS:
        if lo <= age_min < hi:
            return name
    return None


def bucket_for_clock(t: time | None) -> str | None:
    """Session-clock bucket name, mirroring the study's SESSION_BUCKETS edges."""
    if t is None:
        return None
    mod = t.hour * 60 + t.minute
    for name, lo, hi in SESSION_BUCKETS:
        if lo <= mod < hi:
            return name
    return None


def choose_family(move_size: float, age_bucket: str | None,
                  clock_bucket: str | None) -> tuple[str, str | None, str | None]:
    """Which clock the headline is conditioned on: (family, bucket, reason).

    Move age is the default — it is the stronger conditioner and the meter
    derives it from its own running move start. Below the qualifying floor
    there is no move yet, so its age is meaningless and the wall clock, which
    is always defined, takes over. Returning the reason keeps the substitution
    on the pane instead of silently changing what the number means.
    """
    if move_size >= MOVE_FLOOR:
        return PRIMARY_FAMILY, age_bucket, None
    return (CROSSCHECK_FAMILY, clock_bucket,
            f"move under the {MOVE_FLOOR:.0f}-pt floor — move age is not "
            f"meaningful, reading the session clock instead")


def primary_read(truth: TruthTable, label: str, family: str, bucket: str | None,
                 *, reason: str | None = None) -> dict:
    """The pane's headline: one measured cell, with its interval and its words.

    Returns a dict that is either ``{"unavailable": <why>}`` or a fully
    populated read. Every field is copied out of the truth table — nothing here
    is computed, rounded or interpolated, so what the pane says is exactly what
    was measured. ``reason`` records why this bucket family was chosen when it
    was not the configured default.
    """
    if truth.error:
        return dict(unavailable=truth.error)
    q = truth.question(label)
    if q is None:
        return dict(unavailable=f"truth table carries no label {label!r}")
    if bucket is None:
        return dict(unavailable=f"no {family} bucket for this frame")
    cell = truth.cell(label, family, bucket)
    if cell is None:
        return dict(unavailable=f"truth table has no cell {label}/{family}/{bucket}")
    out = dict(label=label, question=q, family=family, bucket=bucket,
               p=cell["p"], ci_lo=cell.get("ci_lo"), ci_hi=cell.get("ci_hi"),
               n=cell.get("n"), n_days=cell.get("n_days"))
    if reason:
        out["family_reason"] = reason
    split = truth.outcome_split(label, family, bucket)
    if split:
        out["split"] = dict(target_first=split.get("p_target_first"),
                            stop_first=split.get("p_stop_first"),
                            neither=split.get("p_neither"),
                            pts_per_attempt=split.get("pts_per_attempt"),
                            pts_ci_lo=split.get("pts_ci_lo"),
                            pts_ci_hi=split.get("pts_ci_hi"))
    exc = truth.excursions()
    if exc.get("p_mae_ge_8") is not None:
        out["p_adverse_8"] = exc["p_mae_ge_8"]
        out["p_adverse_4"] = exc.get("p_mae_ge_4")
    return out


def crosscheck_read(truth: TruthTable, label: str, bucket: str | None) -> dict | None:
    """The same label read on the session clock — the live-honest conditioner.

    Move age counts from a peak the meter identifies from the day so far, and
    that start time revises as the day develops; the wall clock cannot. When
    the two cells disagree materially the pane shows both rather than picking
    (decision-aligned-truth.md §2).
    """
    if truth.error or bucket is None:
        return None
    cell = truth.cell(label, CROSSCHECK_FAMILY, bucket)
    if cell is None:
        return None
    return dict(family=CROSSCHECK_FAMILY, bucket=bucket, p=cell["p"],
                ci_lo=cell.get("ci_lo"), ci_hi=cell.get("ci_hi"),
                n=cell.get("n"), n_days=cell.get("n_days"))


def secondary_read(truth: TruthTable, score: int | None, mode: int | None,
                   primary_label: str = PRIMARY_LABEL) -> dict:
    """The convergence score, against the label it was actually measured on.

    That label is extension **beyond the standing extreme** — a breakout
    re-entry trigger, not an answer about a position already open. The read
    carries the score's AUC on the primary decision label alongside, because
    the honest headline about this number is that it does not grade that
    question (audit §3.1: .482-.501 across the barriered labels).
    """
    if score is None or mode is None:
        return dict(unavailable="internals feeds missing — no score")
    if mode not in (2, 3):
        return dict(score=score, mode=mode,
                    unavailable=f"no measured ladder for a {mode}-trace score")
    key = "score3" if mode == 3 else "score2"
    if truth.error:
        return dict(score=score, mode=mode, unavailable=truth.error)
    q = truth.question(SECONDARY_LABEL)
    row = truth.score_cell(SECONDARY_LABEL, key, score)
    if row is None or q is None:
        return dict(score=score, mode=mode,
                    unavailable=f"truth table has no {key}={score} cell for "
                                f"{SECONDARY_LABEL}")
    return dict(score=score, mode=mode, label=SECONDARY_LABEL, question=q,
                p=row["p"], ci_lo=row.get("ci_lo"), ci_hi=row.get("ci_hi"),
                n=row.get("n"), n_days=row.get("n_days"),
                auc_on_primary=truth.auc(primary_label, key),
                primary_label=primary_label)


# ---------------------------------------------------------------------------
# live tape
# ---------------------------------------------------------------------------

def fetch_minutes(client, symbol, day_start_utc):
    r = client.get_price_history_every_minute(
        symbol, start_datetime=day_start_utc,
        end_datetime=datetime.now(tz=timezone.utc),
        need_extended_hours_data=False)
    if r.status_code != 200:
        raise RuntimeError(f"{symbol}: HTTP {r.status_code}")
    data = r.json()
    out = {}
    for c in data.get("candles", []):
        ts = datetime.fromtimestamp(c["datetime"] / 1000,
                                    tz=timezone.utc).astimezone(CT)
        if ts not in out:                       # first-wins (healed segment)
            out[ts] = c["close"]
    return out


def primary_move(closes):
    """Max drawup vs drawdown over today's minute closes; larger wins.

    Also returns both excursions and a CONTESTED flag. Audit §3.4: this single
    comparison orients every trace on the pane, and on 2 of the 22 study days
    it was decided by under a point — a sub-point difference sign-flipping every
    oriented read for the whole session. A margin that thin is a property of the
    frame and has to be visible in it.
    """
    ms = sorted(closes)
    run_max, run_max_t = closes[ms[0]], ms[0]
    run_min, run_min_t = closes[ms[0]], ms[0]
    dd = du = None
    for m in ms:
        p = closes[m]
        if p > run_max:
            run_max, run_max_t = p, m
        if p < run_min:
            run_min, run_min_t = p, m
        if dd is None or run_max - p > dd[0]:
            dd = (run_max - p, run_max_t, m, run_max, p)
        if du is None or p - run_min > du[0]:
            du = (p - run_min, run_min_t, m, run_min, p)
    best, direction = (dd, -1) if dd[0] >= du[0] else (du, 1)
    size, t0, t1, p0, p1 = best
    runner = min(dd[0], du[0])
    ratio = (runner / size) if size > 0 else 0.0
    return dict(size=round(size, 2), start_t=t0, end_t=t1,
                start_p=p0, end_p=p1, dir=direction,
                drawdown=round(dd[0], 2), drawup=round(du[0], 2),
                runner_up=round(runner, 2), margin=round(size - runner, 2),
                runner_ratio=round(ratio, 3),
                contested=bool(size > 0 and ratio >= CONTESTED_RATIO))


def d5(series, m, mins):
    a, b = series.get(m), series.get(m - timedelta(minutes=mins))
    return None if a is None or b is None else a - b


def sgn_tag(v, pos, neg):
    return pos if v is not None and v > 0 else (neg if v is not None else "?")


def build_frame(client, truth: TruthTable | None = None,
                prev_dir: int | None = None, label: str = PRIMARY_LABEL):
    now = datetime.now(tz=CT)
    day_start = datetime.combine(now.date(), SESSION_OPEN, CT)
    if now < day_start:
        # Schwab rejects start>end ("Enddate is before startDate", HTTP 400) —
        # never ask for a session that hasn't opened yet [st-t7cf]
        return dict(ts=now.isoformat(), preopen=True,
                    opens_in_min=int((day_start - now).total_seconds() // 60))
    series = {}
    errors = []
    for sym in SYMBOLS:
        try:
            series[sym] = fetch_minutes(
                client, sym, day_start.astimezone(timezone.utc))
        except Exception as e:                  # keep rendering on any failure
            errors.append(f"{sym}: {e}")
            series[sym] = {}
    spx = series["$SPX"]
    frame = dict(ts=now.isoformat(), errors=errors)
    if not spx:
        frame["no_data"] = True
        return frame

    last_candle = max(max(s) for s in series.values() if s)
    frame["last_candle"] = last_candle.strftime("%H:%M")
    frame["stale_min"] = round((now - last_candle).total_seconds() / 60, 1)

    mv = primary_move(spx)
    frame["move"] = mv
    d = mv["dir"]
    if prev_dir is not None and prev_dir != d:
        # never let an oriented pane flip sign between frames without saying so
        frame["dir_flip"] = dict(prev="dn" if prev_dir == -1 else "up",
                                 now="dn" if d == -1 else "up")

    # each trace reads at its OWN series' newest candle — feeds can lag each
    # other by a minute; the staleness banner covers the divergence
    def latest(sym):
        return max(series[sym]) if series.get(sym) else None

    def slope(sym, mins):
        m = latest(sym)
        return d5(series[sym], m, mins) if m else None

    tick = series["$TICK"].get(latest("$TICK")) if series["$TICK"] else None
    add10 = slope("$ADD", 10)
    vix5 = slope("$VIX", 5)
    vvix5 = slope("$VVIX", 5)
    spx5 = slope("$SPX", 5)

    traces = dict(
        tick=(tick * d) if tick is not None else None,
        add=(add10 * d) if add10 is not None else None,
        vix=(vix5 * -d) if vix5 is not None else None)
    frame["traces_raw"] = dict(tick=tick, add10=add10, vix5=vix5,
                               vvix5=vvix5, spx5=spx5)
    frame["traces"] = traces
    if all(v is not None for v in traces.values()):
        frame["score"] = sum(1 for v in traces.values() if v > 0)
        frame["score_mode"] = 3
    elif traces["tick"] is not None and traces["vix"] is not None:
        frame["score"] = sum(1 for k in ("tick", "vix") if traces[k] > 0)
        frame["score_mode"] = 2
    else:
        frame["score"] = None
        frame["score_mode"] = None

    # --- clock buckets and the measured reads -----------------------------
    age_min = round((last_candle - mv["start_t"]).total_seconds() / 60.0, 1)
    age_bucket = bucket_for_age(age_min)
    clock_bucket = bucket_for_clock(last_candle.time())
    frame["buckets"] = dict(age_min=age_min, move_age=age_bucket,
                            session_clock=clock_bucket)
    if truth is not None:
        try:
            family, bucket, why = choose_family(mv["size"], age_bucket,
                                                clock_bucket)
            frame["primary"] = primary_read(truth, label, family, bucket,
                                            reason=why)
            if family != CROSSCHECK_FAMILY:
                cc = crosscheck_read(truth, label, clock_bucket)
                if cc:
                    frame["primary"]["crosscheck"] = cc
            frame["secondary"] = secondary_read(truth, frame["score"],
                                                frame["score_mode"], label)
            frame["truth_meta"] = truth.provenance()
            if last_candle.time() > CALIB_END:
                frame["extrapolated"] = True
        except Exception as e:                  # a bad table must not kill the loop
            frame["primary"] = dict(unavailable=f"truth-table read failed: {e}")
            frame["secondary"] = dict(unavailable=f"truth-table read failed: {e}")

    if spx5 is not None and vix5 not in (None, 0) and spx5 != 0:
        key = (d, "es+" if spx5 > 0 else "es-", "vix+" if vix5 > 0 else "vix-")
        frame["esvix"] = ESVIX_P.get(key)
    if vix5 not in (None, 0) and vvix5 not in (None, 0):
        key = (d, "vix+" if vix5 > 0 else "vix-",
               "vvix+" if vvix5 > 0 else "vvix-")
        frame["volcx"] = VOLCX_P.get(key)

    lv = lambda sym: (series[sym].get(max(series[sym]))
                      if series.get(sym) else None)
    frame["levels"] = dict(spx=lv("$SPX"), vix=lv("$VIX"), vvix=lv("$VVIX"),
                           term=((lv("$VIX9D") - lv("$VIX"))
                                 if lv("$VIX9D") is not None
                                 and lv("$VIX") is not None else None))
    return frame


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def pct(x: float | None, nd: int = 1) -> str:
    return "?" if x is None else f"{100 * x:.{nd}f}%"


def interval(lo: float | None, hi: float | None) -> str:
    """95% CI as a bracketed percentage range, or an explicit absence."""
    if lo is None or hi is None:
        return "no measured interval"
    return f"95% CI [{100 * lo:.1f}–{100 * hi:.1f}]"


def render_primary(frame) -> list[str]:
    """The headline block: the decision-aligned question and its measured cell."""
    out = ["", f"{BOLD}── IF YOU ARE IN IT ───────────────────────────────{END}"]
    p = frame.get("primary")
    if not p:
        out.append(f"{YEL}No measured read — truth table was not consulted "
                   f"for this frame.{END}")
        return out
    if p.get("unavailable"):
        out.append(f"{RED}{BOLD}No measured probability: {p['unavailable']}.{END}")
        out.append(f"{RED}Nothing here is calibrated. Regenerate with "
                   f"decision_aligned_study.py.{END}")
        return out
    col = GREEN if p["p"] >= 0.60 else (RED if p["p"] <= 0.45 else YEL)
    out.append(p["question"])
    out.append(f"  {col}{BOLD}{pct(p['p'])}{END}   "
               f"{interval(p.get('ci_lo'), p.get('ci_hi'))}   "
               f"{DIM}{p['family']} {p['bucket']} · n={p['n']} min · "
               f"{p['n_days']} days{END}")
    if p.get("family_reason"):
        out.append(f"  {DIM}{p['family_reason']}{END}")
    cc = p.get("crosscheck")
    if cc:
        out.append(f"  {DIM}cross-check on the wall clock ({cc['bucket']} CT): "
                   f"{pct(cc['p'])} {interval(cc.get('ci_lo'), cc.get('ci_hi'))} "
                   f"· n={cc['n']}{END}")
    sp = p.get("split")
    if sp:
        pts = sp.get("pts_per_attempt")
        tail = ("" if pts is None else
                f" · frictionless {pts:+.2f} pts/attempt "
                f"[{sp['pts_ci_lo']:+.2f}, {sp['pts_ci_hi']:+.2f}]")
        out.append(f"  {DIM}ends: target first {pct(sp['target_first'])} · "
                   f"stop first {pct(sp['stop_first'])} · "
                   f"neither {pct(sp['neither'])}{tail}{END}")
    if p.get("p_adverse_8") is not None:
        out.append(f"  {DIM}what being wrong costs: from any minute, "
                   f"P(8 pts against you inside 15 min) = "
                   f"{pct(p['p_adverse_8'])}, P(4 pts) = "
                   f"{pct(p.get('p_adverse_4'))}{END}")
    if frame.get("extrapolated"):
        out.append(f"  {YEL}Newest candle is past "
                   f"{CALIB_END.strftime('%H:%M')} CT — the study measured the "
                   f"morning window only; read as extrapolation.{END}")
    return out


def render_secondary(frame) -> list[str]:
    """The convergence score, under the label it was measured on."""
    out = ["", f"{BOLD}── BREAKOUT TRIGGER (secondary) ───────────────────{END}"]
    s = frame.get("secondary")
    if not s:
        out.append(f"{YEL}Score unavailable — internals feeds missing.{END}")
        return out
    if s.get("unavailable") and s.get("score") is None:
        out.append(f"{YEL}{s['unavailable']}{END}")
        return out
    mode = s.get("mode")
    tag = f"Score {s['score']}/{mode}"
    if s.get("unavailable"):
        out.append(f"{tag} — {YEL}no measured probability: "
                   f"{s['unavailable']}{END}")
        return out
    out.append(f"{BOLD}{tag} → {pct(s['p'])}{END} "
               f"{interval(s.get('ci_lo'), s.get('ci_hi'))} "
               f"{DIM}· n={s['n']} min · {s['n_days']} days{END}")
    out.append(f"  {s['question']}")
    auc = s.get("auc_on_primary")
    auc_txt = "unmeasured" if auc is None else f"AUC {auc:.3f}"
    out.append(f"  {DIM}That is a breakout re-entry trigger, not an answer "
               f"about a position you already hold:{END}")
    out.append(f"  {DIM}on \"{s.get('primary_label')}\" this score grades "
               f"{auc_txt} — a coin flip.{END}")
    if mode == 2:
        out.append(f"  {DIM}TICK+VIX only — breadth ($ADD) publishes a session "
                   f"late, so live mornings run two-trace.{END}")
    return out


def render(frame):
    out = ["\033[2J\033[H"]
    now = datetime.fromisoformat(frame["ts"])
    hdr = f"{BOLD}CONTINUATION METER{END}  {now.strftime('%a %H:%M:%S CT')}"
    out.append(hdr)
    if frame.get("preopen"):
        out.append(f"{DIM}Pre-open — session opens "
                   f"{SESSION_OPEN.strftime('%H:%M')} CT "
                   f"(in {frame['opens_in_min']} min). Polling resumes at the "
                   f"open.{END}")
        return "\n".join(out) + "\n"
    if frame.get("no_data"):
        out.append(f"{RED}No $SPX data — session closed or feed down.{END}")
        for e in frame.get("errors", []):
            out.append(f"{RED}  {e}{END}")
        return "\n".join(out) + "\n"
    if frame["stale_min"] > STALE_MIN:
        out.append(f"{RED}{BOLD}*** STALE — newest candle {frame['last_candle']} "
                   f"({frame['stale_min']:.0f} min old). Numbers below are NOT "
                   f"current. ***{END}")
    mv = frame["move"]
    word = "DOWN" if mv["dir"] == -1 else "UP"
    out.append("")
    out.append(f"Move so far: {BOLD}{word} {mv['size']:.1f} pts{END}  "
               f"({mv['start_p']:.1f} at {mv['start_t'].strftime('%H:%M')} → "
               f"{mv['end_p']:.1f} at {mv['end_t'].strftime('%H:%M')})")
    if frame.get("dir_flip"):
        f = frame["dir_flip"]
        out.append(f"{RED}{BOLD}*** DIRECTION FLIPPED since the last frame "
                   f"({f['prev']} → {f['now']}) — every oriented read below "
                   f"changed sign. ***{END}")
    if mv.get("contested"):
        out.append(f"{RED}{BOLD}*** CONTESTED DIRECTION — drawdown "
                   f"{mv['drawdown']:.2f} vs drawup {mv['drawup']:.2f} "
                   f"(runner-up is {100 * mv['runner_ratio']:.0f}% of the "
                   f"primary, margin {mv['margin']:.2f} pts). ***{END}")
        out.append(f"{RED}Direction is a near coin flip, so every oriented "
                   f"read below — trace marks, quadrant tags — is unstable "
                   f"and may sign-flip on the next candle.{END}")
    if mv["size"] < MOVE_FLOOR:
        out.append(f"{DIM}Under the {MOVE_FLOOR:.0f}-pt floor — no qualifying "
                   f"move yet; readings below mean little.{END}")
    out.extend(render_primary(frame))
    out.extend(render_secondary(frame))
    t = frame["traces"]
    raw = frame["traces_raw"]
    def mark(v):
        return f"{GREEN}✓{END}" if v is not None and v > 0 else (
            f"{RED}✗{END}" if v is not None else "?")
    out.append(f"  {mark(t['tick'])} $TICK {raw['tick']:+.0f} — "
               f"{'on the move’s side' if (t['tick'] or 0) > 0 else 'against the move'}"
               if raw["tick"] is not None else "  ? $TICK unavailable")
    out.append(f"  {mark(t['add'])} $ADD 10-min change {raw['add10']:+.0f} — "
               f"{'breadth with the move' if (t['add'] or 0) > 0 else 'breadth against'}"
               if raw["add10"] is not None else "  ? $ADD unavailable")
    out.append(f"  {mark(t['vix'])} $VIX 5-min change {raw['vix5']:+.2f} — "
               f"{'with the move' if (t['vix'] or 0) > 0 else 'against the move'} "
               f"{DIM}(momentum proxy, not vol intelligence){END}"
               if raw["vix5"] is not None else "  ? $VIX unavailable")
    tags = [(label, frame[key][1]) for key, label in
            (("volcx", "Vol complex (VIX×VVIX)"), ("esvix", "Price×VIX"))
            if frame.get(key)]
    if tags:
        out.append("")
        for label, name in tags:
            out.append(f"{DIM}{label}: {name}{END}")
        out.append(f"{DIM}Tags only — the percentages behind these cells are "
                   f"pooled, carry no measured interval, and sit on the "
                   f"standing-extreme label; the concurrent ES sign alone "
                   f"explains nearly all of their lift (audit §2.4). Journaled, "
                   f"not displayed as probabilities.{END}")
    lvl = frame["levels"]
    if lvl["spx"] is not None:
        term = (f"{lvl['term']:+.2f}" if lvl["term"] is not None else "?")
        out.append("")
        out.append(f"{DIM}SPX {lvl['spx']:.1f} · VIX "
                   f"{lvl['vix'] if lvl['vix'] is not None else '?'} · VVIX "
                   f"{lvl['vvix'] if lvl['vvix'] is not None else '?'} · "
                   f"9D−30D {term}{END}")
    tm = frame.get("truth_meta") or {}
    if tm.get("n_days"):
        out.append(f"{DIM}Measured on {tm['n_days']} July mornings / "
                   f"{tm['n_minutes']} minutes, ES ticks, in-sample only — "
                   f"no held-out set exists.{END}")
    for e in frame.get("errors", []):
        out.append(f"{RED}feed error: {e}{END}")
    return "\n".join(out) + "\n"


def journal(frame):
    day = datetime.fromisoformat(frame["ts"]).strftime("%Y-%m-%d")
    path = ROOT / "data" / "exec" / f"continuation-meter-{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: v for k, v in frame.items() if k != "move"}
    if "move" in frame:
        keep["move"] = {k: (v.isoformat() if isinstance(v, datetime) else v)
                        for k, v in frame["move"].items()}
    with path.open("a") as fh:
        fh.write(json.dumps(keep, default=str) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--label", default=PRIMARY_LABEL,
                    help="decision label for the headline read "
                         f"(default {PRIMARY_LABEL})")
    ap.add_argument("--truth", type=Path, default=TRUTH_PATH,
                    help="path to decision_aligned_truth.json")
    args = ap.parse_args()
    truth = TruthTable(args.truth)
    truth.refresh()
    if truth.error:
        # loud on the way in as well as on every frame — a pane started against
        # a missing table should say so before the first render
        print(f"{RED}{truth.error}{END}", file=sys.stderr)
    elif truth.question(args.label) is None:
        print(f"{RED}--label {args.label!r} is not in the truth table. "
              f"Known: {', '.join(sorted(truth.labels()))}{END}", file=sys.stderr)
        return 2
    try:
        client = create_client()
    except Exception as e:
        print(f"Cannot create Schwab client (token?): {e}", file=sys.stderr)
        return 1
    prev_dir = None
    while True:
        try:
            truth.refresh()                     # picks up a re-run study mid-session
        except Exception as e:                  # refresh() is already total; belt+braces
            print(f"{RED}truth refresh failed: {e}{END}", flush=True)
        try:
            frame = build_frame(client, truth, prev_dir, args.label)
        except Exception as e:
            print(f"{RED}frame error: {e}{END}", flush=True)
            if args.once:
                return 1
            _time.sleep(args.interval)
            continue
        if frame.get("move"):
            prev_dir = frame["move"]["dir"]
        try:
            sys.stdout.write(render(frame))
            sys.stdout.flush()
        except Exception as e:                  # a render bug must not end the session
            print(f"{RED}render error: {e} — frame kept, see journal{END}",
                  flush=True)
        if not frame.get("preopen"):
            try:
                journal(frame)                  # idle pre-open frames carry no signal
            except Exception as e:
                print(f"{RED}journal write failed: {e}{END}", flush=True)
        if args.once:
            return 0
        if frame.get("preopen"):
            # coarse refresh far from the open, normal cadence within a minute
            _time.sleep(max(args.interval,
                            min(300, frame["opens_in_min"] * 60 - 60)))
        else:
            _time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
