# DaysActivity - 2026-05-19

## 13:06 - Session Handoff [TV Capture Tool Debug + ORB Walkthrough]

**Summary**: Dry ORB walkthrough completed. TV capture tool deployed to Windows but failed to produce screenshots during entire morning session (8:30–11:30 CT). Root cause: window title matching was brittle — matched File Explorer instead of TradingView app, then matched nothing after Explorer closed. Rewrote capture tool to use process-based detection (`tradingview.exe`). TradingView then reported plan limits exceeded (expired credit card), ending the session.

**Open Work**:
- st-lh3: bun convention (COO-routed, not actionable here)
- TV capture tool rewritten and deployed — needs restart after TV subscription is restored
- Schwab quote reader has import error (`schwab.auth` not found) — discovered during session, not fixed
- 5-minute cron loop was set up and cancelled — restart when screenshots are flowing

**Tried**:
- Window title matching (`"TradingView"` fragment) → matched File Explorer folder path instead of TV app
- Closed Explorer, retried → TV Desktop window title doesn't contain "TradingView" at all, nothing matched
- Explorer exclusion filter → still no match because TV title has no "TradingView" string
- Process-based detection (`tradingview.exe`) → deployed but TV closed due to expired CC before testing
- Monitor-based capture (no window detection) → Steve rejected, can't guarantee TV is on a specific monitor

**Files Changed**:
tools/tv_capture/tv_capture.py
mancini/archive/2026-05-19/session_commentary.md

---

## 07:05 - Session Handoff [Mancini Pipeline — Cleanup, Archive, Replay, Post-Mortem]

**Summary**: Closed st-w9l (Mancini Pine renderer). Cleaned getting-started scaffolding from mancini/, built archive structure, pulled May 19 email from Gmail, ran full pipeline (60 levels extracted). Added replay renderer (trade recap slides), post-mortem renderer (prior forecast vs actual action slides with level scorecard), and restored compositor/gallery from git for PNG slide generation. Aligned capture tool filename convention with parser (`ES_YYYYMMDD_HHMM.png`).

**Open Work**:
- st-6mo: Mancini daily workflow — cleanup, archive, post-mortem + forecast pipeline (in progress, not yet committed)
- st-lh3: bun convention (COO-routed, not actionable here)
- TV capture tool (`tools/tv_capture/`) still not deployed to Windows — no screencaps available for PNG slide compositing
- PNG slide deck cannot be generated until capture pipeline is running

**Key Decisions**:
- Archive structure: `mancini/archive/<date>/` holds raw email, parsed JSON, Pine indicator, replay, post-mortem, and slides
- Compositor + gallery restored from git commit 07490cf after premature deletion
- Capture filename convention aligned: `ES_YYYYMMDD_HHMM.png` (was `tv_YYYYMMDD_HHMMSS.png`)
- Original PNG slide requirements retrieved from claude-monitor conversation log (87102730, May 16 session)

**Files Changed**:
mancini/codegen.py
mancini/parser.py
mancini/compositor.py
mancini/gallery.py
mancini/replay.py
mancini/post_mortem.py
mancini/archive/2026-05-18/forecast_2026-05-18.json
mancini/archive/2026-05-18/forecast_2026-05-18.pine
mancini/archive/2026-05-19/email_2026-05-19_raw.txt
mancini/archive/2026-05-19/forecast_2026-05-19.json
mancini/archive/2026-05-19/forecast_2026-05-19.pine
mancini/archive/2026-05-19/forecast_tuesday.md
mancini/archive/2026-05-19/post_mortem.md
mancini/archive/2026-05-19/post_mortem_2026-05-19.md
mancini/archive/2026-05-19/replay_2026-05-19.md
tools/tv_capture/tv_capture.py

---
