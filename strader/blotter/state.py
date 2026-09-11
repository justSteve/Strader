"""The state a registered rule reads at its fire minute. [st-djb9]

WHY
    The two rules the blotter starts with (``footprint-up-1445``,
    ``launch-into-no-lid-1445``) were pre-registered on 2026-08-29 against the
    final-hour lens state — the footprint box, the Mancini level replay and the
    GEX majors rebuilt at T from prints before T
    (``scripts/measurement/final_hour_lens.py``). A rule scored on a state the
    lens did not compute would be a different rule, so this module does not
    fork that computation: it imports the script and calls the same functions
    the 08-29 run did, with two guarantees the script's own driver does not
    give —

    * the outcome group (``out``: what happened after T) is never built, so a
      rule cannot be handed lookahead by accident; and
    * every path is explicit (corpus root, parsed-letter root), so a test can
      point it at a synthetic day.

WHAT
    :func:`day_inputs` reads one day's tape, letter and GEX once.
    :func:`state_at` builds the lens state at one CT minute from those inputs.
    ``STATE_KIND`` names this state shape; a rule module declares which shape
    it consumes and the registry refuses a mismatch.

    Deterministic: same files, same code, same dict. No clock, no network.
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from market.corpus.paths import resolve_existing

__all__ = ["STATE_KIND", "DayInputs", "day_inputs", "state_at", "lens_module", "minute_of_day"]

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LENS_SCRIPT = REPO_ROOT / "scripts" / "measurement" / "final_hour_lens.py"
DEFAULT_CORPUS = REPO_ROOT / "data" / "corpus"
DEFAULT_PARSED = REPO_ROOT / "runbook" / "mancini" / "parsed"

#: The state shape this module produces: the final-hour lens row without its
#: outcome group. A rule's ``STATE`` must equal this to be registered.
STATE_KIND = "final-hour-lens"

#: The lens skips a day with fewer RTH prints than this (its own threshold).
MIN_TAPE_PRINTS = 1000

_lens: ModuleType | None = None


def lens_module() -> ModuleType:
    """``scripts/measurement/final_hour_lens.py`` imported by path, once.

    The script reads ``sys.argv`` at import for its own output name; it is
    imported with a neutral argv so a harness's flags never reach it.
    """
    global _lens
    if _lens is None:
        spec = importlib.util.spec_from_file_location("strader_blotter_final_hour_lens", LENS_SCRIPT)
        assert spec is not None and spec.loader is not None, LENS_SCRIPT
        mod = importlib.util.module_from_spec(spec)
        saved = sys.argv
        sys.argv = [str(LENS_SCRIPT)]
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.argv = saved
        _lens = mod
    return _lens


def minute_of_day(hhmm: str) -> int:
    """"14:45" -> 885, minutes since midnight CT."""
    if len(hhmm) != 5 or hhmm[2] != ":":
        raise ValueError(f"minute must be 'HH:MM' CT, got {hhmm!r}")
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


@dataclass
class DayInputs:
    """One day's inputs to the lens, read once and shared across fire minutes."""

    day: str
    trades: list                 # (hms_utc, price, size, side), RTH only, sorted
    seg: Any                     # seg(a, b) -> prints in [a, b) CT minutes of day
    levels: list | None          # the parsed letter's levels, or None (no Mancini leg)
    bias: str | None
    gex: list                    # [(epoch, spot, zero, mpos, mneg)]
    skip: str | None = None      # "no-es-file" | "thin" when the day cannot be scored
    n_prints: int = 0

    @property
    def scoreable(self) -> bool:
        return self.skip is None


def day_inputs(day: str, *, corpus: Path = DEFAULT_CORPUS, parsed: Path = DEFAULT_PARSED) -> DayInputs:
    """Read ``day``'s ES tape, parsed letter and GEX rows the way the lens does."""
    L = lens_module()
    es = resolve_existing(Path(corpus) / day / "databento_glbx_es.jsonl")
    if es is None:
        return DayInputs(day, [], None, None, None, [], skip="no-es-file")
    off = L.ct_offset_hours(day)
    trades = L.load_tape(str(es), off)
    if len(trades) < MIN_TAPE_PRINTS:
        return DayInputs(day, trades, None, None, None, [], skip="thin", n_prints=len(trades))
    levels, bias = L.load_levels(day, str(parsed))
    gex = L.load_gex(day, str(corpus))
    return DayInputs(day, trades, L.segmenter(trades, off), levels, bias, gex, n_prints=len(trades))


def state_at(inputs: DayInputs, fire_ct: str) -> dict | None:
    """The lens state at ``fire_ct`` ("HH:MM" CT) from prints before it, or
    None when the day has no prints between 13:00 and the fire minute.

    The dict carries ``day``, ``T`` ("HHMM"), ``full``, ``pT``, ``n``, ``fp``,
    ``mc``, ``gx`` — and never ``out``.
    """
    if not inputs.scoreable:
        return None
    L = lens_module()
    row = L.lens_state(inputs.day, minute_of_day(fire_ct), inputs.trades, inputs.seg,
                       inputs.levels, inputs.bias, inputs.gex, with_outcome=False)
    if row.get("skip"):
        return None
    assert "out" not in row
    return row
