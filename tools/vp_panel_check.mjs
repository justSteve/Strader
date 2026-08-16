/**
 * Behavioural check for the anchored volume-profile panel on the LIVE page. [st-n0qm.4]
 *
 * WHAT IT COVERS
 *   Steve, 2026-08-16: "a Volume Profile Chart that is anchored on the prior
 *   day's opening trade and is live-updated until EOD. The bars should be
 *   color coded to indicate the aggressor side of the trade." The bridge's
 *   `profile` slot arrives on every /bars response; the page draws it as rows
 *   to the LEFT of the columns on the cells' own yFor, so a VP row and the
 *   cell at that price share a pixel row.
 *
 * WHAT IT ASSERTS
 *   1. with a profile in the payload the panel shows and #cols is pushed right;
 *   2. every VP row's `top` equals the `top` of the newest column's cell at the
 *      same tick — at three zoom levels (the alignment IS the feature);
 *   3. sell (red) segments come before buy (blue) segments; the prior-day
 *      layer is drawn faint under today's;
 *   4. POC row outlined exactly once; value-area rows tinted; HVN/LVN ticks;
 *   5. the hole banner text comes from the payload, not a string in the page;
 *   6. `v` hides the panel and restores the columns' left edge, `v` again shows it;
 *   7. a growing profile (n increases) redraws without a bar arriving.
 *
 * DEPENDENCY  node + jsdom@24 out-of-tree; a LIVE page for 2026-08-07:
 *     .venv/bin/python scripts/live_footprint_page.py --date 2026-08-07 --out <scratch>/live-cue.html
 *     bash tools/nodecheck.sh tools/vp_panel_check.mjs <scratch>/live-cue.html
 * EXIT  0 = every check passed; 1 = at least one failed.
 */
import fs from "fs";
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");

const file = process.argv[2];
if (!file) { console.error("usage: node tools/vp_panel_check.mjs <live-page.html>"); process.exit(2); }

