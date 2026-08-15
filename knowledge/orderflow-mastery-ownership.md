---
type: decision
title: "Orderflow Mastery — the directive, and who owns it"
description: "The 2026-08-06 standing order to master GexBot's Orderflow indicator during the Quant month, its 08-08/08-10 steers, and Steve's 2026-08-15 ruling returning ownership from COO to Strader. Read before resuming any orderflow work: this is where the directive lives now."
timestamp: 2026-08-15T09:00:00-05:00
metadata:
  bead: st-ygy1
  coo_decision: co-u58u2
  supersedes: "COO auto-memory project_orderflow-mastery-directive (retired to a pointer 2026-08-15)"
---

# Orderflow Mastery — the directive, and who owns it

## Ownership: Strader, as of 2026-08-15

Steve, 2026-08-15, in a COO session (COO decision bead **co-u58u2**):

> "I need to reduce the range of doctrines you are responsible for -- in
> particular the Mastery of Orderflow was a mistake on my part. That needs to
> land back with Strader."

The 2026-08-06 exception that made COO the owner of this effort is revoked.
The directive itself is not — the work continues under the epic **st-ygy1**
(Orderflow Mastery), which has lived in this store since the day it was given.
What changes is where the directive is *kept* and who is answerable for it:
here, and Strader. COO's private auto-memory copy is now a pointer to this file.

Why: COO carrying live trading doctrine was the recurrence mechanism behind
the butterfly-doctrine failures (co-y3fdk — canon here, sessions there) and the
08-11 corrections. Steve's chosen fix is to move the doctrine's owner, not to
keep duplicating trading doctrine into COO.

## The directive as given (2026-08-06, Steve's words)

> "I want your attention spent on gb's Orderflow indicator. We have a full
> month of access — I'd like you to master its utility in that time. I'm going
> to leave your model level at Fable… This might seem counter to the declared
> division of labor but I'm going to declare an exception to accommodate this
> effort."

Time-bound to the Quant month (tier decision ~Sep 1, see
[`entitlements-registry`](entitlements-registry.md)); "master its utility"
means understand the vendor's intended reading of the indicator, test its
claims against our tape, and produce utility Steve can trade with — not merely
decode the data (done, st-ek8b).

## Steers that still bind

- **2026-08-08 — singleton scalp-proxy target.** Orderflow edges serve
  single-leg SPX scalp-proxy trades, not fly assistance; score by MFE/MAE in
  5–15 minute windows and fast-move tails, not median drift. (This scopes the
  *measurement program*; it says nothing about what the instruments are good
  for — see [`directional-gex-butterflies`](directional-gex-butterflies.md).)
- **2026-08-10 — Counter-Dictum tabled.**
  [`counter-dictum-program`](counter-dictum-program.md) is under construction
  and must not affect work product; comprehension of the Orderflow *dataset*
  first, guided by Freddy (`docs/gexbot/community/freddy_orderflow_series.md`,
  `docs/gexbot/orderflow-intended-read.md`, `docs/gexbot/canonical/`).
- **2026-08-10 — the named target.** Find an edge where direction can be
  detected; if OF can't help, the sub is cancelled ~Sep 1. Leading hypothesis
  (Freddy, endorsed by Steve): OF *confirms* the lean derived from recognising
  which levels are relevant — levels first, OF as confirmation. Steve's own
  caution attached: guard against tunnel vision; keep enumerating other places
  direction could be detectable.
- **Method:** [`channel-family-taxonomy`](channel-family-taxonomy.md)'s
  traverse-first procedure is binding — clock/hour-of-day is the strongest
  predictor found and was skipped by four rounds (st-1bv1).

## What stayed with COO

Restraint, not doctrine: COO's `.claude/rules/fly-doctrine.md` bans (a mirror
of canon here) and the "his trades are not your subject" line remain in COO
because they govern what COO *says* when Steve asks it something, and Steve
still asks COO things mid-session. The wider partition of trading-adjacent
material out of COO is to come from COO's 2026-08-15 enterprise self-audit as a
proposal, not from unilateral cuts.
