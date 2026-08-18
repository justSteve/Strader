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
  // The panel is an absolute overlay, so what decides whether it can cover
  // whole rows is its CONTAINING BLOCK. Anchored to the control strip alone it
  // ended mid-way through the readouts and cut the text. The invariant that
  // has to hold: the rows it overlays are inside the same positioned ancestor.
  // Since st-fgno that ancestor is the floating frame (#livehud), which
  // buildHud fills by MOVING the header, readouts, controls, row and panel.
  const block = panel.closest("#livehud");
  ok("panel is anchored to the floating frame", block !== null);
  ok("the readouts row is inside that frame — so the panel can cover it whole",
     !!block && block.contains(d.querySelector(".readouts")));
  ok("the emissions row is inside it too",
     !!block && block.contains(d.getElementById("emrow")));

  // Rollover flicker [st-9olq]. The panel opens UNDER the pointer, so the row
  // gets mouseleave the moment it appears; the old close-on-leave tore the
  // panel down 120 ms later, the pointer was back on the chip, mouseenter
  // re-opened it — a flicker for as long as you held still. The pair must stay
  // open while the pointer is on either half and close once it has left both.
  w.eval(`emPinned = false; emPinnedIdx = null; closeEmPanel(); seekTo(${target})`);
  const chip0 = d.querySelector("#emrow .em-chip");
  const emrow = d.getElementById("emrow");
  const fire = (el, type) => el.dispatchEvent(new w.MouseEvent(type, { bubbles: false }));
  fire(chip0, "mouseenter");                       // hover the chip → panel opens
  const openedOnHover = panel.style.display === "block";
  fire(emrow, "mouseleave");                       // the panel now covers the row
  fire(panel, "mouseenter");                       // …and the pointer is on the panel
  setTimeout(() => {
    ok("hovering a chip opens the panel", openedOnHover);
    ok("panel stays open once it has covered the row (no flicker)",
       panel.style.display === "block");
    fire(panel, "mouseleave");                     // pointer leaves the pair
    setTimeout(() => {
      ok("leaving the pair closes it", panel.style.display === "none");
      part2();
    }, 250);
  }, 250);
}, 900);

