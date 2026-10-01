"""Generated sessions — seeded tapes, seeded actions, every invariant every step. [st-ug1h]

Each ``walk_seed`` makes one random-walk tape (gaps, stale stretches, wide
frames) and one random session on it: entries through the order form's
pricing (side, delta cap, lots, stop distance, sometimes a close-at
level), Steve moving his stop or target, FLATTEN, a restart of the box,
and the watcher's pass every three seconds. Fast mode runs
``conftest.FAST_SEEDS`` of them on 200-frame tapes; ``--scenario-wide``
runs ``WIDE_SEEDS`` on 600 frames and adds resting (dip-buy) entries.

A failure prints the seed, the tape's parameters and the whole sequence,
CT-stamped; the same seed reproduces it exactly::

    python3 -m pytest 'tests/execd/scenario/test_generated.py::test_a_generated_session[17]'

**What the sessions steer around.** Open defects that every session would
otherwise walk into are not re-found here; each is pinned by its own strict
xfail (``known_bugs.py``) and the avoidance below names it, so it comes out
when the defect is fixed:

* H2 — fixed (st-yeph, 2026-10-01): a stop distance at or under the
  spread is refused at the ticket. The sessions still enter on no wide
  frame and give two or more lots a stop distance of 0.30 or more, so
  they keep entering rather than being refused;
* D1 — no restart once a leg of the open position has been replaced
  (the trail, an adjust, a better fill);
* D8 — at most three lots (the tier-0 rounding needs about six);
* H6 — resting entries (wide mode only) fill in gapped and wide markets;
  the stop that cannot follow the fill is waived there. (H5, a close-at
  level the fill is already past, cannot happen since no entry carries an
  SPX stop level, st-a54y; an SPX level is the card's after the fill.)
"""

from __future__ import annotations

import random

from .conftest import wide_mode
from .tape import random_walk


def replaced(scn) -> bool:
    """Has a leg of the open position been moved by a replace (D1)?"""
    ids = {p.intent_id for p in scn.service._open.values()}
    return any(e.get("replaced") and e.get("intent_id") in ids
               for e in scn.events("stop_adjusted", "target_adjusted"))


def session(scn, rng: random.Random, *, resting: bool) -> dict[str, int]:
    done = {"entries": 0, "adjusts": 0, "flattens": 0, "restarts": 0}
    while scn.elapsed + 3 <= scn.tape.length_s:
        frame = scn.tape.frame(scn.clock())
        flat = not scn.held() and not scn.service._working
        roll = rng.random()
        if flat and roll < 0.12 and not frame.stale and frame.spread is None:
            side = rng.choice(["call", "put"])
            lots = rng.choice([1, 1, 1, 2, 3])
            stopoff = rng.choice([None, 0.30, 0.50, 1.00])
            if lots > 1 and (stopoff is None or stopoff < 0.30):
                stopoff = 0.50                                  # H2
            sel = {"delta": rng.choice([0.3, 0.4, 0.5, 0.6, 0.7, 0.8]), "lots": lots,
                   "stopoff": stopoff}
            t = scn.ticket(side, **sel)
            if t.ready and not t.error:
                if resting and rng.random() < 0.3:
                    t = scn.ticket(side, **{**sel, "strike": t.contract.strike,
                                            "limit": round(t.limit - 0.10, 2)})
                out = scn.send(t)
                done["entries"] += out.get("refused") is None
        elif scn.held() and roll < 0.04:
            sym = next(iter(scn.held()))
            pos = scn.position(sym)
            q = scn.quote(sym)
            if pos is not None and pos.stop_price and rng.random() < 0.5:
                to = round(max(0.05, pos.stop_price - 0.30), 2)
                if q.bid > to:
                    scn.adjust(sym, stop_price=to)
                    done["adjusts"] += 1
            elif pos is not None and pos.target_price and q.bid > 0:
                to = round(q.ask + 1.0 + (0.0 if q.ask + 1.0 < 3 else 0.0), 1)
                scn.adjust(sym, target_price=to)
                done["adjusts"] += 1
        elif scn.held() and roll < 0.05:
            scn.flatten()
            done["flattens"] += 1
        elif roll < 0.053 and not replaced(scn):                  # D1
            scn.restart()
            done["restarts"] += 1
        scn.tick(3.0)
    return done


def test_a_generated_session(make, walk_seed, request):
    wide = wide_mode(request.config)
    tape = random_walk(walk_seed, steps=600 if wide else 200, gap_prob=0.02, gap_pts=5.0,
                       stale_prob=0.02, stale_len=4, wide_prob=0.03, sigma_pts=0.9)
    waive = {"stop_dollars_off_ticket": "H6"} if wide else None
    scn = make(tape, waive=waive)
    done = session(scn, random.Random(walk_seed * 7919 + 1), resting=wide)
    # what was closed was booked once per contract sold
    sold = sum(o.filled_qty for o in scn.paper._orders.values()
               if o.side.value == "SELL_TO_CLOSE" and o.is_filled)
    assert sum(c["qty"] for c in scn.closes()) == sold


def test_the_generated_sessions_trade(make):
    """The sessions do trade, adjust and flatten — a generator that never
    sent would pass every invariant and test nothing."""
    done = {"entries": 0, "adjusts": 0, "flattens": 0, "restarts": 0}
    for seed in range(4):
        scn = make(random_walk(seed, steps=200))
        for k, v in session(scn, random.Random(seed * 7919 + 1), resting=False).items():
            done[k] += v
    assert done["entries"] >= 8 and done["adjusts"] >= 2, done
