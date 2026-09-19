"""The shadow lane — the registered rules run on the live record, at real time. [st-uaxf]

WHAT
    The replay lane scores a day after the fact. The shadow lane scores it as
    it happens: at each rule's fire minute, once that minute has closed on the
    wall clock, it builds the same lens state the replay builds — from the
    live corpus files as they stand at that moment (the Databento capture
    appends ``data/corpus/<today>/databento_glbx_es.jsonl`` all session; this
    module only READS it, never opens a second feed) — calls the same rule
    functions, and on a call records the entry the 14:45 close-watch Schwab
    snapshot gives (``schwab.jsonl``, written by the schwab-stages cron at
    14:45:05). After the close it prices the call with the same
    :func:`strader.blotter.legs.price_call` the replay uses and writes the row
    through the same composer (:func:`strader.blotter.replay.build_row`) with
    ``lane: shadow`` and the wall-clock stamps of when each step was seen.

    Two files per day under the blotter directory:

    ``shadow-<day>.jsonl``      the rows, same schema as ``replay-<day>.jsonl``
    ``shadow-<day>.log.jsonl``  the journal: one record per step at real time —
                                ``fire`` (state built, every rule's answer),
                                ``entry`` (the snapshot seen, or not), ``close``
                                (rows written), ``unpriced``

THE ACCEPTANCE — the determinism quarantine (co-itsck)
    Replaying the day afterwards must reproduce every answer the shadow
    journaled at the fire minute (rule id, fire minute, call — including "no
    call") and every shadow row's entry minute and contract. :func:`compare`
    does that against :func:`strader.blotter.replay.replay_day` and names
    each mismatch. A mismatch is a wall-clock or live-only read in a rule, or
    the live tape lagging the archive at the fire minute — either way the diff
    says which rule or row. A day on which no rule called anything is still a
    comparison: the replay must agree there was nothing to write
    (:func:`read_journal` gives the compare its side of that day; 2026-09-11,
    day 1, had no rows file and the first compare refused to run). One week
    of clean compares earns the systemd unit; until then this is hand-run
    (the 08-23 feeder crash, st-wnuk, is why).

THE ONLY CLOCK
    ``now_fn`` is the one place a wall clock is read, and it is injected so a
    test can drive a whole session in milliseconds. The rules never see it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Sequence
from zoneinfo import ZoneInfo

from strader.blotter import legs as L
from strader.blotter.replay import EVENTS_LOOKBACK_MIN, _events_before, build_row, replay_day
from strader.blotter.rows import LANE_SHADOW
from strader.blotter.rules import Rule
from strader.blotter.state import DEFAULT_CORPUS, DEFAULT_PARSED, day_inputs, state_at
from strader.marks.estimated import Calibration, minute_index

__all__ = ["CT", "FIRE_GRACE_S", "CLOSE_GRACE_S", "SNAPSHOT_WAIT_S", "ShadowReport",
           "run_shadow", "compare", "read_journal", "shadow_rows_path", "shadow_log_path", "COMPARE_KEYS",
           "ACCEPTANCE_DAYS", "REALTIME_SLACK_S", "DEFAULT_VERDICT_DIR", "verdict_path", "fire_lags_s",
           "write_verdict", "acceptance_streak"]

CT = ZoneInfo("America/Chicago")
FIRE_GRACE_S = 5          # seconds after a fire minute closes before the state is built
CLOSE_GRACE_S = 20        # seconds after the close before the rows are priced
SNAPSHOT_WAIT_S = 120     # how long to wait for the close-watch snapshot after a fire
SNAPSHOT_POLL_S = 5

#: Clean compares in a row before the lane earns its systemd unit (st-uaxf).
ACCEPTANCE_DAYS = 7
#: How late a fire may be seen and still count as having been seen at real time.
REALTIME_SLACK_S = 120
#: Where the wrapper records one verdict per day for the acceptance clock.
DEFAULT_VERDICT_DIR = Path("/var/moo/state/blotter-shadow")

#: What a replay must reproduce for a shadow row to count as clean.
COMPARE_KEYS = ("rule_id", "fire_ct", "call", "entry_minute", "occ_symbol")


def shadow_rows_path(out_dir: Path, day: str) -> Path:
    return Path(out_dir) / f"shadow-{day}.jsonl"


def shadow_log_path(out_dir: Path, day: str) -> Path:
    return Path(out_dir) / f"shadow-{day}.log.jsonl"


@dataclass
class ShadowReport:
    day: str
    rows: list[dict] = field(default_factory=list)
    journal: list[dict] = field(default_factory=list)
    fires: list[dict] = field(default_factory=list)
    unpriced: list[dict] = field(default_factory=list)
    skip: str | None = None


def _at(day: str, hhmm: str, plus_s: int = 0) -> datetime:
    """``day`` at ``HH:MM`` or ``HH:MM:SS`` Central, plus ``plus_s`` seconds."""
    y, m, d = (int(x) for x in day.split("-"))
    parts = [int(x) for x in hhmm.split(":")]
    h, mi = parts[0], parts[1]
    s = parts[2] if len(parts) > 2 else 0
    return datetime(y, m, d, h, mi, s, tzinfo=CT) + timedelta(seconds=plus_s)


def _wait_until(target: datetime, now_fn: Callable[[], datetime], sleep_fn: Callable[[float], None],
                step_s: float = 30.0) -> None:
    while True:
        remaining = (target - now_fn()).total_seconds()
        if remaining <= 0:
            return
        sleep_fn(min(step_s, remaining))


def run_shadow(day: str, rules: Sequence[Rule], *, corpus: Path = DEFAULT_CORPUS, parsed: Path = DEFAULT_PARSED,
               cal: Calibration | None, out_dir: Path, now_fn: Callable[[], datetime] = lambda: datetime.now(CT),
               sleep_fn: Callable[[float], None] | None = None, events: bool = True,
               fire_grace_s: int = FIRE_GRACE_S, close_grace_s: int = CLOSE_GRACE_S,
               snapshot_wait_s: int = SNAPSHOT_WAIT_S, snapshot_poll_s: float = SNAPSHOT_POLL_S,
               lookback_min: int = EVENTS_LOOKBACK_MIN) -> ShadowReport:
    """Shadow one day: wait for each fire minute, read, call, record; price at the close."""
    import time as _time
    sleep_fn = sleep_fn or _time.sleep
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rep = ShadowReport(day=day)
    log_path = shadow_log_path(out_dir, day)

    def journal(record: dict) -> None:
        record = {"seen_at": now_fn().isoformat(timespec="seconds"), "day": day, **record}
        rep.journal.append(record)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    rules = sorted(rules, key=lambda r: r.id)
    fire_minutes = sorted({t for r in rules for t in r.fire_at}, key=minute_index)
    close_ct = max((r.exit.time_ct for r in rules), key=minute_index) if rules else "15:00"
    calls: list[tuple[Rule, str, str, dict]] = []      # (rule, fire_ct, call, state)

    for fire_ct in fire_minutes:
        _wait_until(_at(day, fire_ct, 60 + fire_grace_s), now_fn, sleep_fn)
        inputs = day_inputs(day, corpus=corpus, parsed=parsed)
        if not inputs.scoreable:
            journal({"phase": "fire", "fire_ct": fire_ct, "skip": inputs.skip, "n_prints": inputs.n_prints})
            rep.skip = inputs.skip
            continue
        state = state_at(inputs, fire_ct)
        answers = []
        for rule in rules:
            if fire_ct not in rule.fire_at:
                continue
            call = rule.call(state) if state is not None else None
            answers.append({"rule_id": rule.id, "call": call})
            rep.fires.append({"rule_id": rule.id, "fire_ct": fire_ct, "call": call})
            if call is not None:
                calls.append((rule, fire_ct, call, state))
        journal({"phase": "fire", "fire_ct": fire_ct, "n_prints": inputs.n_prints,
                 "state": None if state is None else {"pT": state["pT"], "fp": state.get("fp"),
                                                       "lid": (state.get("mc") or {}).get("lid")},
                 "answers": answers})
        if not any(a["call"] for a in answers):
            continue
        # The entry: the close-watch snapshot, which lands seconds after the fire.
        fire_sec = minute_index(fire_ct) * 60
        deadline = now_fn() + timedelta(seconds=snapshot_wait_s)
        chain = None
        while True:
            market = L.read_day_market(day, corpus)
            if market.opra is not None and market.opra.prints:
                journal({"phase": "entry", "fire_ct": fire_ct, "source": "prints",
                         "note": "the day holds OPRA prints; the entry is the first print at or after the fire minute"})
                break
            chain = market.chain_near(fire_sec)
            if chain is not None:
                seen = []
                for rule, fct, call, _ in calls:
                    if fct != fire_ct:
                        continue
                    right, strike = L.strike_for(call, chain.spot_spx, rule.offset_spx)
                    q = chain.quote(right, strike)
                    seen.append({"rule_id": rule.id, "call": call, "right": right, "strike": strike,
                                 "occ_symbol": L.occ_symbol(day, right, strike),
                                 "ask": None if q is None else q.get("ask"), "bid": None if q is None else q.get("bid")})
                journal({"phase": "entry", "fire_ct": fire_ct, "source": "schwab-snapshot",
                         "snapshot_ct": L.hms(chain.sec_ct), "stage": chain.stage,
                         "spot_spx": chain.spot_spx, "spot_es": chain.spot_es, "legs": seen})
                break
            if now_fn() >= deadline:
                journal({"phase": "entry", "fire_ct": fire_ct, "source": None,
                         "note": f"no OPRA prints and no Schwab snapshot within {snapshot_wait_s}s of the fire minute"})
                break
            sleep_fn(snapshot_poll_s)

    # The close: price every call exactly as the replay does, from the files as they stand.
    _wait_until(_at(day, close_ct, close_grace_s), now_fn, sleep_fn)
    if calls:
        market = L.read_day_market(day, corpus)
        seq: dict[str, int] = {}
        events_cache: dict[str, list[dict]] = {}
        for rule, fire_ct, call, state in calls:
            priced = L.price_call(market, call, fire_ct, offset_spx=rule.offset_spx,
                                  stop_pts=rule.exit.stop_pts, target_pct=rule.exit.target_pct, cal=cal)
            if isinstance(priced, L.Unpriced):
                u = {"rule_id": rule.id, "fire_ct": fire_ct, "call": call, "reason": priced.reason, "detail": priced.detail}
                rep.unpriced.append(u)
                journal({"phase": "unpriced", **u})
                continue
            seq[rule.id] = seq.get(rule.id, 0) + 1
            if events and fire_ct not in events_cache:
                events_cache[fire_ct] = _events_before(day, fire_ct, lookback_min)
            row = build_row(day, rule, fire_ct, call, state, priced, seq[rule.id], lane=LANE_SHADOW,
                            events=events_cache.get(fire_ct, []) if events else [], lookback_min=lookback_min)
            d = row.to_dict()
            d["shadow"] = {
                "fired_seen_at": next((j["seen_at"] for j in rep.journal if j.get("phase") == "fire" and j.get("fire_ct") == fire_ct), None),
                "entry_seen_at": next((j["seen_at"] for j in rep.journal if j.get("phase") == "entry" and j.get("fire_ct") == fire_ct), None),
                "closed_at": now_fn().isoformat(timespec="seconds"),
            }
            rep.rows.append(d)
        rep.rows.sort(key=lambda r: (r["rule_id"], r["fire_ct"], r["id"]))
        if rep.rows:                      # a day with calls but no priceable row leaves no rows file
            with open(shadow_rows_path(out_dir, day), "w", encoding="utf-8") as f:
                for r in rep.rows:
                    f.write(json.dumps(r, sort_keys=True) + "\n")
    journal({"phase": "close", "n_calls": len(calls), "n_rows": len(rep.rows), "n_unpriced": len(rep.unpriced)})
    return rep


# ---------------------------------------------------------------- compare ---

def _key(r: dict) -> tuple:
    return (r["rule_id"], r["fire_ct"])


def _view(r: dict) -> dict:
    return {"rule_id": r["rule_id"], "fire_ct": r["fire_ct"], "call": r["call"],
            "entry_minute": r["entry_ts"][:5], "occ_symbol": r["occ_symbol"]}


def _journal_records(out_dir: Path, day: str) -> list[dict]:
    log = shadow_log_path(out_dir, day)
    if not log.is_file():
        return []
    return [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]


def read_journal(out_dir: Path, day: str) -> tuple[list[dict], list[dict]] | None:
    """The shadow's side of ``day`` from its files: ``(rows, fires)``.

    ``rows`` is the rows file, or empty when the day wrote none. ``fires`` is
    one ``{"rule_id", "fire_ct", "call"}`` per answer the journal holds.
    Returns None when the journal is missing or has no ``close`` record — the
    day has not been shadowed to its close, so there is nothing to compare.
    """
    journal = _journal_records(out_dir, day)
    if not journal or not any(j.get("phase") == "close" for j in journal):
        return None
    fires = [{"rule_id": a["rule_id"], "fire_ct": j["fire_ct"], "call": a["call"]}
             for j in journal if j.get("phase") == "fire" for a in j.get("answers", [])]
    rows_file = shadow_rows_path(out_dir, day)
    rows = ([json.loads(l) for l in rows_file.read_text(encoding="utf-8").splitlines() if l.strip()]
            if rows_file.is_file() else [])
    return rows, fires


def compare(day: str, shadow_rows: Sequence[dict], rules: Sequence[Rule], *, corpus: Path = DEFAULT_CORPUS,
            parsed: Path = DEFAULT_PARSED, cal: Calibration | None,
            shadow_fires: Sequence[dict] | None = None) -> dict:
    """Replay the day and hold it against the shadow rows — and, when
    ``shadow_fires`` is given, against every answer the shadow journaled.

    Returns ``{"clean": bool, "fire_mismatches": [...], "mismatches": [...],
    "shadow_only": [...], "replay_only": [...], "n_shadow": n, "n_replay": n,
    "n_fires": n}``. A fire mismatch names the rule and minute whose call
    differs (``"absent"`` when one lane never answered); a row mismatch names
    the row and the key that differs.
    """
    rep = replay_day(day, rules, corpus=corpus, parsed=parsed, cal=cal, events=False)
    fire_mismatches = []
    if shadow_fires is not None:
        s_calls = {(f["rule_id"], f["fire_ct"]): f["call"] for f in shadow_fires}
        r_calls = {(f["rule_id"], f["fire_ct"]): f["call"] for f in rep.fires}
        for k in sorted(set(s_calls) | set(r_calls)):
            a, b = s_calls.get(k, "absent"), r_calls.get(k, "absent")
            if a != b:
                fire_mismatches.append({"rule_id": k[0], "fire_ct": k[1], "shadow": a, "replay": b})
    replay = {_key(r): r for r in rep.rows}
    shadow = {_key(r): r for r in shadow_rows}
    mismatches = []
    for k in sorted(set(replay) & set(shadow)):
        a, b = _view(shadow[k]), _view(replay[k])
        diff = {f: {"shadow": a[f], "replay": b[f]} for f in COMPARE_KEYS if a[f] != b[f]}
        if diff:
            mismatches.append({"row_id": shadow[k]["id"], "differs": diff})
    out = {
        "day": day,
        "n_fires": len(shadow_fires) if shadow_fires is not None else None,
        "n_shadow": len(shadow), "n_replay": len(replay),
        "fire_mismatches": fire_mismatches,
        "shadow_only": [shadow[k]["id"] for k in sorted(set(shadow) - set(replay))],
        "replay_only": [replay[k]["id"] for k in sorted(set(replay) - set(shadow))],
        "mismatches": mismatches,
        "replay_skip": rep.skip,
        "replay_unpriced": [{"rule_id": u["rule_id"], "reason": u["reason"]} for u in rep.unpriced],
    }
    out["clean"] = not (fire_mismatches or out["shadow_only"] or out["replay_only"] or mismatches)
    return out


# ------------------------------------------------------------- acceptance ---
#
# The acceptance clock. The bead asks for a week of clean compares before the
# lane earns a systemd unit, and until 2026-09-19 that week was counted by
# hand: the run was started by hand and the compare remembered by hand, which
# is why four of the five session days after day 2 were never shadowed at all.
# The count is now an artifact — one verdict file per day — and it is strict
# about what may advance it:
#
#   - a day the REPLAY could not score (``replay_skip``: a holiday, a tape too
#     thin to lens) is not evidence, and neither is a day on which the shadow
#     journaled no answer at all;
#   - a day whose fires were seen LATE is not evidence either. Started after
#     the fire minute, the shadow reads the same finished files the replay
#     reads and agrees with it trivially — a clean compare that proves nothing
#     about the wall clock. ``fire_lags_s`` measures that from the journal's
#     own ``seen_at`` stamps, so the verdict carries its own proof rather than
#     trusting whoever launched the run.
#
# An uncounted day neither advances the clock nor breaks it.


def verdict_path(verdict_dir: Path, day: str) -> Path:
    return Path(verdict_dir) / f"{day}.json"


def fire_lags_s(out_dir: Path, day: str) -> list[float]:
    """Seconds between each fire minute's scheduled read and when it was seen.

    One entry per ``fire`` record the journal holds, in journal order. The
    scheduled read is the fire minute plus 60 (the minute must close) plus
    :data:`FIRE_GRACE_S`. A negative lag is impossible in a real run and is
    reported as it is measured rather than clamped.
    """
    lags = []
    for j in _journal_records(out_dir, day):
        if j.get("phase") != "fire" or not j.get("seen_at") or not j.get("fire_ct"):
            continue
        try:
            seen = datetime.fromisoformat(j["seen_at"])
            due = _at(day, j["fire_ct"], 60 + FIRE_GRACE_S)
        except ValueError:
            continue
        lags.append((seen - due).total_seconds())
    return lags


def write_verdict(verdict_dir: Path, day: str, out: dict, *, out_dir: Path,
                  slack_s: float = REALTIME_SLACK_S,
                  now_fn: Callable[[], datetime] = lambda: datetime.now(CT)) -> dict:
    """Record one day's compare as an acceptance verdict and return it.

    ``counted`` says whether this day may advance the acceptance clock;
    ``why`` names the reason when it may not. The write is tmp+rename so a
    reader never sees half a file.
    """
    lags = fire_lags_s(out_dir, day)
    late = [round(x, 1) for x in lags if x > slack_s]
    if out.get("replay_skip"):
        counted, why = False, f"the day could not be scored ({out['replay_skip']})"
    elif not lags:
        counted, why = False, "the journal holds no fire the acceptance can read"
    elif not out.get("n_fires"):
        counted, why = False, "no rule answered at the fire minute"
    elif late:
        counted, why = False, (f"seen {max(late):.0f}s after the fire minute, past the {slack_s:.0f}s "
                               "slack — a late read agrees with the replay trivially")
    else:
        counted, why = True, None
    verdict = {
        "day": day,
        "ts": now_fn().isoformat(timespec="seconds"),
        "clean": bool(out.get("clean")),
        "counted": counted,
        "why_not_counted": why,
        "fire_lag_s": round(max(lags), 1) if lags else None,
        "n_fires": out.get("n_fires"),
        "n_shadow": out.get("n_shadow"),
        "n_replay": out.get("n_replay"),
        "replay_skip": out.get("replay_skip"),
        "fire_mismatches": out.get("fire_mismatches") or [],
        "mismatches": out.get("mismatches") or [],
        "shadow_only": out.get("shadow_only") or [],
        "replay_only": out.get("replay_only") or [],
    }
    d = Path(verdict_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = verdict_path(d, day)
    tmp = d / f".{path.name}.tmp"
    tmp.write_text(json.dumps(verdict, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return verdict


def acceptance_streak(verdict_dir: Path, *, needed: int = ACCEPTANCE_DAYS) -> dict:
    """How many counted days in a row have compared clean, newest backwards.

    Walks the verdict files from the most recent day, counting clean counted
    days and stopping at the first counted day that was not clean. Uncounted
    days are passed over. Returns ``{"streak", "needed", "earned", "last_day",
    "broke_on", "n_verdicts"}``; a missing or empty directory is a streak of
    zero, not an error.
    """
    d = Path(verdict_dir)
    files = sorted(d.glob("*.json"), reverse=True) if d.is_dir() else []
    streak, last_day, broke_on, n = 0, None, None, 0
    for f in files:
        try:
            v = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        n += 1
        if not v.get("counted"):
            continue
        if not v.get("clean"):
            broke_on = v.get("day")
            break
        streak += 1
        last_day = last_day or v.get("day")
    return {"streak": streak, "needed": needed, "earned": streak >= needed,
            "last_day": last_day, "broke_on": broke_on, "n_verdicts": n}
