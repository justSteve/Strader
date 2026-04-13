# Rule: Zgent Permissions

## Tier: Consumer

Strader is a Consumer tier zgent — it consumes intel from service providers and operates within its own repo scope.

## Filesystem
- READ any file under the enterprise root directory tree
- WRITE only within this repository's directory
- NEVER read or write outside the enterprise root

## GitHub
- READ any repository under the same GitHub owner as this repo's origin
- WRITE (push, branch, PR, issues) only to this repository
- Cross-repo writes require explicit delegation via beads

## Secrets
- NEVER commit credentials, tokens, or API keys to tracked files
- Use environment variables or gitignored .env files

## MCP Access
- TradingView MCP server for chart control, market data, Pine Script, and screenshot capture (owned instrument)
- Fetch MCP for external data retrieval
- GitHub MCP for repository operations (own repo only)

## Restrictions
- No autonomous order execution without human confirmation
- No access to .env files or credential stores
- No cross-repo writes without bead authorization
