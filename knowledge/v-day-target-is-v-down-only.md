---
type: playbook
title: "V-Day Target Is v_down Only"
description: "For st-r2o V-day detection, Steve's actual butterfly-strategy target is v_down only; v_up (inverted-V) is diagnostic, not a trade setup"
timestamp: 2026-05-24T11:39:23-05:00
metadata:
  originSessionId: 417364af-b8f5-494c-8463-f0d1ba555a6d
  graduated_from: feedback_v_day_target_is_down_only.md
  source_type: feedback
---

For st-r2o V-day detection (and the butterfly strategy it supports), Steve's actual trading targets are **v_down only** — consolidation → drop → recovery toward the neck. v_up (rally → fade → recovery) is not the trade setup, even though earlier scope discussions included "treat inverted-V symmetrically" as an algorithmic choice.

**Why:** The butterfly play centers on a consolidation that *breaks down*. The late-day rally back to consolidation is what re-prices the centered fly profitably. The mirror case (rally then fade back to center) doesn't fit the entry mechanics — fly placement, sizing, and risk are calibrated for the drop-then-recover dynamic.

**Evidence:** Steve's 2026-05-24 eyeball verdict on `docs/measurement/v_day_eyeball_v0.md` confirmed 13 days, **all 13 were v_down**. None of the 6 detector-flagged v_up days made his list. He pasted only v_down candidates from the checklist.

**How to apply:**
- For future V-detector iterations, prioritize v_down recall and precision; v_up output stays in the schema for completeness but isn't part of trading signal.
- The earlier "treat inverted-V symmetrically" decision was about the *detection algorithm* running both arms; the *strategic target* is still v_down. Don't re-propose dropping the v_up arm — keep it, but don't weight tuning around it.
- For [[project-v-detection-v0]] greek-correlation work, the labeled set is v_down only. Control population should also be drawn from non-V days, not v_up days.
