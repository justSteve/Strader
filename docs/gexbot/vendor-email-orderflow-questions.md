# Vendor followup — Orderflow field questions

*Revised 2026-08-07 [st-ygy1], second revision after Steve's read: the
Discord non-response was a support failure, not a phrasing problem — the
followup email doubles as a support-posture probe for the ~Sep 1 tier
decision. Composition principle: as short as the Discord ask, but built
around the one question measurement cannot answer, so even a one-line reply
yields the blocking unknown. Everything else is held for round two.*

---

## Recommended followup (short)

**To:** support contact per gexbot.com/support
**Subject:** Orderflow package field definitions — agg vs net dex

> Hi — Quant subscriber. I asked this in the Discord support channel on
> [date] without a response, so following up here.
>
> The API spec types the orderflow package's 34 fields but doesn't describe
> them. Most I've worked out empirically; the one I can't: what
> distinguishes `agg_dex` / `agg_call_dex` / `agg_put_dex` from their
> `net_` counterparts? The site docs define "aggdex" only.
>
> Is there a field reference for the orderflow package — and if not, could
> you answer that one directly? Thanks.

Fill in the Discord post date. One neutral mention of the ignored ask —
paper trail, not complaint.

## Held for round two (once a human replies)

1. **Dead-zero fields defect:** `sum_gex_oi`, `delta_risk_reversal`,
   `zero_gamma` identically zero in every state /hist payload across 60+
   sessions — intended or defect?
2. **/hist orderflow payload omits 14 of the spec's 48 declared properties**
   (the `strikes` ladder and most `basic_response` fields) — intended
   live-vs-hist difference?
3. **Confirmations:** `*oflow` = unnormalized per-snapshot first differences
   (contract?); `cvr` = Net Convexity pane = customer-bought GEX − sold GEX
   (verified empirically, correct?).
4. **Minor:** snapshot cadence dropped ~23,400 → ~17,900/day around
   2026-07-08→15 (max gap 2s → 3s) — deliberate?

## Resolved, no longer asked

- Units — UI axes answer it ($MM).
- What is `zcvr`/`ocvr` — solved 2026-08-07 (Net Convexity, tooltip-anchor
  verified).

## The other outcome

If this email also goes unanswered, that is a tier-decision datum in its own
right: a paid tier whose support ignores both channels prices its data
accordingly. Log either outcome to the epic (st-ygy1) for the pre-Sep-1
verdict.
