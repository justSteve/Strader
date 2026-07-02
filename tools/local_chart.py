#!/usr/bin/env python3
"""Local self-contained HTML chart from ES.c.0 corpus data.

Renders a TradingView-style candlestick chart for a given date + CT window
using the lightweight-charts JS library (CDN-loaded, no Python install). The
output is a single HTML file that opens directly in a browser — file:// URL,
no server required.

Designed for chart-eyeball validation (e.g. V-day detector) and ad-hoc
historical review of our own DataBento ES corpus.

Usage as a library:
    from tools.local_chart import render_chart, render_v_day_chart
    path = render_chart(date="2025-09-17", start_ct="13:00", end_ct="15:00",
                        interval_min=5,
                        markers=[{"time_ct": "13:54", "label": "trough",
                                  "price": 6554.0, "side": "below"}],
                        price_lines=[{"price": 6607.61, "title": "VWAP_p"}],
                        title="2025-09-17 — V-DOWN candidate")

Usage as a CLI:
    .venv/bin/python tools/local_chart.py --date 2025-09-17
    .venv/bin/python tools/local_chart.py --from-v-days 2025-09-17
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date, datetime, time as _time
from pathlib import Path
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT = REPO_ROOT / "data" / "corpus"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "measurement" / "charts"
LWC_VERSION = "4.1.3"  # pinned — v5 changed API


def _ct_time(s: str) -> _time:
    h, m = (int(x) for x in s.split(":"))
    return _time(h, m)


def _load_ticks(date_str: str) -> list[tuple[datetime, float]]:
    path = CORPUS_ROOT / date_str / "databento_glbx_es.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"No ES corpus file for {date_str}: {path}")
    ticks: list[tuple[datetime, float]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                ts_event = rec["provenance"]["ts_event"]
                price = rec["data"]["price"]
                if price is None:
                    continue
                ts_utc = datetime.fromisoformat(ts_event)
                ts_ct = ts_utc.astimezone(CENTRAL)
                ticks.append((ts_ct, float(price)))
            except (KeyError, ValueError, TypeError):
                continue
    return ticks


def _aggregate_ohlc(ticks: list[tuple[datetime, float]], interval_min: int,
                    start_ct: _time, end_ct: _time) -> list[dict]:
    """Bucket ticks into interval_min OHLC bars; returns list ordered by time."""
    bars: dict[int, dict] = {}
    for ts, price in ticks:
        tod = ts.time()
        if not (start_ct <= tod < end_ct):
            continue
        # Anchor each bar at its start-of-interval (in CT)
        minutes = ts.hour * 60 + ts.minute
        bucket_minute = (minutes // interval_min) * interval_min
        bucket_ts = ts.replace(
            hour=bucket_minute // 60, minute=bucket_minute % 60,
            second=0, microsecond=0,
        )
        key = int(bucket_ts.timestamp())
        b = bars.get(key)
        if b is None:
            bars[key] = {"time": key, "open": price, "high": price,
                         "low": price, "close": price}
        else:
            b["high"] = max(b["high"], price)
            b["low"] = min(b["low"], price)
            b["close"] = price
    return [bars[k] for k in sorted(bars)]


def _marker_for(date_str: str, time_ct: str, price: float, label: str,
                side: str = "below") -> dict:
    """Build a lightweight-charts marker entry. Accepts HH:MM or HH:MM:SS."""
    d = _date.fromisoformat(date_str)
    parts = [int(x) for x in time_ct.split(":")]
    if len(parts) == 2:
        h, m, s = parts[0], parts[1], 0
    elif len(parts) == 3:
        h, m, s = parts[0], parts[1], parts[2]
    else:
        raise ValueError(f"bad time_ct: {time_ct!r}")
    ts = datetime.combine(d, _time(h, m, s), tzinfo=CENTRAL)
    is_down = side == "below"
    return {
        "time": int(ts.timestamp()),
        "position": "belowBar" if is_down else "aboveBar",
        "color": "#ef5350" if is_down else "#26a69a",
        "shape": "arrowUp" if is_down else "arrowDown",
        "text": f"{label} {price:.2f}",
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <script src="https://unpkg.com/lightweight-charts@{lwc_version}/dist/lightweight-charts.standalone.production.js"></script>
  <style>
    html, body {{ margin: 0; padding: 0; height: 100%; background: #0e1217; color: #d0d0d0;
                  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    #header {{ padding: 10px 20px 8px; border-bottom: 1px solid #1f2530; }}
    h1 {{ margin: 0; font-size: 15px; font-weight: 500; color: #e8e8e8; }}
    #metrics {{ margin-top: 6px; font-size: 12px; color: #8a93a0; }}
    #metrics span {{ margin-right: 16px; }}
    #metrics b {{ color: #c8d2dc; font-weight: 500; }}
    #chart {{ width: 100%; height: calc(100vh - 64px); }}
  </style>
</head>
<body>
  <div id="header">
    <h1>{title}</h1>
    <div id="metrics">{metrics_html}</div>
  </div>
  <div id="chart"></div>
  <script>
    const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
      layout: {{ background: {{ type: 'solid', color: '#0e1217' }}, textColor: '#d0d0d0' }},
      grid: {{ vertLines: {{ color: '#1a1f28' }}, horzLines: {{ color: '#1a1f28' }} }},
      timeScale: {{ timeVisible: true, secondsVisible: false,
                    borderColor: '#2a3140', timezone: 'America/Chicago' }},
      rightPriceScale: {{ borderColor: '#2a3140' }},
      crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
    }});
    const series = chart.addCandlestickSeries({{
      upColor: '#26a69a', downColor: '#ef5350',
      borderUpColor: '#26a69a', borderDownColor: '#ef5350',
      wickUpColor: '#26a69a', wickDownColor: '#ef5350',
    }});
    series.setData({bars_json});
    const markers = {markers_json};
    if (markers.length) series.setMarkers(markers);
    {price_lines_js}
    chart.timeScale().fitContent();
  </script>
</body>
</html>
"""


