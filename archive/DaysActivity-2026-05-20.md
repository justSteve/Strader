# DaysActivity - 2026-05-20

## 14:45 - Session Handoff [Mancini Pipeline, TV Capture, GEXBot Research]

**Summary**: Processed Mancini's May 20 forecast (61 levels, Pine script generated). Fixed and validated the TV screenshot capture tool — process-based detection, Ctrl+Shift+B hotkey, grace period with notification. Removed dead TradingView MCP config. Researched GEXBot as GEX data provider — vanna/charm framework directly supports butterfly thesis. First live EOD exercise: Strader guessed 7,450 (range top magnet), Steve read 7,405 via PAC order block.

**Open Work**:
- st-lh3 (COO-routed, not actionable here)
- st-8cx: Rename local schwab/ wrapper to fix package-name shadow of schwab-py
- Schwab quote reader import error (`schwab.auth`) — unfixed, blocked by st-8cx
- GEXBot evaluation: State tier ($150/mo) identified as the play — vanna/charm ladders for butterfly timing. No subscription yet.
- TV capture running on Windows — validated but needs multi-session soak test

**Decisions**:
- TradingView MCP removed permanently (.mcp.json deleted). Screenshots are the sole chart interface going forward.
- PAC order blocks identified as Steve's primary butterfly strike centering tool (over Mancini levels alone).
- TV capture hotkey settled at Ctrl+Shift+B after Ctrl+Shift+S (Clipmate conflict) and Ctrl+Shift+C (console SIGINT).

**Files Changed**:
tools/tv_capture/tv_capture.py
mancini/archive/2026-05-20/email_2026-05-20_raw.txt
mancini/archive/2026-05-20/forecast_2026-05-20.json
mancini/archive/2026-05-20/forecast_2026-05-20.pine
.mcp.json (deleted)

---
