"""The blotter row — one trade, as a record. [st-uc23]

The schema is the refactor-and-blotter plan's (§5 "Row schema") with Strader's
2026-08-30 counter applied: ``mfe_pts``/``mae_pts`` on every row (§5.3), the
``registered`` sha on every row so a re-registered rule is visible (§5.4),
rows under ``data/measurement/blotter/`` (§5.7), and the id
``<day>-<rule-id>-<seq>`` — speakable: "I disagree with 08-28
launch-into-no-lid-1445 row 1" names one row.

A row is a record, not a zentity (Steve's trading-day ruling). Field names
follow FD0's ``Attempt``/``Ticket`` where they fit (``entry_premium_pts``,
``exit_premium_pts``, ``estimated``, ``lots``) so the fire key's journal and
the blotter read alike when the day comes.

MARK PATHS. ``mark_path`` says where the marks came from, and every aggregate
splits on it (counter §5.2 — pooling makes P&L a function of which days got
an OPRA pull):

    prints     the symbol's own OPRA prints; the declared exit resolves on
               the raw print path, first touch wins, at the print's price.
    estimated  the ES->premium proxy (strader/marks/estimated.py); the row
               carries ``estimated: true`` and ``exit_reason: time`` ONLY —
               the standing contract until the estimated-mark write-up's
               stop-timing tables are ruled on, bin by bin. What the proxy
               would have resolved is carried beside, in ``estimated_exit``,
               never in the P&L columns.

The stop x target grid (``grid``) is the blotter's premium grid on registered
rules — NOT st-fpc4's ES-point grid on recognizer confirmations (counter
§5.5). It is filled on printed rows only; on estimated rows it is null.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

__all__ = ["LANE_REPLAY", "LANE_SHADOW", "MARK_PRINTS", "MARK_ESTIMATED", "EXIT_REASONS",
           "USD_PER_PT", "Row", "row_id"]

LANE_REPLAY = "replay"
LANE_SHADOW = "shadow"
MARK_PRINTS = "prints"
MARK_ESTIMATED = "estimated"
EXIT_REASONS = ("stop", "target", "time", "rule-off", "close")
USD_PER_PT = 100.0     # one SPX option point on one contract


def row_id(day: str, rule_id: str, seq: int) -> str:
    return f"{day}-{rule_id}-{seq}"


@dataclass
class Row:
    id: str
    lane: str
    day: str
    rule_id: str
    registered: str                 # the rule's pre-registration sha, carried on every row
    call: str                       # up | down
    sources: list[str]              # register ids from the entity's sources:
    instrument: str
    occ_symbol: str
    right: str                      # C | P
    strike: float
    lots: int
    fire_ct: str                    # the minute the rule was called, "HH:MM" CT
    entry_ts: str                   # "HH:MM:SS" CT of the entry print (or the entry minute's close for estimated)
    entry_premium_pts: float
    spx_at_entry: float             # parity-inferred (prints) or basis-inferred (estimated)
    es_at_entry: float
    exit_ts: str
    exit_premium_pts: float
    exit_reason: str
    pnl_pts: float
    pnl_usd: float
    mfe_pts: float                  # best mark after entry, premium points above the entry
    mae_pts: float                  # worst mark after entry, premium points below the entry (<= 0)
    mark_path: str                  # prints | estimated
    estimated: bool
    n_marks: int                    # prints after the entry, or proxy minutes
    state: dict                     # the lens fields the rule read (no outcome)
    events: list[dict]              # the tape emissions in the window before the fire
    excerpts: list[str]             # entity ids the row cites
    replay: str                     # the drill page's spoken region: "<day> <from> to <to>"
    grid: dict | None = None        # {"<stop_pts>x<target_pct>": {exit_reason, pnl_pts, exit_ts}} on printed rows
    estimated_exit: dict | None = None   # what the proxy would have resolved, on estimated rows
    extrapolated: bool = False      # any proxy mark outside the calibrated window
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
