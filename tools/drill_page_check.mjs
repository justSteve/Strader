/**
 * Behavioural check for the drill page's emissions surface. [st-b0n9, st-en7w]
 *
 * WHY THIS EXISTS, SEPARATELY FROM page_boot_check.mjs
 *   That one answers "does the page boot without throwing" — the class of
 *   defect that shipped a blank live footprint for a session (ea77d7a). This
 *   one answers "does the thing Steve asked for actually appear", which a
 *   clean boot does not establish: a render path that silently paints nothing
 *   boots perfectly.
 *
 *   The emissions row, the rollover panel and the tape markers are pure
 *   browser behaviour. No pytest reaches them. Without this, the only proof
 *   the panel works is somebody looking at it, and that proof expires the next
 *   time the template changes.
 *
 * WHAT IT ASSERTS
 *   An emitting bar paints chips; a quiet bar says "nothing on this bar"
 *   rather than looking broken (most bars are quiet — that is the common
 *   case, and the failure mode is it reading as an outage); the panel opens,
 *   tabulates, carries the "why" column and sits inside the control strip;
 *   a pin survives the tape advancing; and the tape marks EXACTLY the
 *   emitting columns in the rendered window.
 *
 * DEPENDENCY
 *   node + jsdom, same as page_boot_check.mjs and out-of-tree for the same
 *   reason (no declared JS runtime; the convention proposal is open with COO
 *   as st-lh3). See that file's header. Install and run:
 *
 *     cd <scratch> && bun add jsdom@24
 *     NODE_PATH=<scratch>/node_modules node tools/drill_page_check.mjs <page.html>
 *
 *   Needs a page WITH emissions — generate one first:
 *     .venv/bin/python scripts/orderflow_drill.py --date <day> --no-open --out <page.html>
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
  console.error("usage: node tools/drill_page_check.mjs <drill-page.html>");
  process.exit(2);
}

const errors = [];
const dom = new JSDOM(fs.readFileSync(file, "utf8"), {
  runScripts: "dangerously",
  url: "http://localhost/",   // file:// is an opaque origin to jsdom; localStorage throws there
  pretendToBeVisual: true,
  beforeParse(w) {
    w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    // The bridge is deliberately down: a desk page must render its own data
    // without one.
    w.fetch = () => Promise.reject(new Error("bridge down (by design in this check)"));
    w.addEventListener("error", e => errors.push(`uncaught: ${e.message}`));
  },
});

const w = dom.window, d = w.document;
function ok(name, cond, detail = "") {
  console.log(`${cond ? "  PASS" : "  FAIL"}  ${name}${detail ? " — " + detail : ""}`);
  if (!cond) errors.push(name);
}

setTimeout(() => {
  const bars = w.eval("typeof bars === 'undefined' ? null : bars");
  if (!bars || !bars.length) {
    console.error(`FAIL — page carries no bars; generate one via scripts/orderflow_drill.py`);
    process.exit(1);
  }
  const emitting = [], quiet = [];
  bars.forEach((b, i) => ((b.ev || []).length ? emitting : quiet).push(i));
  console.log(`${file}\npage: ${bars.length} bars, ${emitting.length} emitting, ${quiet.length} quiet`);
  if (!emitting.length) {
    console.error("FAIL — no bar on this page emitted anything; nothing to check");
    process.exit(1);
  }

  // the emissions row
  const target = emitting[Math.floor(emitting.length / 2)];
  w.eval(`seekTo(${target})`);
  const chips = d.querySelectorAll("#emrow .em-chip");
  ok("emitting bar paints chips", chips.length > 0,
     `bar ${target + 1}: ${chips.length} — "${chips[0]?.textContent.trim()}"`);
  ok("chips carry the stack's reason as tooltip",
     [...chips].some(c => (c.getAttribute("title") || "").length > 0));

  const q = quiet.find(i => i > 5);
  if (q != null) {
    w.eval(`seekTo(${q})`);
    ok("quiet bar reads as quiet, not broken", !!d.querySelector("#emrow .em-none"),
       `"${d.querySelector("#emrow .em-none")?.textContent}"`);
    ok("quiet bar paints no chips", d.querySelectorAll("#emrow .em-chip").length === 0);
  }

  // the rollover panel
  w.eval(`seekTo(${target}); openEmPanel(${target})`);
  const panel = d.getElementById("empanel");
  ok("rollover opens the panel", panel.style.display === "block");
  ok("panel tabulates the emissions", panel.querySelectorAll("tbody tr").length > 0,
     `${panel.querySelectorAll("tbody tr").length} row(s)`);
  ok("panel carries the 'why' column",
     [...panel.querySelectorAll("th")].some(t => /why/i.test(t.textContent)));
  ok("panel overlays the control strip", panel.closest(".controls") !== null);

  const finN = w.eval("FINAL.length");
  ok("end-of-session block renders when present",
     finN === 0 || /End of session/.test(panel.innerHTML), `FINAL=${finN}`);

  // a pin has to outlive the tape moving, or it is not a pin
  const after = quiet.find(i => i > target);
  if (after != null) {
    w.eval(`emPinned = true; seekTo(${after})`);
    ok("pinned panel survives a move to a quiet bar",
       d.getElementById("empanel").style.display === "block");
  }
  w.eval("emPinned = false; closeEmPanel()");
  ok("close hides it", d.getElementById("empanel").style.display === "none");

  // the tape markers
  w.eval(`seekTo(${target})`);
  const marks = d.querySelectorAll("#colstrip .evmark");
  const cols = d.querySelectorAll("#colstrip .col");
  const expected = [...cols].filter(c => (bars[+c.dataset.i].ev || []).length).length;
  ok("tape marks exactly the emitting columns", marks.length === expected,
     `${marks.length} marks / ${expected} emitting of ${cols.length} rendered`);
  ok("markers name their emissions on hover",
     [...marks].every(m => (m.getAttribute("title") || "").length > 0));

  if (errors.length) {
    console.error(`\nFAIL — ${errors.length}:`);
    errors.forEach(e => console.error("  " + e));
    process.exit(1);
  }
  console.log("\nall checks clean");
  process.exit(0);
}, 900);
