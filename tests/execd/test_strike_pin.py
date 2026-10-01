"""A strike he sets stays put until a fill. [st-6ogv]

Steve, 2026-10-01: the staged strike follows the market — the highest delta
the account can pay for — until he enters one by hand; then it holds through
every repaint, with a cue on the box, until a new position resets the form.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from execd.orderpage import PANE_LOGIC

from .conftest import page_send, schwab_chain_maps
from .test_orderform import chain, mono, order_page, text  # noqa: F401 — fixtures


def strike_on(ticket_html: str) -> str:
    return re.search(r"id=strikebox [^>]*value='([0-9.]+)'", ticket_html).group(1)


def pin_on(ticket_html: str) -> str:
    return re.search(r"class='pin (manual|auto)' id=strikepin", ticket_html).group(1)


def test_a_manual_strike_holds_through_a_price_move_and_auto_follows(order_page, armed, chain):
    auto = order_page.get("/exec/order/state?side=call").json["fd0_html"]
    manual = order_page.get("/exec/order/state?side=call&strike=6380").json["fd0_html"]
    assert pin_on(auto) == "auto" and pin_on(manual) == "manual"
    assert strike_on(manual) == "6380"
    assert strike_on(auto) == "6350"                    # 0.78, the highest under 0.80
    # the market moves: the deltas rise and the 0.80 cap now falls on 6360
    maps = schwab_chain_maps()
    for key, legs in next(iter(maps["calls"].values())).items():
        leg = legs[0]
        leg["delta"] = round(min(0.95, leg["delta"] + 0.07), 2)
        leg["bid"], leg["ask"] = leg["bid"] + 1.0, leg["ask"] + 1.0
    chain.set_chain("SPXW", maps)
    moved = order_page.get("/exec/order/state?side=call&strike=6380").json["fd0_html"]
    assert strike_on(moved) == "6380" and pin_on(moved) == "manual"
    followed = order_page.get("/exec/order/state?side=call").json["fd0_html"]
    assert strike_on(followed) == "6360" and pin_on(followed) == "auto"


def test_after_a_fill_the_cleared_selection_follows_the_market_again(order_page, armed):
    """The fill resets the form's strike (the script clears the hidden
    field, pinned by the node test below); the selection without it is the
    market's choice again."""
    page_send(order_page, {"side": "call", "strike": "6400"})
    assert armed.status()["positions"]
    after = order_page.get("/exec/order/state?side=call").json["fd0_html"]
    assert pin_on(after) == "auto" and strike_on(after) == "6350"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on this box")
def test_a_fill_hands_the_strike_back_under_node():
    cases = [["working", "filled", True], ["none", "filled", True], ["refused", "filled", True],
             ["filled", "filled", False], ["none", "working", False], ["filled", "closed", False]]
    js = ("var window = {};" + PANE_LOGIC + f"var cases = {json.dumps(cases)};"
          + "var bad = cases.filter(function(c){ return window.__strikeResets(c[0], c[1]) !== c[2]; });"
          + "console.log(JSON.stringify(bad));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == []


def test_the_page_wires_the_reset_and_the_cleared_box(order_page):
    body = text(order_page.get("/exec/order?side=call&strike=6380"))
    assert "window.__onFilled = function(){ if (!form) return; strikeAuto(); reprice(); };" in body
    assert "if (!t.value.trim()) strikeAuto(); else strikeTo(v);" in body
    assert "window.__strikeResets(stageNow() || 'none', j.panel_stage)" in body
