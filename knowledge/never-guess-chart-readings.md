---
type: rule
title: "Never Guess Chart Readings"
description: "MANDATORY procedure for reading chart screenshots — crop regions at full resolution before quoting any number"
timestamp: 2026-05-21T11:20:10-05:00
metadata:
  originSessionId: 039a17ab-32e5-43ab-b749-821b26733e60
  graduated_from: feedback_never_guess_chart_readings.md
  source_type: feedback
---

## Hard Procedure: Reading Chart Screenshots

Full-resolution TV screenshots (1920x1080) are scaled down when displayed. Text on price axes, indicator labels, and headers becomes unreadable at display scale. NEVER quote a number from a scaled-down view.

**Before quoting ANY price, level, or indicator value from a screenshot:**

1. Crop the **price axis** (rightmost ~120px) and save to /tmp
2. Crop the **chart header** (top ~80px, first 600px wide) and save to /tmp
3. Crop any **indicator label regions** relevant to the question
4. Read the cropped images — these render at full resolution
5. Only then quote numbers

**Why:** On 2026-05-21, Strader called ES at 7,450 when it was 7,418. The 7,450 came from Mancini's forecast text, not the chart — Strader carried forward a stale expected price and presented it as a live reading. Then fabricated ORB levels by misidentifying Mancini indicator lines as ORB zones. Steve caught every error.

**Additional rules:**
- Never carry forward a price from forecast text or prior analysis into a chart reading. Read the chart independently.
- Never conflate one indicator's visual elements with another's. If unsure which lines belong to which indicator, say so.
- The ORB is cash-session only (8:30 AM CT) and takes 30-60 min to define. Don't read ORB levels before the window closes.
- Don't ask the user for data you can get yourself (`ls` the captures directory, crop the image, etc.).
