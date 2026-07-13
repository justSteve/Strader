# 02 · Volume — The Auction's Honesty Meter

*Foundation series, document 2 of 8. Rests on: [01 · The Auction](01-the-auction.md)
(resting vs aggressive orders, why price moves, balance vs imbalance).*

---

## The one idea

Price is an **advertisement**; volume is **business actually done**. Price can move
on nothing — a thin book lets a handful of contracts print a dramatic-looking move.
Volume is the receipt trail: it proves how many participants genuinely committed
money at each price. When price and volume tell the same story, believe it. When
they disagree, the disagreement IS the signal — and most of the reads you'll learn
are named disagreements.

## What volume is (and isn't)

**Volume = contracts changing hands.** One contract traded is one unit of volume,
even though a buyer and a seller both touched it (it's counted once, not twice).

Volume is a measure of **participation**, not direction. 50,000 contracts traded in
an hour tells you the market was busy; it says nothing yet about which side was
pressing. Direction enters only when you split volume by aggressor — who was
impatient, per document 01. That split gets its own document (05 · Order Flow).
For now, volume is simply: *how much business*.

## The three lenses

The same stream of trades can be totaled three different ways, and the three ways
become three different tools:

| Lens | Question it answers | Becomes |
|------|--------------------|---------|
| Volume **over time** | "How busy was each slice of the day?" | The classic volume histogram under a chart; the pace of volume bars (document 06) |
| Volume **at price** | "At which price levels was the business done?" | Volume Profile (document 04) |
| Volume **by aggressor side** | "Which side was forcing the trades?" | Delta and all of order flow (document 05) |

Keep this table in mind — the next four documents are just these three lenses,
taken one at a time.

## Acceptance and rejection

This pair of ideas is the workhorse of everything profile-related, so it's worth
building carefully.

Recall from document 01: the auction advertises price to find business. Volume is
how you *score* each advertisement:

- **Acceptance** — price spends time at a level AND heavy volume trades there. Both
  sides were willing to do business at that price; the market considers it fair
  (for now). Accepted prices act "sticky" when revisited — there's a natural
  population of traders willing to transact there again.

- **Rejection** — price touches a level and leaves quickly, with little volume.
  The advertisement failed: one side refused to play. Rejected prices leave a
  visible hole in the volume record — very few contracts ever traded there. That
  hole is durable information: nobody agreed to do business at that price.

Hold onto the idea of the *hole* — in document 04 it gets its proper name
(low-volume node) and turns out to be the single most important structure in the
zone-trading style we model (Carmine Rosato's method).

## Effort versus effect

The oldest idea in tape reading (it goes back to Richard Wyckoff, a 1910s-era tape
reader whose framework still underlies most of this) is to treat every move as a
physics problem:

- **Effort** = volume. How much force was spent?
- **Effect** = price movement. What did the force accomplish?

Cross them and you get four situations. Plain-language names now; these exact four
become the "single-bar reads" of the drill curriculum later, so the table is worth
sitting with:

| | **Big effect** (price moved) | **Small effect** (price stuck) |
|---|---|---|
| **Big effort** (heavy volume) | **Conviction.** A real fight with a clear winner. Healthy move; expect follow-through. | **Absorption.** Massive force spent, price didn't budge — someone enormous is quietly taking the other side of every trade. The strongest reversal tell there is. |
| **Small effort** (light volume) | **Hollow move.** Price traveled but nobody did business — usually document 01's movement-by-withdrawal: the other side wasn't beaten, it stepped aside. Evaporates on contact with a real opponent. | **Dead.** Nothing happened. Rest. |

The arm-wrestling picture, since it will come back: effort is the strain in the
arms, effect is whether the arm actually moves. A huge strain with no movement
(absorption) doesn't mean nothing is happening — it means the guy on the other
side is far stronger than he looks, and when he decides to push, the arm goes
*his* way fast.

## VWAP — the day's average price, weighted by business

One more volume-built tool, because it's on your charts already:

**VWAP** (Volume-Weighted Average Price) is the session's running average trade
price, where every trade counts in proportion to its size. In plain terms: *the
average price at which the day's actual business was done.*

- Institutions grade their executions against it ("did we buy the day cheaper than
  average?"), which makes it a self-fulfilling benchmark — algorithms lean on it,
  defend it, and revert to it.
- The **standard-deviation bands** around VWAP measure how *stretched* price is
  from the day's average business. Price at the second band down means "far below
  where today's business was done" — a statistical rubber band, and one of the
  confirming conditions for the late-day butterfly entry.

## Calibration: what "a lot" looks like on /ES

Numbers only mean something against a baseline. For the day session on /ES:

- A normal day trades on the order of **1–2 million contracts** (our fixed
  reference day, July 2, traded 1.34 million).
- The drills cut the day into bars of **2,000 contracts each** — so July 2 became
  667 bars. At a quiet lunchtime crawl one such bar can take many minutes; in a
  violent burst it can fill in seconds. Same business per bar, wildly different
  urgency — that inversion is the whole reason drills use volume bars, and it gets
  its full treatment in document 06.

---

## Check yourself

*Questions only — bring your answers to the open Strader session.*

1. Price is called an advertisement and volume the business actually done. What
   kind of lie does that distinction let you catch?
2. The same stream of trades can be totaled three different ways. What are the
   three, and which tool does each become?
3. What do acceptance and rejection mean in auction terms — and what does a
   rejected price leave behind in the volume record?
4. Name the four effort-vs-effect situations. Which one is the strongest reversal
   tell, and what does it say is happening behind the scenes?
5. What is VWAP, and why do its bands work as a "how stretched is price" meter?

**Next: [03 · Market Profile](03-market-profile.md) — reading where price spends
its time.**
