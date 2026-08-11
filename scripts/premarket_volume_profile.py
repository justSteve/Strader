#!/usr/bin/env python3
"""Premarket anchored volume profile → steves-desk Trading window. [st-eo0]

Steve, 2026-08-11: a chart built each premarket showing the volume profile
anchored on the PRIOR DAY'S RTH OPEN (08:30 CT), delivered as a page linked in
the Desk's Trading window. Runs at 08:15 CT alongside the Mancini prep.

    ./scripts/run.sh scripts/premarket_volume_profile.py
    ./scripts/run.sh scripts/premarket_volume_profile.py --dry-run   # no publish

The window spans the prior cash open through now — prior day session, the
evening/overnight, and the premarket as ONE distribution. POC / VAH / VAL
therefore describe everything since the last time the cash market opened, which
is the question a premarket read is actually asking: where has value been built
since yesterday's bell, and where is price standing relative to it.

Source is Schwab 5-minute extended-hours candles, not the tick corpus — see the
module docstring of market/orderflow/anchored_profile.py for why (the corpus has
an ~11h nightly hole that would silently swallow the evening session).

Failure contract: on a fetch failure the previously published page is LEFT IN
PLACE and the script exits non-zero. The page always stamps its own anchor and
generated-at time in the header, so a stale page is visibly stale rather than
quietly wrong.
"""
from __future__ import annotations

import argparse
import html
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market.corpus.paths import most_recent_session_day
from market.entities.volume_profile import VolumeProfile
from market.orderflow.anchored_profile import (
    CENTRAL,
    ValueArea,
    anchor_utc,
    build_profile_from_bars,
    value_area,
)

logger = logging.getLogger("premarket_vp")

SYMBOL = "/ES"
# Published page + its Trading-window registration. Stable filename so the desk
# link never moves; the CONTENT is replaced each morning.
DESK_TRADING = Path("/root/projects/COO/myDesk/trading")
PAGE = DESK_TRADING / "premarket-volume-profile.html"
DESK_REGISTER = Path("/root/projects/COO/tmuxMOO/bin/desk-register.sh")


