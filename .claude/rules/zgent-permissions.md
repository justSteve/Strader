# Rule: Zgent Permissions

## Tier: Consumer

Strader is a Consumer tier zgent — it consumes intel from service providers and operates within its own repo scope.

## Filesystem
- READ any file under the enterprise root directory tree
- WRITE only within this repository's directory, with one exception: delivering
  an A2A memo and its `inbox.md` line into a peer's `docs/a2a/` (the announce
  channel — see "Inbound" below). Nothing else in a peer's tree, ever
- NEVER read or write outside the enterprise root

## GitHub
- READ any repository under the same GitHub owner as this repo's origin
- WRITE (push, branch, PR, issues) to this repository
- Strader's writes into a **peer's** repo: only the A2A channel (a memo file
  under their `docs/a2a/` plus the matching `inbox.md` line) — anything beyond
  that requires explicit delegation via beads

## Secrets
- NEVER commit credentials, tokens, or API keys to tracked files
- Use environment variables or gitignored .env files

## MCP Access
- TradingView MCP server for chart control, market data, Pine Script, and screenshot capture (owned instrument)
- Fetch MCP for external data retrieval
- GitHub MCP for repository operations (own repo only)

## Inbound: COO's standing authority to write here

**COO holds standing authority to commit directly into this repository.** Ratified
by Steve 2026-08-13 (decision 1 of `docs/plans/2026-08-12-zgent-sync-plan.md`,
st-aski). This file is now the canonical written record of that grant, which until
today existed only as a verbal authorization remembered in COO's memory (dated
2026-07-01) while this rule said the opposite. Rule and reality now agree.

The grant is real: COO files, claims, and closes `st-` beads here, pushes to
master, and edits harness surfaces. That bandwidth is worth keeping — over ten
days it delivered a beads repair, cron fixes, and lifecycle work Strader did not
have to stop trading to do. **The silence, not the writing, is what burned us**:
~15 unannounced commits including `CLAUDE.md`, `settings.json`, skills, and the
Schwab reauth script, one of which blind-staged `settings.json` into a
schwab-gate violation that nobody saw.

So the authority carries two gates. Both are conditions of the grant, not
etiquette.

### Gate 1 — read the owner's canon first

A write into another agent's territory reads that agent's canonical source
**before** the change, not after a correction. For this repo:

| Domain | Canon that must be read first |
|---|---|
| Trading doctrine, strategy, fly construction | `knowledge/` — especially `directional-gex-butterflies.md`, `buying-movement-delta-first.md` |
| Operator profile, Steve's error modes, tone | `knowledge/` — every concept typed `operator-profile` (`direction-inversion-watch.md`, `perceptual-profile.md`, …); `knowledge/index.md` is the entry point |
| Anything that changes what this agent is told | `CLAUDE.md` and `.claude/rules/` in full |

This gate exists because doctrine corrected at source in this repo on 08-05 did
not bind COO's sessions, and ATM/theta flies were priced during a live trade on
08-11 anyway. Strader's `knowledge/` is the single home for trading doctrine and
operator profile; a peer building against a reconstruction of it is building
against something Steve already corrected.

### Gate 2 — announce in the same commit

**Every commit by a peer agent into this repo appends one line to
`docs/a2a/inbox.md`, in that same commit.** Not a follow-up commit, not a memo
instead, not a mention in the peer's own log. The format contract and worked
example are in `docs/a2a/inbox.md`; the receipt rules are in
`docs/a2a/receipt-protocol.md`.

The announce is **absolutely required** — no "small change" exemption — for:

| Class | Paths |
|---|---|
| Agent instructions | `CLAUDE.md`, `AGENTS.md` |
| Harness surface | `.claude/**` — rules, hooks, skills, state |
| Settings | `.claude/settings.json`, `.claude/settings.local.json` |
| Schwab-adjacent | `broker_schwab/**`, `scripts/run.sh`, any path matching `*schwab*`, anything touching `tokens/` or the gate key |
| Trading canon | `knowledge/**` |
| Beads | any `st-` bead filed, claimed, or closed by a peer — one line, who and why |

For everything else in this repo the announce is expected and omitted only for
pure housekeeping. Strader's tap-in reads the inbox; an announced commit is
seen, an unannounced one is not, and that is the whole difference.

**If a commit lands without its line**, the next Strader session appends the
missing line itself (noting in `WHY` that it is reconstructed) and files a bead.
The ledger stays complete; the lapse stays visible.

### What the standing authority does NOT cover

The grant is broad but not unlimited. These still require Steve's explicit,
in-session approval — an inbox line is not sufficient authorization:

- **The Schwab gate.** Changes to `.claude/rules/schwab-api-gate.md`, the
  `schwab-gate.sh` hook, the `broker_schwab/readers/` allow-list, or any
  permission rule touching `schwab_gate_key`, `tokens/schwab*`, or credential
  paths. The gate is a hard boundary in both layers (the hobbled `lib/schwab-py`
  fork and the permissions surface); nothing in this section relaxes it.
- **The hard boundaries.** No-autonomous-orders, no-financial-advice, and the
  $5,000 notional escalation are not editable under a standing grant.
- **Credential material.** No peer commit may add, move, or read `.env`, tokens,
  or keys here under any authorization.

Exceptions to any of the above are **written, dated, and loaded by both agents**
— never carried in one agent's memory. An exception nobody can read is how this
rule spent weeks contradicting reality.

## Restrictions
- No autonomous order execution without human confirmation
- No access to .env files or credential stores
- Strader does not write into a peer's repo beyond the A2A channel without bead authorization
- Peer writes into this repo without an `inbox.md` line are a protocol violation, regardless of authorization
