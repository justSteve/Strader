# 05 · Order Flow — The Trade-by-Trade View

*Foundation series, document 5 of 8. Rests on: [01 · The Auction](01-the-auction.md)
(aggressor vs resting) and [02 · Volume](02-volume.md) (effort vs effect).
Depth companion with sources: `docs/research/2026-07-03-orderflow-primitives-research.md`.*

---

## The one idea

The profiles (documents 03–04) gave you the map — what kind of day, and where the
**decision prices** sit. A decision price is document 04's "decision point"
generalized: any price the market can't just drift through — a low-volume node, a
prior value edge, a range extreme, a naked POC, a widely watched level — because a
stored pile of commitments (stops, waiting entries, defenders) must resolve when
price arrives. Contrast the middle of a value area, where price can rotate all
afternoon with nothing at stake. Order flow is the **live camera at the decision
price**: as price arrives, it shows you which side is pressing, whether the
pressing is working, and whether someone big is quietly standing in the way —
which answer is winning, while the question is still being asked.
Every order-flow tool is arithmetic on one fact you already own from document 01:
every trade is tagged by who forced it — the aggressive buyer or the aggressive
seller.

## The raw material: the tape

The exchange publishes every trade as it happens: price, size, and (on CME futures)
the aggressor tag. This stream is the **tape** — the phrase "reading the tape" is a
century old and means exactly this. Nobody reads it print-by-print anymore; the
tools below are all ways of summarizing it faster than the eye could.

## Delta — the pressure gauge

**Delta** (for any slice of the day — one bar, one hour, whatever) is:

> buy-aggressor volume − sell-aggressor volume

That's the whole definition. A bar with delta +420 means impatient buyers forced
420 more contracts than impatient sellers did during that bar. Delta is the auction
answering *"who was pressing, and how hard?"* — one number per bar.

The running total from the session open is **cumulative delta** (also "session
delta" — on the drill screen it's the `Session Δ` readout). Guard against a
natural misreading: cumulative delta is a **signed** sum, not a volume-like
counter that only grows. It *falls* during every bar the sellers dominate and
rises when the buyers do — it wanders up and down all day, like price does. Two
rules for using it:

- **The level means nothing; the trend means everything.** Cumulative delta's
  absolute value depends on where the count started. Read its *slope* and its
  *turns*, never its number.
- **It's evidence, not a trigger.** Delta tells you who's pressing. Whether the
  pressing *matters* depends on where price is (the map) and what price does about
  it (effect).

## Divergence — when pressing stops paying

Now combine delta with price and you get the first real signal:

**Divergence** = price makes a new extreme, but delta doesn't confirm it. Example:
price grinds to a new low of the day, but cumulative delta sits *higher* than it
was at the previous low. Translation: the sellers pressing this new low are fewer
or weaker than the ones who made the last low — **the pressing is no longer being
paid**. That's document 02's "effort without effect" caught in the act, and it's
the classic early warning of **exhaustion**: the aggressive side running out of
participants.

Exhaustion is early, not precise. It says "this move is running on fumes," not
"reverse now." It earns its keep as a *background condition* — the reversal setups
you'll drill are far more trustworthy when the flush into them shows fading delta.

## Absorption — the strongest single tell

From document 02's effort-vs-effect table, the top-right cell — big effort, no
effect — was named **absorption**. Now you can see its machinery:

Aggressive sellers hammer a price. Heavy sell-aggressor volume prints, trade after
trade. And price... does not go down. For that to be mechanically possible
(document 01: price falls when resting bids are consumed), someone must be
**refilling the resting bids as fast as they're eaten** — a participant with
enormous size, patiently buying everything thrown at them, at one price, without
chasing.

That is absorption: *visible aggression meeting invisible, bottomless patience.*
The aggressive side is spending its ammunition into a wall. When the ammunition
runs out — and it always runs out — the wall's owner is sitting on a massive
position acquired at one price, and the path of least resistance flips hard the
other way.

Why would anyone trade this way? Because for genuine size, it's the ONLY way in.
A player who wants thousands of contracts has a problem small traders never face:
their own order is big enough to wreck their own price. Buy aggressively at that
scale and every fill pushes price higher — they end up chasing their own demand.
So size must sit still at a chosen price, passive, and let the market deliver.
Seen from that chair, a panic flush is a *fire sale*: a crowd of forced sellers
dumping inventory at one price, into the one buyer built to take it all. The
absorber isn't nobly defending a level at a loss — they're **shopping**, and the
"dampening" of the move is a side effect of how size has to shop. (Carmine's word
for the fingerprint is the **re-load**: the resting orders getting eaten and
reappearing at the same price, again and again.) They can still be wrong — the
level can fail and they eat the loss — but risk of loss and intent to lose are
different things.

Distinguish the two ways a move stalls, because they look similar and mean
different things about *who* is in control:

| | Exhaustion | Absorption |
|---|---|---|
| What stops the move | The aggressors thin out (fewer pressing) | The aggressors keep pressing but a resting giant eats them |
| Delta looks like | Shrinking bar deltas into the level | Big, loud deltas — with no price progress |
| Who's in control after | Nobody yet — vacuum | The absorber — and they now hold size |

Both are reversal conditions; absorption is the stronger and more precise one,
because someone *proved* their intent with size.

## Sweeps and urgency

One more pattern worth naming: a **sweep** — a single aggressive order so large it
consumes several price levels of the book at once. Sweeps are the loudest form of
impatience: someone wanted in/out NOW, at any price. By construction a sweep moves
price *at the moment it executes* — it walks through several rungs of resting
orders. The information is in what happens next: if fresh orders instantly re-load
the eaten rungs and price snaps back, the sweep failed to make the move *stick* —
the most motivated order type in existence was fully digested, which means someone
even bigger is on the other side. A sweep *into* a key level often starts the
violent flush you'll study in document 07; a sweep that can't make price stick is
as strong as tells get.

## The compass, assembled

Everything in this document folds back into the two words from document 02, now
with precise instruments behind them:

- **Force** = aggression = delta, its size and side.
- **Effect** = price progress.

Force *with* effect: healthy move, respect it. Force *without* effect: absorption
or exhaustion — reversal conditions, identified by whether the force is loud
(absorption) or fading (divergence/exhaustion). Effect *without* force: hollow
move over thin liquidity; don't trust it. That compass — not any single number —
is what you're actually training in the drills.

## What order flow cannot do

Kept explicit, because over-trusting the tape is how order-flow traders die:

- It reads the **present**, not the future. Absorption can be overrun; the
  absorber can be wrong, or can quit.
- It's meaningless in the **middle of nowhere**. The same delta pattern that means
  everything AT a mapped level (documents 03–04) is noise in the middle of a
  range. Flow answers "what's happening HERE?"; the map decides whether HERE
  matters.
- It needs **calibration to context** — 2,000 contracts of absorption at 2 PM on a
  quiet day is enormous; the same at the open is Tuesday.

---

## Check yourself

*Questions only — bring your answers to the open Strader session.*

1. Define delta in one sentence. Why does cumulative delta's slope matter while
   its absolute level means nothing?
2. Price makes a new low of the day, but cumulative delta sits higher than at the
   previous low. What is that called, and what does it say about the sellers?
3. Exhaustion and absorption both stop a move. Who stops it in each case, what
   does the delta look like in each, and who is in control afterward?
4. What is a sweep, and what does it mean when even a sweep fails to move price?
5. Why is order flow only meaningful at mapped levels — and which tools supply
   the map?

**Next: [06 · Bars and the Footprint](06-bars-and-the-footprint.md) — the display
that shows all of this at once, and how to read every element of the drill screen.**
