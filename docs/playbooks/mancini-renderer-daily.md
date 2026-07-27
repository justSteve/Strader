# Mancini Forecast — Daily Routine & Verification [st-5rc]

## Morning (4 actions, no Pine Editor)
The parse chain pushes the day's payload to the Windows clipboard automatically.
1. Double-click the **Mancini Forecast** indicator title on the /ES chart.
2. Click into the **Daily payload (v1)** field.
3. Ctrl+A, Ctrl+V.
4. OK.

## Reading the chart
- Solid = major, dashed = minor; teal = support, red = resistance.
- `K` = narrative-cited key level (always visible if the toggle is on). `◆` = profile-confluent.
- `+n` = n held closes (defenses). `✕` = broken (restyled to the other side's color, dashed). `↺` = reclaimed — the Failed Breakdown pattern rendered in place.
- HUD (default top-left): nearest level above/below, distance, tier, state.
- **Red top banner** = the payload date is not today (or no payload). Repaste before trusting anything.

## If the indicator is lost (reinstall)
Pine Editor → paste `pine/mancini_forecast.pine` from the repo → Save → Add to chart.
The repo file is the source of record; if you hotfix in the editor, sync it back.

## Manual verification protocol (run once per renderer change; live or replayed day)
- [ ] Paste today's payload → levels render; count matches the payload's S/R lines.
- [ ] Touch: watch (or bar-replay) price into a level ± tolerance → state moves untouched→held; `+n` increments on defended closes.
- [ ] Break: a CLOSE beyond a level by > tolerance → dashed restyle + `✕` (wick through must NOT trigger it).
- [ ] Reclaim: close back on the original side after a break → `↺` highlight.
- [ ] Zone: a `price2` line renders as a shaded band; touch uses near edge, break uses far edge.
- [ ] HUD shows the true nearest above/below with correct distances.
- [ ] Staleness: paste yesterday's payload deliberately → red banner; repaste today's → banner clears.
- [ ] Ceiling: paste `ceiling_probe` payloads (2/4/8/16 KB) → find the text_area limit; record it here: **limit = ___ KB**. If < 4 KB, engage the A/B split fallback (spec).
- [ ] Parity (migration week): per-day script + stable renderer on the same chart show identical level sets.
