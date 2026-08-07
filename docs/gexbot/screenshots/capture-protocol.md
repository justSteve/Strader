# Orderflow view — screenshot capture protocol [st-ygy1]

Agreed with Steve 2026-08-06 (Phase 3 of Orderflow Mastery). Screenshots are
the *view-side* record: what the vendor rendered and what Steve read at the
moment the archive holds the numbers. Cumulative panes are reconstructable
from the archived API fields; the screenshots' unique value is (a) validating
the pane↔field mapping, (b) recording the level lines as drawn, (c) the
shared read-training loop between Steve and COO.

## Drop path

Steve saves to `C:\Users\steve\zgent-bridge\` (sanctioned dropbox). COO files
into this directory as `YYYY-MM-DD-<slug>.png` and reads them against the
archive each session.

## Schedule

| When | Panes (top → bottom) | Why |
|---|---|---|
| ~9:40–9:45 AM | convexity orderflow / gex orderflow / net convexity | Two-signal entry pair + regime tape; Freddy's morning scenario |
| ~3:45–3:55 PM | **net vanna** / gex orderflow / net convexity | The $800MM/$1000MM last-hour thresholds (stated for net -vanna) + EOD positioning read |
| Nightly (optional) | same as close, window widened 30min → full session | Freddy's nightly whole-day-shape practice |
| On-call | whatever is up | Doctrine in motion: convexity dump after a lift morning; spikes dwarfing the day's prior bars |

The view is fixed at three panes (confirmed 2026-08-06 — no add-pane
affordance), so the close capture is a one-dropdown swap of the top pane:
convexity orderflow → net vanna. Net charm is not routinely displayed; the
archived `zcharm` field covers it continuously, and on suspected extreme
days an on-call swap to net charm is the exception.

## Standing settings

- Ticker **SPX**, overlay **spot price** (not es future)
- Expiry **latest** (0DTE — matches doctrine default and the `z*` field family)
- **spot ON**, **combine OFF** (combine's function unknown — do not enable
  until its tooltip/meaning is recorded)
- Window **30min** intraday; full session for the nightly capture

## UI metric roster — observed 2026-08-06 (drift from docs noted)

The metric dropdown offers **eight** choices (screenshot
`2026-08-06-1554-spx-metric-dropdown-roster.png`): aggregate dex, net gex,
net convexity, **net vanna (β)**, **net charm (β)**, dex orderflow, gex
orderflow, convexity orderflow. Drift from the captured docs
(`../canonical/orderflow_view.md`): the docs describe a combined "Net
-Vanna/Charm" section; the UI splits it into two metrics, both beta-flagged —
matching the vendor's own "still learning best practices" caveat on that
layer. There is no "net gamma" metric; net gex is the gamma-family pane.

## One-off: the mapping tour (pending)

Cycle the metric dropdown through all eight values above — one screenshot
each, tooltip hover showing value + timestamp where possible (Snipping Tool
delay timer captures hover states; ClipMate cannot). Purpose: empirical pane↔field mapping against the archive at
the same second — net convexity vs `zcvr` (Phase 2 experiment #1), net gex vs
`zgr`, -vanna/charm vs `zvanna`/`zcharm`, flow panes vs `dexoflow`/`gexoflow`/
`cvroflow`.

## Tooltip anchors — pane↔field verification ledger

One row per tooltip capture; verified against the archive when the day's
harvest lands (`/mnt/z/Harvest/gexbot-hist/`).

| Anchor time (ET) | Pane metric | Tooltip values | Screenshot | Archive check |
|---|---|---|---|---|
| 2026-08-06 3:59:59 PM | aggregate dex | aggregate dex 449.20; agg call dex 265.15; agg put dex 184.05; spot 7709.64 | `2026-08-06-1559-spx-aggdex-tooltip-anchor.png` | **VERIFIED 2026-08-07** — archive snapshot 19:59:59 UTC exact: `agg_dex` 449.20, `agg_call_dex` 265.15, `agg_put_dex` 184.05, spot 7709.64. Pane ↔ field mapping closed. |
| 2026-08-06 8:55:41 AM **CT** (9:55:41 ET) | net vanna | net vanna 46.97; spot 7735.35 | `2026-08-06-fullday-spx-netvanna.jpg` | **VERIFIED 2026-08-07** — archive snapshot 13:55:41 UTC exact: `zvanna` 46.97, spot 7735.35 (`ovanna` 102.75 ≠, ruling out second expiry). Net vanna @ latest = `zvanna`; confirms `z*` ↔ "latest" family-wide. |

Remaining tour: net gex, net convexity (→`zcvr`, experiment #1), net charm,
dex orderflow, gex orderflow, convexity orderflow.

### First -vanna threshold observation (2026-08-06) — MEASURED, ambiguous

Initially pixel-read from `2026-08-06-fullday-spx-netvanna.jpg` as "plateau
holding above $800MM through the last hour, spot lifting into close —
consistent." **The measured `zvanna` series corrects that** (computed
2026-08-07 from the verified archive, last hour 3–4 PM ET, 2,678 snapshots):

- `zvanna` range −227 … +1,276, closing at +608 — it *collapsed* off the
  midday plateau (session max +1,703) during the last hour, dipping negative
  once
- above the $800MM threshold only **56%** of the hour; above $1,000MM 22%
- spot over the same hour: 7713.03 → 7711.38 (**−1.65, net flat**), with a
  mid-hour dip to ~7703 and recovery

Verdict: **ambiguous, not a hit.** Sign positive and magnitude intermittently
over threshold, but the prediction target (bullish passive flows into close)
reads net-flat at best. Lesson recorded: the doctrine claim needs an
operationalized hit/miss definition *before* tallying (what counts as
"relevant effects" — direction? magnitude? the mid-hour recovery?). That
definition is Phase 2 test #8's first deliverable. Tally: 0 hits, 0 misses,
1 ambiguous.

## UI color legend — from the Settings panel (2026-08-06 capture)

Settings panel (`2026-08-06-1559-spx-aggdex-tooltip-anchor.png`, right side)
decodes every line: **zero gamma** orange · **major positive/negative
history** green/red · **major call gamma** green · **major put gamma** red ·
**major long gamma** cyan · **major short gamma** purple · **net convexity**
blue · **aggregate DEX** cyan · **aggregate call DEX** green · **aggregate
put DEX** red · **net GEX** green. Also present: Show Tooltips toggle, Price
Transform (multiplier + offset — the index/ETF converter the State docs
mention), timezone New York (UTC−4).

## Baseline record — first capture, 2026-08-06 3:46:18 PM

Settings active: SPX, spot price; three panes all latest (08/06), spot ON,
combine OFF, 30min: **aggregate dex / net gex / net convexity**. Readable
content: net gex ≈ −$9,000MM band; net convexity's strongest positive spikes
of the window (+2,000 to +4,000 $MM) during the 3:40–3:45 spot slide
~7713 → ~7705 (vendor sell-off signature); levels drawn: long gamma 7710,
short gamma 7716, call 7720, put 7718, spot 7707. Saved as
`2026-08-06-1546-spx-aggdex-netgex-netconvexity.png` in this directory.
