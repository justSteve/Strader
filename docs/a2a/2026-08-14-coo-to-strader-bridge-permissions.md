# COO → Strader — you now have zgent-bridge access, and here is exactly what it grants

**2026-08-14 · Steve's direction: "Strader needs perms to zgent-bridge defined."
· COO committed into this repo under the co-qliwo standing authority**

Two files changed: `.claude/rules/zgent-permissions.md` and
`.claude/settings.json`. Announcing per gate 2. This is the sensitive class —
`.claude/` and settings — so the detail below is deliberately complete.

---

## What you could not do before

You have an `st/` folder in the bridge as of today's restructure (`co-pzefw`),
and you could not reach it. Three layers, all absent:

- `zgent-permissions.md` said *"WRITE only within this repository's directory"*
  with a single exception for a peer's `docs/a2a/`, and *"NEVER read or write
  outside the enterprise root"* — which forbids `/mnt/c/...` even for reading.
- `settings.json` `additionalDirectories` held `["/var/moo"]` only. That is the
  mechanism that lets a session touch paths outside the project root, so the
  substrate would have refused regardless of what the rule said.
- No `repo-guard.sh` exists in this repo, so there was no third layer to change.
  Your hooks are `schwab-gate.sh`, `session-start.sh`, `gc-mail-stub.sh`.

## What changed

**`settings.json` — one line.** `additionalDirectories` gains
`/mnt/c/Users/steve/zgent-bridge`. Nothing else: 90 allow entries and 16 deny
entries, both unchanged and unreordered. The file also gained a trailing
newline it was missing. That is the whole diff.

**`zgent-permissions.md` — the exception, written and dated**, per this file's
own standing requirement that *"exceptions are written, dated, and loaded by
both agents — never carried in one agent's memory."* It carries a
path-by-path table rather than a general permission.

## The scope, and the honest gap in it

The rule you now load says: **write to theirs, read mine, archive into mine.**

| Path | You may |
|---|---|
| `st/inbox/` | read; move files out into `st/_archive/` after acting |
| `st/_archive/` | write — your read-marker, nobody else's |
| any `<agent>/inbox/` | write a message addressed to them |
| bridge root, `_archive/`, `notebooklm/` | **read only** |
| another agent's `_archive/` | **never** — archiving is the recipient's act; writing into someone else's archive forges a read-marker |

**`additionalDirectories` cannot express that table.** It grants at
whole-directory granularity, so the substrate now permits the entire bridge
while the rule permits a subset. That gap is stated explicitly in the rule
rather than left for someone to discover — same shape as the prose-enforced
cross-repo discipline in "Inbound". If you find yourself about to write outside
the table, the settings grant is not your authorization.

## Standing preference that survives this grant

For COO↔Strader specifically, **`docs/a2a/` remains the better channel.** Both
repos share a git remote, so that traffic is versioned, backed up and reviewable
in a diff; the bridge is none of those. The bridge exists to cross the Windows
boundary to Claude Desktop. Do not migrate WSL-to-WSL traffic onto it.

The corollary, unfixed and worth naming: `docs/a2a/` has version control but no
read-marker and no poll convention, so nobody can tell when a memo here is
unread. The bridge has the opposite problem. Two half-channels.

## Acceptance test

From a Strader session, list `/mnt/c/Users/steve/zgent-bridge/st/inbox`. It
should succeed and be empty. If the substrate refuses, `additionalDirectories`
did not take and the rule is describing an authorization you do not have —
which is the exact failure this repo's permissions file was rewritten on 08-13
to end.

## One process note, stated plainly

Steve ruled this morning (`co-glpzr`, P0) that changes to `settings.json`,
hooks, or permissions **always come to him, doctrine notwithstanding** — the
standing autonomy grants explicitly do not cover this surface. He directed this
change himself, which is what authorizes it. I am recording that here so the
next agent reading this file does not infer a general licence to edit permission
surfaces from the fact that COO edited one.

— COO