def _price_lines_js(price_lines: list[dict]) -> str:
    chunks = []
    for pl in price_lines:
        title = pl.get("title", "")
        color = pl.get("color", "#8a93a0")
        price = pl["price"]
        chunks.append(
            f"series.createPriceLine({{ price: {price}, color: '{color}', "
            f"lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, "
            f"axisLabelVisible: true, title: {json.dumps(title)} }});"
        )
    return "\n    ".join(chunks)


def render_chart(date: str, start_ct: str = "13:00", end_ct: str = "15:00",
                 interval_min: int = 5, markers: list[dict] | None = None,
                 price_lines: list[dict] | None = None,
                 title: str | None = None, metrics: dict | None = None,
                 out_dir: Path | None = None) -> Path:
    """Render a single-day chart HTML file. Returns the output path."""
    start_t = _ct_time(start_ct)
    end_t = _ct_time(end_ct)
    ticks = _load_ticks(date)
    bars = _aggregate_ohlc(ticks, interval_min, start_t, end_t)
    if not bars:
        raise ValueError(f"No bars produced for {date} in [{start_ct}, {end_ct}) CT")

    marker_objs = []
    for m in markers or []:
        marker_objs.append(_marker_for(
            date_str=date, time_ct=m["time_ct"], price=m["price"],
            label=m["label"], side=m.get("side", "below"),
        ))

    out_dir = out_dir or DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{date}_{start_ct.replace(':','')}-{end_ct.replace(':','')}.html"
    out_path = out_dir / fname

    title = title or f"{date} · ES {interval_min}m · {start_ct}–{end_ct} CT"
    metrics_html = ""
    if metrics:
        parts = [f"<span><b>{k}:</b> {v}</span>" for k, v in metrics.items()]
        metrics_html = "".join(parts)

    html = HTML_TEMPLATE.format(
        title=title,
        lwc_version=LWC_VERSION,
        bars_json=json.dumps(bars),
        markers_json=json.dumps(marker_objs),
        price_lines_js=_price_lines_js(price_lines or []),
        metrics_html=metrics_html,
    )
    out_path.write_text(html)
    return out_path


def render_v_day_chart(v_row: dict, out_dir: Path | None = None,
                       interval_min: int = 1) -> Path:
    """Render a chart pre-annotated with v_days.jsonl row diagnostics."""
    date = v_row["date"]
    label = v_row.get("label", "unlabeled")
    vwap_p = v_row.get("vwap_p")
    trough_p = v_row.get("trough_p")
    trough_t = v_row.get("trough_t")
    peak_p = v_row.get("peak_p")
    peak_t = v_row.get("peak_t")
    latr_20 = v_row.get("latr_20")

    markers = []
    if trough_p is not None and trough_t:
        # trough_t is ISO; extract HH:MM:SS in local CT
        t_hms = trough_t.split("T")[1].split("-")[0].split("+")[0][:8]
        markers.append({"time_ct": t_hms, "price": trough_p,
                        "label": "trough", "side": "below"})
    if peak_p is not None and peak_t:
        t_hms = peak_t.split("T")[1].split("-")[0].split("+")[0][:8]
        markers.append({"time_ct": t_hms, "price": peak_p,
                        "label": "peak", "side": "above"})

    price_lines = []
    if vwap_p is not None:
        price_lines.append({"price": round(vwap_p, 2), "title": "VWAP_p", "color": "#a8b3c0"})

    metrics = {"label": label.upper()}
    if vwap_p is not None: metrics["VWAP_p"] = f"{vwap_p:.2f}"
    if latr_20 is not None: metrics["LATR_20"] = f"{latr_20:.2f}"
    for arm in ("v_down", "v_up"):
        if arm in v_row:
            a = v_row[arm]
            metrics[f"{arm}.depth"] = f"{a['depth']:.2f}"
            metrics[f"{arm}.reco"] = f"{a['recovery']:.2f}"
            metrics[f"{arm}.land"] = f"{a['landing']:.2f}"

    title = f"{date} · {label.upper()} · ES {interval_min}m · 13:00–15:00 CT"
    return render_chart(
        date=date, start_ct="13:00", end_ct="15:00", interval_min=interval_min,
        markers=markers, price_lines=price_lines, title=title, metrics=metrics,
        out_dir=out_dir,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Render local ES chart HTML")
    parser.add_argument("--date", help="YYYY-MM-DD")
    parser.add_argument("--start-ct", default="13:00")
    parser.add_argument("--end-ct", default="15:00")
    parser.add_argument("--interval", type=int, default=5,
                        help="Bar interval in minutes (default 5)")
    parser.add_argument("--from-v-days", metavar="DATE",
                        help="Render with detector annotations from data/measurement/v_days.jsonl")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else None

    if args.from_v_days:
        v_path = REPO_ROOT / "data" / "measurement" / "v_days.jsonl"
        rows = [json.loads(l) for l in v_path.open()]
        match = next((r for r in rows if r["date"] == args.from_v_days), None)
        if match is None:
            print(f"ERR: no v_days.jsonl row for {args.from_v_days}", file=sys.stderr)
            return 1
        path = render_v_day_chart(match, out_dir=out_dir)
    elif args.date:
        path = render_chart(date=args.date, start_ct=args.start_ct,
                            end_ct=args.end_ct, interval_min=args.interval,
                            out_dir=out_dir)
    else:
        parser.error("must provide either --date or --from-v-days")
        return 2

    print(f"wrote {path}")
    print(f"file://{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
