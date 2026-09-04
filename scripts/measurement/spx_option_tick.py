#!/usr/bin/env python3
"""Measure the SPX option quoting increment from a recorded chain. [st-pohq]

``execd/stops.py`` rounds every protective stop to a 0.05 tick. Index options
are quoted in $0.05 below $3.00 and — by exchange rule — $0.10 at and above
it, and a stop resting on an off-grid price is a stop the exchange rejects
under a live position. This script reads a chain capture from
``scripts/record_schwab_shapes.py`` and counts, per price band, how many bids
and asks sit on the 0.10 grid and how many need the 0.05 grid. The answer is
in the counts, not in anyone's memory of the rule.

    .venv/bin/python scripts/measurement/spx_option_tick.py <dir-with-chain.json>

Reads only the file. Makes no call.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def on_grid(price: float, tick: float) -> bool:
    cents = round(price * 100)
    step = round(tick * 100)
    return cents % step == 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(argv[1]) / "chain.json" if Path(argv[1]).is_dir() else Path(argv[1])
    chain = json.loads(path.read_text(encoding="utf-8"))
    meta_path = path.parent / "_capture.json"
    label = json.loads(meta_path.read_text())["label"] if meta_path.exists() else "?"

    bands = [(0.0, 3.0, "below 3.00"), (3.0, 10.0, "3.00-9.99"), (10.0, 50.0, "10.00-49.99"),
             (50.0, 1e9, "50.00 and up")]
    counts: dict[str, Counter] = {name: Counter() for _lo, _hi, name in bands}
    off_grid_examples: list[tuple[str, str, float]] = []
    quotes = 0
    for key in ("callExpDateMap", "putExpDateMap"):
        for _exp, strikes in (chain.get(key) or {}).items():
            for _strike, contracts in strikes.items():
                for c in contracts:
                    for side in ("bid", "ask"):
                        px = c.get(side)
                        if not px or px <= 0:
                            continue
                        quotes += 1
                        for lo, hi, name in bands:
                            if lo <= px < hi:
                                ctr = counts[name]
                                ctr["quotes"] += 1
                                if on_grid(px, 0.10):
                                    ctr["on_0.10"] += 1
                                elif on_grid(px, 0.05):
                                    ctr["on_0.05_only"] += 1
                                    if lo >= 3.0 and len(off_grid_examples) < 12:
                                        off_grid_examples.append((c.get("symbol", "?"), side, px))
                                else:
                                    ctr["off_both"] += 1
                                break

    print(f"chain: {path}  ({label})  underlying {chain.get('underlyingPrice')}  "
          f"contracts {chain.get('numberOfContracts')}  quoted sides {quotes}")
    print(f"{'band':<14} {'quotes':>7} {'on 0.10':>8} {'0.05 only':>10} {'off both':>9}")
    for _lo, _hi, name in bands:
        c = counts[name]
        print(f"{name:<14} {c['quotes']:>7} {c['on_0.10']:>8} {c['on_0.05_only']:>10} {c['off_both']:>9}")
    if off_grid_examples:
        print("\nquotes at or above 3.00 that need the 0.05 grid (first 12):")
        for sym, side, px in off_grid_examples:
            print(f"  {sym}  {side} {px:.2f}")
    above = sum(counts[n]["on_0.05_only"] for _l, _h, n in bands if n != "below 3.00")
    total_above = sum(counts[n]["quotes"] for _l, _h, n in bands if n != "below 3.00")
    print(f"\nat/above 3.00: {total_above} quoted sides, {above} need the 0.05 grid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
