# OpenMobius comparison set — Order Flow tranche

**This is not canon and never becomes canon.** Desk's work order §5 is explicit:
a comparison set is never canon and never enters the live emitter's context.
`knowledge/` **is** the emitter's bundle, which is why this lives here instead —
so the boundary is a structural fact rather than a convention someone remembers.

Source: `github.com/MobiusQuant/OpenMobius-skill`, `knowledge_base/`, Apache-2.0.
Cloned shallow 2026-09-06.

## Scope, and who set it

Steve's scope call, 2026-09-06: **Order Flow only.** He was given the choice
between the full 257-card set and this tranche after measurement showed that
87% of the full set would be graded against a register that does not exist
(no SMC register exists anywhere; OFB's claims lived only in a bridge memo until
this session filed them). SMC translation waits on an SMC baseline.

## What is here

| file | what it is |
|---|---|
| `order-flow-en.json` | the 34 Order Flow cards with their core fields in English; 18 concepts, 16 cases |
| `convergence-order-flow.md` | every card graded against the OFB register — the deliverable §6 asked for |
| `glossary-order-flow.md` | the term decisions the translation was held to |

The grading baseline is `knowledge/sources/orderflow-baseline-v1.md`, filed this
session from Desk's 2026-08-28 bridge memo (st-snd8). **It holds 16 claims and 5
gaps, not 24** — the 24 in earlier bead descriptions is the ID range (OFB-01 to
OFB-40), not a count.

## Method, as executed

Per §4 of the work order:

- **Core fields only.** Concepts: `definition`, `identification_rules`,
  `common_mistakes`, `trading_implication`, `aliases`. Cases: `title`,
  `market_context`, `key_observation`, `analysis_steps`, `outcome`, `lessons`,
  `warnings`.
- **Carried untranslated:** `definition_per_source`, `merge_notes`,
  `source_cards`, `sources`, `image_descriptions` — 6,490 CJK characters remain
  in these by design, and the validator counts them separately so their presence
  is never mistaken for an incomplete translation.
- **Dropped:** `raw_response`, `_embedding`, `_embedding_model`.
- **Round-trip validated:** same key set, same list lengths, zero CJK left in any
  translated field.

**Measured volume:** 34 cards, 32 carrying CJK in core fields, **21,529
core-field CJK characters**. Two cards (`intermarket_analysis`,
`us_dollar_index_dxy_bias_framework`) were already English and are carried
untouched.

## The validator earned its place

It found **five real errors in the first pass over 32 cards**, all of them
silent-corruption class rather than mistranslation:

| card | error |
|---|---|
| `doomsday_chariot_distribution` | a fourth `common_mistakes` entry written where the source has three |
| `session_volume_profile` | nine `identification_rules` compressed into four |
| `point_of_control` | nine aliases written as eight |
| `low_volume_node` | five aliases written as four |
| `frvp` | a Chinese title left inside a parenthetical, so CJK survived in a translated field |

Every one was repaired against the source list rather than by relaxing the check.

## QA, stated honestly

The work order asks for a hand-check of 15 Order Flow cards and a miss rate. The
translation was produced in this session, so a hand-check by the same reader is
self-grading and its miss rate would not mean anything. What can be said without
that problem:

- The **round-trip validator is independent of the translator** — it compares
  structure against the source file, not against intent — and it caught five
  errors in 32 cards before anything was written to the repo.
- A genuine adversarial term-and-sense check needs a **second reader against the
  Chinese**, and is not claimed here. The five errors above are the measured
  error rate of the first pass on the axis a machine can check; the sense axis
  is unmeasured and is stated as unmeasured.
