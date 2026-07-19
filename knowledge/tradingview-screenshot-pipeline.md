---
type: decision
title: "TradingView Screenshot Pipeline"
description: "TradingView MCP is dead — screenshots via tv_capture.py are the sole chart interface. No MCP, no CDP."
timestamp: 2026-05-20T08:52:15-05:00
metadata:
  originSessionId: b58776c9-0081-4241-8274-43f16ef9784e
  graduated_from: project_tv_screenshot_pipeline.md
  source_type: project
---

TradingView MCP is removed. The .mcp.json config has been deleted. Screenshots via `tools/tv_capture/tv_capture.py` are the sole interface to chart state.

**Why:** TradingView Desktop v3.x strips CDP. MCP depended on CDP. Screenshot capture (process-based detection, Ctrl+Shift+B hotkey, 5-min auto-capture during market hours) replaces it entirely.

**How to apply:** Never attempt to use TV MCP tools. Read chart state from screenshot images. Pine Scripts are pasted manually by Steve — codegen pipeline emits `.pine` files, Steve copies them into the editor.
