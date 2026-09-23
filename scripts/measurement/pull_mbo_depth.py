#!/usr/bin/env python3
"""Historical ES MBO pull for the depth comparison [co-4owbx].

Bought 2026-09-23 on Steve's word ("go ahead with historical depth first"):
52 recorded sessions 07-02..09-22, $33.32 by metadata.get_cost, 61 files,
11 GB zstd DBN in /var/moo/depth/mbo/ (kept out of the repo and the corpus;
absorption_depth_survey.py reads it there). Days inside Databento's trailing
month price at $0 on the Standard plan.

One file per session: GLBX.MDP3 MBO, 00:00 UTC (the synthetic book snapshot)
to 20:05 UTC (past the 15:00 CT close). ES.c.0 except the September roll week,
where the calendar symbol stayed on ESU6 while volume moved to ESZ6: those
days pull both raw contracts. Skips files already present; logs cost per day.

Usage (the day list is a JSONL of {"day": "YYYY-MM-DD"} rows):
    .venv/bin/python scripts/measurement/pull_mbo_depth.py days.jsonl
Check the cost first: metadata.get_cost per day, as this script logs.
"""
import sys, json, time
from datetime import date, datetime, time as T
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, "/root/projects/Strader")
from strader.settings import load_databento
load_databento()
import databento as db

UTC = ZoneInfo("UTC")
OUT = Path("/var/moo/depth/mbo")
ROLL = {"2026-09-08","2026-09-09","2026-09-10","2026-09-11","2026-09-14","2026-09-15","2026-09-16","2026-09-17","2026-09-18"}
c = db.Historical()
days = [json.loads(l)["day"] for l in open(sys.argv[1])]
total = 0.0
for d in days:
    dd = date.fromisoformat(d)
    s, e = datetime.combine(dd, T(0, 0), UTC), datetime.combine(dd, T(20, 5), UTC)
    jobs = [("ESU6", "raw_symbol"), ("ESZ6", "raw_symbol")] if d in ROLL else [("ES.c.0", "continuous")]
    for sym, st in jobs:
        f = OUT / f"{d}_{sym}.mbo.dbn.zst"
        if f.exists() and f.stat().st_size > 0:
            print(d, sym, "exists", flush=True); continue
        kw = dict(dataset="GLBX.MDP3", symbols=[sym], stype_in=st, schema="mbo", start=s, end=e)
        cost = c.metadata.get_cost(**kw)
        t0 = time.time()
        for attempt in range(3):
            try:
                tmp = f.with_suffix(".part")
                c.timeseries.get_range(**kw, path=tmp)
                tmp.rename(f); break
            except Exception as ex:
                print(d, sym, "attempt", attempt, "failed:", ex, flush=True); time.sleep(10)
        else:
            print(d, sym, "GAVE UP", flush=True); continue
        total += cost
        print(d, sym, f"${cost:.2f}", f"{f.stat().st_size/1e6:.0f} MB on disk", f"{time.time()-t0:.0f}s", f"running ${total:.2f}", flush=True)
print("DONE running cost", round(total, 2), flush=True)