const TICK = 0.25, BASE = 6400;
function makeBar(i) {
  const px = BASE + (i % 3) * TICK;
  const t = new Date(Date.UTC(2026, 7, 7, 14, 30 + i, 0)).toISOString().replace("Z", "+00:00");
  const cells = [];
  for (let k = -2; k <= 3; k++) cells.push([px + k * TICK, 200 + 40 * (k + 2), 300 - 30 * (k + 2)]);
  return { t0: t, t1: t, o: px, h: px + 3 * TICK, l: px - 2 * TICK, c: px + TICK, v: 2000,
           d: 10, nv: 0, dur: 30, poc: px, cells, steps: [], ev: [] };
}
const TAPE = Array.from({ length: 12 }, (_, i) => makeBar(i));
// A profile spanning BASE-4t .. BASE+8t (13 buckets), with a clear POC at BASE+1t.
const LO = Math.round((BASE - 4 * TICK) / TICK);
const N = 13;
const buy = Array.from({ length: N }, (_, i) => 100 + (i === 5 ? 900 : i * 20));
const sell = Array.from({ length: N }, (_, i) => 80 + (i === 5 ? 700 : i * 10));
const sBuy = buy.map(v => Math.floor(v * 0.4)), sSell = sell.map(v => Math.floor(v * 0.4));
const total = buy.map((b, i) => b + sell[i]);
const pocI = total.indexOf(Math.max(...total));
const profileOf = (n) => ({
  v: 1, anchor: "prior-rth", anchor_ts: "2026-08-06T13:30:00+00:00", session_day: "2026-08-07",
  bucket: TICK, n, first_ts: "2026-08-06T13:30:00-05:00", last_ts: "2026-08-07T09:00:00-05:00",
  hole: [["2026-08-06T15:05:02-05:00", "2026-08-07T02:50:07-05:00"]],
  lo_tick: LO, buy, sell, none: buy.map(() => 0),
  seeded: { n: Math.floor(n * 0.6), through_ts: "2026-08-06T15:05:02-05:00", buy: sBuy, sell: sSell },
  va: { poc: (LO + pocI) * TICK, vah: (LO + pocI + 2) * TICK, val: (LO + pocI - 2) * TICK },
  hvn: [(LO + 9) * TICK], lvn: [(LO + 2) * TICK],
});
let served = 0, profileN = 5000;
const publish = n => { served = Math.min(TAPE.length, served + n); };

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
      if (u.includes("/bars")) {
        const since = Number(new URL(u).searchParams.get("since") || 0);
        return json({ bars: TAPE.slice(since, served), meta: { bar_n: 2000, day: "2026-08-07" },
                      final: [], developing: null, profile: profileOf(profileN) });
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
const vp = () => d.getElementById("vp");
const rows = () => [...d.querySelectorAll("#vp .vprow")];
const newestCol = () => d.querySelector(`#colstrip .col[data-i="${w.eval("bars.length") - 1}"]`);
function aligned() {
  const col = newestCol(); if (!col) return { checked: 0, bad: 1 };
  let checked = 0, bad = 0;
  for (const r of rows()) {
    const cell = col.querySelector(`.cell[data-tk="${r.dataset.tk}"]`);
    if (!cell) continue;
    checked++;
    if (cell.style.top !== r.style.top || cell.style.height !== r.style.height) bad++;
  }
  return { checked, bad };
}

(async () => {
  await sleep(500);
  if (!w.eval("LIVE")) { console.error("FAIL — not a LIVE page"); process.exit(1); }
  publish(8);
  await sleep(POLL());
  ok("panel shows when the payload carries a profile", d.body.classList.contains("vp-on") && vp().style.width !== "0px", `width ${vp().style.width}`);
  ok("columns are pushed right of the panel", d.getElementById("cols").style.left === vp().style.width, d.getElementById("cols").style.left);
  ok("rows render", rows().length > 5, `${rows().length} rows`);

  // 2. alignment at three zoom levels
  for (const z of [13, 18, 24]) {
    w.eval(`cellH = ${z}; repaintAll();`);
    const a = aligned();
    ok(`VP rows share the cells' pixel rows at cellH=${z}`, a.checked > 3 && a.bad === 0, `${a.checked} compared, ${a.bad} misaligned`);
  }
  w.eval("cellH = 13; repaintAll();");

  // 3. segment order and prior-day layer
  const pocRow = rows().find(r => r.classList.contains("poc"));
  ok("POC row is outlined exactly once", rows().filter(r => r.classList.contains("poc")).length === 1 && Number(pocRow.dataset.tk) === LO + pocI);
  const segs = pocRow ? [...pocRow.querySelectorAll(".seg")].map(s => s.className.replace("seg ", "")) : [];
  ok("sell segments precede buy segments; prior-day faint then today solid", segs.join(",") === "ss,st,bs,bt", segs.join(","));
  ok("value-area rows are tinted", rows().filter(r => r.classList.contains("va")).length >= 3);
  ok("HVN and LVN ticks present", rows().some(r => r.classList.contains("hvn")) && rows().some(r => r.classList.contains("lvn")));

  // 5. hole banner from payload
  const hole = d.querySelector("#vp .vphole");
  ok("hole banner is drawn from the payload", hole && /hole 15:05→02:50 CT/.test(hole.textContent), hole && hole.textContent);
  const hdr = d.querySelector("#vp .vphdr");
  ok("header names the anchor and print count", hdr && /anchor Thu 08:30 CT/.test(hdr.textContent) && /5\.0k prints/.test(hdr.textContent), hdr && hdr.textContent);

  // 6. toggle
  d.dispatchEvent(new w.KeyboardEvent("keydown", { code: "KeyV", bubbles: true }));
  ok("v hides the panel", !d.body.classList.contains("vp-on") && d.getElementById("cols").style.left === "0px");
  d.dispatchEvent(new w.KeyboardEvent("keydown", { code: "KeyV", bubbles: true }));
  ok("v shows it again", d.body.classList.contains("vp-on") && rows().length > 5);

  // 7. growth without a bar
  profileN = 7000;
  await sleep(POLL());
  ok("a grown profile redraws without a new bar", /7\.0k prints/.test(d.querySelector("#vp .vphdr").textContent), d.querySelector("#vp .vphdr").textContent);

  if (errors.length) { console.error(`\nFAIL — ${errors.length}:`); errors.forEach(e => console.error("  " + e)); process.exit(1); }
  console.log("\nall checks clean");
  process.exit(0);
})();
