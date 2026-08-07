/**
 * Behavioural check for the LIVE page's follow state. [st-ug3f]
 *
 * WHY THIS EXISTS, SEPARATELY FROM THE OTHER TWO CHECKS
 *   page_boot_check.mjs answers "does it boot"; drill_page_check.mjs answers
 *   "does the emissions surface paint". Neither runs the page against a moving
 *   tape, and the defect this covers only exists on one:
 *
 *   Steve, 2026-08-07: clicking a tape marker to read what a bar emitted froze
 *   the live chart for the rest of the session. The marker seeked, the seek
 *   landed behind a tip that keeps moving, following switched off, and the
 *   readout still said `live · N bars` — so a page that had stopped drawing was
 *   indistinguishable from a dead feed. Stepping forward could not recover it:
 *   the tip advances while you step, so idx never reaches bars.length-1 and
 *   follow never re-arms. Reload was the only way out.
 *
 *   That is a bug you can only see by feeding the page bars over time. This
 *   does exactly that, against a stubbed bridge.
 *
 * WHAT IT ASSERTS
 *   1. bars pushed by the bridge advance the display on their own (follow on);
 *   2. reading a marked bar does NOT stop that (the fix);
 *   3. a deliberate seek back DOES stop it, and SAYS SO in the readout;
 *   4. the readout offers a way back, and it works against a moving tip.
 *
 * DEPENDENCY
 *   node + jsdom, out-of-tree for the reason in page_boot_check.mjs's header.
 *
 *     cd <scratch> && bun add jsdom@24
 *     bash tools/nodecheck.sh tools/live_follow_check.mjs <live-page.html>
 *
 *   Needs a LIVE page (meta.source === "live"), i.e. one produced by
 *   scripts/live_footprint_page.py. It must open with an EMPTY tape — this
 *   check supplies the bars itself.
 *
 * EXIT
 *   0 = every check passed.  1 = at least one failed (all are printed).
 */
import fs from "fs";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");

const file = process.argv[2];
if (!file) {
  console.error("usage: node tools/live_follow_check.mjs <live-page.html>");
  process.exit(2);
}

// ── a synthetic tape ─────────────────────────────────────────────────────
// Key-for-key the shape live_footprint_feed.bar_payload sends. Synthetic on
// purpose: this check is about WHEN the page redraws, not what a bar looks
// like, and a self-contained tape means it runs without a corpus day on disk.
const TICK = 0.25;
function makeBar(i, withEv) {
  const px = 6400 + i * TICK;
  const t = new Date(Date.UTC(2026, 7, 7, 14, 30 + i, 0)).toISOString().replace("Z", "+00:00");
  return {
    t0: t, t1: t, o: px, h: px + TICK, l: px - TICK, c: px + TICK,
    v: 2000, d: (i % 2 ? -1 : 1) * (40 + i), nv: 0, dur: 30, poc: px,
    cells: [[px - TICK, 300, 400], [px, 500, 400], [px + TICK, 200, 200]],
    steps: [],
    ev: withEv ? [{ type: "SweepPrint", direction: "up", total_size: 900,
                    ticks_swept: 4, start_price: px, end_price: px + TICK,
                    reason: "synthetic emission for the follow check" }] : [],
  };
}
const TAPE = Array.from({ length: 40 }, (_, i) => makeBar(i, i === 5 || i === 12));
let served = 0;                       // how many bars the "feeder" has published
const publish = n => { served = Math.min(TAPE.length, served + n); };

