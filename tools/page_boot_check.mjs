/**
 * Boot a desk page in a headless DOM and fail on the first uncaught error.
 * [st-b0n9]
 *
 * WHY THIS EXISTS
 *   On 2026-08-04 the live footprint page rendered blank for a full session.
 *   Three separate defects fired in sequence at page init, all of them live-
 *   only: fields a replay always populates and a live payload does not. The
 *   headless data-path proof passed the whole time — it covered the DATA path,
 *   not the BOOT path. Bars in, bars out, byte-identical, and three crashes
 *   upstream of any of that.
 *
 *   Nothing in the repo executed the page. This does. It is the cheapest
 *   possible version of "somebody opened it": parse the HTML, run the scripts,
 *   collect anything that throws.
 *
 * WHAT IT CATCHES
 *   Exactly the class that bit us — an unguarded field access during init that
 *   kills the rest of the boot script. A page that boots clean here can still
 *   look wrong; a page that fails here is definitely broken.
 *
 * DEPENDENCY, DELIBERATELY NOT VENDORED
 *   Needs node + jsdom. jsdom does not run under bun (its vm rejects a Proxy
 *   in the global prototype chain) and jsdom >= 25 needs a newer node than the
 *   nvm default here, so: node 20 + jsdom@24. This repo declares no JS runtime
 *   and the convention proposal for one is still open with COO (st-lh3), so
 *   the install stays out-of-tree rather than adding an undeclared dependency:
 *
 *     cd <scratch> && bun add jsdom@24
 *     NODE_PATH=<scratch>/node_modules node tools/page_boot_check.mjs <page.html>
 *
 * USAGE
 *   node tools/page_boot_check.mjs /tmp/desk-live-footprint.html
 *   node tools/page_boot_check.mjs page.html --expect-empty   # zero-bar page
 *
 * EXIT
 *   0 = booted clean.  1 = something threw (the messages are printed).
 */
import fs from "fs";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");

const file = process.argv[2];
if (!file) {
  console.error("usage: node tools/page_boot_check.mjs <page.html> [--expect-empty]");
  process.exit(2);
}
const expectEmpty = process.argv.includes("--expect-empty");

const errors = [];
const dom = new JSDOM(fs.readFileSync(file, "utf8"), {
  runScripts: "dangerously",
  // A real origin: file:// is an opaque origin to jsdom and localStorage
  // throws there. Chrome allows it from file://, so that failure would be a
  // harness artifact, not a page defect.
  url: "http://localhost/",
  pretendToBeVisual: true,
  beforeParse(w) {
    // jsdom gaps, not page bugs — Chrome has both.
    w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    // The bridge is deliberately DOWN. A desk page must boot without it: the
    // launcher starts bridge and page together and losing that race must not
    // leave a dead page (that was defect #3 in ea77d7a).
    w.fetch = () => Promise.reject(new Error("bridge down (by design in this check)"));
    w.addEventListener("error", (e) => errors.push(`uncaught: ${e.message}`));
  },
});

const w = dom.window;
const d = w.document;

setTimeout(() => {
  // Boot is not enough — the page must also survive being DRIVEN. Walking the
  // tape exercises every per-bar render path, which is where sparse fields bite.
  try {
    const n = w.eval("typeof bars === 'undefined' ? -1 : bars.length");
    if (n > 0) {
      w.eval("seekTo(0); while (idx < bars.length - 1) step();");
      w.eval("seekTo(0)");
    }
    const meta = (d.getElementById("meta")?.textContent || "").trim();
    console.log(`booted: ${file}`);
    console.log(`  bars   : ${n < 0 ? "no bars binding" : n}`);
    console.log(`  meta   : ${meta || "(empty)"}`);
    if (expectEmpty && n > 0) {
      errors.push(`--expect-empty but the page carries ${n} bars`);
    }
  } catch (e) {
    errors.push(`driving the page threw: ${e.message}`);
  }

  if (errors.length) {
    console.error(`\nFAIL — ${errors.length} error(s):`);
    for (const e of errors) console.error("  " + e);
    process.exit(1);
  }
  console.log("  status : clean");
  process.exit(0);
}, 900);
