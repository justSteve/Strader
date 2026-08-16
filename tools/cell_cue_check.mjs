/**
 * Behavioural check for the cell cues on the LIVE page. [st-n0qm.2]
 *
 * WHAT IT COVERS
 *   Steve, 2026-08-16: when a PA structure triggers the emitter, "provide a
 *   visual clue on the relevant cells themselves … a brief flash or glow that
 *   draws the eye which transitions to a inobtrusive visual element that
 *   remains visible."  The page resolves each emission to cells from the
 *   fields it already carries (an ImbalanceStack's prices, a SweepPrint's
 *   start..end, a DeltaDivergence's pivot) and paints them: a ~900 ms flash
 *   class that is removed on a timer, and a persistent mark that must survive
 *   repaintAll() (zoom / resize / cell-mode rebuild every column).
 *
 * WHAT IT ASSERTS
 *   1. a fresh bar carrying an ImbalanceStack paints exactly its prices[]
 *      cells with .cue.cue-stack, and they carry .cue-new right after arrival;
 *   2. the flash class is gone after CUE_FLASH_MS; the mark remains;
 *   3. repaintAll() rebuilds the columns and the marks are still there, with
 *      no .cue-new (state lives outside the DOM);
 *   4. a SweepPrint marks its swept range; a DeltaDivergence marks the pivot
 *      cell on the EARLIER bar that traded that price (back-search);
 *   5. a since=0 style backlog (many bars in one poll) paints marks and does
 *      NOT flash;
 *   6. `x` toggles every cue off and back on;
 *   7. the developing column never carries a cue;
 *   8. clicking a cued cell opens the emissions panel pinned to the source bar.
 *
 * DEPENDENCY  node + jsdom@24 out-of-tree (see page_boot_check.mjs header):
 *     cd <scratch> && bun add jsdom@24
 *     bash tools/nodecheck.sh tools/cell_cue_check.mjs <live-page.html>
 *   The page must be a LIVE page rendered for 2026-08-07 (the stub's day):
 *     .venv/bin/python scripts/live_footprint_page.py --date 2026-08-07 --out <scratch>/live-cue.html
 *
 * EXIT  0 = every check passed; 1 = at least one failed (all printed).
 */
import fs from "fs";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");

const file = process.argv[2];
if (!file) { console.error("usage: node tools/cell_cue_check.mjs <live-page.html>"); process.exit(2); }

const TICK = 0.25;
const BASE = 6400;
// A bar whose cells span BASE-2t .. BASE+3t; every price traded so the cue
// targets are real cells (an ImbalanceStack's prices are traded cells by
// construction; the check mirrors that).
function makeBar(i, ev) {
  const px = BASE + (i % 3) * TICK;
  const t = new Date(Date.UTC(2026, 7, 7, 14, 30 + i, 0)).toISOString().replace("Z", "+00:00");
  const cells = [];
  for (let k = -2; k <= 3; k++) cells.push([px + k * TICK, 200 + 40 * (k + 2), 300 - 30 * (k + 2)]);
  return { t0: t, t1: t, o: px, h: px + 3 * TICK, l: px - 2 * TICK, c: px + TICK, v: 2000,
           d: (i % 2 ? -1 : 1) * (40 + i), nv: 0, dur: 30, poc: px, cells, steps: [], ev: ev || [] };
}
const stack = (px) => ({ type: "ImbalanceStack", direction: "buy", prices: [px, px + TICK, px + 2 * TICK],
                         ratios: [3.1, 3.4, 4.0], confidence: 0.7, reason: "synthetic stack" });
const sweep = (lo, hi) => ({ type: "SweepPrint", direction: "up", total_size: 900, ticks_swept: 3,
                             start_price: lo, end_price: hi, reason: "synthetic sweep" });
const diverg = (pivot) => ({ type: "DeltaDivergence", kind: "bearish", price_extreme: pivot,
                             prior_extreme: pivot - TICK, cvd_at_extreme: 10, cvd_at_prior: 40, reason: "synthetic div" });

const TAPE = [];
for (let i = 0; i < 60; i++) TAPE.push(makeBar(i));
// bar 5: a stack at BASE+2t (its px = BASE+2t; cells cover it)
TAPE[5] = makeBar(5, [stack(BASE + 2 * TICK)]);
// bar 8: a sweep from BASE to BASE+2t (px = BASE+2t → l = BASE; range inside its own cells)
TAPE[8] = makeBar(8, [sweep(BASE, BASE + 2 * TICK)]);
// bar 20: a sweep that STARTED below bar 20's low (px = BASE+2t → l = BASE) — the
// plan's "sweep in i-1" case: bar 19 (px = BASE+1t → l = BASE-1t) traded it → lands on 19.
TAPE[20] = makeBar(20, [sweep(BASE - TICK, BASE + TICK)]);
// bar 12: a divergence whose pivot is BASE+3t+2t? keep it inside an earlier bar:
//   bar 11 has px = BASE+2t → h = BASE+5t; bar 12 has px = BASE → h = BASE+3t.
//   pivot BASE+4t is in bar 11's range only → back-search must land on 11.
TAPE[12] = makeBar(12, [diverg(BASE + 4 * TICK)]);
// bars 30..45: a backlog burst, several with stacks — must not flash
for (let i = 30; i < 46; i++) if (i % 4 === 0) TAPE[i] = makeBar(i, [stack(BASE + (i % 3) * TICK)]);

