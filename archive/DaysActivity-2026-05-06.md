# DaysActivity - 2026-05-06

## 15:35 - Session Handoff [TradingView CDP Dead End → Screenshot Pipeline]

**Summary**: Attempted to establish CDP connection from WSL2 to TradingView Desktop on Windows. Exhausted all approaches — TradingView v3.x deliberately strips `--remote-debugging-port` before Chromium parses it. Confirmed via community research (5 open GitHub issues). Steve rejected Chrome browser workaround; next direction is a screenshot-based pipeline that bypasses CDP entirely.

**Tried**:
- Store exe directly with `--remote-debugging-port=9222` → `bind()` permission denied (MSIX sandbox)
- Elevated (admin) launch → CDP hung the app, TV became unresponsive
- `CHROMIUM_FLAGS` env var → ignored by Store app
- Registry key `HKCU:\Software\TradingView\CommandLineArgs` → ignored
- Copied app out of WindowsApps to `$LOCALAPPDATA\TradingView-CDP` → launches but CDP returns empty replies (`curl: (52) Empty reply from server`)
- `--remote-allow-origins=*`, `--no-sandbox`, `ELECTRON_ENABLE_REMOTE_DEBUGGING=1` → all ignored
- Windows `netsh portproxy` + firewall rule for WSL2 bridge → configured but moot without CDP
- Research confirmed: TV v3.x (Electron 38.2.2, Chrome 140) strips the debug flag intentionally. Pre-v3 worked fine.

**Open Work**:
- st-xb2: TradingView CDP connection — research and resolve (open)
- st-lh3: COO — establish bun-over-node convention enterprise-wide (open, routed)

**Key Decision**: Steve wants a screenshot-based pipeline for TV interaction, not the Chrome browser fallback. This changes the architecture — vision analysis replaces CDP DOM inspection.

**Files Changed**:
.mcp.json
.claude/state/tv-cdp-research.md
.claude/state/checkpoint.json

---

## 12:56 - Session Handoff [MCP Confirmation]

**Summary**: Confirmed TradingView MCP pipe is fully operational — first successful tool execution (tv_health_check returned structured JSON response). TradingView Desktop not running with CDP, but the MCP plumbing chain (Claude Code → MCP server → tool → response) is verified end-to-end. Decided to keep SDK pinned at 1.12.1; no reason to unpin.

**Tried**:
- ToolSearch for tv_health_check → schema loaded successfully (first time)
- tv_health_check call → structured error response confirming MCP server running, TV Desktop not launched with CDP
- Evaluated reversing SDK 1.12.1 pin → decided against; pin is load-bearing, no upside to unpinning

**Open Work**:
- st-lh3: COO — establish bun-over-node convention enterprise-wide (open, routed)

---

## 12:17 - Session Handoff [MCP SDK Fix]

**Summary**: Root-caused the TradingView MCP silent tool drop across four sessions. The `@modelcontextprotocol/sdk` resolved to v1.27.1 which auto-injects `execution: { taskSupport: "forbidden" }` on every tool definition — a newer spec field that Claude Code 2.1.131 silently rejects. Pinned SDK to 1.12.1 in tradingview-mcp, verified clean tools/list response. Session restart required to confirm tools load.

**Tried**:
- Web search for others reporting custom MCP servers not connecting → found GitHub issue #25081 (extra fields cause silent tool drop)
- Inspected tools/list response via stdin pipe → found non-standard `execution` key on every tool
- Traced `execution` field to `@modelcontextprotocol/sdk` v1.27.1 (auto-injected, not in server source)
- Confirmed SDK 1.12.1 does NOT include the field → clean tool definitions
- Pinned SDK, reinstalled, verified tools/list returns only `name`, `description`, `inputSchema`

**Open Work**:
- st-lh3: COO — establish bun-over-node convention enterprise-wide (open, routed)

**Files Changed**:
/root/projects/tradingview-mcp/package.json
/root/projects/tradingview-mcp/bun.lock

---

## 11:36 - Session Handoff [MCP Connection Verification]

**Summary**: Verified TradingView MCP server works end-to-end — full protocol handshake returns 78 tools under bun. Claude Code's MCP client still not connecting; changed config from bare `bun` to `/usr/local/bin/bun` (full path) to address the same PATH-not-inherited issue from last session. Session restart required.

**Tried**:
- ToolSearch for `tradingview` → zero deferred tools, confirming MCP client not connected
- `bun src/server.js` direct → starts clean, no errors
- MCP initialize + tools/list via stdin pipe → full handshake succeeds, 78 tools returned
- Checked stderr output (warning banner) → present but shouldn't block MCP clients
- Full path fix: `bun` → `/usr/local/bin/bun` in `.claude/settings.json`

**Open Work**:
- st-lh3: COO — establish bun-over-node convention enterprise-wide (open, routed)

**Files Changed**:
.claude/settings.json

---

## 11:30 - Session Handoff [TradingView MCP Debug]

**Summary**: Diagnosed TradingView MCP tools not loading — server was fine but Claude Code's MCP launcher doesn't source shell profiles, so nvm's `node` shim wasn't on PATH. Switched MCP config from bare `node` to `bun` (stable at `/usr/local/bin/bun`, no shim). Verified server runs identically under bun. Created bead st-lh3 routing a bun-over-node convention proposal to COO for enterprise-wide adoption.

**Tried**:
- Manual MCP handshake via stdin → server responds correctly, not a server bug
- ToolSearch for `tradingview` → confirmed zero tools loaded, not a display issue
- Root cause: nvm requires profile sourcing; Claude Code MCP launcher skips that

**Open Work**:
- st-lh3: COO — establish bun-over-node convention enterprise-wide (open, routed)

**Next Session Actions**:
1. Restart session to verify TradingView MCP tools load under bun
2. Complete Schwab OAuth flow
3. Build headless Schwab client modules

**Files Changed**:
.claude/settings.json
.beads/issues.jsonl

---

## 10:18 - Session Handoff [Schwab + TradingView MCP Setup]

**Summary**: Cloned and installed TradingView MCP server (tools will load next session). Cloned schwab-py fork, created venv with editable install, installed python-dotenv. Steve configured .env with Schwab credentials; OAuth auth flow pending. Searched claude-monitor DB to confirm tradingview-mcp repo exists as justSteve fork on GitHub.

**Key Decisions**:
- schwab-py installed as editable from fork per Fork Doctrine (not pip from PyPI)
- venv at `.venv/` due to PEP 668 system-packages restriction
- TradingView MCP cloned to `/root/projects/tradingview-mcp/` — server starts clean, tools load on next session

**Next Session Actions**:
1. Verify TradingView MCP tools (`mcp__tradingview__*`) are loading
2. Complete Schwab OAuth flow in tmux session (`strader`) — `.venv/bin/python hello_schwab.py`
3. Once token lands, build headless Schwab client modules (options chain fetcher, GEX calculator)

**Files Changed**:
.beads/issues.jsonl
.beads/interactions.jsonl

---
