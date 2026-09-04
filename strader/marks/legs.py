"""Leg-days: the hypothetical 0DTE singles calibration and validation both
walk. [st-9hhc]

One leg-day = one (day, entry time, moneyness offset, side): the single
bought at the first print at/after the entry time, marked from its own prints
to 15:00 CT. Same construction as final_hour_premium.py (st-g0jo) — put and
call at ~10 ITM, ATM, ~10 OTM, nearest 5-pt strike, SPX at entry inferred
from 0DTE put-call parity — at four entry times so the calibration sees the
whole 13:00-15:00 CT window, not just the final hour.

Deterministic: legs come back in a fixed order (entry time, then offset,
then P before C), skips are rows with a reason rather than silence.
"""
from __future__ import annotations

from dataclasses import dataclass

from strader.marks import prints as pr

#: Entry times, CT seconds. 13:00 is the start of print coverage; its parity
#: window is clipped to [13:00, 13:03) rather than reaching back before
#: coverage.
ENTRY_TIMES_CT = (13 * 3600, 13 * 3600 + 1800, 14 * 3600, 14 * 3600 + 1800)

#: Moneyness offsets in SPX pts: negative = ITM (Steve leans ITM for the
#: futures-proxy single), 0 = ATM, positive = OTM.
OFFSETS = (-10, 0, 10)

MIN_PRINTS = 5        # fewer prints after entry than this: too thin to score
ENTRY_SLACK_S = 300   # first print must land within 5 min of the entry time


@dataclass(frozen=True)
class LegDay:
    day: str
    entry_ct_s: int          # the nominal entry time (13:00 etc.)
    name: str                # e.g. "put_itm10"
    side: str                # "C" | "P"
    strike: float
    spx_entry: float         # parity-inferred SPX near the entry time
    t_entry_s: int           # the actual first print's CT second
    entry: float             # that print's price = entry premium
    raw_path: list           # [(ct_s, price)] prints at/after t_entry_s
    marks: list              # [(minute_ct_s, price)] LOCF minute grid to 15:00
    skip: str | None = None  # set on an unscoreable leg; other fields best-effort

    @property
    def cls(self) -> str:
        """itm / atm / otm — pooled over sides, the write-up's row key."""
        return self.name.split("_")[1].rstrip("0123456789")


def leg_specs(spx: float) -> list[tuple[str, str, float]]:
    """(name, side, strike) for the six legs, fixed order."""
    out = []
    for off in OFFSETS:
        tag = "itm" if off < 0 else ("atm" if off == 0 else "otm")
        out.append((f"put_{tag}{abs(off)}", "P", round((spx - off) / 5.0) * 5))
        out.append((f"call_{tag}{abs(off)}", "C", round((spx + off) / 5.0) * 5))
    return out


def build_day(day: str, root: str = "data/corpus") -> list[LegDay]:
    """Every leg-day for one corpus day, skips included as rows.

    Returns [] when the day lacks prints or ES tape entirely — the caller's
    day list should come from prints.corpus_days, which already requires
    both.
    """
    opra = pr.opra_path(day, root)
    if opra is None:
        return []
    day_prints = pr.load_day_prints(opra, day)
    if not day_prints:
        return []
    out: list[LegDay] = []
    for entry_ct_s in ENTRY_TIMES_CT:
        spx = pr.infer_spx(day_prints, entry_ct_s)
        if spx is None:
            out.append(LegDay(day, entry_ct_s, "-", "-", 0.0, 0.0, 0, 0.0,
                              [], [], skip="no-parity"))
            continue
        y, m, d = map(int, day.split("-"))
        exp = f"{y % 100:02d}{m:02d}{d:02d}"
        for name, side, strike in leg_specs(spx):
            sym = f"SPXW  {exp}{side}{int(strike * 1000):08d}"
            path = day_prints.get(sym, [])
            after = [(t, p) for t, p in path if t >= entry_ct_s]
            if not after or after[0][0] > entry_ct_s + ENTRY_SLACK_S:
                out.append(LegDay(day, entry_ct_s, name, side, strike, spx, 0,
                                  0.0, [], [], skip="no-entry-print"))
                continue
            if len(after) < MIN_PRINTS:
                out.append(LegDay(day, entry_ct_s, name, side, strike, spx,
                                  after[0][0], after[0][1], after, [],
                                  skip="thin"))
                continue
            t_entry, entry = after[0]
            marks = pr.minute_marks(after, t_entry, pr.WINDOW_END_S)
            out.append(LegDay(day, entry_ct_s, name, side, strike, spx,
                              t_entry, entry, after, marks))
    return out
