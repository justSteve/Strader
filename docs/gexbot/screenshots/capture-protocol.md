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
| ~3:45–3:55 PM | **net -vanna/charm** / gex orderflow / net convexity | The $800MM/$1000MM last-hour thresholds + EOD positioning read |
| Nightly (optional) | same as close, window widened 30min → full session | Freddy's nightly whole-day-shape practice |
| On-call | whatever is up | Doctrine in motion: convexity dump after a lift morning; spikes dwarfing the day's prior bars |

If the UI allows a fourth pane, run all four (convexity OF / gex OF / net
convexity / net -vanna-charm) all day and skip the close-time dropdown swap.

## Standing settings

- Ticker **SPX**, overlay **spot price** (not es future)
- Expiry **latest** (0DTE — matches doctrine default and the `z*` field family)
- **spot ON**, **combine OFF** (combine's function unknown — do not enable
  until its tooltip/meaning is recorded)
- Window **30min** intraday; full session for the nightly capture

## One-off: the mapping tour (pending)

Cycle the metric dropdown through all seven values — dex orderflow, gex
orderflow, convexity orderflow, net gex, net convexity, aggregate dex, net
-vanna/charm — one screenshot each, tooltip hover showing value + timestamp
where possible. Purpose: empirical pane↔field mapping against the archive at
the same second — net convexity vs `zcvr` (Phase 2 experiment #1), net gex vs
`zgr`, -vanna/charm vs `zvanna`/`zcharm`, flow panes vs `dexoflow`/`gexoflow`/
`cvroflow`.

## Baseline record — first capture, 2026-08-06 3:46:18 PM

Settings active: SPX, spot price; three panes all latest (08/06), spot ON,
combine OFF, 30min: **aggregate dex / net gex / net convexity**. Readable
content: net gex ≈ −$9,000MM band; net convexity's strongest positive spikes
of the window (+2,000 to +4,000 $MM) during the 3:40–3:45 spot slide
~7713 → ~7705 (vendor sell-off signature); levels drawn: long gamma 7710,
short gamma 7716, call 7720, put 7718, spot 7707. Stored in COO session
image cache; file to be moved here on next drop.
