#!/usr/bin/env python3
"""Session review — Mancini commentary coupled to the orderflow framework. [st-6b0]

Pick a trading day; get one page holding:
  - the FORECAST letter (last Mancini letter published before that session's
    open — "how well did he anticipate it?")
  - the RETRO letter (first letter published after that session's close — his
    recap; absent gracefully when he skipped, e.g. holidays)
  - data coverage for the day's ES ticks, with an explicit notice + backfill
    quote when only the legacy 13:00-15:00 window exists (NO auto-backfill —
    historical pulls are metered and per-day approved by Steve)
  - a link to the day's footprint drill, generated alongside, with candidate
    ES levels harvested from the forecast letter offered as "M:" chips
    (regex-harvested NUMBERS, clearly labeled — not parsed levels; level
    parsing stays prompt-driven per project memory).

Letters live in Azure blob (account stradermailh27ssjitr7spy, container
mancini, names yyyy-MM-dd-HHmmss.txt UTC). Downloads are cached under
data/mancini-letters/ (gitignored) so repeat reviews never re-hit Azure.
Auth: az CLI storage-key lookup, same pattern as
COO/infra/azure/email-ingress/scripts/read-latest.sh.

Usage:
    .venv/bin/python scripts/session_review.py --date 2026-07-02
    .venv/bin/python scripts/session_review.py --date 2026-07-02 --no-open
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import logging
import re
import subprocess
import sys
from collections import Counter
from datetime import date as _date, datetime, time as _time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from runbook.mancini.clean import clean_newsletter as clean_letter          # noqa: E402
from market.orderflow.replay import read_corpus_day, es_day_path  # noqa: E402
import orderflow_drill                                            # noqa: E402

logger = logging.getLogger("session_review")

CENTRAL = ZoneInfo("America/Chicago")
ACCOUNT = "stradermailh27ssjitr7spy"
CONTAINER = "mancini"
CACHE = REPO_ROOT / "data" / "mancini-letters"
MORNING_BACKFILL_COST = 0.51  # $ estimate for 08:30-13:00 trades (st-f05 probe 2026-07-04)


# ── blob layer ──────────────────────────────────────────────────────────────
def _az(*args: str) -> str:
    proc = subprocess.run(["az", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"az {' '.join(args[:3])}… failed: {proc.stderr.strip()[:300]}")
    return proc.stdout.replace("\r", "")


def _account_key() -> str:
    return _az("storage", "account", "keys", "list", "--account-name", ACCOUNT,
               "--query", "[0].value", "-o", "tsv", "--only-show-errors").strip()


def list_letter_blobs(key: str) -> list[str]:
    out = _az("storage", "blob", "list", "--account-name", ACCOUNT,
              "--account-key", key, "--container-name", CONTAINER,
              "--query", "[].name", "-o", "tsv")
    return sorted(n for n in out.split() if n.endswith(".txt"))


def blob_utc(name: str) -> datetime:
    return datetime.strptime(name[:-4], "%Y-%m-%d-%H%M%S").replace(tzinfo=timezone.utc)


def fetch_letter(name: str, key: str | None) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists():
        if key is None:
            raise RuntimeError("letter not cached and no Azure key available")
        _az("storage", "blob", "download", "--account-name", ACCOUNT,
            "--account-key", key, "--container-name", CONTAINER,
            "--name", name, "--file", str(path), "--no-progress", "-o", "none")
        logger.info("downloaded %s (%.0f KB)", name, path.stat().st_size / 1024)
    return clean_letter(path.read_text(encoding="utf-8", errors="replace"))


def resolve_letters(day: _date, names: list[str]) -> tuple[str | None, str | None]:
    """(forecast, retro) blob names for a session date. Forecast = last letter
    published before the 08:30 CT open. Retro = first letter published after
    13:30 CT on the session day: Mancini writes the recap into the close
    (observed ~14:30 CT publishes), so a 15:00 boundary would miss the same-day
    letter; when he skips (holiday/weekend), the next letter still recaps the
    session days later."""
    open_utc = datetime.combine(day, _time(8, 30), tzinfo=CENTRAL).astimezone(timezone.utc)
    close_utc = datetime.combine(day, _time(13, 30), tzinfo=CENTRAL).astimezone(timezone.utc)
    forecast = None
    retro = None
    for n in names:
        ts = blob_utc(n)
        if ts < open_utc:
            forecast = n
        elif ts > close_utc and retro is None:
            retro = n
    return forecast, retro


# ── level harvesting (numbers, not parsed levels) ──────────────────────────
def harvest_candidates(text: str, lo: float, hi: float, top: int = 10) -> list[float]:
    """Frequency-ranked ES-priced numbers mentioned in the letter, bounded to
    the neighborhood of the session's actual range. Deterministic order:
    count desc, then first mention."""
    first_pos: dict[float, int] = {}
    counts: Counter[float] = Counter()
    for m in re.finditer(r"\b(\d{4}(?:\.(?:25|5|50|75))?)\b", text):
        v = float(m.group(1))
        if lo <= v <= hi:
            counts[v] += 1
            first_pos.setdefault(v, m.start())
    ranked = sorted(counts, key=lambda v: (-counts[v], first_pos[v]))
    return ranked[:top]


# ── review page ─────────────────────────────────────────────────────────────
STYLE = """
body { margin:0; background:var(--page); color:var(--ink);
  font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif; }
