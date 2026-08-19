/**
 * Behavioural check for the coach cursor on the footprint page. [st-135m]
 *
 * WHAT IT COVERS
 *   The bridge's coach channel gained two verbs: `point {bar, price, text,
 *   pulse, hold_ms}` puts a page-drawn pointer on a cell (bar index + price)
 *   with a label beside it and, optionally, a ring pulse on the cell and a
 *   persistent outline; `clear` removes all of it. Steve, 2026-08-18: "a
 *   hover would allow you to draw my eye to a specific place on the screen …
 *   a cursor would be awesome."
 *
 * WHAT IT ASSERTS
 *   1. a `point` command arriving on /commands draws exactly one cursor and one
 *      label, cursor `top` == yFor(price), `left` == that column's centre;
 *   2. the label carries the text; `pulse` marks the target cell (.coach-hi
 *      outline, .coach-pulse animation class present right after);
 *   3. a second `point` MOVES the cursor (still one), to the new bar/price;
 *   4. the cursor survives a zoom repaint (re-placed, not lost);
 *   5. bar omitted → the newest bar (idx); a bar off the left edge → the
 *      cursor parks at the edge and the label says so;
 *   6. `clear` removes cursor, label and outline; `hold_ms` clears itself;
 *   7. no uncaught errors.
 *
 * DEPENDENCY  node + jsdom@24 out-of-tree; a LIVE page:
 *     .venv/bin/python scripts/live_footprint_page.py --date 2026-08-07 --out <scratch>/live-cue.html
 *     bash tools/nodecheck.sh tools/coach_point_check.mjs <scratch>/live-cue.html
 * EXIT  0 = every check passed; 1 = at least one failed.
 */
import fs from "fs";
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");

const file = process.argv[2];
if (!file) { console.error("usage: node tools/coach_point_check.mjs <live-page.html>"); process.exit(2); }

const TICK = 0.25, BASE = 6400;
const tIso = (i, s = 0) => new Date(Date.UTC(2026, 7, 7, 13, 30 + i, s)).toISOString().replace("Z", "+00:00");
function makeBar(i) {
  const px = BASE + (i % 3) * TICK;
  const cells = [];
  for (let k = -2; k <= 3; k++) cells.push([px + k * TICK, 200 + 40 * (k + 2), 300 - 30 * (k + 2)]);
  return { t0: tIso(i), t1: tIso(i + 1), o: px, h: px + 3 * TICK, l: px - 2 * TICK, c: px + TICK, v: 2000,
           d: 10, nv: 0, dur: 30, poc: px, cells, steps: [], ev: [] };
}
const N = 60;                                    // more than KEEP_COLS so a bar can be off the left edge
const TAPE = Array.from({ length: N }, (_, i) => makeBar(i));
let served = 0;
const publish = n => { served = Math.min(N, served + n); };
let COMMANDS = [];                               // what /commands serves; ids assigned here
const queue = cmd => { COMMANDS.push({ ...cmd, id: COMMANDS.length + 1 }); };

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
      if (u.includes("/commands")) {
        const since = Number(new URL(u).searchParams.get("since") || 0);
        return json({ commands: COMMANDS.filter(c => c.id > since), last: COMMANDS.length });
      }
      if (u.includes("/state")) return json({ ok: true });
      if (u.includes("/alerts")) return json({ alerts: [], total: 0, day: "2026-08-07" });
      if (u.includes("/bars")) {
        const since = Number(new URL(u).searchParams.get("since") || 0);
        return json({ bars: TAPE.slice(since, served), meta: { bar_n: 2000, day: "2026-08-07" },
                      final: [], developing: null, profile: null });
      }
      return Promise.reject(new Error("unstubbed: " + u));
    };
  },
});
const w = dom.window, d = w.document;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const POLL = () => w.eval("POLL_MS") + 300;
const COACH_POLL = 2300;                         // pollCoach runs every 2 s
function ok(name, cond, detail = "") {
  console.log(`${cond ? "  PASS" : "  FAIL"}  ${name}${detail ? " — " + detail : ""}`);
  if (!cond) errors.push(name);
}
const cursors = () => [...d.querySelectorAll(".coach-cursor")];
const labels = () => [...d.querySelectorAll(".coach-label")];
const his = () => [...d.querySelectorAll(".cell.coach-hi")];
const colCentre = i => w.eval(`(function(){ const c=$("cols"); const {x,on}=senColX(${i}); return on ? (c.offsetLeft||0) + x + COL_W/2 : null; })()`);
const cellOf = (i, price) => d.querySelector(`.col[data-i="${i}"] .cell[data-tk="${Math.round(price / TICK)}"]`);

