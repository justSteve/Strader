/**
 * Behavioural check for sentinel rows on the LIVE footprint page. [st-n0qm.9]
 *
 * WHAT IT COVERS
 *   The orderflow sentinel posts SPX-domain level alerts to the bridge; the
 *   page polls /alerts and draws each level on the ES axis at strike + basis,
 *   where the basis is the `bs` the newest closed bar carries. Steve ruled
 *   the web page is the surface for anything at the FP chart's level.
 *
 * WHAT IT ASSERTS
 *   1. alerts with NO basis on any bar → no rows, and the strip says why;
 *   2. once bars carry `bs`, one row per level, `top` == yFor(spx + basis),
 *      `left` == the firing bar's column edge, tag names the level and the ES
 *      price, tooltip carries the arithmetic;
 *   3. a second alert for the same level replaces its row (newest value) and
 *      the earlier alert keeps a mark on its bar;
 *   4. the strip carries the newest sentence and the basis;
 *   5. `s` hides rows and strikes the strip; `s` again restores;
 *   6. a bridge reset (total < seen) refetches from 0 rather than duplicating;
 *   7. rows follow a repaint (zoom) — no stale tops; no uncaught errors.
 *
 * DEPENDENCY  node + jsdom@24 out-of-tree; a LIVE page for 2026-08-07:
 *     .venv/bin/python scripts/live_footprint_page.py --date 2026-08-07 --out <scratch>/live-sent.html
 *     bash tools/nodecheck.sh tools/sentinel_rows_check.mjs <scratch>/live-sent.html
 * EXIT  0 = every check passed; 1 = at least one failed.
 */
import fs from "fs";
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");

const file = process.argv[2];
if (!file) { console.error("usage: node tools/sentinel_rows_check.mjs <live-page.html>"); process.exit(2); }

const TICK = 0.25, BASE = 6400, BASIS = 20.75;
// Bars one minute apart from 08:30 CT (13:30Z); bar i spans [13:30+i, 13:31+i).
const tIso = (i, s = 0) => new Date(Date.UTC(2026, 7, 7, 13, 30 + i, s)).toISOString().replace("Z", "+00:00");
function makeBar(i, withBs) {
  const px = BASE + (i % 3) * TICK;
  const cells = [];
  for (let k = -2; k <= 3; k++) cells.push([px + k * TICK, 200 + 40 * (k + 2), 300 - 30 * (k + 2)]);
  const b = { t0: tIso(i), t1: tIso(i + 1), o: px, h: px + 3 * TICK, l: px - 2 * TICK, c: px + TICK, v: 2000,
              d: 10, nv: 0, dur: 30, poc: px, cells, steps: [], ev: [] };
  if (withBs) b.bs = { pts: BASIS, n: 10, age_s: 0.5 };
  return b;
}
let barsHaveBs = false;
const TAPE = () => Array.from({ length: 12 }, (_, i) => makeBar(i, barsHaveBs));
let served = 0;
const publish = n => { served = Math.min(12, served + n); };

// alerts: SPX-domain. mLG at 6379.46 → ES 6400.21 (inside the fixture view).
const A1 = { kind: "approach", level: "z_mlgamma", name: "major long gamma", value: 6379.46, spot: 6381.6,
             distance_pts: 2.14, side: "from_above", strike: 6380,
             ts_alert_utc: tIso(5, 4), ts_row: tIso(5, 3) };                 // fires in bar 5
const A2 = { kind: "approach", level: "z_msgamma", name: "major short gamma", value: 6380.5, spot: 6382.1,
             distance_pts: 1.6, side: "from_below", strike: 6380,
             ts_alert_utc: tIso(7, 10), ts_row: tIso(7, 9) };                // bar 7
const A3 = { kind: "relocation", level: "z_mlgamma", name: "major long gamma", old: 6379.46, new: 6381.0,
             spot: 6382.0, strike: 6380, ts_alert_utc: tIso(9, 30), ts_row: tIso(9, 29) };  // bar 9, same level as A1
let ALERTS = [];
const withIds = list => list.map((a, i) => ({ ...a, id: i + 1, received_utc: a.ts_alert_utc }));

const errors = [];
const dom = new JSDOM(fs.readFileSync(file, "utf8"), {
  runScripts: "dangerously", url: "http://localhost/", pretendToBeVisual: true,
  beforeParse(w) {
    w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    w.addEventListener("error", e => errors.push(`uncaught: ${e.message}`));
    Object.defineProperty(w.HTMLElement.prototype, "clientHeight", { get() { return 700; }, configurable: true });
    Object.defineProperty(w.HTMLElement.prototype, "clientWidth", { get() { return 1400; }, configurable: true });
    w.fetch = (url) => {
      const u = String(url);
      const json = body => Promise.resolve({ json: () => Promise.resolve(body) });
      if (u.includes("/health/producers")) return json({ producers: {} });
      if (u.includes("/health")) return json({ ok: true });
      if (u.includes("/commands")) return json({ commands: [], last: 0 });
      if (u.includes("/state")) return json({ ok: true });
      if (u.includes("/alerts")) {
        const since = Number(new URL(u).searchParams.get("since") || 0);
        const all = withIds(ALERTS);
        return json({ alerts: all.slice(since), total: all.length, day: "2026-08-07" });
      }
      if (u.includes("/bars")) {
        const since = Number(new URL(u).searchParams.get("since") || 0);
        return json({ bars: TAPE().slice(since, served), meta: { bar_n: 2000, day: "2026-08-07" },
                      final: [], developing: null, profile: null });
      }
      return Promise.reject(new Error("unstubbed: " + u));
    };
  },
});
const w = dom.window, d = w.document;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const POLL = () => w.eval("POLL_MS") + 300;
function ok(name, cond, detail = "") {
  console.log(`${cond ? "  PASS" : "  FAIL"}  ${name}${detail ? " — " + detail : ""}`);
  if (!cond) errors.push(name);
}
const lines = () => [...d.querySelectorAll(".sen-line")];
const tags = () => [...d.querySelectorAll(".sen-tag")];
const marks = () => [...d.querySelectorAll(".sen-mark")];
const strip = () => d.getElementById("sen-strip");
const stripText = () => (strip() && strip().querySelector(".sen-txt").textContent) || "";
const colLeft = i => w.eval(`(function(){ const c=$("cols"); const first=Math.max(0, idx-KEEP_COLS+1); return (c.offsetLeft||0) + Math.max(0, (c.clientWidth||0) - (idx-${i}+1)*COL_W); })()`);

