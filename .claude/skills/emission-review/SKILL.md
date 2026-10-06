---
name: emission-review
description: Review one FP-chart emission — build the bar's packet, write the commentary (bias the emission calls, how much it should matter, confirm/negate, hindsight), file the card in the lookback archive and deliver it to Desk, where Steve discusses it. Use when Steve names a bar ("review today's 232 bar", "/emission-review 232", "/emission-review 2026-10-06 232").
---

# Emission Review — one bar, one card, to Desk

[st-rf95] Steve, 2026-10-06: an ongoing lookback — "unpack from the POV of
Bullish Bearish bias the emission is calling, make note of how impactful the
condition being reported actually is expected to be and answer operator
questions". He interacts with the card **in Desk**, not in this terminal. This
session builds and delivers it, then reports one line.

## Step 1 — Build the packet

```bash
.venv/bin/python tools/emission_review.py --bar <N> [--day YYYY-MM-DD]
```

`<N>` is the page's **Bar N** label (index + 1); the tool handles the offset.
It writes `docs/emission-reviews/<day>/bar-NNN.{json,md}` — the card with its
data sections filled in and every commentary section marked
`<!-- REVIEW: fill -->`.

Read the `source` line. `run-log` means the day has rolled off the bridge, so
**context lines (Fuel, GEX) are missing**. If Steve is asking about a Fuel line,
say that the record doesn't hold it. Never review a bar as "quiet" because the
run log has no context lines for it.

## Step 2 — Read what the emission means

For each emission type, open the `canon` pointer in the packet (for Fuel,
`knowledge/trapped-seller-fuel.md`; anything else, the emitting module under
`market/orderflow/` named by its `source`). Grade against the canon's own terms,
never from memory.

## Step 3 — Write the commentary (the five REVIEW sections)

The section order and headings are the contract. Steve reads the cards side by
side over weeks, so do not add, rename or reorder sections.

1. **Bias the emission is calling.** The first line is bold and is one of
   **Bullish** / **Bearish** / **No direction**, plus its condition ("Bullish,
   conditional on 7879 being taken"). This is what *the emission* argues, not a
   trade opinion. Then give the opposing half, if the same line holds it.
2. **How much it should matter.** The first line is bold: **High / Moderate /
   Low**, and then **measured** (cite the file and n) or **by reasoning**. If the
   canon or packet says follow-through is unmeasured, the grade is reasoned and
   the card says so. Break it down per component where the emission has them.
   Compare to the canon's worked example when there is one.
3. **What would confirm · what would negate.** Put both in tape terms on
   2,000-lot bars: closes, delta, levels, and the emission's own rules
   (acceptance, stages).
4. **Outcome** (the hindsight line). Say whether the read held over the packet's
   +5/+10/+20 bars, and how far, in points. Name the later emissions on the same
   level. Hindsight never goes into sections 1–3.
5. **Questions this card should be able to answer.** Write 4–6 questions Steve is
   likely to ask, each with a short answer, at least one of them in SPX terms
   (`basis_approx`). This is what Desk answers from.

Binding throughout: CT timestamps and points. Label every claim as measured or
reasoned. Never give trade advice or tell him what to do with the read
(`hard-boundaries.md`), and write no fly framing that `fly-doctrine.md` bans. If
an answer needs a number the packet doesn't hold, measure it now or say it isn't
measured. Never round a guess into a fact.

Confirm that none of the five `REVIEW: fill` markers remain before delivering.

## Step 4 — Deliver to Desk and file the lookback

```bash
.venv/bin/python tools/emission_review.py --deliver docs/emission-reviews/<day>/bar-NNN.md
```

This copies the card into `zgent-bridge/Desk/inbox/` as
`<ts>__Strader__emission-review-<day>-bar-NNN.md`, with frontmatter
(`expects_reply: false`). The bridge's own sync carries it, so there's no commit
in the bridge from here. It refuses a card that still has a `REVIEW: fill`
marker.

Then commit the card and its packet in this repo with `[st-rf95]` (or the bead
Steve's ask opened): `docs/emission-reviews/` is the lookback record.

## Step 5 — Report

Give one line: day, Bar N, emission type, the bias call and impact grade, and
"delivered to Desk". Follow-up questions go to Desk. If Steve asks here anyway,
answer from the card.