function part2() {
  const bars = w.eval("bars");
  const emitting = [], quiet = [];
  bars.forEach((b, i) => ((b.ev || []).length ? emitting : quiet).push(i));
  const target = emitting[Math.floor(emitting.length / 2)];
  const panel = d.getElementById("empanel");

  // The level picker [st-9olq]: one dropdown, session levels at the top level,
  // Mancini's letter as an <optgroup> under them; picking arms and jumps, and
  // the select snaps back to its label.
  const pick = d.getElementById("lvlpick");
  ok("level picker is one <select>", !!pick && pick.tagName === "SELECT"
     && d.querySelectorAll("#chips button, #chips select").length === 1);
  if (pick) {
    const top = [...pick.children].filter(c => c.tagName === "OPTION" && c.value);
    const grp = pick.querySelector("optgroup");
    ok("session levels sit at the top level", top.length > 0,
       top.map(o => o.textContent).join(" | "));
    ok("Mancini levels are the second layer (optgroup)",
       !grp || (/mancini/i.test(grp.label) && grp.querySelectorAll("option").length > 0),
       grp ? `${grp.querySelectorAll("option").length} M: level(s)` : "no Mancini levels on this page");
    const first = top[0] || (grp && grp.querySelector("option"));
    if (first) {
      pick.value = first.value; pick.dispatchEvent(new w.Event("change"));
      ok("picking arms the level", w.eval("level") != null && Math.abs(w.eval("level") - +first.value) < 0.01,
         `armed ${w.eval("level")} from "${first.textContent}"`);
      ok("picker snaps back to its label", pick.value === "");
    }
  }

  // Confidence: an invalidated setup is scored 0.0, meaning not-applicable.
  // Printing "0.00" invites reading it as a measurement. [st-emy5]
  const invalidated = bars.findIndex(b =>
    (b.ev || []).some(e => e.type === "SetupRecognition" && e.state === "invalidated"));
  if (invalidated >= 0) {
    w.eval(`seekTo(${invalidated}); openEmPanel(${invalidated})`);
    const cells = [...d.querySelectorAll("#empanel tbody tr")]
      .filter(r => /invalidated/.test(r.textContent)).map(r => r.cells[2].textContent.trim());
    ok("invalidated setup shows no confidence number", !cells.includes("0.00"),
       JSON.stringify(cells));
  }
  const scoredAt = bars.findIndex(b =>
    (b.ev || []).some(e => e.type === "SetupRecognition" && e.state === "forming"));
  if (scoredAt >= 0) {
    w.eval(`seekTo(${scoredAt}); openEmPanel(${scoredAt})`);
    const cells = [...d.querySelectorAll("#empanel tbody tr")]
      .filter(r => /forming/.test(r.textContent)).map(r => r.cells[2].textContent.trim());
    ok("a scored emission still prints its confidence",
       cells.some(s => /^\d\.\d\d$/.test(s)), JSON.stringify(cells));
  }

  // "stages", never "beats" — the four-part sequence collides with the musical
  // sense. Read RENDERED text only: the embedded DATA blob legitimately carries
  // a field named `beats`, and body.textContent would sweep the <script> in.
  const walker = d.createTreeWalker(d.body, w.NodeFilter.SHOW_TEXT);
  const banned = [];
  for (let n; (n = walker.nextNode()); ) {
    const tag = n.parentElement?.tagName;
    if (tag === "SCRIPT" || tag === "STYLE") continue;
    if (/\bbeats?\b/i.test(n.textContent)) banned.push(n.textContent.trim().slice(0, 80));
  }
  ok("no 'beats' in rendered text — the sequence is STAGES", banned.length === 0,
     banned.length ? JSON.stringify(banned.slice(0, 3)) : "");

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

  // ── closing churn [st-hnl7] ────────────────────────────────────────────
  // From 14:50 CT the tape is settlement flow, not auction: a sweep there
  // renders identically to a 09:45 sweep and means nothing like the same
  // thing. The page has to SAY that. Suppressing the emissions would be a
  // lie about the record, so the assertion is that they are demoted and
  // captioned — still present, visibly discounted. Both directions matter:
  // an unconditional banner would be exactly as useless as none.
  const minCT = b => { const m = /T(\d{2}):(\d{2})/.exec(b.t0 || ""); return m ? +m[1] * 60 + +m[2] : null; };
  const churnBar = emitting.find(i => (minCT(bars[i]) ?? 0) >= 14 * 60 + 50);
  const dayBar = emitting.find(i => { const m = minCT(bars[i]); return m != null && m < 14 * 60 + 50; });
  if (churnBar != null) {
    w.eval(`seekTo(${churnBar}); openEmPanel(${churnBar})`);
    const p = d.getElementById("empanel");
    ok("closing-churn bar is captioned in the panel", !!p.querySelector(".em-churn"),
       `bar ${churnBar + 1} @ ${bars[churnBar].t0.slice(11, 16)} CT`);
    ok("its emissions are still listed, not suppressed",
       p.querySelectorAll("tbody tr").length > 0,
       `${p.querySelectorAll("tbody tr").length} row(s)`);
    ok("its chips are demoted", d.querySelectorAll("#emrow .em-chip.churn").length > 0);
    ok("its tape mark is demoted", !!d.querySelector("#colstrip .evmark.churn"));
  } else {
    console.log("  SKIP  closing churn — this page has no emitting bar after 14:50 CT");
  }
  if (dayBar != null) {
    w.eval(`seekTo(${dayBar}); openEmPanel(${dayBar})`);
    ok("a mid-session bar is NOT captioned as churn",
       !d.getElementById("empanel").querySelector(".em-churn"),
       `bar ${dayBar + 1} @ ${bars[dayBar].t0.slice(11, 16)} CT`);
    ok("mid-session chips are not demoted",
       d.querySelectorAll("#emrow .em-chip.churn").length === 0);
  }
  w.eval("emPinned = false; closeEmPanel()");

  if (errors.length) {
    console.error(`\nFAIL — ${errors.length}:`);
    errors.forEach(e => console.error("  " + e));
    process.exit(1);
  }
  console.log("\nall checks clean");
  process.exit(0);
}