const errors = [];
const dom = new JSDOM(fs.readFileSync(file, "utf8"), {
  runScripts: "dangerously",
  url: "http://localhost/",
  pretendToBeVisual: true,
  beforeParse(w) {
    w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    w.addEventListener("error", e => errors.push(`uncaught: ${e.message}`));
    // Stubbed bridge. /bars honours `since` as a COUNT, like the real one.
    w.fetch = (url, opts) => {
      const u = String(url);
      const json = body => Promise.resolve({ json: () => Promise.resolve(body) });
      if (u.includes("/health")) return json({ ok: true });
      if (u.includes("/commands")) return json({ commands: [], last: 0 });
      if (u.includes("/state")) return json({ ok: true });
      if (u.includes("/bars")) {
        const since = Number(new URL(u).searchParams.get("since") || 0);
        return json({ bars: TAPE.slice(since, served), meta: { bar_n: 2000, day: "2026-08-07" },
                      final: [], developing: null });
      }
      return Promise.reject(new Error("unstubbed: " + u));
    };
  },
});

const w = dom.window, d = w.document;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const POLL = 2200;   // the page polls every 2000ms; wait past one full cycle
function ok(name, cond, detail = "") {
  console.log(`${cond ? "  PASS" : "  FAIL"}  ${name}${detail ? " — " + detail : ""}`);
  if (!cond) errors.push(name);
}
const idx = () => w.eval("idx");
const held = () => w.eval("bars.length");
const following = () => w.eval("liveFollow");
const dotText = () => d.getElementById("bridge-dot").textContent;

(async () => {
  await sleep(600);
  if (!w.eval("LIVE")) {
    console.error("FAIL — this is not a LIVE page; generate one with scripts/live_footprint_page.py");
    process.exit(1);
  }
  ok("page opens with an empty tape", held() === 0, `${held()} bars`);

  // 1. following: bars pushed by the bridge draw themselves
  publish(8);
  await sleep(POLL);
  ok("bars arriving from the bridge advance the display",
     held() === 8 && idx() === 7, `idx ${idx()} of ${held()}`);

  // 2. THE FIX: reading a marked bar must not stop the tape
  const mark = d.querySelector(`#colstrip .col[data-i="5"] .evmark`);
  ok("an emitting bar carries a tape marker", !!mark);
  if (mark) {
    mark.onclick();
    ok("reading a marked bar opens its panel",
       d.getElementById("empanel").style.display === "block");
    ok("the panel names the bar it is reading, not the current one",
       /Bar 6\b/.test(d.getElementById("empanel").innerHTML),
       d.getElementById("empanel").querySelector("h4")?.textContent.trim());
    ok("reading a marked bar does NOT stop following", following() === true);
  }
  publish(6);
  await sleep(POLL);
  ok("the tape keeps advancing after a marker was read",
     held() === 14 && idx() === 13, `idx ${idx()} of ${held()}`);
  ok("the pinned panel still shows the bar that was read, not the newest",
     /Bar 6\b/.test(d.getElementById("empanel").innerHTML));

  // 3. a deliberate seek back stops following — and has to SAY so
  w.eval("seekTo(4)");
  ok("seeking back turns following off", following() === false);
  ok("the readout says it is holding, not that it is live",
     /holding at bar 5 of 14/.test(dotText()), JSON.stringify(dotText()));
  publish(6);
  await sleep(POLL);
  ok("held page does not advance", idx() === 4, `idx ${idx()}`);
  ok("but it still reports the tape growing behind it",
     /of 20/.test(dotText()), JSON.stringify(dotText()));

  // 4. the way back has to work against a MOVING tip — this is the part
  //    stepping forward by hand cannot do.
  d.getElementById("bridge-dot").onclick();
  ok("click-to-follow re-arms following", following() === true);
  ok("click-to-follow lands on the newest bar", idx() === held() - 1,
     `idx ${idx()} of ${held()}`);
  publish(8);
  await sleep(POLL);
  ok("and the tape draws itself again", held() === 28 && idx() === 27,
     `idx ${idx()} of ${held()}`);
  ok("readout is back to the live count", /^live · 28 bars$/.test(dotText()),
     JSON.stringify(dotText()));

  if (errors.length) {
    console.error(`\nFAIL — ${errors.length}:`);
    errors.forEach(e => console.error("  " + e));
    process.exit(1);
  }
  console.log("\nall checks clean");
  process.exit(0);
})();
