#!/usr/bin/env bash
# st-3vu validation batch: estimate -> pull 13 labeled days -> run recognizer vs Mancini.
# One-shot experiment driver (Steve approved ~$7.80 batch 2026-07-06); the durable
# rerunnable scorer lands as scripts/score_recognizer.py per the bead's AC.
set -uo pipefail
cd /root/projects/Strader
PY=.venv/bin/python
DAYS="2025-07-22 2025-08-01 2025-08-27 2025-09-23 2025-09-25 2025-10-03 2025-10-06 2025-10-14 2025-10-29 2026-01-02 2026-02-13 2026-03-20 2026-04-23"

echo "== PHASE 1: estimates =="
TOTAL=0
for d in $DAYS; do
  EST=$($PY scripts/corpus_pull_databento_es.py --date "$d" --start-ct 08:30 --end-ct 15:00 --estimate-only 2>/dev/null | grep "estimated cost" | grep -oP '[0-9.]+')
  echo "  $d: \$${EST:-FAILED}"
  TOTAL=$(python3 -c "print(f'{$TOTAL + ${EST:-0}:.2f}')")
done
echo "  BATCH TOTAL: \$$TOTAL (approved ~\$7.80, guard \$12.00)"
python3 -c "import sys; sys.exit(0 if $TOTAL <= 12.0 else 1)" || { echo "ABORT: total exceeds guard"; exit 1; }

echo "== PHASE 2: pulls (coverage-aware) =="
for d in $DAYS; do
  F="data/corpus/$d/databento_glbx_es.jsonl"
  if [ -f "$F" ]; then
    # legacy late-day backfill files start at 18:00 UTC (13:00 CT); a full
    # RTH file contains 13:3x UTC (08:3x CT) morning events
    if grep -qm1 '"ts_event": "[0-9-]*T1[34]:' "$F"; then
      echo "  $d: full coverage present, skipping"
      continue
    fi
    echo "  $d: afternoon-only -> pulling MORNING 08:30-13:00..."
    $PY scripts/corpus_pull_databento_es.py --date "$d" --start-ct 08:30 --end-ct 13:00 2>&1 | grep -E "estimated|wrote|ERR" | sed 's/^/    /'
  else
    echo "  $d: absent -> pulling FULL 08:30-15:00..."
    $PY scripts/corpus_pull_databento_es.py --date "$d" --start-ct 08:30 --end-ct 15:00 2>&1 | grep -E "estimated|wrote|ERR" | sed 's/^/    /'
  fi
done

echo "== PHASE 3: recognizer vs Mancini =="
$PY - <<'PYEOF'
import json, sys
from datetime import date
sys.path.insert(0, ".")
from market.orderflow.replay import read_corpus_day
from market.orderflow.bars import build_bars
from market.orderflow.recognizer import Anchor, SetupRecognizer

labels = json.load(open("docs/measurement/mancini-setup-labels-2026-07-06.json"))
BATCH = ["2025-07-22","2025-08-01","2025-08-27","2025-09-23","2025-09-25","2025-10-03",
         "2025-10-06","2025-10-14","2025-10-29","2026-01-02","2026-02-13","2026-03-20","2026-04-23"]
by_day = {}
for e in labels:
    if e["session_date"] in BATCH and e["es_levels"] and e["setup"] in ("failed_breakdown","level_reclaim"):
        by_day.setdefault(e["session_date"], []).append(e)

results = []
for day_s in BATCH:
    evs = by_day.get(day_s, [])
    if not evs:
        continue
    try:
        trades = read_corpus_day(date.fromisoformat(day_s))
    except FileNotFoundError:
        results.append({"day": day_s, "error": "no tick data"}); print(f"{day_s}: NO TICK DATA"); continue
    bars = list(build_bars(trades, n=2000, include_partial=True))
    anchors, seen = [], set()
    for e in evs:
        for lv in e["es_levels"]:
            if 5000 < lv < 9000 and lv not in seen:
                seen.add(lv)
                anchors.append(Anchor(float(lv), "support", "mancini", mancini=True))
    recs = SetupRecognizer(anchors).run(bars)
    confirmed = [{"t": r.timestamp.strftime("%H:%M CT"), "setup": r.setup, "anchor": r.anchor_price,
                  "beats": list(r.beats)} for r in recs if r.state == "confirmed"]
    results.append({"day": day_s,
                    "labels": [(e["setup"], e["explicitness"], e.get("time_et"), e["es_levels"]) for e in evs],
                    "n_bars": len(bars), "anchors": sorted(seen),
                    "confirmed": confirmed,
                    "invalidated": sum(1 for r in recs if r.state == "invalidated"),
                    "forming": sum(1 for r in recs if r.state == "forming")})
    print(f"{day_s}: {len(bars)} bars | anchors {sorted(seen)}")
    print(f"   Mancini said: {[(e['setup'], e.get('time_et')) for e in evs]}")
    print(f"   machine confirmed: {confirmed if confirmed else 'NONE'}")
    print(f"   invalidated: {results[-1]['invalidated']}")
json.dump(results, open("data/mancini-labels/validation-run-1.json", "w"), indent=1)
print("\nsaved -> data/mancini-labels/validation-run-1.json")
PYEOF
echo "== BATCH COMPLETE =="
