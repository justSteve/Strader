#!/usr/bin/env python3
"""Anchored Market Profile (TPO) — a named open through now. [st-jz12]

The time sibling of ``scripts/premarket_volume_profile.py``. Same window, same
anchor, same failure contract; where that page answers "how many contracts
traded here", this one answers "how many half hours accepted this price".

Steve, 2026-09-10: a standalone Market Profile page mirroring the standalone
Volume Profile page — ONE profile anchored on the prior day's RTH open (08:30
CT) and running to now, so the prior cash session, the overnight and today so
far are a single TPO distribution. POC, value area, Initial Balance and single
prints therefore describe everything since the last time the cash market
opened.

    ./scripts/run.sh scripts/anchored_market_profile.py --dry-run
    .venv/bin/python scripts/anchored_market_profile.py --out /tmp/mp.html
    .venv/bin/python scripts/anchored_market_profile.py --anchor overnight

The window start is one of the three anchors Steve settled on (2026-09-10),
defined once in ``anchored_profile.ANCHORS`` and shared with the volume page:
``prior`` (the prior day's 08:30 CT cash open, the default), ``overnight``
(the most recent 17:00 CT Globex open) and ``today`` (the most recent 08:30 CT
cash open). The header names the one in force and carries links that switch
it; ``scripts/profile_server.py`` reads them off ``?anchor=``.

The renderer is importable, so the on-demand HTTP server never shells out::

    from scripts.anchored_market_profile import build, render_html
    html = render_html(build(anchor="overnight"))

Bracket letters restart at every session boundary, so a cash session reads
A, B, C … exactly as ``scripts/market_profile_drill.py`` teaches it, and the
overnight reads in its own lower-case run. The three stretches are coloured
apart and the legend names them.

Source is the ES tick corpus — real prints, native resolution — read through
``premarket_volume_profile.trades_from_corpus`` so the two pages cannot drift
onto different windows or disagree about a packed corpus day.

Failure contract, matching the sibling: on a fetch failure nothing is written
and the script exits non-zero, leaving any previously written page in place.
The page stamps its own anchor and generated-at time, so a stale page is
visibly stale rather than quietly wrong.
"""
from __future__ import annotations

import argparse
import html
import logging
import subprocess
import sys
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market.orderflow.anchored_profile import (                  # noqa: E402
    ANCHORS,
    CENTRAL,
    anchor_start,
    anchor_utc,
)
from market.orderflow.tpo import (                               # noqa: E402
    BRACKET_MIN,
    HALT_END,
    HALT_START,
    ROLE_OVERNIGHT,
    ROLE_PRIOR_RTH,
    ROLE_TODAY_RTH,
    TPO_ROW_TICKS,
    build_anchored_tpo,
    counts_by_role,
    poc_row,
    segment_initial_balance,
    single_print_rows,
    value_area,
)
from market.signals.orderflow_config import TICK                 # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The window reader lives in the volume sibling; importing it keeps ONE
# definition of "which corpus days does this anchor touch, and how is a packed
# day opened" — the defect that bit the sibling on 2026-08-18 is fixed in one
# place or in neither.
from premarket_volume_profile import (                           # noqa: E402
    hole_banner,
    trades_from_corpus,
)

logger = logging.getLogger("anchored_mp")

SYMBOL = "/ES"
#: Stable desk slot, alongside the volume sibling. Written only when --out is
#: left at its default; the HTTP server calls build()/render_html() in-process
#: and never touches disk.
DESK_TRADING = Path("/root/projects/COO/myDesk/trading")
PAGE = DESK_TRADING / "anchored-market-profile.html"
DESK_REGISTER = Path("/root/projects/COO/tmuxMOO/bin/desk-register.sh")

ROLE_NAMES = {
    ROLE_PRIOR_RTH: "prior cash session",
    ROLE_OVERNIGHT: "overnight (Globex)",
    ROLE_TODAY_RTH: "today's cash session",
}
ROLE_CLASS = {ROLE_PRIOR_RTH: "rp", ROLE_OVERNIGHT: "ro", ROLE_TODAY_RTH: "rt"}


