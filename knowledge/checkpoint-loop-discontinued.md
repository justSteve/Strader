---
type: decision
title: "Checkpoint Loop Discontinued"
description: "The 30-min /checkpoint auto-save loop is discontinued (2026-07-13) — do not start it at session start"
timestamp: 2026-07-13T05:19:07-05:00
metadata:
  originSessionId: 10c153bc-421f-4f71-a582-28941810eb92
  graduated_from: feedback_checkpoint_discontinued.md
  source_type: feedback
---

Steve discontinued the /checkpoint practice on 2026-07-13.

**Why:** Checkpoints were a safety net for WSL/terminal session crashes; those are now stabilized, so the loop is pure overhead.

**How to apply:** Do not start `/loop 30m /checkpoint` at session start (the session-start.sh hook mandate was removed the same day). The checkpoint skill still exists for manual use only. `/handoff` (snapshot.json) remains the real state-capture ritual.
