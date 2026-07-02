# DaysActivity - 2026-05-21

## 11:10 - Session Handoff [Mancini Ritual + TV Capture Fix]

**Summary**: Ran daily Mancini email pipeline (66 levels, Pine script, post-mortem with slides), fixed parser time anchor regex to catch Mancini's informal time formats, and rewrote tv_capture.py to use Win+6 taskbar hotkey instead of unreliable SetForegroundWindow for chart screenshots.

**Open Work**:
- st-oit: `_try_quote()` 400s on /ES futures — use `get_quotes()` not `get_quote()`
- st-8cx: Rename local `schwab/` to fix package-name shadow (blocking quote reader — hit it this session)
- st-lh3: bun convention (COO-routed)

**Tried**:
- PrintWindow API for capturing occluded TV window → abandoned; Chromium GPU rendering means PrintWindow returns black/stale frames for Electron apps
- SetForegroundWindow with Alt-key trick → this is what was failing; Windows focus-stealing prevention blocks background processes. Root cause of Discord screenshots in capture output
- Win+N taskbar hotkey → confirmed working (Win+6 brings TV forward). Shell-level hotkey bypasses focus-stealing prevention entirely. Chosen approach.

**Critical Feedback Logged**: Fabricated chart readings (called ES at 7450 when it was 7418, invented ORB levels from Mancini indicator lines). Memory saved: never guess price/indicator values — crop and verify at full resolution or say "can't read."

**Files Changed**:
mancini/parser.py
tools/tv_capture/tv_capture.py
mancini/archive/2026-05-21/email_2026-05-21_raw.txt
mancini/archive/2026-05-21/forecast_2026-05-21.json
mancini/archive/2026-05-21/forecast_2026-05-21.pine
mancini/archive/2026-05-21/post_mortem_2026-05-21.md
mancini/archive/2026-05-21/slides/

---
