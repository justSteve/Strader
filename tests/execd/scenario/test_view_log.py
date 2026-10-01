"""The view log on the replayed market: what the screen showed, and why. [st-6pfc]

Desk's work order (2026-10-01): at 12:15 CT Steve asked why the staged
bullish ticket's price rose while ES fell. The answer — the chooser
re-picks the highest-delta legal strike at or under the 0.80 cap on every
repaint, so the strike steps down as the index falls — should be one line
of this file, not a reconstruction.
"""

from __future__ import annotations

import json

from execd.viewlog import EXCLUDED_KEYS, ViewLog

from .screen import OrderScreen
from .tape import ramp


def read(vl: ViewLog) -> list[dict]:
    return [json.loads(ln) for f in sorted(vl.dir.glob("*.jsonl"))
            for ln in f.read_text().splitlines()]


def keys(v, out=None):
    out = set() if out is None else out
    if isinstance(v, dict):
        for k, x in v.items():
            out.add(k)
            keys(x, out)
    elif isinstance(v, list):
        for x in v:
            keys(x, out)
    return out


def test_a_falling_spx_across_a_strike_switch_says_the_switch_and_why(make, tmp_path):
    scn = make(ramp((0, 6380), (240, 6340), (300, 6340)))
    scn.view_log = vl = ViewLog(tmp_path / "surface", clock=scn.clock, start=False)
    screen = OrderScreen(scn)
    screen.pick("call")                                  # auto: the highest delta <= 0.80
    for _ in range(90):
        scn.tick(3.0)
        screen.poll()
        vl.drain(force=True)
    lines = read(vl)
    chosen = [ln["chosen"]["strike"] for ln in lines if ln.get("chosen")]
    switches = [ln for ln in lines if (ln.get("decision") or {}).get("changed")]
    assert len(set(chosen)) >= 2, chosen                  # the strike stepped as SPX fell
    assert chosen[-1] < chosen[0]
    last = switches[-1]
    assert last["cap"] == 0.8 and last["chosen"]["delta"] <= 0.8
    reasons = {r["lost"] for r in last["decision"]["runners_up"]}
    assert "over the cap" in reasons
    assert last["decision"]["reason"].startswith("highest delta at or under 0.8")
    # a line is written only when what the screen shows changed: fewer lines than polls
    assert len(lines) < 90 and vl.counts["unchanged"] > 0
    # lines between switches carry the chosen strike's numbers, no runners-up
    plain = [ln for ln in lines if ln.get("chosen") and not (ln.get("decision") or {}).get("changed")]
    assert plain and all("runners_up" not in (ln.get("decision") or {}) for ln in plain)
    assert all(ln["viewer"].startswith("desktop-") and ln["ts_ct"] for ln in lines)
    print("\nSAMPLE " + json.dumps(last)[:1600])


def test_no_excluded_field_ever_appears(make, tmp_path):
    """Through a send, a fill with its bracket resting (order ids on every
    position), an adjust and a close: no line carries an account, a token,
    a passphrase or a broker order id."""
    scn = make(ramp((0, 6380), (60, 6380), (150, 6370), (200, 6370)))
    scn.view_log = vl = ViewLog(tmp_path / "surface", clock=scn.clock, start=False)
    screen = OrderScreen(scn)
    screen.pick("call", delta=0.5)
    screen.send()
    for _ in range(60):
        scn.tick(3.0)
        screen.poll()
        vl.drain(force=True)
    lines = read(vl)
    assert any(ln.get("positions") for ln in lines) and any(ln.get("closed") for ln in lines)
    found = set().union(*(keys(ln) for ln in lines))
    assert not found & EXCLUDED_KEYS, found & EXCLUDED_KEYS
    text = "".join(f.read_text() for f in vl.dir.glob("*.jsonl"))
    ids = {o.order_id for o in scn.paper._orders.values()}
    assert ids and not any(i in text for i in ids)
    assert "sekrit" not in text and "refresh" not in text.lower()
