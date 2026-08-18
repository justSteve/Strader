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
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market.corpus.paths import most_recent_session_day
from market.entities.volume_profile import VolumeProfile
from market.orderflow.anchored_profile import (
    CENTRAL,
    ValueArea,
    anchor_utc,
    build_profile_from_bars,
    build_split_profile,
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


def bars_from_corpus(start_utc: datetime) -> list[dict]:
    """Five-minute bars aggregated from the ES tick corpus. Offline fallback.

    Honest but INCOMPLETE: the corpus captures 02:50-15:05 CT, so a profile
    built this way is missing the 15:05->02:50 evening session entirely. The
    rendered page says so in a banner — a gap you cannot see is the one that
    reads as an LVN. Used when Schwab is unavailable (dead token), which
    otherwise leaves this job with no source at all.
    """
    from market.corpus.paths import CORPUS_ROOT

    bars: dict[int, dict] = {}
    day = start_utc.astimezone(CENTRAL).date()
    today = datetime.now(tz=CENTRAL).date()
    while day <= today:
        path = CORPUS_ROOT / day.isoformat() / "databento_glbx_es.jsonl"
        if path.exists():
            with path.open() as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        ts = datetime.fromisoformat(
                            rec["provenance"]["ts_event"].replace("Z", "+00:00"))
                    except (ValueError, KeyError):
                        continue
                    if ts < start_utc:
                        continue
                    price, size = rec["data"]["price"], rec["data"]["size"]
                    k = int(ts.timestamp()) // 300 * 300
                    b = bars.get(k)
                    if b is None:
                        bars[k] = {"datetime": k * 1000, "open": price, "high": price,
                                   "low": price, "close": price, "volume": size}
                    else:
                        b["high"] = max(b["high"], price)
                        b["low"] = min(b["low"], price)
                        b["close"] = price
                        b["volume"] += size
        day += timedelta(days=1)
    if not bars:
        raise RuntimeError("tick corpus holds no ES trades in the anchor window")
    return [bars[k] for k in sorted(bars)]


def trades_from_corpus(start_utc: datetime):
    """Real ES prints from the tick corpus, aggressor flag intact. [st-6gs3]

    The high-resolution path. Bars cannot support tick buckets honestly — a
    bar's volume has to be smeared across the prices it touched — and they
    carry no aggressor at all. Prints carry both.
    """
    from market.corpus.paths import CORPUS_ROOT
    from market.entities.trade import Trade

    day = start_utc.astimezone(CENTRAL).date()
    today = datetime.now(tz=CENTRAL).date()
    n = 0
    while day <= today:
        path = CORPUS_ROOT / day.isoformat() / "databento_glbx_es.jsonl"
        if path.exists():
            with path.open() as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        ts = datetime.fromisoformat(
                            rec["provenance"]["ts_event"].replace("Z", "+00:00"))
                    except (ValueError, KeyError):
                        continue
                    if ts < start_utc:
                        continue
                    d = rec["data"]
                    n += 1
                    yield Trade(ts=ts.astimezone(CENTRAL), symbol=d["symbol"],
                                instrument_id=d.get("instrument_id") or 0,
                                price=d["price"], size=d["size"],
                                side=d.get("side") or "N")
        day += timedelta(days=1)
    if not n:
        raise RuntimeError("tick corpus holds no ES trades in the anchor window")


class _Tally:
    """Pass-through counter for a streaming trade generator.

    The profile builder consumes the generator, so anything the page needs
    about the raw stream — how many prints, and what the last one was — has to
    be captured while it flows past. Re-reading a 100MB corpus file to answer
    "what was the last price" would be absurd.
    """

    __slots__ = ("n", "last")

    def __init__(self):
        self.n = 0
        self.last = None

    def __call__(self, it):
        for t in it:
            self.n += 1
            self.last = t
            yield t


def _ct(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(CENTRAL)


SOURCES = {
    "ticks": ("the ES tick corpus — real prints at native resolution",
              "Every contract sits at the price it actually traded, and the buy/sell "
              "split is Databento's aggressor flag, not an inference. Nothing is "
              "smeared across a bar's range. The window is INCOMPLETE — see the "
              "banner above."),
    "schwab": ("Schwab 5-minute extended-hours candles",
               "Each bar's volume is spread across the prices it touched, so this is a "
               "bar-resolution approximation, not a tick-exact profile. The tick corpus "
               "is not used here — it captures 02:50–15:05 CT only, and would drop the "
               "evening session silently."),
    "corpus": ("the ES tick corpus, aggregated to 5-minute bars",
               "Volume is real prints rather than distributed bar volume, but the window "
               "is INCOMPLETE — see the banner above."),
}
# Shown when the profile is corpus-sourced. Loud by design: an invisible hole in
# a profile reads as a price the market rejected, which is the opposite of true.
CORPUS_BANNER = (
    "Fallback source — the 15:05→02:50 CT evening session is MISSING from this "
    "profile. The tick corpus does not capture it. Treat thin buckets in that "
    "price region as unmeasured, not as rejected price."
)


def render_page(profile, va: ValueArea, last: float, bar_count: int,
                end_ct: datetime, anchor_ct: datetime, generated_ct: datetime,
                source: str = "ticks", aggressor: bool = True) -> str:
    """TradingView-style profile: right-justified bars at tick resolution.

    Layout follows TV's price scale — the axis is on the RIGHT and the bars
    grow leftward from it, so the eye reads the histogram against the price
    column the way it does on a chart. Each row splits buy-aggressor from
    sell-aggressor volume when the source carries it.

    Self-contained: no external assets (one inline script for label thinning
    and the draggable frame), desk pages must render with no network.
    """
    prices = profile.prices
    buys = getattr(profile, "buy_volumes", None)
    sells = getattr(profile, "sell_volumes", None)
    totals = profile.volumes
    peak = max(totals) or 1

    # Price labels only on whole points — at 1-tick resolution every row would
    # be a label and the axis becomes unreadable noise.
    label_every = max(1, int(round(1.0 / profile.bucket_pts)))
    rows = []
    for i in range(len(prices) - 1, -1, -1):          # high price at the top
        price, tot = prices[i], totals[i]
        cls = []
        if price == va.poc:
            cls.append("poc")
        elif va.val <= price <= va.vah:
            cls.append("va")
        if price <= last < price + profile.bucket_pts:
            cls.append("here")
        if aggressor and buys is not None:
            b, s = buys[i], sells[i]
            seg = (f'<i class="sell" style="width:{s / peak * 100:.3f}%"></i>'
                   f'<i class="buy" style="width:{b / peak * 100:.3f}%"></i>')
            title = f"{price:g}  vol {tot:,}  buy {b:,}  sell {s:,}  delta {b - s:+,}"
        else:
            seg = f'<i class="flat" style="width:{tot / peak * 100:.3f}%"></i>'
            title = f"{price:g}  vol {tot:,}"
        show = (round(price / profile.bucket_pts) % label_every == 0)
        label = f"{price:g}" if show else ""
        rows.append(
            f'<div class="r {" ".join(cls)}" title="{title}">'
            f'<div class="bars">{seg}</div>'
            f'<div class="px">{label}</div></div>'
        )

    pos = ("inside the value area" if va.val <= last <= va.vah
           else "above the value area" if last > va.vah else "below the value area")
    delta = getattr(profile, "delta", None)
    delta_stat = (f'<div class="stat"><span>Net delta</span>'
                  f'<b class="{"up" if delta > 0 else "dn"}">{delta:+,}</b></div>'
                  if aggressor and delta is not None else "")
    legend = ('<span class="k"><i class="buy"></i>buy aggressor</span>'
              '<span class="k"><i class="sell"></i>sell aggressor</span>'
              if aggressor else '<span class="k"><i class="flat"></i>volume</span>')

    return f"""<!doctype html>
<meta charset="utf-8">
<title>Premarket Volume Profile — {SYMBOL} — anchored {anchor_ct:%a %b %-d} 08:30 CT</title>
<style>
 :root {{ color-scheme: light dark; --ink:#1c1f24; --dim:#6b7280; --line:#e3e6ea;
          --bg:#fff; --buy:#26a69a; --sell:#ef5350; --flat:#9aa7b8;
          --vaTint:rgba(120,160,220,.13); --poc:#f2b134; --here:#d1495b; }}
 @media (prefers-color-scheme: dark) {{ :root {{ --ink:#e8eaed; --dim:#9aa0a6;
          --line:#2c3036; --bg:#15171a; --flat:#4a5568;
          --vaTint:rgba(120,160,220,.10); --poc:#d9992b; --here:#e06c78; }} }}
 /* The profile IS the page [st-9olq]: it fills the viewport top to bottom and
    every row takes an equal share of the height, so a 400-row profile fits a
    900 px window at ~2 px a row instead of scrolling. Everything that used to
    sit above it lives in a floating frame at the top-left, over the empty
    left side of the histogram (bars grow leftward from the axis on the
    right), sized to its own content and draggable — the treatment Steve
    gave the live footprint page. */
 html, body {{ height:100%; }}
 body {{ margin:0; background:var(--bg); color:var(--ink); overflow:hidden;
        font:14px/1.5 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif; }}
 .prof {{ position:absolute; inset:0; display:flex; flex-direction:column; padding:4px 0; }}
 .r {{ flex:1 1 0; min-height:0; display:flex; align-items:stretch; }}
 .r .bars {{ flex:1; display:flex; justify-content:flex-end; align-items:stretch; min-width:200px; }}
 .r .bars i {{ display:block; height:100%; }}
 .r .px {{ width:58px; flex:none; display:flex; align-items:center; justify-content:flex-end;
           padding-left:8px; color:var(--dim); font:10px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
           overflow:visible; white-space:nowrap; }}
 .r .px.thin {{ visibility:hidden; }}   /* thinned by the script when rows are tight */
 .r.va {{ background:var(--vaTint); }}
 .r.poc {{ background:var(--vaTint); box-shadow:inset 0 0 0 1px var(--poc); }}
 .r.poc .px {{ color:var(--poc); font-weight:700; visibility:visible; }}
 .r.here .px {{ color:var(--here); font-weight:700; visibility:visible; }}
 .r.here {{ box-shadow:inset 0 -1px 0 var(--here); }}
 /* The floating frame. width:max-content, capped — the note and the banner are
    the only long runs and they wrap at their own max-width, so the frame's
    width is set by the stats row, not by a sentence. */
 #hud {{ position:absolute; top:10px; left:10px; z-index:5; width:max-content;
         max-width:min(420px, calc(100vw - 110px)); padding:8px 12px 9px;
         border:1px solid var(--line); border-radius:8px;
         background:color-mix(in srgb, var(--bg) 90%, transparent); backdrop-filter:blur(3px);
         box-shadow:0 2px 10px rgba(0,0,0,.25); cursor:grab; user-select:none; font-size:12px; }}
 #hud.dragging {{ cursor:grabbing; box-shadow:0 4px 16px rgba(0,0,0,.4); }}
 h1 {{ font-size:14px; margin:0; }}
 .sub {{ color:var(--dim); font-size:11px; line-height:1.4; margin:2px 0 0; }}
 .stats {{ display:flex; gap:12px 16px; flex-wrap:wrap; margin:7px 0 0;
           padding:7px 9px; border:1px solid var(--line); border-radius:6px; }}
 .stat b {{ display:block; font:600 15px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace; }}
 .stat b.up {{ color:var(--buy); }} .stat b.dn {{ color:var(--sell); }}
 .stat span {{ color:var(--dim); font-size:10px; text-transform:uppercase; letter-spacing:.05em; }}
 .legend {{ display:flex; gap:12px; flex-wrap:wrap; margin:6px 0 0; color:var(--dim); font-size:11px; }}
 .k {{ display:flex; align-items:center; gap:5px; }}
 .k i {{ width:10px; height:10px; border-radius:2px; display:inline-block; }}
 i.buy {{ background:var(--buy); }} i.sell {{ background:var(--sell); }}
 i.flat {{ background:var(--flat); }}
 .note {{ margin:6px 0 0; color:var(--dim); font-size:11px; line-height:1.4; max-width:380px; }}
 .banner {{ margin:6px 0 0; padding:6px 9px; max-width:380px; border-radius:6px; line-height:1.4;
            background:#fff4e5; border:1px solid #f0c987; color:#7a4b06; font-size:11px; }}
 @media (prefers-color-scheme: dark) {{ .banner {{ background:#3a2c12;
            border-color:#7a5a1e; color:#f0d9a8; }} }}
</style>
<div class="prof" id="prof" data-bucket="{profile.bucket_pts:g}">{"".join(rows)}</div>
<div id="hud">
<h1>Premarket Volume Profile — {SYMBOL}</h1>
<div class="sub">
  Anchored {anchor_ct:%A %b %-d, 08:30 CT} (prior RTH open) → {end_ct:%a %H:%M CT}<br>
  {bar_count:,} {"prints" if source == "ticks" else "bars"} ·
  {profile.total:,} contracts · {profile.bucket_pts:g}-pt buckets ·
  generated {generated_ct:%Y-%m-%d %H:%M CT}
</div>
{f'<div class="banner"><b>Incomplete window.</b> {CORPUS_BANNER}</div>'
 if source in ("ticks", "corpus") else ""}
<div class="stats">
  <div class="stat"><span>VAH</span><b>{va.vah:g}</b></div>
  <div class="stat"><span>POC</span><b>{va.poc:g}</b></div>
  <div class="stat"><span>VAL</span><b>{va.val:g}</b></div>
  <div class="stat"><span>VA width</span><b>{va.width:g}</b></div>
  <div class="stat"><span>Last</span><b>{last:g}</b></div>
  <div class="stat"><span>vs POC</span><b>{last - va.poc:+g}</b></div>
  {delta_stat}
</div>
<div class="legend">{legend}<span class="k">hover a row for exact volumes</span></div>
<p class="note">
  Price is <b>{html.escape(pos)}</b>. Value area holds {va.achieved:.0%} of volume
  ({va.volume:,} of {va.total:,} contracts). {SOURCES[source][1]}
</p>
</div>
<script>
// Inline, no external assets (desk pages render with no network).
(function () {{
  var prof = document.getElementById("prof"), hud = document.getElementById("hud");
  // Price labels: the HTML labels whole points; when rows are tighter than
  // the type (a full-height profile at ~2 px a row), keep only every 2, 5,
  // 10, 25 … points so labels never overprint. POC and Last always show.
  function thin() {{
    var rows = prof.querySelectorAll(".r"); if (!rows.length) return;
    var rowH = prof.clientHeight / rows.length, bucket = +prof.dataset.bucket || 0.25;
    var steps = [1, 2, 5, 10, 25, 50, 100], step = steps[steps.length - 1];
    for (var i = 0; i < steps.length; i++) {{ if (steps[i] / bucket * rowH >= 12) {{ step = steps[i]; break; }} }}
    rows.forEach(function (r) {{
      var px = r.querySelector(".px"); if (!px || !px.textContent) return;
      var p = parseFloat(px.textContent);
      px.classList.toggle("thin", Math.abs(p / step - Math.round(p / step)) > 1e-9);
    }});
  }}
  thin(); window.addEventListener("resize", thin);
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
    ap.add_argument("--source", choices=("ticks", "schwab", "corpus"), default="ticks",
                    help="ticks (default): real prints from the tick corpus, tick "
                         "resolution + buy/sell aggressor split, evening session "
                         "MISSING. schwab: continuous coverage, 5-min bars, no "
                         "aggressor. corpus: 5-min bars aggregated from ticks.")
    ap.add_argument("--bucket-ticks", type=int, default=1,
                    help="bucket width in ES ticks for the tick path "
                         "(1 = 0.25pt, native; default 1)")
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

    source, aggressor = args.source, False
    try:
        if source == "ticks":
            # Tally as the generator drains: the profile streams, so the print
            # count and the LAST PRINT (a real traded price, not a bucket floor)
            # have to be captured in passing rather than recomputed.
            tally = _Tally()
            profile = build_split_profile(tally(trades_from_corpus(start)),
                                          bucket_ticks=args.bucket_ticks)
            va = value_area(profile.as_volume_profile())
            last, end_ct, n = tally.last.price, tally.last.ts, tally.n
            aggressor = True
        else:
            bars = fetch_bars(start) if source == "schwab" else bars_from_corpus(start)
            profile = build_profile_from_bars(bars, symbol=SYMBOL)
            va = value_area(profile)
            last = float(bars[-1]["close"])
            end_ct, n = _ct(bars[-1]["datetime"]), len(bars)
    except Exception as e:  # noqa: BLE001 — last-good contract
        logger.error("source %r unusable, published page LEFT AS-IS: %s", source, e)
        return 2

    generated = datetime.now(tz=CENTRAL)
    publish(render_page(profile, va, last, n, end_ct, anchor_ct, generated,
                        source, aggressor), args.dry_run)

    extra = f"   delta {profile.delta:+,}" if aggressor else ""
    print(f"{SYMBOL} anchored VP [{source}] — {n:,} "
          f"{'prints' if source == 'ticks' else 'bars'}, "
          f"{profile.total:,} contracts, {profile.bucket_pts:g}pt buckets\n"
          f"  anchor {anchor_ct:%a %H:%M CT}  ->  {end_ct:%a %H:%M CT}\n"
          f"  VAH {va.vah:g}   POC {va.poc:g}   VAL {va.val:g}   "
          f"(VA {va.achieved:.0%}, width {va.width:g}){extra}\n"
          f"  last {last:g} ({last - va.poc:+g} vs POC)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
