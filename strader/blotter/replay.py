"""The replay lane — registered rules over the corpus, one row per trade. [st-uc23]

For each day in a range: read the lens inputs once, call every registered
rule at each of its fire minutes on the state built from prints before that
minute, and on a call price the instrument (:mod:`strader.blotter.legs`) and
write a :class:`strader.blotter.rows.Row`. A call that cannot be priced is
recorded as unpriced, with the reason; a day that cannot be scored is
recorded as skipped, with the reason. Nothing is silently dropped.

DETERMINISM. Days sorted; rows sorted by (rule id, fire minute) within a
day; every number rounded where it is produced; JSON written with sorted
keys and no timestamps. Two runs over one range with unchanged code and
files are byte-identical — the acceptance floor (Ruling 9 extended to
trades). A rule change ships its blotter diff as the review.

EVENTS. The row's ``events`` are the tape-path emissions (PLAN-LEVEL,
SUPERLATIVE, CLIMAX, ABSORPTION-CLUSTER) inside the window the rule read —
``market/orderflow/region_replay.py``, the one playback engine — so the row
opens onto what the emitter said in the half hour before the fire. They are
gathered on fire days only (the engine costs ~10 s a day).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date as _date, datetime
from pathlib import Path
from typing import Iterable, Sequence

from strader.blotter import legs as L
from strader.blotter.rows import LANE_REPLAY, Row, row_id
from strader.blotter.rules import Rule, load_rules
from strader.blotter.state import DEFAULT_CORPUS, DEFAULT_PARSED, day_inputs, state_at
from strader.marks.estimated import Calibration, minute_index

__all__ = ["EVENTS_LOOKBACK_MIN", "DayReport", "replay_day", "replay_range", "write_day_rows",
           "corpus_days_in", "rows_path"]

EVENTS_LOOKBACK_MIN = 30


@dataclass
class DayReport:
    day: str
    rows: list[dict] = field(default_factory=list)
    fires: list[dict] = field(default_factory=list)       # every call, priced or not
    unpriced: list[dict] = field(default_factory=list)
    skip: str | None = None
    n_prints: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def corpus_days_in(corpus: Path, day_from: str, day_to: str) -> list[str]:
    """Every day directory in [from, to] that holds an ES file, sorted."""
    out = []
    for d in sorted(Path(corpus).iterdir()) if Path(corpus).is_dir() else []:
        if not d.is_dir() or len(d.name) != 10 or d.name[4] != "-":
            continue
        if not (day_from <= d.name <= day_to):
            continue
        if (d / "databento_glbx_es.jsonl").exists() or (d / "databento_glbx_es.jsonl.gz").exists():
            out.append(d.name)
    return out


def _events_before(day: str, fire_ct: str, lookback_min: int) -> list[dict]:
    """Tape-path emissions in [fire - lookback, fire] CT, as their records."""
    from market.orderflow.region_replay import PATH_TAPE, emit_day  # heavy import, on demand
    y, m, d = (int(x) for x in day.split("-"))
    fire_idx = minute_index(fire_ct)
    lo = fire_idx - lookback_min
    out = []
    for em in emit_day(_date(y, m, d), paths=(PATH_TAPE,)):
        ts = em.record.get("ts")
        try:
            t = datetime.fromisoformat(ts)
        except (TypeError, ValueError):
            continue
        idx = t.hour * 60 + t.minute
        if lo <= idx <= fire_idx:
            out.append(em.record)
    return out


def _replay_say(day: str, fire_ct: str, close_ct: str, lookback_min: int) -> str:
    idx = minute_index(fire_ct) - lookback_min
    return f"{day} {idx // 60:02d}:{idx % 60:02d} to {close_ct}"


def replay_day(day: str, rules: Sequence[Rule], *, corpus: Path = DEFAULT_CORPUS, parsed: Path = DEFAULT_PARSED,
               cal: Calibration | None = None, events: bool = True,
               lookback_min: int = EVENTS_LOOKBACK_MIN) -> DayReport:
    rep = DayReport(day=day)
    inputs = day_inputs(day, corpus=corpus, parsed=parsed)
    rep.n_prints = inputs.n_prints
    if not inputs.scoreable:
        rep.skip = inputs.skip
        return rep
    market: L.DayMarket | None = None
    seq: dict[str, int] = {}
    events_cache: dict[str, list[dict]] = {}
    for rule in sorted(rules, key=lambda r: r.id):
        for fire_ct in rule.fire_at:
            state = state_at(inputs, fire_ct)
            if state is None:
                rep.fires.append({"rule_id": rule.id, "fire_ct": fire_ct, "call": None, "skip": "no-state"})
                continue
            call = rule.call(state)
            fire = {"rule_id": rule.id, "fire_ct": fire_ct, "call": call}
            if call is None:
                rep.fires.append(fire)
                continue
            if market is None:
                market = L.read_day_market(day, corpus)
            priced = L.price_call(market, call, fire_ct, offset_spx=rule.offset_spx,
                                  stop_pts=rule.exit.stop_pts, target_pct=rule.exit.target_pct, cal=cal)
            if isinstance(priced, L.Unpriced):
                fire.update({"priced": False, "reason": priced.reason, "detail": priced.detail})
                rep.fires.append(fire)
                rep.unpriced.append(fire)
                continue
            seq[rule.id] = seq.get(rule.id, 0) + 1
            if events and fire_ct not in events_cache:
                events_cache[fire_ct] = _events_before(day, fire_ct, lookback_min)
            row = Row(
                id=row_id(day, rule.id, seq[rule.id]), lane=LANE_REPLAY, day=day, rule_id=rule.id,
                registered=rule.registered, call=call, sources=list(rule.entity.sources),
                instrument=rule.instrument, occ_symbol=priced.symbol, right=priced.right,
                strike=priced.strike, lots=1, fire_ct=fire_ct, entry_ts=L.hms(priced.entry_sec),
                entry_premium_pts=priced.entry_pts, spx_at_entry=priced.spx_at_entry,
                es_at_entry=priced.es_at_entry, exit_ts=L.hms(priced.exit_sec),
                exit_premium_pts=priced.exit_pts, exit_reason=priced.exit_reason,
                pnl_pts=priced.pnl_pts, pnl_usd=round(priced.pnl_pts * 100.0, 2),
                mfe_pts=priced.mfe_pts, mae_pts=priced.mae_pts, mark_path=priced.mark_path,
                estimated=priced.mark_path == "estimated", n_marks=priced.n_marks,
                state={"T": state["T"], "pT": state["pT"], "fp": state.get("fp"), "mc": state.get("mc"),
                       "gx": state.get("gx")},
                events=events_cache.get(fire_ct, []) if events else [],
                excerpts=[rule.id, *rule.entity.sources],
                replay=_replay_say(day, fire_ct, rule.exit.time_ct, lookback_min),
                grid=priced.grid, estimated_exit=priced.estimated_exit,
                extrapolated=priced.extrapolated, notes=list(priced.notes),
            )
            fire.update({"priced": True, "row_id": row.id})
            rep.fires.append(fire)
            rep.rows.append(row.to_dict())
    rep.rows.sort(key=lambda r: (r["rule_id"], r["fire_ct"], r["id"]))
    return rep


def rows_path(out_dir: Path, day: str) -> Path:
    return Path(out_dir) / f"replay-{day}.jsonl"


def write_day_rows(out_dir: Path, rep: DayReport) -> Path | None:
    """``replay-<day>.jsonl`` for a day with rows; nothing for a day without."""
    if not rep.rows:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    p = rows_path(out_dir, rep.day)
    with open(p, "w", encoding="utf-8") as f:
        for r in rep.rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    return p


# ------------------------------------------------------------ the range ---

_WORKER: dict = {}


def _init_worker(rule_ids: list[str] | None, corpus: str, parsed: str, cal_path: str | None,
                 events: bool, lookback_min: int) -> None:
    rules = load_rules()
    if rule_ids:
        rules = [r for r in rules if r.id in set(rule_ids)]
    _WORKER.update(rules=rules, corpus=Path(corpus), parsed=Path(parsed),
                   cal=Calibration.load(Path(cal_path)) if cal_path else None,
                   events=events, lookback_min=lookback_min)


def _run_day(day: str) -> dict:
    w = _WORKER
    return replay_day(day, w["rules"], corpus=w["corpus"], parsed=w["parsed"], cal=w["cal"],
                      events=w["events"], lookback_min=w["lookback_min"]).to_dict()


def replay_range(days: Iterable[str], *, rule_ids: Sequence[str] | None = None, corpus: Path = DEFAULT_CORPUS,
                 parsed: Path = DEFAULT_PARSED, cal_path: Path | None = None, events: bool = True,
                 lookback_min: int = EVENTS_LOOKBACK_MIN, workers: int = 1) -> list[DayReport]:
    """Every day in order. ``workers > 1`` runs a spawn pool (fork under a
    threaded parent can deadlock the child; ``estimated_mark_*`` learned it)."""
    days = sorted(days)
    args = (list(rule_ids) if rule_ids else None, str(corpus), str(parsed),
            str(cal_path) if cal_path else None, events, lookback_min)
    if workers <= 1 or len(days) <= 1:
        _init_worker(*args)
        return [DayReport(**_run_day(d)) for d in days]
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    with ctx.Pool(workers, initializer=_init_worker, initargs=args) as pool:
        return [DayReport(**d) for d in pool.imap(_run_day, days)]