(async () => {
  await sleep(500);
  if (!w.eval("LIVE")) { console.error("FAIL — not a LIVE page"); process.exit(1); }
  publish(10);                                   // bars 0..9 on screen
  await sleep(POLL()); await sleep(POLL());
  ok("bars on screen", w.eval("bars.length") === 10 && w.eval("idx") === 9, `bars=${w.eval("bars.length")} idx=${w.eval("idx")}`);

  // 1–2. point at bar 5, its POC price, with a label and a pulse
  const p5 = BASE + (5 % 3) * TICK;
  queue({ type: "point", bar: 5, price: p5, text: "the POC of bar 6", pulse: true });
  await sleep(COACH_POLL);
  ok("one cursor, one label", cursors().length === 1 && labels().length === 1, `${cursors().length}/${labels().length}`);
  const c1 = cursors()[0];
  ok("cursor top == yFor(price)", c1 && c1.style.top === w.eval(`yFor(${p5})`) + "px", c1 && `${c1.style.top} vs ${w.eval(`yFor(${p5})`)}px`);
  ok("cursor left == the column's centre", c1 && c1.style.left === colCentre(5) + "px", c1 && `${c1.style.left} vs ${colCentre(5)}px`);
  ok("label carries the text", labels()[0] && /the POC of bar 6/.test(labels()[0].textContent), labels()[0] && labels()[0].textContent);
  const cell5 = cellOf(5, p5);
  ok("target cell outlined (.coach-hi)", cell5 && cell5.classList.contains("coach-hi") && his().length === 1);
  ok("pulse class applied on arrival", cell5 && cell5.classList.contains("coach-pulse"));

  // 3. move it
  const p8 = BASE + (8 % 3) * TICK + TICK;
  queue({ type: "point", bar: 8, price: p8, text: "one tick above bar 9's POC" });
  await sleep(COACH_POLL);
  ok("still exactly one cursor after a move", cursors().length === 1 && labels().length === 1);
  ok("moved to the new bar/price", cursors()[0].style.left === colCentre(8) + "px" && cursors()[0].style.top === w.eval(`yFor(${p8})`) + "px");
  ok("outline moved with it", his().length === 1 && cellOf(8, p8) && cellOf(8, p8).classList.contains("coach-hi") && !(cell5 && cell5.classList.contains("coach-hi")));

  // 4. survives a zoom repaint
  w.eval("cellH = 24; repaintAll();");
  ok("cursor re-placed after a zoom", cursors().length === 1 && cursors()[0].style.top === w.eval(`yFor(${p8})`) + "px");
  w.eval("cellH = 13; repaintAll();");

  // 5a. bar omitted → newest bar
  queue({ type: "point", price: BASE });
  await sleep(COACH_POLL);
  ok("bar omitted → the newest bar", cursors()[0].style.left === colCentre(w.eval("idx")) + "px", `${cursors()[0].style.left} vs ${colCentre(w.eval("idx"))}`);
  // 5b. bar off the left edge → parked at the edge, label says so
  publish(50);                                   // bars 10..59; KEEP_COLS pushes bar 5 off-screen
  await sleep(POLL()); await sleep(POLL()); await sleep(POLL());
  queue({ type: "point", bar: 2, price: BASE, text: "an early bar" });
  await sleep(COACH_POLL);
  ok("off-screen bar → cursor parked, label says off-screen", cursors().length === 1 && labels()[0] && /off-screen/.test(labels()[0].textContent) && labels()[0].classList.contains("edge"), labels()[0] && labels()[0].textContent);

  // 6. clear; then hold_ms self-clear
  queue({ type: "clear" });
  await sleep(COACH_POLL);
  ok("clear removes cursor, label and outline", cursors().length === 0 && labels().length === 0 && his().length === 0);
  queue({ type: "point", price: BASE, hold_ms: 3500 });   // longer than one coach poll, so we can see it before it goes
  await sleep(COACH_POLL);
  ok("hold_ms: shown …", cursors().length === 1);
  await sleep(3800);
  ok("… then clears itself", cursors().length === 0 && labels().length === 0);

  ok("no uncaught errors", errors.filter(e => e.startsWith("uncaught")).length === 0, errors.filter(e => e.startsWith("uncaught")).join("; "));
  console.log(errors.length ? `\n${errors.length} FAILED` : "\nALL PASS");
  process.exit(errors.length ? 1 : 0);
})();