(async () => {
  await sleep(500);
  if (!w.eval("LIVE")) { console.error("FAIL — not a LIVE page"); process.exit(1); }
  ok("strip present in the HUD", !!strip() && strip().closest("#livehud") !== null);

  // 1. alerts before any basis
  ALERTS = [A1];
  publish(3);                       // bars 0..2 without bs
  await sleep(POLL());
  ok("alerts polled", w.eval("sentAlerts.length") === 1, `sentAlerts=${w.eval("sentAlerts.length")}`);
  ok("no basis → no rows", lines().length === 0);
  ok("strip explains the missing basis", /no basis yet/.test(stripText()), stripText());

  // 2. bars carry bs → row appears
  barsHaveBs = true;
  w.eval("bars.length = 0; sentSeen = 0; sentAlerts = []; idx = -1;");   // restart the page's tape cleanly
  served = 0; publish(8);            // bars 0..7 with bs; alert A1 fired in bar 5
  await sleep(POLL()); await sleep(POLL());
  ok("bars carry bs", w.eval("basisNow() && basisNow().pts") === BASIS);
  ok("one row for the one level", lines().length === 1 && tags().length === 1, `${lines().length} lines`);
  const es1 = 6379.46 + BASIS;
  const top1 = w.eval(`yFor(${es1})`) + "px";
  ok("row top == yFor(spx + basis)", lines()[0] && lines()[0].style.top === top1, `${lines()[0] && lines()[0].style.top} vs ${top1}`);
  ok("row starts at the firing bar's column", lines()[0] && lines()[0].style.left === colLeft(5) + "px", `${lines()[0] && lines()[0].style.left} vs ${colLeft(5)}px`);
  ok("tag names level, strike, kind and ES price", tags()[0] && /mLG 6380 · approach · ES 6400\.25/.test(tags()[0].textContent), tags()[0] && tags()[0].textContent);
  ok("tooltip carries the arithmetic", tags()[0] && /SPX 6379\.46 \+ basis 20\.75 = ES 6400\.21/.test(tags()[0].title), tags()[0] && tags()[0].title);
  // basis is in the strip's tooltip since st-9olq (noise on the line, useful on hover)
  ok("strip carries the sentence; the basis rides its tooltip", /6380 major long gamma — approach from above/.test(stripText()) && /basis \+20\.75 \(n10\)/.test(strip().title || ""), stripText() + " | " + (strip().title || ""));

  // 3. a second level, then a relocation of the first
  ALERTS = [A1, A2];
  await sleep(POLL());
  ok("two levels → two rows", lines().length === 2 && new Set(lines().map(l => l.dataset.level)).size === 2, `${lines().length}`);
  ALERTS = [A1, A2, A3];
  publish(2);                        // bars 8..9 so A3's bar exists
  await sleep(POLL()); await sleep(POLL());
  const ml = lines().find(l => l.dataset.level === "z_mlgamma");
  ok("relocation replaces the level's row at the NEW value", ml && ml.style.top === w.eval(`yFor(${6381.0 + BASIS})`) + "px" && ml.classList.contains("sen-relocation"), ml && ml.style.top);
  ok("still one row per level", lines().length === 2, `${lines().length}`);
  ok("the earlier approach keeps a mark on its bar", marks().length === 1 && marks()[0].dataset.level === "z_mlgamma", `${marks().length} marks`);
  ok("strip shows the newest sentence", /relocation \(was 6379\)/.test(stripText()), stripText());

  // 5. toggle
  d.dispatchEvent(new w.KeyboardEvent("keydown", { code: "KeyS", bubbles: true }));
  ok("s hides the rows and strikes the strip", lines().length === 0 && strip().classList.contains("off"));
  d.dispatchEvent(new w.KeyboardEvent("keydown", { code: "KeyS", bubbles: true }));
  ok("s restores them", lines().length === 2 && !strip().classList.contains("off"));

  // 7. rows follow a zoom repaint
  w.eval("cellH = 24; repaintAll();");
  ok("rows re-place after a zoom", ml && lines().find(l => l.dataset.level === "z_mlgamma").style.top === w.eval(`yFor(${6381.0 + BASIS})`) + "px");
  w.eval("cellH = 13; repaintAll();");

  // 6. bridge reset: fewer alerts than seen → refetch from zero, no duplicates
  ALERTS = [A2];
  await sleep(POLL());
  ok("bridge reset refetches from zero", w.eval("sentAlerts.length") === 1 && w.eval("sentSeen") === 1 && lines().length === 1, `sentAlerts=${w.eval("sentAlerts.length")} seen=${w.eval("sentSeen")}`);

  ok("no uncaught errors", errors.filter(e => e.startsWith("uncaught")).length === 0, errors.filter(e => e.startsWith("uncaught")).join("; "));
  console.log(errors.length ? `\n${errors.length} FAILED` : "\nALL PASS");
  process.exit(errors.length ? 1 : 0);
})();