:root { --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#898781; --ring:rgba(11,11,11,.10); --warn-bg:#fdf3e2; --warn-ink:#7a5200;
  --accent:#2a78d6; }
@media (prefers-color-scheme: dark) { :root { --page:#0d0d0d; --surface:#1a1a19;
  --ink:#fff; --ink2:#c3c2b7; --ring:rgba(255,255,255,.10);
  --warn-bg:#3a2f14; --warn-ink:#fab219; --accent:#3987e5; } }
main { max-width: 980px; margin: 0 auto; padding: 24px 20px 60px; }
h1 { font-size: 20px; } h1 small { color:var(--ink2); font-weight:400; }
.banner { background:var(--warn-bg); color:var(--warn-ink); border-radius:8px;
  padding:10px 14px; margin:10px 0; font-size:14px; }
.card { background:var(--surface); border:1px solid var(--ring); border-radius:10px;
  padding:4px 18px 14px; margin:14px 0; }
details > summary { cursor:pointer; font-weight:600; padding:10px 0; }
pre.letter { white-space:pre-wrap; font:14px/1.65 system-ui,sans-serif;
  color:var(--ink); max-height:520px; overflow:auto; }
.meta { color:var(--ink2); font-size:13px; }
a.drill { display:inline-block; background:var(--accent); color:#fff; border-radius:8px;
  padding:10px 18px; text-decoration:none; font-weight:600; margin:6px 0; }
.chips span { display:inline-block; border:1px solid var(--ring); border-radius:6px;
  padding:2px 8px; margin:2px; font-size:13px; font-variant-numeric:tabular-nums; }
"""


def build_page(day: _date, sections: dict) -> str:
    esc = html_mod.escape
    f, r = sections["forecast"], sections["retro"]
    parts = [f"<style>{STYLE}</style><main>"]
    parts.append(f"<h1>Session review — {day.isoformat()} <small>ES · Mancini × orderflow</small></h1>")
    for b in sections["banners"]:
        parts.append(f'<div class="banner">{esc(b)}</div>')
    parts.append('<div class="card"><h3>Drill</h3>')
    if sections["drill_file"]:
        parts.append(f'<a class="drill" href="{sections["drill_file"]}">Open the footprint drill for {day.isoformat()}</a>')
        parts.append(f'<p class="meta">{sections["coverage"]}</p>')
        if sections["candidates"]:
            chips = " ".join(f"<span>{v:.2f}</span>" for v in sections["candidates"])
            parts.append(f'<p class="meta">Candidate levels harvested from the forecast letter '
                         f'(frequency-ranked <b>numbers</b>, not parsed levels — verify against the text): '
                         f'</p><p class="chips">{chips}</p>'
                         f'<p class="meta">The same candidates appear as “M:” chips inside the drill.</p>')
    else:
        parts.append(f'<p class="meta">{sections["coverage"]}</p>')
    parts.append("</div>")
    for title, blob, text in (("Forecast letter (published before the open)", *f),
                              ("Retro letter (first letter after the close)", *r)):
        parts.append('<div class="card"><details open><summary>' + esc(title) + "</summary>")
        if text:
            when = blob_utc(blob).astimezone(CENTRAL).strftime("%Y-%m-%d %H:%M CT")
            parts.append(f'<p class="meta">blob {esc(blob)} · published {when}</p>')
            parts.append(f'<pre class="letter">{esc(text)}</pre>')
        else:
            parts.append('<p class="meta">No letter found for this slot (Mancini skips holidays/weekends; '
                         "the next published letter had not arrived when this page was generated).</p>")
        parts.append("</details></div>")
    parts.append("</main>")
    return "<!DOCTYPE html><html><head><meta charset='utf-8'>" \
           f"<title>Session review {day.isoformat()}</title></head><body>" + "".join(parts) + "</body></html>"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mancini x orderflow session review [st-6b0]")
    ap.add_argument("--date", required=True, help="Session day YYYY-MM-DD")
    ap.add_argument("--bar-n", type=int, default=None, help="Override contracts/bar for the drill")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    day = _date.fromisoformat(args.date)
    banners: list[str] = []

    # letters (cache-first; Azure only when needed)
    key = None
    try:
        key = _account_key()
        names = list_letter_blobs(key)
    except RuntimeError as e:
        logger.warning("Azure unavailable (%s); using local cache only", e)
        names = sorted(p.name for p in CACHE.glob("*.txt"))
        banners.append("Azure unreachable — letters resolved from local cache only; a newer letter may exist.")
    fc_name, rt_name = resolve_letters(day, names)
    fc_text = fetch_letter(fc_name, key) if fc_name else None
    rt_text = fetch_letter(rt_name, key) if rt_name else None
    if not fc_name:
        banners.append("No forecast letter exists before this session's open.")
    if not rt_name:
        banners.append("No retro letter published after this session yet (holiday/weekend skip or too recent).")

    # corpus coverage + drill
    drill_file = None
    candidates: list[float] = []
    coverage = ""
    try:
        trades = read_corpus_day(day)
        t0, t1 = trades[0].ts, trades[-1].ts
        full = t0.time() <= _time(8, 35) and t1.time() >= _time(14, 55)
        coverage = (f"Tick coverage {t0.strftime('%H:%M')}–{t1.strftime('%H:%M')} CT · "
                    f"{sum(t.size for t in trades):,} contracts")
        if not full:
            banners.append(f"Partial tick coverage ({t0.strftime('%H:%M')}–{t1.strftime('%H:%M')} CT — the legacy "
                           f"butterfly window). Morning backfill for this day ≈ ${MORNING_BACKFILL_COST:.2f}; "
                           "ask COO to run it if this session deserves the full picture.")
        lo, hi = min(t.price for t in trades) - 30, max(t.price for t in trades) + 30
        if fc_text:
            candidates = harvest_candidates(fc_text, lo, hi)
        bar_n = args.bar_n or orderflow_drill.VOLUME_BAR_N
        payload = orderflow_drill.bars_payload(day, bar_n)
        payload["mancini_candidates"] = candidates
        drill_file = f"desk-orderflow-drill-{day.isoformat()}.html"
        orderflow_drill.render(payload, Path("/tmp") / drill_file)
    except FileNotFoundError:
        coverage = "No ES tick data in the corpus for this day — no drill generated."
        banners.append(coverage + " Historical pulls are metered; ask COO to fetch this day if needed.")

    out = Path(f"/tmp/desk-session-review-{day.isoformat()}.html")
    out.write_text(build_page(day, {
        "banners": banners, "coverage": coverage, "drill_file": drill_file,
        "candidates": candidates,
        "forecast": (fc_name, fc_text), "retro": (rt_name, rt_text),
    }), encoding="utf-8")
    logger.info("wrote %s", out)
    if not args.no_open:
        orderflow_drill.open_in_browser(out)
    print(f"review ready: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
