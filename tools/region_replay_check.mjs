/**
 * Behavioural check for the drill page's region-replay door. [co-j9t1g]
 *
 * WHY, SEPARATELY FROM page_boot_check.mjs AND drill_page_check.mjs
 *   Boot proves nothing threw; the emissions check proves the per-bar panel
 *   paints. Neither reaches the replay row: the typed sentence, the request
 *   the page sends to the bridge, the list it paints from the answer, and
 *   the click that seeks the tape. Those are pure browser behaviour and no
 *   pytest touches them. Without this the only proof is somebody dragging on
 *   the chart, and that proof expires with the next template change.
 *
 * WHAT IT ASSERTS
 *   The row and its kind chips exist and boot with the bridge DOWN (the seed
 *   vocabulary stands); a sentence in the box becomes GET /replay?say=…&day=…
 *   with the page's day and the selected chips as kind=…; the answer paints
 *   one row per record in order, with the record's clock and kind; clicking
 *   a row seeks the tape to that bar and pins its emission panel; a bridge
 *   error lands in the status, not in the console as an uncaught throw;
 *   Escape closes the list.
 *
 * DEPENDENCY
 *   node + jsdom, out-of-tree like the other checks (see page_boot_check.mjs):
 *     cd <scratch> && bun add jsdom@24
 *     bash tools/nodecheck.sh tools/region_replay_check.mjs <drill-page.html>
 *   Needs a DRILL page (bars baked in):
 *     .venv/bin/python scripts/orderflow_drill.py --date 2026-08-25 --no-open --out <page.html>
 *
 * EXIT  0 = every check passed.  1 = at least one failed (all are printed).
 */
import fs from "fs";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");

const file = process.argv[2];
if (!file) { console.error("usage: node tools/region_replay_check.mjs <drill-page.html>"); process.exit(2); }

const errors = [];
const check = (ok, what) => { if (!ok) errors.push(what); };
const fetches = [];

// The bridge as the page will see it: /replay/kinds and /replay answer, the
// rest is down. The replay answer is two records at known bars.
const REPLAY = {
  request: { day: "2026-08-25", readback: "Replay Tue 2026-08-25, 13:30 to 14:10 CT, plan-level and sweeps only.",
             text: "13:30 to 14:10, sweeps and plan-level only", unknown: [] },
  day: "2026-08-25", count: 2, took_ms: 4200, cached: false,
  records: [
    { day: "2026-08-25", ts: "2026-08-25T13:46:00-05:00", path: "tape", kind: "PLAN-LEVEL", subtype: "TOUCH", sig: "note",
      fields: { level: "7692" }, line: "13:46 CT  EVENT PLAN-LEVEL TOUCH  sig=note  level=7692  anchor=resistance" },
    { day: "2026-08-25", ts: "2026-08-25T13:51:37-05:00", path: "engine", kind: "SweepPrint", subtype: "sell", sig: null,
      fields: { start_price: 7691.0 }, line: "13:51:37 CT  ENGINE SweepPrint sell  sell sweep 7691.00->7690.50", bar_i: 300 },
  ],
};
let replayAnswer = () => ({ ok: true, status: 200, json: async () => REPLAY });

const dom = new JSDOM(fs.readFileSync(file, "utf8"), {
  runScripts: "dangerously",
  url: "http://localhost/",
  pretendToBeVisual: true,
  beforeParse(w) {
    w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    w.fetch = (url) => {
      const u = String(url);
      fetches.push(u);
      if (u.includes("/replay/kinds")) return Promise.resolve({ ok: true, status: 200, json: async () => ({
        kinds: [{ id: "PLAN-LEVEL", path: "tape", label: "plan-level" }, { id: "SweepPrint", path: "engine", label: "sweeps" }] }) });
      if (u.includes("/replay?")) return Promise.resolve(replayAnswer());
      return Promise.reject(new Error("bridge down (by design in this check)"));
    };
    w.addEventListener("error", e => errors.push(`uncaught: ${e.message}`));
    w.HTMLElement.prototype.scrollIntoView = function () {};
  },
});
const w = dom.window, d = w.document;
const tick = (ms = 30) => new Promise(r => setTimeout(r, ms));

await tick(200);

// 1. the row is there and booted
const inp = d.getElementById("rqinput"), btn = d.getElementById("rqrun"), panel = d.getElementById("rqpanel");
check(inp && btn && panel, "replay row (#rqinput, #rqrun, #rqpanel) missing");
check(panel && panel.hidden, "the list must start hidden");
const chips = () => [...d.querySelectorAll("#rqkinds .rq-kind")];
check(chips().length >= 2, `kind chips: expected chips from /replay/kinds, got ${chips().length}`);