#: How far outside the halt window a silence may reach and still be called the
#: halt. ES prints many times a second right up to the bell, so the last print
#: before a halt lands within seconds of 16:00 CT (15:59:57 on 2026-09-09) and
#: the first after it within seconds of 17:00. Five minutes is slack for a
#: thin tape; anything wider is unexplained and gets the loud banner.
HALT_PAD_MIN = 5


def _halt_only(a: datetime, b: datetime) -> bool:
    """True when a tape silence is explained by CME's daily maintenance halt.

    The market was shut from 16:00 to 17:00 CT — no bracket is missing and no
    price was rejected, so this silence is not the hole the sibling's banner
    warns about. Judged by containment in a padded halt window rather than by
    duration, so a capture that actually died over the same hour still reads
    as a hole (it would start well before 15:55 or end well after 17:05).
    """
    a_ct, b_ct = a.astimezone(CENTRAL), b.astimezone(CENTRAL)
    if a_ct.date() != b_ct.date() or a_ct.weekday() >= 5:
        return False
    pad = timedelta(minutes=HALT_PAD_MIN)
    halt_open = datetime.combine(a_ct.date(), HALT_START, tzinfo=a_ct.tzinfo)
    halt_shut = datetime.combine(a_ct.date(), HALT_END, tzinfo=a_ct.tzinfo)
    return halt_open - pad <= a_ct and b_ct <= halt_shut + pad


def build(now_utc: datetime | None = None, *, anchor: str = "prior",
          bucket_ticks: int = TPO_ROW_TICKS, bracket_min: int = BRACKET_MIN,
          session_day: _date | None = None) -> dict:
    """The page's data payload — JSON-serialisable, renderer-independent.

    ``anchor`` is one of ``ANCHORS`` and says where the window starts:
    ``prior`` the prior day's 08:30 CT cash open, ``overnight`` the most recent
    17:00 CT Globex open, ``today`` the most recent 08:30 CT cash open. The
    timestamp comes from ``anchored_profile.anchor_start`` — the one definition
    both profile pages and the server share, so a link on one page and a link
    on the other cannot mean different moments.

    ``session_day`` pins the ``prior`` anchor to a given day (the tests and any
    caller replaying a past morning); with any other anchor there is no day to
    pin and it is ignored. The window runs from the anchor to ``now_utc``
    (default: now).

    ``bucket_ticks`` is the price-row width in ES ticks. The default 4 (1.0 pt)
    is the classic ES Market Profile row, the one ``market_profile_drill.py``
    teaches on, and the resolution at which a two-session window's letters fit
    the viewport at full size (measured 2026-09-10: 82 rows against 324). Pass
    1 for the volume sibling's native 0.25-pt rows; the page still renders, but
    it scrolls and the browser shrinks the letters to about 5.5 px.

    Raises on an unusable source or an unknown anchor — the caller keeps
    last-good rather than writing a hole.
    """
    if anchor not in ANCHORS:
        raise ValueError(f"anchor must be one of {', '.join(ANCHORS)}; got {anchor!r}")
    end_utc = now_utc or datetime.now(tz=timezone.utc)
    if anchor == "prior" and session_day is not None:
        day, start_utc = session_day, anchor_utc(session_day)
    else:
        start_utc = anchor_start(anchor, end_utc)
        day = start_utc.astimezone(CENTRAL).date()
    anchor_ct = start_utc.astimezone(CENTRAL)
    end_ct = end_utc.astimezone(CENTRAL)
    logger.info("anchor: %s (%s) -> %s",
                anchor_ct.strftime("%a %Y-%m-%d %H:%M CT"), ANCHORS[anchor],
                end_ct.strftime("%a %H:%M CT"))

    anchored = build_anchored_tpo(
        trades_from_corpus(start_utc), anchor_ct,
        row_ticks=bucket_ticks, bracket_min=bracket_min, end_ct=end_ct)

    profile = anchored.profile
    counts = profile.counts()
    poc_i = poc_row(profile)
    val_i, vah_i = value_area(profile)
    singles = single_print_rows(profile)
    roles = anchored.roles()
    by_role = counts_by_role(anchored)
    total = sum(counts)
    va_tpos = sum(counts[val_i:vah_i + 1])

    segments = []
    for seg in anchored.segments:
        ib = segment_initial_balance(anchored, seg)
        segments.append({
            "role": seg.role, "kind": seg.kind, "day": seg.day.isoformat(),
            "start_ct": seg.start_ct.isoformat(), "end_ct": seg.end_ct.isoformat(),
            "label": seg.label, "n_brackets": len(seg.indices),
            "ib": {"low": ib[0], "high": ib[1]} if ib else None,
        })

    holes = [{"from": a.isoformat(), "to": b.isoformat(),
              "secs": (b - a).total_seconds(), "halt_only": _halt_only(a, b)}
             for a, b in anchored.holes]

    return {
        "v": 1,
        "symbol": SYMBOL,
        "anchor": anchor,
        "anchor_label": ANCHORS[anchor],
        "session_day": day.isoformat(),
        "anchor_ct": anchor_ct.isoformat(),
        "end_ct": anchored.end_ct.isoformat(),
        "generated_ct": datetime.now(tz=CENTRAL).isoformat(),
        "bracket_min": bracket_min,
        "bucket_ticks": bucket_ticks,
        "row_pts": profile.row_pts,
        "n_trades": anchored.n_trades,
        "n_brackets": len(profile.brackets),
        "total_tpos": total,
        "prices": list(profile.prices),
        "counts": list(counts),
        "counts_by_role": {k: list(v) for k, v in by_role.items()},
        "brackets": [{
            "letter": b.letter, "index": b.index, "role": roles[b.index],
            "kind": b.segment, "t0": b.start_ts.isoformat(),
            "t1": b.end_ts.isoformat(), "touched": list(b.row_indices),
            "close": b.close,
        } for b in profile.brackets],
        "segments": segments,
        "poc": profile.prices[poc_i], "poc_row": poc_i,
        "vah": profile.prices[vah_i], "vah_row": vah_i,
        "val": profile.prices[val_i], "val_row": val_i,
        "va_tpos": va_tpos, "va_achieved": va_tpos / total if total else 0.0,
        "singles": [profile.prices[i] for i in singles],
        "single_rows": singles,
        "last": anchored.last_price,
        "holes": holes,
    }


