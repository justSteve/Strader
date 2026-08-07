# Vendor email — remaining Orderflow questions (post-tour revision)

*Revised 2026-08-07 [st-ygy1] after the pane↔field mapping tour closed the
34-field decode. Supersedes the earlier 7/8-item list: three questions are
answered or resolved and are dropped or downgraded to confirmations below.
Discord open-ended ask went unanswered; this is the email version — specific,
evidence-first, answerable in a few lines.*

**Status of the old list:** units question resolved (UI axes are $MM);
zcvr/ocvr identified (Net Convexity pane, verified by tooltip anchor);
oflow-as-first-differences confirmed empirically. Still open: agg-vs-net DEX
(headline), the dead-zero state fields, the /hist orderflow payload gap,
oflow normalization, and the July cadence change.

---

## Ready-to-send draft

**To:** support@gexbot.com (or the contact on gexbot.com/support)
**Subject:** Quant subscriber — three questions on orderflow package fields

Hi —

I'm a Quant-tier subscriber archiving the orderflow package via /hist and
have reverse-engineered most of the field semantics empirically (the spec
types the 34 orderflow scalars but doesn't describe them). Three questions
remain that measurement can't settle:

1. **What distinguishes `agg_*_dex` from `net_*_dex`?** Both are signed and
   cumulative, both satisfy call + put = total exactly, yet their daily
   correlation ranges from +0.999 down to +0.53 across sessions in my
   archive. Your docs define "aggdex" but the `net_` variant appears nowhere.
   This is the main blocker on interpreting half the DEX family.

2. **Three fields arrive identically zero in every state /hist payload:**
   `sum_gex_oi`, `delta_risk_reversal`, and `zero_gamma` — across 60+
   sessions. Is that intended (fields reserved/deprecated for /hist) or a
   defect?

3. **The /hist orderflow payload omits 14 of the 48 properties the spec's
   `orderflow_response` declares** (the `strikes` ladder and most
   `basic_response` fields). Intended difference between live and /hist, or
   a gap?

Two quick confirmations, if easy: the `*oflow` fields measure as exact
per-snapshot first differences of their cumulative counterparts
(unnormalized — a 3-second publication gap reports 3 seconds of change) —
is that the contract? And `zcvr`/`ocvr` match your Net Convexity pane
exactly — correct that this is "total customer-bought GEX − total
customer-sold GEX"?

Minor, only if known offhand: snapshot counts dropped ~23,400 → ~17,900/day
around 2026-07-08→15 (max gap 2s → 3s) — deliberate cadence change?

Thanks — happy to share the measurement writeups if useful.

---

## Why this shape

- **Lead with the unanswerable-by-measurement question.** agg-vs-net is the
  only remaining semantic unknown that blocks interpretation; everything
  else is confirmation or defect-report.
- **Evidence in every question** — shows the homework is done, makes each
  answerable in one or two lines by whoever reads it, and distinguishes this
  from the open-ended Discord ask that went unanswered.
- **Defect report framed neutrally** (#2) — a paid-feed data-quality issue
  the vendor likely wants to know about regardless.
- The confirmations cost them nothing and, if we're subtly wrong about
  either, the correction is exactly what we need before Phase 2 leans on
  those identities.
