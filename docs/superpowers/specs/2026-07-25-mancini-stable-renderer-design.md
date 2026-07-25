# Mancini Stable Renderer — Design

**Bead:** st-3c4 (Stable Renderer Design) · **Date:** 2026-07-25 · **Status:** approved by Steve 2026-07-25

## Problem

The Mancini pipeline emits a brand-new Pine script every day (`runbook/mancini/charts/<date>.pine`, date in the indicator title, levels baked in as code). A new script per day forces a daily trip through TradingView's Pine Editor — open editor, find script, select-all, paste, save — the most keystroke-expensive, most mis-navigable flow in the morning routine. The display logic (~radius activation, tier styling, touch filters) is identical every day; only the levels change.

## Architecture: ship data, not code

Split the daily artifact in two:

1. **Stable renderer** — ONE permanent Pine v6 script, "Mancini Forecast", installed in the /ES chart layout once and never edited again. All display/state logic lives here. The day's levels arrive through a single `input.text_area` field.
2. **Daily payload** — a compact, human-readable text block emitted by the morning chain and pushed to the Windows clipboard via `clip.exe` (WSL-side, zero keystrokes).

Steve's daily interaction: double-click the indicator → click the field → Ctrl+A, Ctrl+V → OK. Four actions, no Pine Editor.

This supersedes per-day script emission (parallel-run during migration, then retired). It also instantiates the post-Clipmate clipboard doctrine: shrink the payload → stabilize the destination → only then automate residual navigation (no AHK in v1; revisit only if the 4-action residue annoys after the trial week).

## Payload format v1

Multi-line text, line-based, eyeballable:

```
v1 2026-07-27 ES
S 7447 7450 major conf
R 7506 . major key "bear case triggers below"
S 7412 . minor
P poc 7461
P vah 7472
P val 7438
P lvn 7433
```

- **Header line:** `v1 <date> <symbol>`. The renderer's staleness guard reads `<date>`.
- **Level lines:** `S|R <price> <price2|.> <major|minor> [key] [conf] ["note"]`
  - `price2` present ⇒ zone (shaded band); `.` ⇒ single line.
  - `key` = narrative-cited level (parser-tagged from bull/bear cases).
  - `conf` = confluent with a measured profile level within `CONFLUENCE_TOLERANCE_PTS` (2.0), computed Python-side.
  - `"note"` = short narrative fragment, key levels only.
- **Profile lines:** `P poc|vah|val|lvn <price>` — the measured family from `market/orderflow/profile.py` (prior-RTH-session window), our pipeline, not TradingView's.
- Zone pairing is reconstructed emitter-side by grouping extractor levels on shared `source_quote` (the extractor already expands "7640-45" into both edges; no parser change).
- Size: ~2 KB for a 60-level day.
- **Known risk:** Pine `input.text_area` length ceiling is unverified. First implementation task validates it with a synthetic max-size payload; fallback is two text-area inputs (`payload A/B`, concatenated), format unchanged.

## Renderer v1 features

Carried over unchanged: radius activation (+SMA smoothing), visible-range filter, touched-today hiding, tier show/hide, label toggles, extend/history inputs.

New (feature-tour cards in parentheses):

- **(A) Level states.** Per level: `untouched → tested/held → broken → reclaimed`.
  - *touch* = a bar trades within touch tolerance (existing input).
  - *held* = touched, and the bar **closes** on the correct side. Tick marks at each defense.
  - *broken* = bar **close** beyond the level by > tolerance (close, not wick — wicks are flush noise). Broken support restyles to dashed resistance styling (color swap).
  - *reclaimed* = after a break, a close back on the original side — highlighted (this is the failed-breakdown pattern rendered in place).
- **(B) Zones.** `price2` levels render as shaded bands with edge lines; state logic uses the far edge for break, near edge for touch.
- **(C) Proximity HUD.** Corner table: nearest level above and below with distance in points, tier, and state word. Serves the /ES tab's job as Steve's situational map (his answer: role (a)).
- **(D) Staleness guard.** If payload date ≠ chart session date: loud red banner "LEVELS FROM <date> — STALE". Kills the silent-stale failure mode of a manual paste step.
- **(E) Confluence ticks.** `conf` levels render double-stroke + ◆ marker. Confluence computed in Python against the prior session's measured profile; display-only on chart.
- **(G) Narrative notes.** `"note"` text on key levels as tooltip (hover) with an input toggle for always-visible compact labels.

**Placement conventions (Steve, 2026-07-25):** all level labels and the HUD sit **chart-left** (price axis owns the right edge). HUD default top-left, position selectable via input.

## Volume Profile placement (decided)

- **No VP indicator on the /ES tab** — it already carries 3 LuxAlgo overlays + this renderer.
- Distilled profile **levels** (POC/VAH/VAL/LVNs) ride this renderer's `P` family.
- The full histogram **shape** belongs on the FootPrint chart (execution/orderflow surface) via TradingView's built-in Session Volume Profile, at Steve's discretion.

## Daily flow

1. Morning chain (existing cron): letter fetch → parse → `corpus_daily` lands yesterday's tape.
2. New step: payload emitter builds the block (Mancini levels + zone pairing + key/conf flags + notes + prior-session profile levels) and pushes it to the Windows clipboard (`clip.exe`).
3. Steve pastes into the indicator settings (4 actions).
4. Renderer date-check guards a forgotten paste with the STALE banner.

## Migration

Per-day script emission runs **in parallel for one trading week** — the old flow stays available every morning. After a clean week, per-day emission retires (emitter keeps writing the payload only).

## Explicitly out of scope

- **Alerts** — deliberately excluded from v1; owned by **Alerting Architecture Brainstorm** (st-gip): LuxAlgo alerting vs TV-native `alert()`, separate session.
- Opening range / session shading (card H) — v2 candidate after the v1 has lived a week.
- AutoHotkey layer — only if the 4-action residue proves annoying.
- LuxAlgo integration beyond visual coexistence — Pine cannot read other indicators' internals.
- Any change to level *extraction* — the deterministic listlevels parser is untouched.

## Testing

- **Emitter (Python, pytest):** payload golden test from a real ParseResult fixture (zone pairing, key/conf flags, note escaping, header date); confluence-flag unit test at the 2.0-pt tolerance boundary; clipboard push smoke-tested via injected command (no `clip.exe` in CI).
- **Renderer (Pine, manual protocol):** a documented checklist against a replayed day on the chart — state transitions (touch/hold/break/reclaim on known bars), zone rendering, HUD contents, staleness banner (paste yesterday's payload deliberately), max-size payload.
- **Parity during migration week:** per-day script and stable renderer on the same chart must show identical level sets; any divergence is an emitter bug.

## Components

| Unit | Responsibility |
|---|---|
| `runbook/mancini/payload_emitter.py` (new) | ParseResult + profile levels → payload text; zone pairing; flags; notes |
| `runbook/mancini/run.py` (modify) | chain step: emit payload → `clip.exe`; parallel-run per-day pine during migration |
| `pine/mancini_forecast.pine` (new, tracked) | the stable renderer source of record (installed manually once; updated rarely, deliberately) |
| `docs/playbooks/mancini-renderer-daily.md` (new) | the 4-action morning routine + STALE banner meaning + reinstall procedure |
