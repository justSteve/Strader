---
type: decision
title: "TradingView Chart Interface"
description: "There is no automated TradingView interface — MCP and the screenshot/Vision pipeline are both dead. Chart state comes from our own corpus; Pine is hand-pasted."
timestamp: 2026-05-20T08:52:15-05:00
updated: 2026-08-02T02:00:00-05:00
metadata:
  originSessionId: b58776c9-0081-4241-8274-43f16ef9784e
  graduated_from: project_tv_screenshot_pipeline.md
  source_type: project
  supersedes_title: "TradingView Screenshot Pipeline"
---

**Two successive attempts at an automated TradingView interface both failed. There is no third one running.** Read chart state from our own corpus, not from TradingView.

**What died, in order:**

1. **MCP (2026-05-20)** — TradingView Desktop v3.x strips CDP, and the MCP server depended on CDP. `.mcp.json` was deleted; the repo has had no MCP config since.
2. **Screenshot → Vision (2026-07-02, `st-5xe`)** — the replacement for MCP: a Windows-side capture tool feeding Vision extraction. Removed as a dead end, viable only as real-time screenshot parsing; a multi-step capture→infer chain could not carry a read. Its files went with it.

**How to apply:**

- Never attempt TV MCP tools. There is no server and no config.
- Do not reach for a capture-and-infer screenshot step. That approach was tried and rejected on the merits, not abandoned half-built.
- For chart eyeballing, render from our own DataBento corpus with `tools/local_chart.py` — a self-contained HTML candlestick chart for a given date and CT window, opened over `file://`. This is the supported path for detector validation and historical review.
- Pine Scripts are still pasted by hand: the codegen pipeline emits `.pine` files, Steve copies them into the editor.

**Standing gap:** nothing reads Steve's *live* chart. Live chart state reaches Strader only by Steve describing it or pasting an image. Any future proposal here starts from that fact rather than rediscovering it.
