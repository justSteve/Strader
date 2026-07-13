# 03 · Market Profile — Where Price Spends Its Time

*Foundation series, document 3 of 8. Rests on: [01 · The Auction](01-the-auction.md)
(balance vs imbalance, acceptance vs rejection) and [02 · Volume](02-volume.md).*

---

## The one idea

Market Profile reorganizes the day. Instead of asking "what did price do as time
passed?" (a normal chart), it asks **"how much time did price spend at each
level?"** — and the shape of the answer tells you what *kind* of day the auction is
having. That matters to you directly: your best strategy (the late-day butterfly)
is a bet on one kind of day and gets hurt by another kind, and the profile is how
you tell them apart *while the day is still developing*.

## How a profile is built

Take the day session, cut it into half-hour brackets, and letter them: A for the
first half hour (8:30–9:00 Central), B for the next, and so on. For each bracket,
mark every price it touched with its letter. Stack the letters up at each price.
That's it — the result is called a **Market Profile**, and each letter-mark is
called a **TPO** (Time-Price Opportunity; just read it as "one half-hour visited
this price").

A balanced day builds a bell shape lying on its side:

```
6260
6258    D
6256    CDE
6254    BCDEF
6252    ABCDEFGH     ← fattest row: most time spent here
6250    ABCEFGH
6248    ABGH
6246    AH
6244    A
```

Reading it: the day opened in bracket A, probed as low as 6244 (only A ever went
there — the probe was *rejected*, in document 02's vocabulary), then spent the rest
of the day rotating through the middle. The market found its fair area and did
business there — *acceptance*, made visible.

## The vocabulary that falls out of the shape

Three terms, used constantly on your charts and in Mancini's letters:

- **Point of Control (POC)** — the single price with the most TPOs (6252 above).
  The fairest price of the day: where the auction spent the most time doing
  business.
- **Value Area** — the band around the POC holding ~70% of the day's TPOs
  (roughly one standard deviation, but never mind the math — it's "the middle
  bulge"). Its edges are the **Value Area High (VAH)** and **Value Area Low
  (VAL)**.
- **Initial Balance (IB)** — the range of the first two brackets (the first hour,
  8:30–9:30 Central). It frames the early auction; the day either builds inside
  it (balance) or breaks out of it (possible imbalance). This is the "opening
  range" your opening-range-breakout strategy is built on.

These persist beyond the day they formed. Yesterday's VAH, VAL, and POC are levels
today's traders watch — and a **naked POC** (a prior day's POC that price hasn't
revisited since) acts like unfinished business, a magnet the market tends to
return to eventually.

## Day types — the shapes and what they mean for you

The profile's shape classifies the day. Three shapes carry most of the weight:

**D-shape — balance / rotation day.** The bell above. Two-sided trade around an
agreed value area. Price probes out, gets rejected, rotates back. *This is the
friendly environment for your butterfly:* range-bound close, price pinning back
into value.

**P-shape and b-shape — one-sided days.** Imagine the bell with a long thin stem:

- **P**: stem at the bottom, bulge on top — price rallied hard early (thin stem =
  little time spent, one-directional move) then built value up high. Typically a
  short-covering rally: aggressive buying that *ends* with acceptance at highs.
- **b**: the mirror — a hard sell-off, then value built down low. Typically long
  liquidation.

**Trend day — elongated profile.** No bulge at all; a thin ladder of letters
marching in one direction all day. The auction is in full *imbalance* — searching
for the other side and not finding it. **This is the day that hurts the
butterfly**: there is no rotation back, no pin, no mean-reversion. The single most
valuable thing profile-watching does for you is recognize a developing trend day
by early afternoon and keep you out of reversal trades.

## Single prints — rejection you can point to

When price moves so fast that only ONE half-hour bracket ever touched a stretch of
prices, the profile shows a thin line of solitary letters — **single prints**.
They are the profile's record of *rejection in motion*: the market fled through
those prices without pausing to do business.

Two things about single prints matter to your trading:

1. They mark **emotional, one-sided moves** — exactly the kind of move the
   late-afternoon "sharp drop out of consolidation" produces.
2. The market has a well-documented habit of **coming back to repair them** —
   revisiting those unfinished prices to check whether business belongs there
   after all. That repair tendency is part of the mechanical basis for the
   rally-back your butterfly entry waits for.

(Related profile furniture you'll hear named: a **tail** or "excess" — single
prints at the day's extreme, meaning a probe was firmly rejected, which is
*healthy* structure; and a **poor high/low** — a flat, multiple-letter extreme
with no tail, meaning the auction just ran out of time rather than finding real
rejection, and often gets revisited.)

## Time is not volume — the honest caveat

Market Profile counts *time at price*. Document 02's lenses tell you there's a
sibling question — *contracts at price* — and the two usually agree but sometimes
don't (price can loiter somewhere while very little actually trades). When they
disagree, volume is the more honest witness: business done beats time spent. That
sibling — the Volume Profile — is the next document, and it's where the structure
Carmine Rosato trades comes from.

---

## Check yourself

*Questions only — bring your answers to the open Strader session.*

1. How is a Market Profile physically built, and what does one TPO mark mean?
2. What are the Point of Control, the Value Area, and the Initial Balance — and
   why do *yesterday's* versions still matter today?
3. What's "naked" about a naked POC, and what does the market tend to do about it?
4. A D-shaped day and a trend day: describe each in balance/imbalance terms, and
   say which one the late-day butterfly wants and why.
5. What do single prints record, and why does the market tend to come back and
   repair them?

**Next: [04 · Volume Profile](04-volume-profile.md) — where the business was done,
and the gaps where it wasn't.**