def fetch_bars(start_utc: datetime, end_utc: datetime | None = None) -> list[dict]:
    """Five-minute /ES candles, extended hours included. Raises on anything
    unusable — the caller keeps last-good rather than publishing a hole."""
    from broker_schwab.client import create_client

    client = create_client()
    end_utc = end_utc or datetime.now(tz=timezone.utc)
    r = client.get_price_history_every_five_minutes(
        SYMBOL, start_datetime=start_utc, end_datetime=end_utc,
        need_extended_hours_data=True,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Schwab price history HTTP {r.status_code}")
    data = r.json()
    candles = data.get("candles", [])
    if data.get("empty") or not candles:
        raise RuntimeError(f"Schwab returned no candles for {SYMBOL}")
    return candles


def _ct(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(CENTRAL)


def render_page(profile: VolumeProfile, va: ValueArea, bars: list[dict],
                anchor_ct: datetime, generated_ct: datetime) -> str:
    """Self-contained HTML: horizontal histogram, value area shaded, last price
    marked. No external assets — desk pages must render with no network."""
    last = float(bars[-1]["close"])
    peak = max(profile.volumes) or 1
    rows = []
    # High price at the top, the way a profile is read off a chart.
    for price, vol in sorted(zip(profile.prices, profile.volumes),
                             key=lambda pv: pv[0], reverse=True):
        classes = []
        if price == va.poc:
            classes.append("poc")
        elif va.val <= price <= va.vah:
            classes.append("va")
        if price <= last < price + profile.bucket_pts:
            classes.append("here")
        rows.append(
            f'<tr class="{" ".join(classes)}">'
            f'<td class="px">{price:g}</td>'
            f'<td class="bar"><span style="width:{vol / peak * 100:.2f}%"></span></td>'
            f'<td class="vol">{vol:,}</td></tr>'
        )

    pos = ("inside the value area" if va.val <= last <= va.vah
           else "above the value area" if last > va.vah else "below the value area")
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Premarket Volume Profile — {SYMBOL} — anchored {anchor_ct:%a %b %-d} 08:30 CT</title>
<style>
 :root {{ color-scheme: light dark; --ink:#1c1f24; --dim:#6b7280; --line:#e3e6ea;
          --bg:#fff; --bar:#9aa7b8; --va:#cfe0f5; --poc:#f2b134; --here:#d1495b; }}
 @media (prefers-color-scheme: dark) {{ :root {{ --ink:#e8eaed; --dim:#9aa0a6;
          --line:#2c3036; --bg:#15171a; --bar:#4a5568; --va:#24344a;
          --poc:#d9992b; --here:#e06c78; }} }}
 body {{ margin:0; padding:24px 28px; background:var(--bg); color:var(--ink);
        font:14px/1.5 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif; }}
 h1 {{ font-size:19px; margin:0 0 2px; }}
 .sub {{ color:var(--dim); font-size:12.5px; margin-bottom:18px; }}
 .stats {{ display:flex; gap:26px; flex-wrap:wrap; margin:0 0 20px;
           padding:14px 16px; border:1px solid var(--line); border-radius:8px; }}
 .stat b {{ display:block; font:600 20px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace; }}
 .stat span {{ color:var(--dim); font-size:11.5px; text-transform:uppercase;
               letter-spacing:.05em; }}
 .wrap {{ overflow-x:auto; }}
 table {{ border-collapse:collapse; width:100%; max-width:760px;
          font:12.5px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace; }}
 td {{ padding:1px 8px; white-space:nowrap; }}
 td.px {{ text-align:right; width:1%; color:var(--dim); }}
 td.vol {{ text-align:right; width:1%; color:var(--dim); }}
 td.bar {{ width:100%; }}
 td.bar span {{ display:block; height:11px; background:var(--bar); border-radius:2px; }}
 tr.va td.bar span {{ background:var(--va); }}
 tr.va td.px {{ color:var(--ink); }}
 tr.poc td.bar span {{ background:var(--poc); }}
 tr.poc td.px, tr.poc td.vol {{ color:var(--ink); font-weight:700; }}
 tr.here td.px {{ color:var(--here); font-weight:700; }}
 tr.here td.px::after {{ content:" ◀ last"; font-weight:400; }}
 .note {{ margin-top:20px; color:var(--dim); font-size:12px; max-width:760px; }}
</style>
<h1>Premarket Volume Profile — {SYMBOL}</h1>
<div class="sub">
  Anchored {anchor_ct:%A %b %-d, 08:30 CT} (prior RTH open) →
  {_ct(bars[-1]["datetime"]):%a %H:%M CT} ·
  {len(bars)} five-minute bars · {profile.total:,} contracts ·
  generated {generated_ct:%Y-%m-%d %H:%M CT}
</div>
<div class="stats">
  <div class="stat"><span>VAH</span><b>{va.vah:g}</b></div>
  <div class="stat"><span>POC</span><b>{va.poc:g}</b></div>
  <div class="stat"><span>VAL</span><b>{va.val:g}</b></div>
  <div class="stat"><span>VA width</span><b>{va.width:g}</b></div>
  <div class="stat"><span>Last</span><b>{last:g}</b></div>
  <div class="stat"><span>vs POC</span><b>{last - va.poc:+g}</b></div>
</div>
<div class="wrap"><table>{"".join(rows)}</table></div>
<p class="note">
  Price is <b>{html.escape(pos)}</b>. Value area holds {va.achieved:.0%} of
  volume ({va.volume:,} of {va.total:,} contracts) in {profile.bucket_pts:g}-point
  buckets. Built from Schwab 5-minute extended-hours candles: each bar's volume
  is spread across the prices it touched, so this is a bar-resolution
  approximation, not a tick-exact profile. The tick corpus is not used here — it
  captures 02:50–15:05 CT only, and would drop the evening session silently.
</p>
"""


def publish(page_html: str, dry_run: bool = False) -> None:
    if dry_run:
        logger.info("dry run — page NOT written (%d bytes would go to %s)",
                    len(page_html), PAGE)
        return
    if not DESK_TRADING.exists():
        raise RuntimeError(f"desk trading dir absent: {DESK_TRADING}")
    PAGE.write_text(page_html, encoding="utf-8")
    logger.info("page: %s (%d bytes)", PAGE, len(page_html))
    # Idempotent: skips if already registered. Non-fatal — a written page that
    # is not re-registered is still correct and still at its stable URL.
    try:
        out = subprocess.run(
            [str(DESK_REGISTER), "Trading", f"myDesk/trading/{PAGE.name}"],
            capture_output=True, text=True, timeout=30)
        if out.returncode:
            logger.warning("desk-register failed (rc=%d): %s",
                           out.returncode, out.stderr.strip()[:200])
        else:
            logger.info("registered in Trading window: %s", PAGE.name)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("desk-register skipped: %s", e)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="anchor session day (YYYY-MM-DD); "
                                   "default = most recent completed session")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and summarise, publish nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    session_day = (datetime.strptime(args.date, "%Y-%m-%d").date()
                   if args.date else most_recent_session_day())
    start = anchor_utc(session_day)
    anchor_ct = start.astimezone(CENTRAL)
    logger.info("anchor: %s (prior RTH open)", anchor_ct.strftime("%a %Y-%m-%d %H:%M CT"))

    try:
        bars = fetch_bars(start)
    except Exception as e:  # noqa: BLE001 — last-good contract
        logger.error("fetch failed, published page LEFT AS-IS: %s", e)
        return 2

    profile = build_profile_from_bars(bars, symbol=SYMBOL)
    va = value_area(profile)
    generated = datetime.now(tz=CENTRAL)
    publish(render_page(profile, va, bars, anchor_ct, generated), args.dry_run)

    last = float(bars[-1]["close"])
    print(f"{SYMBOL} anchored VP — {len(bars)} bars, {profile.total:,} contracts\n"
          f"  anchor {anchor_ct:%a %H:%M CT}  ->  {_ct(bars[-1]['datetime']):%a %H:%M CT}\n"
          f"  VAH {va.vah:g}   POC {va.poc:g}   VAL {va.val:g}   "
          f"(VA {va.achieved:.0%}, width {va.width:g})\n"
          f"  last {last:g} ({last - va.poc:+g} vs POC)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
