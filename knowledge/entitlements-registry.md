---
type: convention
title: "Entitlements Registry"
description: "Subscription and entitlement state lives in ONE file, config/entitlements.yaml, probed at statement time — bundle docs point at it and never restate its figures"
timestamp: 2026-08-13T04:20:00-05:00
metadata:
  bead: st-g0or
  plan: docs/plans/2026-08-12-zgent-sync-plan.md
---

Every subscription, plan, tier, and data entitlement this desk runs on is recorded in
**one file** — `config/entitlements.yaml` — and read by running its probe:

```bash
.venv/bin/python3 scripts/entitlements_probe.py
```

No other document states a plan name, a tier, a price, or a cancellation date. Bundle
concepts, `CurrentStatus.md`, and A2A memos **point at the registry**; they record the
decision *shape* only. A restated figure is a figure that goes stale silently.

## Two kinds of entry, and the distinction is the whole point

| Kind | What it is | How to speak it |
|------|-----------|-----------------|
| **PROBED** | Re-derived every run from a local JSON state file or a corpus directory listing. An observation. | "As of right now, the orderflow leg is landing." |
| **DATED** | What Steve reported from a billing portal on a date, unverified since. | "As of 2026-08-05, Steve reported the Quant tier active." |

A green probed line proves **the data is landing**, never that the contract is paid — a
cancelled plan keeps delivering until its billing period ends. Only Steve can move a
dated fact, and re-confirming an unchanged fact still counts as an update, because the
**date** is the load-bearing part.

The probe reads local files only. It calls no vendor API, holds no credentials, and the
registry never records how to authenticate anything — only what we are entitled to
(`.claude/rules/schwab-api-gate.md`).

## Why

Four of the costliest incidents in the ten days to 2026-08-12 were subscription gaps that
only Steve could close, because the facts lived in his head and in portals no agent can
read:

1. **Databento OPRA → Futures swap (~2026-08-04).** This bundle still asserted the
   cancelled OPRA sub as "Live data: Active" a week later — arguing the opposite of the
   collector it described.
2. **The GexBot resub (2026-08-05).** A morning spent telling Steve "we have no GEX" while
   the collector wrote to the corpus in the next tmux window.
3. **The State → Quant tier reveal (2026-08-05 PM).** A full night of 1DTE and orderflow
   legs silently uncollected. The code was already correct; it was auto-skipping on
   entitlement. *"We should have been working all night."*
4. **The OPRA cancellation both agents still assumed active on 2026-08-11.**

Each was a fact with no home, so it lived in several docs at once and rotted in all of
them. The registry gives it one home and a probe that reports it fresh.

## How to apply

- **Before stating anything about a subscription** — tier, cost, what is covered, what
  was cancelled — run the probe. Do not answer from memory, from a bundle doc, or from
  CurrentStatus.
- **Quote a dated line with its date, always.** "As of `<date>`, Steve reported …". Never
  as current truth.
- **NEEDS STEVE is a real output**, not a formatting flourish. Items there (never
  confirmed, aged past their horizon, or past a review date) are the only way those facts
  ever get closed. Surface them when they matter; do not nag daily.
- **Agents may add probed entries freely. Agents may never invent or advance a dated
  fact.** That edit is Steve's.
- **A mismatch between the registry and the code is the finding** — e.g. the registry
  says we hold a dataset the collector is not pulling, or a halted usage-billed stream
  reappears in the corpus.

Related: [[databento-live-collection]], [[counter-dictum-program]], [[schwab-auth-pattern]].