let served = 0;
const publish = n => { served = Math.min(TAPE.length, served + n); };
let developing = null;

const errors = [];
const dom = new JSDOM(fs.readFileSync(file, "utf8"), {
  runScripts: "dangerously", url: "http://localhost/", pretendToBeVisual: true,
  beforeParse(w) {
    w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    w.addEventListener("error", e => errors.push(`uncaught: ${e.message}`));
    // jsdom does no layout: every clientHeight is 0, and renderColumn skips a
    // cell whose row would clip against stage.clientHeight - FOOT_H — so with
    // no stub NO cell is ever built and every cue assertion is vacuous. Give
    // the stage a height (the follow check never needed cells; this one does).
    Object.defineProperty(w.HTMLElement.prototype, "clientHeight", { get() { return 700; }, configurable: true });
    Object.defineProperty(w.HTMLElement.prototype, "clientWidth", { get() { return 1400; }, configurable: true });
    w.fetch = (url) => {
      const u = String(url);
      const json = body => Promise.resolve({ json: () => Promise.resolve(body) });
      if (u.includes("/health")) return json({ ok: true });
      if (u.includes("/commands")) return json({ commands: [], last: 0 });
      if (u.includes("/state")) return json({ ok: true });
      if (u.includes("/bars")) {
        const since = Number(new URL(u).searchParams.get("since") || 0);
        return json({ bars: TAPE.slice(since, served), meta: { bar_n: 2000, day: "2026-08-07" },
                      final: [], developing });
      }
      return Promise.reject(new Error("unstubbed: " + u));
    };
  },
});
const w = dom.window, d = w.document;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const POLL = () => w.eval("POLL_MS") + 250;
function ok(name, cond, detail = "") {
  console.log(`${cond ? "  PASS" : "  FAIL"}  ${name}${detail ? " — " + detail : ""}`);
  if (!cond) errors.push(name);
}
const col = i => d.querySelector(`#colstrip .col[data-i="${i}"]`);
// Wait until the page has drawn bar i (the poll is asynchronous), then return
// at once — the flash is short and a fixed sleep would outlive it.
async function waitForCol(i, maxMs = 2500) {
  const t0 = Date.now();
  while (Date.now() - t0 < maxMs) { if (col(i)) return true; await sleep(25); }
  return false;
}
const cued = (i, cls = "cue") => col(i) ? [...col(i).querySelectorAll(`.cell.${cls}`)] : [];
const tks = els => els.map(e => Number(e.dataset.tk)).sort((a, b) => a - b);
const tk = p => Math.round(p / TICK);

