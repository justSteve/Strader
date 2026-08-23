# Intent Dialect — Design of Record

**Beads:** Intent Dialect Design (st-79z.2) · Intent Dialect Parser (st-79z.3) · epic Trade Language Front (st-79z)
**Date:** 2026-08-22 · **Ruling:** Steve's "Go" on COO's first move (st-xhxs), the same morning
**Entity model:** `docs/research/2026-07-25-trade-language-entity-survey.md` (st-79z.1)
**Code:** `strader/intent/` · tests `strader/tests/test_intent_*.py` · fixtures `tests/fixtures/intent/`

## What it is, in Steve's words

2026-07-26: *"the language that goes into describing a day's price action and the
opportunities we have based on that — from a spoken-word point of view."* 2026-07-27: the
words are *"meta-code that evolves to formal, executable CLI code — a dialect that expresses
trading intent, a UI purpose-built for Strader."* 2026-07-31: *"Instead of ticking boxes on an
order editor, we can speak what we see and have the form pre-populate."*

## The pipeline, as built

```
dictation (typed, or Whisper-local on the COO side)
  → sentences → four extractors, every sentence through all four
      levels (with frame + provenance) · regime (day type, control, pivot, tags)
      intents (if/then branches, with the first move's direction) · structure (the vehicle)
  → DayPlan (persisted after every verb, data/intent/<day>.json)
  → read-back: four tiers, for the eye or for the ear (speech phrasebook prices)
  → direction-anchor echo on every branch; only "yes" arms it
  → price: the latest vehicle resolved against a chain snapshot → Order
      (a directional single also hands the contract to FD0 → budget-derived stop + exit fields)
  → go: TOS paste string + OCC legs (+ the FD0 exit block for a single),
        staged as data under data/intent/staged/. Never sent.
```

## Decisions (each reversible; each a one-line change where it lives)

1. **Deterministic first.** Tables of attested words (`grammar.py`), no model call anywhere.
   A sentence no extractor recognises is read back as "I did not understand", never guessed.
   A model may later be a bounded function over exactly those sentences — a separate bead.
2. **Frames.** Every price carries ES or SPX. A spoken frame word after the number wins
   ("sixty-three twenty spx"); a Mancini or Carmine attribution makes it ES; otherwise the
   day's default, ES, settable with `frame spx`. Every resolution is echoed with its reason.
   The ES→SPX basis is set once per session with `basis <points>`; pricing an ES-framed centre
   without it is refused by name.
3. **A number under 2,000 is not a price** (`PRICE_FLOOR`) — it is a time, a count or a width.
4. **The direction-anchor echo is mandatory** (`knowledge/direction-inversion-watch.md`).
   Setup families in `entities.SETUP_FAMILY`: trap setups pay against the first move,
   continuation setups pay with it. The echo names the first move, what the family pays,
   what Steve said; if they disagree it says INVERTED — and a `yes` still keeps his call.
5. **Mancini and Carmine stay separate namespaces** (st-1s1): a Level carries its source and
   nothing asserts two sources' levels are one level.
6. **TOS strings: single-leg verified, multi-leg inferred.** Until the fixture pass lands
   (st-79z.5, `tests/fixtures/tos/<shape>.txt`), every multi-leg rendering is reported as
   *inferred*, on the page and in the staged ticket. Sub-dollar prices render `.55` (the
   documented example reads `@.20`); FD0's single-leg renderer writes `0.55` — the fixture
   pass settles which, and the two will then be made one function.
7. **`go` never routes.** It writes a staged record and returns the paste line for Steve's
   own hands. The execution gate (st-5ey) and the fire server's covenant are untouched; the
   fire server's own staging file (`data/exec/fire-ticket.json`) is deliberately not written.
8. **Persistence is a value.** The plan is saved whole after every verb; a new Session on the
   same day loads it. The one intent waiting for a yes or no persists too, with the time it
   was staged: a dictation pane runs one line per process, so `yes` has to find what `read`
   staged. `go` refuses while anything waits; a `yes` more than ten minutes after staging is
   refused — the tape has moved, say it again. (The first landing kept the pending intent in
   memory only; the smoke run showed `go` then staging an order nobody had confirmed, and
   that is the direction this rule closes.)

## The verbs (survey §5, as shipped)

| Verb | Does | Answers with |
|---|---|---|
| `read <dictation>` | all four extractors over free text | the read-back, plus an echo per branch found |
| `mark <level talk>` | a level, zone, or the pivot a control clause names | read-back |
| `call <regime talk>` | day type, control, tags | read-back |
| `arm <branch talk>` | stages one intent | the direction-anchor echo |
| `yes` / `no` | arms or drops the staged intent | read-back / "Dropped" |
| `fly` / `single <structure talk>` | a vehicle: width, expiry, right, lots, centre, delta hint | read-back |
| `price` | latest vehicle against the chain snapshot | the order in words, the paste line and its status |
| `go` | stages the priced order, hands back the paste line | "Staged, nothing sent" |
| `stand down` | clears pending and priced | — |
| `frame es|spx`, `basis N` | the defaults | one line |
| `show` | the read-back | — |

Run: `python -m strader.intent [--once "..."] [--speak] [--chain FILE.json] [--day D] [--plan-dir DIR]`.

## The bracket — built 2026-08-23 (st-79z.3 × st-apzt)

A priced **directional single** (a long put or a long call — the futures-proxy play)
now carries an FD0 bracket. At `price`, with the chain in hand, `strader/intent/bracket.py`
hands the chosen contract to FD0's budget engine; FD0 derives the stop distance from its
standing ceiling ($100, two attempts) at the live delta and sets the SPX-conditional
trigger on the loss side — **above** spot for a put, **below** for a call. `price` reads
back the stop and the exit fields; `go` writes them into the staged record's `fd0` block
and prints the exit lines under the paste line. The bracket persists on the plan
(`DayPlan.bracket`), so the one-line-per-process dictation pane can `price` in one process
and `go` in the next.

A **butterfly is defined-risk** — its loss is the debit the dialect already prints — so
there is nothing for a stop to protect and `go` stages it unbracketed. Verticals and
condors the dialect does not price yet, so they are not bracketable either.

The stop the bracket derives is FD0's counter-chase stop, tight by construction ($100/2
funds roughly one SPX point at 0.3δ). That is right for a chase into a flush; whether a
futures-proxy single wants the same ceiling is Steve's to set — the budget is a one-line
default in `bracket()` today.

## What is not built, and where it goes
- **Position and management verbs** (scale, runner, cut): entities exist in
  `market/entities/position.py` and `strader/entities/singleton.py`; the dialect reads
  them next, after a real specimen shows how Steve says them.
- **Vertical and condor pricing** — `_resolve` refuses them by name today.
- **Live chain** — `price` takes a snapshot file; the feed adapter is FD0's `feed.py`.
- **A model as a bounded function** over the unparsed remainder — only after the specimen.
- **The real specimen** (st-79z.4) replaces `tests/fixtures/intent/constructed-day-read.txt`
  as the binding test the day it lands.

## Measured at landing

See the bead's close reason for the test counts and the CLI transcript on the constructed
specimen.