// 2. a sentence + a chip → the request the bridge sees
const sweepChip = chips().find(c => c.textContent === "sweeps");
check(!!sweepChip, "no 'sweeps' chip");
if (sweepChip) sweepChip.click();
inp.value = "13:30 to 14:10, plan-level";
inp.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
await tick(100);
const req = fetches.find(u => u.includes("/replay?"));
check(!!req, "no GET /replay after Enter");
if (req) {
  const q = new w.URL(req).searchParams;
  check(q.get("say") === "13:30 to 14:10, plan-level", `say param wrong: ${q.get("say")}`);
  check(q.get("day") === "2026-08-25", `day param should be the page's day, got ${q.get("day")}`);
  check(q.getAll("kind").includes("SweepPrint"), `selected chip not sent as kind=: ${q.getAll("kind")}`);
}

// 3. the answer paints, in order, with clock and kind
check(!panel.hidden, "list did not open on a good answer");
const rows = [...d.querySelectorAll("#rqpanel tr.rq-row")];
check(rows.length === 2, `expected 2 rows, got ${rows.length}`);
if (rows.length === 2) {
  check(rows[0].querySelector("td.t").textContent === "13:46:00", `row 1 clock: ${rows[0].querySelector("td.t").textContent}`);
  check(rows[1].querySelector("td.k").textContent === "Sweep", `row 2 kind label: ${rows[1].querySelector("td.k").textContent}`);
  check(/PLAN-LEVEL TOUCH/.test(rows[0].textContent), "row 1 gist should carry the line's content");
  check(/bar 301/.test(rows[1].textContent), `engine row should name its bar (bar_i 300 → bar 301): ${rows[1].textContent}`);
}
check(/2 emissions/.test(panel.querySelector("h4").textContent), "header should count the emissions");
check(/Replay Tue 2026-08-25/.test(panel.querySelector("h4").textContent), "header should carry the read-back");

// 4. clicking a row seeks the tape and pins the emission panel. The readout
// numbers bars within the cash session, so read the tape itself: after a seek
// the last painted column is the sought bar.
const lastCol = () => { const cols = d.querySelectorAll("#colstrip .col"); return cols.length ? cols[cols.length - 1].dataset.i : null; };
rows[1].click();
await tick(50);
check(lastCol() === "300", `clicking the engine row should seek to bar index 300, tape ends at ${lastCol()}`);
check(rows[1].classList.contains("cur") || d.querySelector("#rqpanel tr.rq-row.cur"), "clicked row not highlighted");
const em = d.getElementById("empanel");
check(em && em.style.display === "block", "emission panel should be pinned open on the sought bar");

// 5. keys: n/p move, g labels
d.dispatchEvent(new w.KeyboardEvent("keydown", { code: "KeyP", bubbles: true }));
await tick(30);
check(d.querySelector("#rqpanel tr.rq-row.cur") && d.querySelector("#rqpanel tr.rq-row.cur").dataset.k === "0", "p should move to the previous row");
d.dispatchEvent(new w.KeyboardEvent("keydown", { code: "KeyG", bubbles: true }));
await tick(30);
check(d.querySelector("#rqpanel tr.rq-row[data-k='0'] td.l").textContent === "✓", "g should mark the row kept");
check(!!w.localStorage.getItem("oflow-replay-labels-2026-08-25"), "label should persist to localStorage");

// 6. a bridge error is a status line, not a throw
replayAnswer = () => ({ ok: false, status: 400, json: async () => ({ error: "window runs backwards: 14:10 to 13:30" }) });
inp.value = "14:10 to 13:30";
btn.click();
await tick(100);
check(/backwards/.test(d.getElementById("rqstatus").textContent), `error should land in the status: '${d.getElementById("rqstatus").textContent}'`);

// 7. Escape closes
d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
await tick(30);
check(panel.hidden, "Escape should close the list");

// Exit explicitly either way: the page keeps pollers on timers, and a jsdom
// window with live intervals holds node's event loop open forever.
if (errors.length) {
  console.error("region replay check: FAILED");
  for (const e of errors) console.error("  - " + e);
  w.close();
  process.exit(1);
}
console.log("region replay check: all checks passed");
w.close();
process.exit(0);