(async () => {
  await sleep(500);
  if (!w.eval("LIVE")) { console.error("FAIL — not a LIVE page"); process.exit(1); }
  const FLASH = w.eval("CUE_FLASH_MS");
  ok("cue module present", typeof w.eval("resolveTargets") === "function" && FLASH > 0, `flash ${FLASH}ms`);

  // 1. fresh arrival: stack cells cued and flashing
  publish(6);                       // bars 0..5 — 6 bars > CUE_FLASH_MAX_FRESH → backfill, no flash
  await sleep(POLL());
  ok("boot backfill paints the stack's cells", tks(cued(5, "cue-stack")).join() === [tk(BASE + 2 * TICK), tk(BASE + 3 * TICK), tk(BASE + 4 * TICK)].join(),
     `tks ${tks(cued(5, "cue-stack"))}`);
  ok("boot backfill (6 bars at once) does NOT flash", cued(5, "cue-new").length === 0, `${cued(5, "cue-new").length} flashing`);
  ok("marks carry the corner glyph", cued(5)[0] && cued(5)[0].dataset.glyph === "▮", cued(5)[0] && cued(5)[0].dataset.glyph);
  ok("marks compose an inset box-shadow, not an outline", cued(5)[0] && /inset/.test(cued(5)[0].style.boxShadow), cued(5)[0] && cued(5)[0].style.boxShadow);

  // 2. now a single fresh bar with a stack: flash, then mark persists
  TAPE[6] = makeBar(6, [stack(BASE)]);      // px for i=6 is BASE → prices BASE..BASE+2t inside cells
  publish(1);
  await waitForCol(6);
  const fresh = cued(6, "cue-stack");
  ok("a fresh stack paints exactly its prices[] cells", tks(fresh).join() === [tk(BASE), tk(BASE + TICK), tk(BASE + 2 * TICK)].join(), `tks ${tks(fresh)}`);
  ok("…and they flash on arrival", fresh.length === 3 && fresh.every(c => c.classList.contains("cue-new")));
  await sleep(FLASH + 150);
  ok("the flash class is removed on the timer", cued(6, "cue-new").length === 0);
  ok("the persistent mark remains", cued(6, "cue-stack").length === 3);

  // 3. repaintAll rebuilds every column: marks survive, no flash
  w.eval("repaintAll()");
  ok("marks survive repaintAll (state outside the DOM)", cued(6, "cue-stack").length === 3 && cued(5, "cue-stack").length === 3);
  ok("repaintAll does not re-flash", cued(6, "cue-new").length === 0 && cued(5, "cue-new").length === 0);
  ok("POC outline coexists with a cue mark", (() => { const c = col(6) && col(6).querySelector(".cell.poc"); return c && c.classList.contains("cue"); })());

  // 4. sweep range + divergence pivot on an earlier bar
  publish(2);  // 7, 8
  await sleep(POLL());
  ok("a sweep marks its swept range", tks(cued(8, "cue-sweep").concat(cued(8, "cue-sweep_end"))).join() === [tk(BASE), tk(BASE + TICK), tk(BASE + 2 * TICK)].join(),
     `tks ${tks(cued(8, "cue-sweep").concat(cued(8, "cue-sweep_end")))}`);
  ok("the sweep's end cell is marked as the end", cued(8, "cue-sweep_end").length === 1 && Number(cued(8, "cue-sweep_end")[0].dataset.tk) === tk(BASE + 2 * TICK));
  publish(4);  // 9..12
  await sleep(POLL());
  ok("a divergence marks the pivot on the EARLIER bar that traded it", cued(11, "cue-pivot").length === 1 && Number(cued(11, "cue-pivot")[0].dataset.tk) === tk(BASE + 4 * TICK),
     `bar 11 pivots ${tks(cued(11, "cue-pivot"))}, bar 12 pivots ${tks(cued(12, "cue-pivot"))}`);
  ok("the emitting bar itself carries no pivot cell", cued(12, "cue-pivot").length === 0);

  publish(8);  // 13..20
  await sleep(POLL());
  ok("a sweep that began below its bar's low is filed on the bar that traded it (i-1)",
     cued(19, "cue-sweep").concat(cued(19, "cue-sweep_end")).length === 3 && cued(20, "cue-sweep").length === 0,
     `bar 19: ${tks(cued(19, "cue-sweep").concat(cued(19, "cue-sweep_end")))}, bar 20: ${tks(cued(20, "cue-sweep"))}`);

  // 5. backlog burst: marks, no flash
  publish(25); // 21..45 in one poll
  await sleep(POLL());
  const burst = [32, 36, 40, 44].map(i => cued(i, "cue-stack").length);
  ok("a backlog burst paints its stacks", burst.every(n => n === 3), `${burst}`);
  ok("a backlog burst does not flash", [32, 36, 40, 44].every(i => cued(i, "cue-new").length === 0));

  // 6. kill switch
  d.dispatchEvent(new w.KeyboardEvent("keydown", { code: "KeyX", bubbles: true }));
  ok("x hides every cue", d.querySelectorAll("#colstrip .cell.cue").length === 0);
  ok("the chip shows the off state", d.getElementById("cue-chip") && d.getElementById("cue-chip").classList.contains("off"));
  d.dispatchEvent(new w.KeyboardEvent("keydown", { code: "KeyX", bubbles: true }));
  ok("x brings them back", d.querySelectorAll("#colstrip .cell.cue").length > 0);

  // 7. developing column never cued
  developing = Object.assign(makeBar(46, [stack(BASE)]), { v: 900 });
  await sleep(POLL());
  const dev = d.querySelector("#colstrip .col.dev");
  ok("a developing column renders", !!dev);
  ok("…and carries no cue even if the payload had ev", dev && dev.querySelectorAll(".cell.cue").length === 0);
  developing = null;

  // 8. click → panel pinned to the source bar
  const cell = cued(6, "cue-stack")[0];
  cell.onclick();
  const panel = d.getElementById("empanel");
  ok("clicking a cued cell opens the emissions panel", panel.style.display === "block");
  ok("…pinned to the bar that emitted it", /Bar 7\b/.test(panel.innerHTML), panel.querySelector("h4") && panel.querySelector("h4").textContent.trim());
  ok("hover text names the cue", /imbalance stack price/.test(cell.title), cell.title.split("\n").pop());

  if (errors.length) { console.error(`\nFAIL — ${errors.length}:`); errors.forEach(e => console.error("  " + e)); process.exit(1); }
  console.log("\nall checks clean");
  process.exit(0);
})();
