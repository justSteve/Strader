# Mancini extraction contract — the in-session prompt parse

*st-26q5 · The interpretive leg of the Mancini runbook. There is exactly one way
to run it: an agent reads the letter in-session and writes the extraction JSON.*

The runbook has two legs. The **deterministic** leg (`listlevels.py`) scrapes the
explicit `Supports are:` / `Resistances are:` sentences with a regex and needs no
judgment — it runs on every pass and is the sole level source when the
interpretive leg doesn't run. The **interpretive** leg is this document: reading
Mancini's prose for forward-looking conditional guidance, which a regex cannot do.

There is no API path. `run.py` never calls a model. The agent holding the letter
in its context *is* the extractor, and it hands the result to the pipeline as a
file:

```bash
# 1. Fetch the letter (caches under data/mancini-letters/)
PYTHONPATH=. .venv/bin/python -c "from runbook.mancini.fetch import fetch_latest; print(fetch_latest()[0])"

# 2. Read it, apply the instructions below, write the JSON.
#    clean_newsletter() strips the Substack HTML down to ~30k chars of prose,
#    then segment.render() cuts that to the forward plan — a median 16% —
#    split into labelled sections. Read the SEGMENTED text. [st-9r51]

# 3. Feed it back in. This is the last step — it publishes AND concludes by
#    loading the Daily Payload into Steve's Windows clipboard.
PYTHONPATH=. .venv/bin/python -m runbook.mancini.run \
    --from-blob --date YYYY-MM-DD --extraction-json /path/to/extraction.json
```

**The procedure concludes at the clipboard.** [st-llor] A completed interpretive
parse loads the Daily Payload automatically — no flag — so the morning routine is
double-click the indicator, Ctrl+A, Ctrl+V with nothing in between. The push is
the *last* thing the run does, after the store, the chart, and the desk doc, so a
run that halts leaves the clipboard holding whatever it held before. Pass
`--no-clip` when backfilling an old day or checking a renderer change; that is a
diagnostic, not the procedure, and it must not seize a live desktop surface.

Validation is **not** bypassed by this route. `validate.check()` still requires
every price to appear verbatim in the source text, and a failure still keeps
last-good artifacts rather than publishing suspect levels. Being the extractor
does not make you trusted; it makes you responsible for passing the same check
the API path had to pass.

---

## Extraction instructions

Two things matter equally: **accuracy** (every price must be real) and
**completeness** (these letters are dense with explicit levels and you must
capture them all).

**Where the levels are — every letter contains these; extract from all of them:**

- An explicit list like `Supports are: 7383, 7377 (major), 7365 (major), 7355, ...`
  — record EVERY number as a support level. A `(major)` annotation means set
  `label` to `"major"`. These lists commonly hold 25–30 levels.
- An explicit `Resistances are: 7391 (major), 7401, 7415 (major), ...` list —
  record EVERY number as a resistance level, same rules.
- Inline levels in the **Bull case**, **Bear case**, and **In summary**
  paragraphs (breakout targets, range boundaries, pivots, short/long triggers) —
  capture these too, classified by how Mancini frames them
  (target / pivot / trigger / support / resistance).

> **These must be the sections AFTER the ladder.** Mancini reprints his previous
> letter inside the recap — "I expanded on this yesterday:" and then yesterday's
> bull case in full — so `Bull case` appears twice in most letters and the first
> one is out of date. Measured: on 201 of 353 letters the first hit in the file
> is the quoted prior edition. The segmented input (`/tmp/mancini-plan.txt`)
> already contains only the forward sections, which is the reason to read it
> rather than the raw letter. If you are reading raw text for any reason, take
> the sections that follow `Supports are:` and no earlier ones.

**Level callouts — put Mancini's own words in `label`.** [st-eo0, Steve
2026-08-11] When the letter says something specific about a level, carry it:
*"heavily used up now and risky to buy directly"*, *"nice shelf of lows from
noon Thursday to midnight Friday"*, *"very weak, shaky support especially being
in the middle of a range"*, *"a Failed Breakdown of this low is very
actionable"*. These render under each ladder as **Mancini's callouts** and are
the level colour Steve reads the plan for.

The `label` field carries the `(major)` annotation and the callout together,
with `major` as a **prefix**:

| Letter says | `label` |
|---|---|
| `7724 (major)`, plus a shelf-of-lows note | `"major · nice shelf of lows from noon Thursday to midnight Friday"` |
| `7751 (major)`, no note | `"major"` |
| `7767`, called weak and shaky | `"1st support down — very weak, shaky, mid-range"` |

Prefix, never substring: `schema.is_major()` tests `startswith("major")`
precisely because a callout can contain the word ("lost the major June 11th
low") and a substring test would promote that level on the Pine chart and in
the Daily Payload. Do not write `label: "shelf of lows (major)"`.

**Excluded from callouts: Mancini's own runners and position talk.** Steve does
not want to read which runner Mancini is holding or when he entered it — skip
*"I am still holding my 10% long runner from the 4:36PM 7325 Failed
Breakdown"*. This exclusion is narrow: it removes **his positions**, not his
level descriptions. An earlier reading of it collapsed every callout to
`major`/`minor` and stripped the plan of its colour; that was wrong. Keep the
level's character, drop the position.

**Commentary** — the `Bull case tomorrow`, `Bear case tomorrow`, and
`In summary for tomorrow` paragraphs are forward-looking conditional guidance
("defend 7435 then rip to 7458, 7472"; "below 7377 opens breakdown shorts").
Capture each distinct conditional idea as a commentary item with its trigger and
anchor prices. Do NOT record past-session recap as commentary.

**Accuracy rules** — these guarantee correctness; they are NOT a licence to omit
a level that is clearly stated:

- Every price you record MUST appear verbatim in the newsletter. Never invent,
  round, or infer a price that is not written. For `source_quote`, copy the
  minimal exact span that contains the price (e.g. `7377 (major)` from a list, or
  the clause for an inline level) — it need not be the whole paragraph.
- Classify each level's `kind` precisely based on Mancini's framing.
- Returning an empty or near-empty `levels` array for a normal Mancini letter is
  a **failure** — the explicit Supports/Resistances lists alone yield dozens of
  levels. Extract all of them.

---

## JSON shape

The file passed to `--extraction-json` is a single object mapping 1:1 onto
`schema.ParseResult.from_dict`. Field names are exact.

```jsonc
{
  "date": "2026-08-03",        // ISO date the plan is FOR; "" if the letter doesn't say
  "instrument": "ES",          // "" if unclear
  "session_bias": "...",       // short prose summary of Mancini's stated directional bias
  "levels": [
    {
      "price": 7449,           // REQUIRED — must appear literally in the letter
      "kind": "support",       // REQUIRED — support | resistance | pivot | target | trigger
      "label": "major",        // optional
      "source_quote": "7449 (major)"   // REQUIRED — verbatim, minimal span
    }
  ],
  "commentary": [
    {
      "text": "...",           // REQUIRED
      "tags": ["bull_case"],   // optional
      "trigger": {             // REQUIRED
        "type": "price_zone",  // REQUIRED — price_cross | price_zone | time | regime | unconditional
        "anchor_prices": [7449, 7530],   // each MUST appear in the letter
        "condition_text": "..."
      },
      "source_quote": "..."    // REQUIRED — verbatim
    }
  ],
  "raw_excerpt": "..."         // the Trade Plan span the levels came from
}
```

`date`, `instrument`, `session_bias`, `levels`, and `commentary` are required
keys. `kind` and `trigger.type` are closed enums — `schema.LEVEL_KINDS` and
`schema.TRIGGER_TYPES` are authoritative; a value outside them fails validation.

The harness stamps `model` and `parsed_at` itself; do not set them. `run.py`
records `model` as `in-session:<label>` so the store shows which route produced
a given plan-day, and hybrid (levels-only) runs record `deterministic-lists`.

It also stamps each level's `callout_quotes` and `callout_attribution`
(`attribution.annotate`, [st-9r51]) — **do not set these either.** They record
which words of your callout are Mancini's and which are yours, and they are
worth nothing if the writer of the prose also grades it. Write the callout the
way the rules above say; the harness marks it `quoted`, `mixed` or `gloss`
against the letter afterwards.

`gloss` is not a defect to avoid. A callout like "bull-case target" is a true
and useful classification that Mancini never wrote in those words, and it should
stay that way rather than be padded with borrowed phrasing to score better. What
the field exists to prevent is the opposite: a characterisation the sentinel
then attributes to Mancini in an alert. Keep quoting him where he said it.
