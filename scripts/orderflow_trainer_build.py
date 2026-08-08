#!/usr/bin/env python3
"""Two-signal training viewer builder. [st-34q6]

Paints our own chart from the archive: per-day spot path (10s), 0DTE
wall step-lines, and every round-3 p95x6 two-signal event as a marker —
the eye-training surface Steve asked for, and the first brush-stroke of
the merged GB+footprint UI. Rebuild any time with:

    .venv/bin/python3 scripts/orderflow_trainer_build.py

Writes /var/moo/desk/desk-two-signal-trainer.html (self-contained).
Event source: data/derived/acuity-sweep/edge-tests-r3-raw.json (frozen
round-3 definitions; regenerate that first if the archive has grown).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = Path("/var/moo/desk/desk-two-signal-trainer.html")
_spec = importlib.util.spec_from_file_location(
    "sweep", REPO / "scripts" / "orderflow_hist_sweep.py")
sw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sw)

raw = json.loads((REPO / "data/derived/acuity-sweep/edge-tests-r3-raw.json")
                 .read_text())
events_by_day: dict[str, list] = {}
for r in raw["defs"]["p95x6"]:
    events_by_day.setdefault(r["day"], []).append(r)

days_out = {}
for day in sw.hist_days():
    pulls = sw.load_day(day)
    if len(pulls) < 1000:
        continue
    t0 = pulls[0]["epoch"]
    spot, walls, last_w = [], [], None
    for i, p in enumerate(pulls):
        off = p["epoch"] - t0
        if i % 10 == 0:
            spot.append([off, round(p["spot"], 2)])
        if i % 60 == 0 or (p["m_call"], p["m_put"]) != last_w:
            walls.append([off, p["m_call"], p["m_put"]])
            last_w = (p["m_call"], p["m_put"])
    evs = []
    # r3 rows carry no timestamp; recover epochs by re-running the same
    # pairing (cheap) — instead we match on the stored fields via a
    # rebuilt event list from the shared collector.
    days_out[day] = {"t0": t0, "spot": spot, "walls": walls, "events": evs}

# Re-derive event epochs with the identical round-3 collector so the
# markers are exactly the studied events (raw rows lack timestamps).
_spec3 = importlib.util.spec_from_file_location(
    "r3", REPO / "scripts" / "orderflow_edge_tests_r3.py")
r3 = importlib.util.module_from_spec(_spec3)
_spec3.loader.exec_module(r3)


def rederive_with_epochs():
    days_data = {}
    for day in days_out:
        days_data[day] = sw.load_day(day)
    r2 = r3.r2
    for day, pulls in days_data.items():
        spots = [(p["epoch"], p["spot"]) for p in pulls]
        end_epoch = pulls[-1]["epoch"] - r2.CLOSE_CUTOFF
        cvr = [p["cvr_of"] for p in pulls]
        gex = [p["gex_of"] for p in pulls]
        p95c = r2.rolling_bar(cvr)
        p95g = r2.rolling_bar(gex)
        epochs = [p["epoch"] for p in pulls]
        brakes, gexsp = [], []
        for i, p in enumerate(pulls):
            if p["epoch"] > end_epoch:
                break
            bc = 6.0 * p95c[i] if p95c[i] else None
            bg = 6.0 * p95g[i] if p95g[i] else None
            if bc and cvr[i] > bc:
                brakes.append(i)
            if bg and abs(gex[i]) > bg:
                gexsp.append(i)
        gset = {epochs[i]: gex[i] for i in gexsp}
        last_pair = -10**9
        for bi in brakes:
            t_b = epochs[bi]
            near = [(abs(t_b - tg), tg, gv) for tg, gv in gset.items()
                    if abs(t_b - tg) <= r2.PAIR_WINDOW_S]
            if not near:
                continue
            _, tg, gv = min(near)
            tt = max(t_b, tg)
            if tt - last_pair < r2.PAIR_COOLDOWN_S:
                continue
            last_pair = tt
            pi = next(j for j, e in enumerate(epochs) if e >= tt)
            p0 = pulls[pi]
            s0 = p0["spot"]
            trend = s0 - next(
                (s for t, s in reversed(spots)
                 if t <= tt - r2.TREND_LOOKBACK_S), s0)
            wall_d = min(abs(s0 - p0["m_call"]), abs(s0 - p0["m_put"]))
            f = r2.fwd_delta(spots, tt, s0, 30)
            al30 = (round(-f, 2) if trend > 0 else round(f, 2)) \
                if f is not None else None
            days_out[day]["events"].append({
                "off": tt - days_out[day]["t0"], "spot": round(s0, 2),
                "side": "call" if gv > 0 else "put",
                "trend": round(trend, 2), "wall_d": round(wall_d, 2),
                "al30": al30})


rederive_with_epochs()
n_events = sum(len(d["events"]) for d in days_out.values())
expect = len(raw["defs"]["p95x6"])
if n_events != expect:
    print(f"ERROR: rederived {n_events} events, raw has {expect} — "
          "definitions drifted; refusing to build a mismatched trainer")
    sys.exit(1)

built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
payload = json.dumps(days_out, separators=(",", ":"))

html = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Two-Signal Trainer</title>
<style>
:root { --surface-1:#fcfcfb; --page:#f9f9f7; --ink:#0b0b0b; --ink-2:#52514e;
  --muted:#898781; --grid:#e1e0d9; --axis:#c3c2b7;
  --call:#0ca30c; --put:#d03b3b; --spot:#0b0b0b; --shade:rgba(137,135,129,.14); }
@media (prefers-color-scheme: dark) { :root {
  --surface-1:#1a1a19; --page:#0d0d0d; --ink:#fff; --ink-2:#c3c2b7;
  --grid:#2c2c2a; --axis:#383835; --call:#35c435; --put:#e66767;
  --spot:#ffffff; --shade:rgba(137,135,129,.18); }}
*{box-sizing:border-box} body{margin:0;background:var(--page);color:var(--ink);
 font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
header{padding:10px 16px 4px;display:flex;flex-wrap:wrap;gap:8px 18px;align-items:baseline}
h1{font-size:16px;margin:0} .meta{color:var(--ink-2);font-size:12px}
.controls{display:flex;gap:8px;align-items:center;padding:4px 16px 8px;flex-wrap:wrap}
select,button{font:inherit;color:var(--ink);background:var(--surface-1);
 border:1px solid var(--axis);border-radius:6px;padding:4px 10px;cursor:pointer}
.legend{font-size:12px;color:var(--ink-2);display:flex;gap:14px;flex-wrap:wrap}
.chip{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:middle}
#wrap{position:relative;margin:0 8px}
canvas{width:100%;height:520px;display:block}
#tip{position:absolute;display:none;background:var(--surface-1);border:1px solid var(--axis);
 border-radius:6px;padding:6px 9px;font-size:12px;pointer-events:none;max-width:260px;z-index:2}
footer{padding:8px 16px;color:var(--muted);font-size:11px}
</style></head><body>
<header><h1>Two-Signal Trainer</h1>
<span class="meta">strong-print (p95&times;6) two-signals on our own rendering &middot; frozen round-3 definitions [st-34q6] &middot; built __BUILT__</span></header>
<div class="controls">
 <button id="prev">&larr;</button><select id="day"></select><button id="next">&rarr;</button>
 <span class="legend">
  <span><span class="chip" style="background:var(--call)"></span>call-side event</span>
  <span><span class="chip" style="background:var(--put)"></span>put-side event</span>
  <span>ring = within 5 pts of a wall</span>
  <span style="border-bottom:2px dashed var(--call)">call wall</span>
  <span style="border-bottom:2px dashed var(--put)">put wall</span>
  <span>shaded = close-censored (last 30 min)</span></span>
</div>
<div id="wrap"><canvas id="cv"></canvas><div id="tip"></div></div>
<footer>Times are Chicago (UTC-5). Hover markers for details; aligned +30m = reversal-aligned forward move, &ldquo;censored&rdquo; = event too close to the bell to score. Rebuild: scripts/orderflow_trainer_build.py</footer>
<script>
const DATA=__DATA__;
const days=Object.keys(DATA).sort();
const sel=document.getElementById('day');
days.forEach(d=>{const o=document.createElement('option');o.value=d;
 o.textContent=d+' ('+DATA[d].events.length+' ev)';sel.appendChild(o)});
sel.value=days[days.length-1];
const cv=document.getElementById('cv'),tip=document.getElementById('tip');
let hits=[];
function ct(off,t0){const d=new Date((t0+off)*1000);
 return d.toLocaleTimeString('en-US',{timeZone:'America/Chicago',hour:'numeric',minute:'2-digit'});}
function draw(){
 const day=sel.value,D=DATA[day];
 const dpr=window.devicePixelRatio||1,W=cv.clientWidth,H=520;
 cv.width=W*dpr;cv.height=H*dpr;
 const g=cv.getContext('2d');g.scale(dpr,dpr);
 const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
 g.clearRect(0,0,W,H);
 const padL=8,padR=56,padT=10,padB=26;
 const xs=D.spot.map(p=>p[0]),ys=D.spot.map(p=>p[1]);
 const wallVals=D.walls.flatMap(w=>[w[1],w[2]]).filter(v=>v!=null);
 const yAll=ys.concat(wallVals.filter(v=>v>Math.min(...ys)-40&&v<Math.max(...ys)+40));
 const x0=0,x1=Math.max(...xs),ymin=Math.min(...yAll)-2,ymax=Math.max(...yAll)+2;
 const X=t=>padL+(t-x0)/(x1-x0)*(W-padL-padR);
 const Y=v=>padT+(ymax-v)/(ymax-ymin)*(H-padT-padB);
 // close-censored shade
 g.fillStyle=css('--shade');g.fillRect(X(x1-1800),padT,X(x1)-X(x1-1800),H-padT-padB);
 // grid + y labels
 g.strokeStyle=css('--grid');g.fillStyle=css('--ink-2');g.font='11px system-ui';
 const step=Math.max(5,Math.round((ymax-ymin)/8/5)*5);
 for(let v=Math.ceil(ymin/step)*step;v<=ymax;v+=step){
  g.beginPath();g.moveTo(padL,Y(v));g.lineTo(W-padR,Y(v));g.stroke();
  g.fillText(v.toFixed(0),W-padR+6,Y(v)+4);}
 for(let t=0;t<=x1;t+=3600){g.fillText(ct(t,D.t0),X(t)-14,H-8);}
 // walls (stepped dashes)
 g.setLineDash([5,4]);g.lineWidth=1.4;
 for(const[idx,color]of[[1,'--call'],[2,'--put']]){
  g.strokeStyle=css(color);g.beginPath();let started=false;
  for(let i=0;i<D.walls.length;i++){const w=D.walls[i];if(w[idx]==null)continue;
   const xEnd=i+1<D.walls.length?D.walls[i+1][0]:x1;
   if(w[idx]<ymin||w[idx]>ymax){started=false;continue;}
   g.moveTo(X(w[0]),Y(w[idx]));g.lineTo(X(xEnd),Y(w[idx]));}
  g.stroke();}
 g.setLineDash([]);
 // spot
 g.strokeStyle=css('--spot');g.lineWidth=1.2;g.beginPath();
 D.spot.forEach((p,i)=>{i?g.lineTo(X(p[0]),Y(p[1])):g.moveTo(X(p[0]),Y(p[1]))});
 g.stroke();
 // events
 hits=[];
 for(const e of D.events){
  const x=X(e.off),y=Y(e.spot);
  g.fillStyle=css(e.side==='call'?'--call':'--put');
  g.beginPath();g.arc(x,y,5,0,7);g.fill();
  if(e.wall_d<=5){g.strokeStyle=css('--ink');g.lineWidth=1.6;
   g.beginPath();g.arc(x,y,8,0,7);g.stroke();}
  hits.push({x,y,e});}
}
cv.addEventListener('mousemove',ev=>{
 const r=cv.getBoundingClientRect(),mx=ev.clientX-r.left,my=ev.clientY-r.top;
 const h=hits.find(h=>Math.hypot(h.x-mx,h.y-my)<10);
 if(!h){tip.style.display='none';return;}
 const e=h.e,D=DATA[sel.value];
 tip.innerHTML='<b>'+ct(e.off,D.t0)+' CT &middot; '+e.side+'-side</b><br>'
  +'spot '+e.spot+' &middot; wall dist '+e.wall_d+' pts<br>'
  +'30-min trend '+(e.trend>0?'+':'')+e.trend+' pts<br>'
  +'aligned +30m: '+(e.al30==null?'censored (near close)':(e.al30>0?'+':'')+e.al30+' pts');
 tip.style.left=Math.min(h.x+12,cv.clientWidth-270)+'px';tip.style.top=(h.y+14)+'px';
 tip.style.display='block';});
cv.addEventListener('mouseleave',()=>tip.style.display='none');
sel.addEventListener('change',draw);
document.getElementById('prev').onclick=()=>{const i=days.indexOf(sel.value);
 if(i>0){sel.value=days[i-1];draw();}};
document.getElementById('next').onclick=()=>{const i=days.indexOf(sel.value);
 if(i<days.length-1){sel.value=days[i+1];draw();}};
window.addEventListener('resize',draw);
draw();
</script></body></html>
"""
html = html.replace("__BUILT__", built).replace("__DATA__", payload)
OUT.write_text(html)
print(f"{OUT}  ({len(html) // 1024} KB, {len(days_out)} days, "
      f"{n_events} events)")