# ── render ───────────────────────────────────────────────────────────────────

def _row_cells(payload: dict) -> list[list[tuple[str, str]]]:
    """Per price row, the bracket letters that printed there in time order,
    each tagged with its segment role. This is the profile itself."""
    cells: list[list[tuple[str, str]]] = [[] for _ in payload["prices"]]
    for b in payload["brackets"]:                 # already chronological
        cls = ROLE_CLASS[b["role"]]
        for i in b["touched"]:
            cells[i].append((b["letter"], cls))
    return cells


def _runs(cells: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Collapse consecutive same-role letters into one span each — the row's
    HTML is a handful of elements instead of one per letter, and a monospace
    font makes the run's width exactly proportional to its TPO count."""
    out: list[list[str]] = []
    for letter, cls in cells:
        if out and out[-1][0] == cls:
            out[-1][1] += letter
        else:
            out.append([cls, letter])
    return [(cls, text) for cls, text in out]


def render_html(payload: dict) -> str:
    """Self-contained page — no external assets, renders with no network.

    Layout mirrors the volume sibling: the price axis is on the RIGHT and the
    profile grows leftward from it, so the two pages read the same way on the
    desk. Within a row the letters run left to right in time order, packed
    against the axis — the classic stacked-TPO look.
    """
    prices = payload["prices"]
    counts = payload["counts"]
    by_role = payload["counts_by_role"]
    cells = _row_cells(payload)
    singles = set(payload["single_rows"])
    peak = max(counts) or 1
    last = payload["last"]
    row_pts = payload["row_pts"]

    anchor_ct = datetime.fromisoformat(payload["anchor_ct"])
    end_ct = datetime.fromisoformat(payload["end_ct"])
    gen_ct = datetime.fromisoformat(payload["generated_ct"])
    anchor = payload["anchor"]
    # Labels are our own fixed strings, but they land in element text, so
    # escape them the way every other run of prose on this page is escaped.
    anchor_name = html.escape(payload["anchor_label"], quote=False)
    # The three anchors as links that rewrite ?anchor= on the current URL, the
    # markup the volume sibling uses so the two pages switch the same way. A
    # page written to a file has no query string to rewrite, so the links are
    # live only when it is served (scripts/profile_server.py).
    anchor_links = " · ".join(f"<b>{k}</b>" if k == anchor
                              else f'<a href="?anchor={k}">{k}</a>' for k in ANCHORS)

    # Today's Initial Balance is the one marked on the profile; every session's
    # IB is listed in the frame, because the window holds more than one.
    ib_rows: dict[int, str] = {}
    ib_stats = []
    for seg in payload["segments"]:
        if not seg["ib"]:
            continue
        name = "Today IB" if seg["role"] == ROLE_TODAY_RTH else "Prior IB"
        ib_stats.append((name, seg["ib"]))
        if seg["role"] == ROLE_TODAY_RTH:
            for price, side in ((seg["ib"]["low"], "ibl"), (seg["ib"]["high"], "ibh")):
                i = round((price - prices[0]) / row_pts)
                if 0 <= i < len(prices):
                    ib_rows[i] = side

    # Price labels on whole points; the axis is contiguous, one label per point.
    label_every = max(1, int(round(1.0 / row_pts)))
    rows = []
    for i in range(len(prices) - 1, -1, -1):          # high price at the top
        price, tot = prices[i], counts[i]
        cls = []
        if i == payload["poc_row"]:
            cls.append("poc")
        elif payload["val_row"] <= i <= payload["vah_row"]:
            cls.append("va")
        if i == payload["vah_row"]:
            cls.append("vah")
        if i == payload["val_row"]:
            cls.append("val")
        if i in singles:
            cls.append("sp")
        if i in ib_rows:
            cls.append(ib_rows[i])
        if price <= last < price + row_pts:
            cls.append("here")
        seg = "".join(f'<span class="{c}">{t}</span>' for c, t in _runs(cells[i]))
        title = (f"{price:g}  {tot} TPO  ·  prior {by_role[ROLE_PRIOR_RTH][i]}"
                 f" / overnight {by_role[ROLE_OVERNIGHT][i]}"
                 f" / today {by_role[ROLE_TODAY_RTH][i]}")
        if i in singles:
            title += "  ·  single print"
        show = (round(price / row_pts) % label_every == 0)
        label = f"{price:g}" if show else ""
        rows.append(f'<div class="r {" ".join(cls)}" title="{html.escape(title)}">'
                    f'<div class="tpo">{seg}</div>'
                    f'<div class="px">{label}</div></div>')

    pos = ("inside the value area" if payload["val"] <= last <= payload["vah"]
           else "above the value area" if last > payload["vah"] else "below the value area")

    seg_lines = "".join(
        f'<div class="k"><i class="{ROLE_CLASS[s["role"]]}"></i>'
        f'{html.escape(ROLE_NAMES[s["role"]], quote=False)} '
        f'<b>{html.escape(s["label"], quote=False)}</b> '
        f'({s["n_brackets"]})</div>'
        for s in payload["segments"])

    ib_html = "".join(
        f'<div class="stat"><span>{html.escape(n, quote=False)}</span>'
        f'<b>{ib["low"]:g}–{ib["high"]:g}</b></div>' for n, ib in ib_stats)

    banner = ""
    if payload["holes"]:
        worst = max(payload["holes"], key=lambda h: h["secs"])
        a = datetime.fromisoformat(worst["from"])
        b = datetime.fromisoformat(worst["to"])
        if worst["halt_only"]:
            text = (f"No prints from {a.astimezone(CENTRAL):%a %H:%M} to "
                    f"{b.astimezone(CENTRAL):%a %H:%M} CT "
                    f"({worst['secs'] / 3600:.1f} h) — that is CME's daily "
                    f"maintenance halt, not a hole in the capture. No brackets "
                    f"are missing; the profile simply has none there.")
            cls = "banner ok"
        else:
            text = hole_banner((a, b, worst["secs"]))
            cls = "banner"
        banner = (f'<div class="{cls}"><b>'
                  f'{"Exchange halt." if worst["halt_only"] else "Incomplete window."}'
                  f'</b> {html.escape(text, quote=False)}</div>')

    singles_note = (f"{len(singles)} single-print row{'' if len(singles) == 1 else 's'}"
                    " flagged" if singles else "no interior single prints")

    return f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Market Profile — {SYMBOL} — anchored {anchor_ct:%a %b %-d %H:%M} CT ({anchor_name})</title>
<style>
 :root {{ color-scheme: light dark; --ink:#1c1f24; --dim:#6b7280; --line:#e3e6ea;
          --bg:#fff; --prior:#5b8ff9; --on:#9aa7b8; --today:#26a69a;
          --vaTint:rgba(120,160,220,.13); --poc:#f2b134; --here:#d1495b;
          --sp:#b06ab3; --ib:#7a8899; }}
 @media (prefers-color-scheme: dark) {{ :root {{ --ink:#e8eaed; --dim:#9aa0a6;
          --line:#2c3036; --bg:#15171a; --prior:#6f9cf5; --on:#5a6675;
          --today:#2fbfae; --vaTint:rgba(120,160,220,.10); --poc:#d9992b;
          --here:#e06c78; --sp:#c98fd0; --ib:#66717f; }} }}
 html, body {{ height:100%; }}
 body {{ margin:0; background:var(--bg); color:var(--ink); overflow:hidden;
        font:14px/1.5 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif; }}
 /* The profile IS the page, same as the volume sibling: it fills the viewport
    and each price row takes an equal share of the height. When that leaves the
    rows too short for a legible letter the script switches to a fixed row
    height and lets the page scroll — a TPO profile whose letters cannot be
    read is not a TPO profile. */
 .prof {{ position:absolute; inset:0; display:flex; flex-direction:column;
          padding:4px 0; overflow:hidden; }}
 .prof.scroll {{ display:block; overflow-y:auto; }}
 .r {{ flex:1 1 0; min-height:0; display:flex; align-items:stretch; }}
 .prof.scroll .r {{ flex:none; height:var(--rowh,10px); }}
 .tpo {{ flex:1; min-width:0; display:flex; justify-content:flex-end;
         align-items:center; overflow:hidden; white-space:nowrap;
         font:var(--fs,10px)/1 ui-monospace,SFMono-Regular,Menlo,monospace; }}
 .tpo span {{ display:inline-block; }}
 .tpo .rp {{ color:var(--prior); }}
 .tpo .ro {{ color:var(--on); }}
 .tpo .rt {{ color:var(--today); }}
 /* Rows too short for type: the letters go transparent and their spans paint
    as blocks. The monospace advance still sets the width, so the histogram
    keeps exactly the shape it had. */
 .prof.blocks .tpo span {{ color:transparent; }}
 .prof.blocks .tpo .rp {{ background:var(--prior); }}
 .prof.blocks .tpo .ro {{ background:var(--on); }}
 .prof.blocks .tpo .rt {{ background:var(--today); }}
 .r .px {{ width:58px; flex:none; display:flex; align-items:center;
           justify-content:flex-end; padding-left:8px; color:var(--dim);
           font:10px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
           overflow:visible; white-space:nowrap; }}
 .r .px.thin {{ visibility:hidden; }}
 .r.va {{ background:var(--vaTint); }}
 .r.poc {{ background:var(--vaTint); box-shadow:inset 0 0 0 1px var(--poc); }}
 .r.poc .px {{ color:var(--poc); font-weight:700; visibility:visible; }}
 .r.vah {{ box-shadow:inset 0 1px 0 var(--poc); }}
 .r.val {{ box-shadow:inset 0 -1px 0 var(--poc); }}
 .r.vah .px, .r.val .px {{ color:var(--ink); visibility:visible; }}
 .r.here {{ box-shadow:inset 0 -1px 0 var(--here); }}
 .r.here .px {{ color:var(--here); font-weight:700; visibility:visible; }}
 .r.ibh {{ box-shadow:inset 0 1px 0 var(--ib); }}
 .r.ibl {{ box-shadow:inset 0 -1px 0 var(--ib); }}
 /* Single-print flag, drawn in the empty gutter on the left of the row rather
    than inside .tpo (which clips its overflow). Absolutely positioned, so it
    never becomes a flex item and never shifts the histogram. */
 .r.sp {{ position:relative; }}
 .r.sp::before {{ content:"\\203A"; position:absolute; left:4px; top:50%;
                  transform:translateY(-50%); color:var(--sp);
                  font:700 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace; }}
 #hud {{ position:absolute; top:10px; left:10px; z-index:5; width:max-content;
         max-width:min(430px, calc(100vw - 76px)); padding:8px 12px 9px;
         border:1px solid var(--line); border-radius:8px;
         background:color-mix(in srgb, var(--bg) 90%, transparent);
         backdrop-filter:blur(3px); box-shadow:0 2px 10px rgba(0,0,0,.25);
         cursor:grab; user-select:none; font-size:12px; }}
 #hud.dragging {{ cursor:grabbing; box-shadow:0 4px 16px rgba(0,0,0,.4); }}
 h1 {{ font-size:14px; margin:0; }}
 .sub {{ color:var(--dim); font-size:11px; line-height:1.4; margin:2px 0 0; }}
 .sub a {{ color:var(--dim); }}
 .sub b {{ color:var(--ink); }}
 .stats {{ display:flex; gap:12px 16px; flex-wrap:wrap; margin:7px 0 0;
           padding:7px 9px; border:1px solid var(--line); border-radius:6px; }}
 .stat b {{ display:block; font:600 15px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace; }}
 .stat span {{ color:var(--dim); font-size:10px; text-transform:uppercase;
               letter-spacing:.05em; }}
 .legend {{ display:flex; gap:10px 14px; flex-wrap:wrap; margin:6px 0 0;
            color:var(--dim); font-size:11px; }}
 .k {{ display:flex; align-items:center; gap:5px; }}
 .k i {{ width:10px; height:10px; border-radius:2px; display:inline-block; }}
 i.rp {{ background:var(--prior); }} i.ro {{ background:var(--on); }}
 i.rt {{ background:var(--today); }} i.spk {{ background:var(--sp); }}
 .note {{ margin:6px 0 0; color:var(--dim); font-size:11px; line-height:1.4;
          max-width:390px; }}
 .banner {{ margin:6px 0 0; padding:6px 9px; max-width:390px; border-radius:6px;
            line-height:1.4; background:#fff4e5; border:1px solid #f0c987;
            color:#7a4b06; font-size:11px; }}
 .banner.ok {{ background:#eef3f8; border-color:#c8d6e5; color:#42566b; }}
 @media (prefers-color-scheme: dark) {{
   .banner {{ background:#3a2c12; border-color:#7a5a1e; color:#f0d9a8; }}
   .banner.ok {{ background:#1e2530; border-color:#39465a; color:#b9c7d8; }} }}
 #mode {{ margin-left:6px; font:11px/1 inherit; color:var(--dim); cursor:pointer;
          background:none; border:1px solid var(--line); border-radius:4px;
          padding:3px 6px; }}
 @media (max-width:520px) {{ #hud {{ font-size:11px; max-width:calc(100vw - 76px); }} }}
</style>
<div class="prof" id="prof" data-rows="{len(prices)}" data-peak="{peak}">{"".join(rows)}</div>
<div id="hud">
<h1>Market Profile — {SYMBOL}<button id="mode" type="button">fit</button></h1>
<div class="sub">
  Anchored {anchor_ct:%A %b %-d, %H:%M CT} ({anchor_name}) → {end_ct:%a %H:%M CT}<br>
  anchor: {anchor_links}<br>
  {payload['n_trades']:,} prints · {payload['n_brackets']} brackets of
  {payload['bracket_min']} min · {payload['total_tpos']:,} TPO ·
  {row_pts:g}-pt rows · generated {gen_ct:%Y-%m-%d %H:%M CT}
</div>
{banner}
<div class="stats">
  <div class="stat"><span>VAH</span><b>{payload['vah']:g}</b></div>
  <div class="stat"><span>POC</span><b>{payload['poc']:g}</b></div>
  <div class="stat"><span>VAL</span><b>{payload['val']:g}</b></div>
  <div class="stat"><span>VA width</span><b>{payload['vah'] - payload['val']:g}</b></div>
  {ib_html}
  <div class="stat"><span>Last</span><b>{last:g}</b></div>
  <div class="stat"><span>vs POC</span><b>{last - payload['poc']:+g}</b></div>
</div>
<div class="legend">{seg_lines}
  <div class="k"><i class="spk"></i>single print (›)</div>
  <div class="k">hover a row for its TPO split</div>
</div>
<p class="note">
  Price is <b>{html.escape(pos, quote=False)}</b>. Value area holds {payload['va_achieved']:.0%}
  of the TPOs ({payload['va_tpos']:,} of {payload['total_tpos']:,}); {singles_note}.
  One letter is one {payload['bracket_min']}-minute bracket that traded at that
  price — letters restart at each session boundary, so each cash session reads
  A, B, C&hellip; and the overnight reads in lower case.
</p>
</div>
<script>
// Inline, no external assets — desk pages render with no network.
(function () {{
  var prof = document.getElementById("prof"), hud = document.getElementById("hud"),
      btn = document.getElementById("mode");
  var N = +prof.dataset.rows || 1, PEAK = +prof.dataset.peak || 1;
  var AXIS = 66, ADVANCE = 0.62, FLOOR = 5.5, CAP = 13;
  var forced = null;                       // null = auto, else "fit" | "letters"

  function layout() {{
    var availW = Math.max(60, prof.clientWidth - AXIS - 10);
    var fsW = availW / (PEAK * ADVANCE);           // widest row must fit
    var fsH = prof.clientHeight / N * 0.95;        // a row must fit its letter
    var fit = Math.min(fsW, fsH);
    var mode = forced || (fit >= FLOOR ? "fit" : "letters");
    var fs;
    if (mode === "fit") {{
      prof.classList.remove("scroll");
      fs = Math.max(1, Math.min(CAP, fit));
      prof.classList.toggle("blocks", fs < FLOOR);
    }} else {{
      prof.classList.add("scroll");
      prof.classList.remove("blocks");
      fs = Math.max(FLOOR, Math.min(CAP, fsW));
      prof.style.setProperty("--rowh", (fs * 1.3).toFixed(2) + "px");
    }}
    prof.style.setProperty("--fs", fs.toFixed(2) + "px");
    btn.textContent = mode === "fit" ? "fit" : "letters";
    thin();
  }}

  // Whole-point labels are all in the HTML; when rows are tighter than the
  // type, keep every 2, 5, 10, 25 … points so labels never overprint. POC,
  // VAH, VAL and Last always show (CSS forces them visible).
  function thin() {{
    var rows = prof.querySelectorAll(".r"); if (!rows.length) return;
    var rowH = rows[0].getBoundingClientRect().height || 1;
    var steps = [1, 2, 5, 10, 25, 50, 100], step = steps[steps.length - 1];
    for (var i = 0; i < steps.length; i++) {{ if (steps[i] * rowH / {row_pts:g} >= 12) {{ step = steps[i]; break; }} }}
    rows.forEach(function (r) {{
      var px = r.querySelector(".px"); if (!px || !px.textContent) return;
      var p = parseFloat(px.textContent);
      px.classList.toggle("thin", Math.abs(p / step - Math.round(p / step)) > 1e-9);
    }});
  }}

  btn.addEventListener("click", function (e) {{
    e.stopPropagation();
    forced = prof.classList.contains("scroll") ? "fit" : "letters";
    layout();
  }});
  layout(); window.addEventListener("resize", layout);

  // Drag the frame anywhere inside the page; clamped so it cannot be lost.
  var dx = 0, dy = 0, on = false;
  hud.addEventListener("mousedown", function (e) {{
    if (e.target.closest("a,button,select,input")) return;
    var r = hud.getBoundingClientRect(); dx = e.clientX - r.left; dy = e.clientY - r.top;
    on = true; hud.classList.add("dragging"); e.preventDefault();
    function move(ev) {{
      if (!on) return;
      var x = Math.min(Math.max(ev.clientX - dx, 0), Math.max(0, window.innerWidth - hud.offsetWidth));
      var y = Math.min(Math.max(ev.clientY - dy, 0), Math.max(0, window.innerHeight - hud.offsetHeight));
      hud.style.left = x + "px"; hud.style.top = y + "px";
    }}
    function up() {{ on = false; hud.classList.remove("dragging");
      window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); }}
    window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
  }});
}})();
</script>
"""


def publish(page_html: str, out: Path, *, register: bool = False) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page_html, encoding="utf-8")
    logger.info("page: %s (%d bytes)", out, len(page_html))
    if not register:
        return
    try:
        r = subprocess.run([str(DESK_REGISTER), "Trading", f"myDesk/trading/{out.name}"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode:
            logger.warning("desk-register failed (rc=%d): %s",
                           r.returncode, r.stderr.strip()[:200])
        else:
            logger.info("registered in Trading window: %s", out.name)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("desk-register skipped: %s", e)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", help="anchor session day (YYYY-MM-DD); "
                                   "default = most recent completed session")
    ap.add_argument("--out", help=f"output HTML path (default {PAGE})")
    ap.add_argument("--anchor", choices=tuple(ANCHORS), default="prior",
                    help="window start: prior (prior day's 08:30 CT open, "
                         "default), overnight (most recent 17:00 CT Globex "
                         "open), today (most recent 08:30 CT open)")
    ap.add_argument("--bucket-ticks", type=int, default=TPO_ROW_TICKS,
                    help=f"price-row width in ES ticks (default "
                         f"{TPO_ROW_TICKS} = {TPO_ROW_TICKS * TICK:g}pt, the "
                         f"classic Market Profile row; 1 = {TICK:g}pt, the "
                         "volume sibling's native resolution)")
    ap.add_argument("--bracket-min", type=int, default=BRACKET_MIN,
                    help=f"minutes per TPO bracket (default {BRACKET_MIN})")
    ap.add_argument("--register", action="store_true",
                    help="also register the page in the desk's Trading window")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and summarise, write nothing (ignores --out)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    day = _date.fromisoformat(args.date) if args.date else None
    try:
        payload = build(anchor=args.anchor, bucket_ticks=args.bucket_ticks,
                        bracket_min=args.bracket_min, session_day=day)
        page = render_html(payload)
    except Exception as e:  # noqa: BLE001 — last-good contract, same as the sibling
        logger.error("source unusable, any published page LEFT AS-IS: %s", e)
        return 2

    for h in payload["holes"]:
        logger.warning("tape %s: %s -> %s (%.1f h)",
                       "halt" if h["halt_only"] else "hole",
                       h["from"], h["to"], h["secs"] / 3600)

    if args.dry_run:
        logger.info("dry run — page NOT written (%d bytes)", len(page))
    else:
        publish(page, Path(args.out) if args.out else PAGE, register=args.register)

    anchor_ct = datetime.fromisoformat(payload["anchor_ct"])
    end_ct = datetime.fromisoformat(payload["end_ct"])
    segs = "  ".join(f"{s['label']}={ROLE_NAMES[s['role']].split()[0]}"
                     for s in payload["segments"])
    print(f"{SYMBOL} anchored TPO [{payload['anchor']}] — {payload['n_trades']:,} "
          f"prints, {payload['n_brackets']} brackets of "
          f"{payload['bracket_min']}min, {payload['total_tpos']:,} TPO, "
          f"{payload['row_pts']:g}pt rows\n"
          f"  anchor {anchor_ct:%a %H:%M CT} ({payload['anchor_label']})"
          f"  ->  {end_ct:%a %H:%M CT}   [{segs}]\n"
          f"  VAH {payload['vah']:g}   POC {payload['poc']:g}   "
          f"VAL {payload['val']:g}   (VA {payload['va_achieved']:.0%}, "
          f"width {payload['vah'] - payload['val']:g})\n"
          f"  last {payload['last']:g} ({payload['last'] - payload['poc']:+g} vs POC)"
          f"   single prints {len(payload['single_rows'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
