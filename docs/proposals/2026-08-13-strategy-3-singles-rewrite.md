# Proposed rewrite — CLAUDE.md Strategy 3

> **WITHDRAWN 2026-08-13, same day, unapplied.** Steve's answer was that the
> section fails the membership test rather than that it had the wrong content:
> *"there isn't any action you could take that will depend on it."* Strategy
> mechanics come out of `CLAUDE.md` entirely — see st-ylqw. Kept as a record of
> what was proposed and why it was the wrong instinct: it argued about the
> content of a section that should not exist. Its three open questions
> (trade-count cap, slot-3 vs. full transition, hold duration) are moot.

Bead: st-mfpm (closed, superseded) · drafted 2026-08-13 · **never applied**

You said on 08-13: *"rewrite existing strat at next session."* This is that
draft. Nothing has been written into `CLAUDE.md`; the trading judgment is yours,
so it waits on your word.

---

## Why this needs rewriting at all

Your 08-08 redirect to singles went to COO, got duplicated into COO's memory,
and never landed here. So the file I load every single session still teaches
Strategy 3 as PAC range scalps — 3-to-5-point oscillations between pivot
boundaries, 2-3 trades a session.

That matters more than a stale doc usually would. `CLAUDE.md` is always loaded;
the memories carrying your actual intent are only retrieved when something
reminds me to look. When the two disagree, the loaded one wins by default —
which means for five days I have been running on the version you replaced.

---

## What is actually wrong with the current text

Three things, in descending order of how much they'd distort a live read:

1. **It requires price to stay put.** "Price oscillates within a defined range,"
   "A+ level bounces," "not every oscillation." A single is a directional
   vehicle — it wants price to *leave* the level, not rotate around it. The old
   text has the same shape as the fly error you corrected four times: it treats
   the level as the place price stays, when the level is where price departs
   from.
2. **The friction math was written for a different vehicle.** "3-5 point SPX
   moves (wider than a futures scalper) to overcome option spread friction"
   — that widening was priced against multi-leg fills. A single crosses two
   spreads per round trip, not twelve. The target floor should not simply be
   inherited.
3. **It never says what a single *is* to you.** Your frame — an option single is
   a futures contract on its last day — is the whole reason the strategy works
   and the reason existing futures playbooks port over. It appears nowhere.

---

## The proposed replacement

> ### Strategy 3: Long Single-Leg Directional (Singles)
>
> Long single SPX options — calls or puts — traded as a proxy for a futures
> strategy. Steve's frame: *"if it works for futures, unless it is in direct
> contravention to the relevant Greeks — an option single is a futures contract
> on its last day."* A 0DTE single tracks the underlying closely enough that
> order-flow, supply/demand, and scalping playbooks port over directly. The job
> is to adjust only where the Greeks force it — theta cliff, gamma convexity,
> spread friction — not to invent options-native rules from scratch.
>
> **Bearish is long premium.** No short or credit positions, ever — but a
> bearish read is a long put, traded exactly like a bullish call. A
> responsive-seller zone in a plan source is a long-put entry, never "not
> applicable."
>
> - **Setup:** a directional read with room to travel. Order-flow conviction
>   (cumulative delta, footprint) into a confluence level, with GEX pointing the
>   same way. The level framework is unchanged — LuxAlgo PAC zones, Mancini
>   levels, volume nodes, VWAP bands — but price is expected to *leave* the
>   level, not rotate around it.
> - **Entry:** at the zone, on confirmation. Initiative trade *through* the zone
>   kills the idea rather than improving it.
> - **Strike:** leaning ITM buys a cleaner futures proxy — higher delta, tighter
>   spread relative to the move. Whether that means ~.3Δ or ~.6Δ is genuinely
>   unsettled and waits on the rider study; do not state a default as though it
>   were decided.
> - **Exit:** on the repricing, not on a clock. The instrument for this does not
>   exist yet — the candidate is the orderflow stall signal, heavy delta that
>   stops moving price. Both sides showed live on 8/11: a +499 bar at 13:42
>   (above p95) produced 0.5 points and the move was done; +2,249 cumulative
>   across 14:15–14:22 produced +6.25 points and it was still running.
> - **Why a single and not a fly here:** execution overhead. Three legs times two
>   contracts is twelve fills and twelve spreads crossed per round trip, against
>   two for a single. Over a short hold that is most of the edge. This is the
>   stated reason and it is **not** payoff shape — a far-OTM fly pays from the
>   first favorable tick and has no dead zone. Any argument from settlement
>   payoff is answering a question Steve is not asking.
> - **Status:** the direction is settled; the calibration is not. The MFE/MAE
>   scoring harness the 08-08 redirect asked for still does not exist, and the
>   overhead claim above is asserted rather than measured. Treat the numbers here
>   as intent, not evidence.

---

## Five other places in CLAUDE.md that contradict it

A rewrite that fixes the section and leaves these behind reproduces the same
failure in miniature. All five are one-liners:

| Line | Now | Proposed |
|---|---|---|
| 166 | PAC is "primary tool for **range scalping setups**" | "primary tool for locating **entry zones for singles**" |
| 194 | table row: "All session \| **Range scalps (if A+ setup)** \| PAC levels, Volume Profile nodes" | "All session \| **Singles (if A+ directional setup)** \| PAC zones, Volume Profile nodes, Cumulative Delta" |
| 225 | goal 6: "calibrate **range scalping criteria** — which PAC levels warrant entries and which are noise" | "define the A+ directional setup for singles and **build the exit-timing instrument** — the profit-taking skill you named" |
| 236 | "selecting appropriate strikes for ORB and **scalp plays**" | "moneyness selection for ORB and **singles**, where leaning ITM buys a cleaner futures proxy" |
| 267 | domain knowledge: "**Range scalping with options** — spread friction awareness, strike selection for scalps, overtrading risk" | "**Single-leg 0DTE as a futures proxy** — delta/moneyness selection, spread friction, execution overhead vs. multi-leg" |

---

## Three things I did not decide for you

**1. The trade-count cap.** The old text says 2-3 per session maximum. That
number was justified by spread friction on a structure that crossed twelve
spreads; a single crosses two, and PDT is gone. I did not carry it forward and
I did not invent a replacement. Options: drop the cap entirely, keep 2-3, or
replace it with a daily-loss stop instead of a count. Your call — the honest
position is that nothing measured supports any of the three.

**2. Whether this is still slot 3.** The bead you gave me scopes this as
rewriting Strategy 3. But your 08-11 words after the breakeven fly exit were
*"here's why i want to transition to singletons. too much overhead with flies"* —
that reads as a transition away from Strategy 1, not a tidy-up of Strategy 3.
This draft holds to the narrow scope and leaves flies as the primary. If the
larger reordering is what you actually meant, say so and I will draft that
instead; it is a bigger change than this one and shouldn't ride in quietly.

**3. Hold duration.** Your 15-minute lean is deliberately not formalized and I
have not formalized it. The "5-15 minute windows" in the redirect are a
*scoring* window for measurement, not a hold rule, and the draft says "on the
repricing, not on a clock."

---

## What lands if you approve

`CLAUDE.md` only — the section plus the five one-liners. No knowledge-bundle
concept is touched by this; `buying-movement-delta-first.md` already carries the
singles doctrine correctly and this rewrite is bringing the loaded file up to
canon, not changing canon. `knowledge/log.md` gets a line citing st-mfpm.
