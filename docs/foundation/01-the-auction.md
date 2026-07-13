# 01 · The Auction — What a Market Physically Is

*Foundation series, document 1 of 8. Rests on: nothing. Everything else rests on this.*

---

## The one idea

A futures market is a **continuous two-way auction**. Not "like" an auction — it
literally is one, running every millisecond the exchange is open. Everything you will
ever read on a chart is a record of this auction's proceedings. When the auction
mechanics are clear, concepts that sound advanced (delta, absorption, low-volume
nodes) turn out to be simple arithmetic on auction events.

## The two kinds of orders

Every participant in the auction does one of two things:

**Resting orders** (the official term is *limit orders*). "I will buy at 6250.00 and
not a tick higher. I'll wait." This order sits in the exchange's queue at its chosen
price until someone comes to meet it, or it's cancelled. The resting trader has
chosen their **price** but given up control of **when** — maybe they get filled in a
second, maybe never.

**Aggressive orders** (the official term is *market orders*, plus limit orders priced
to trade immediately). "Fill me NOW at whatever's available." The aggressive trader
has chosen their **moment** but given up control of price — they pay whatever the
best waiting order demands.

Remember it as a trade-off: **resting = price certainty, no time certainty.
Aggressive = time certainty, no price certainty.** Every trade that ever prints is
one aggressive order meeting one resting order. Both sides are always present in
every single trade.

Keep that sentence narrow: it describes every **trade**. It says nothing yet about
price **movement** — most trades move nothing at all, and movement turns out to
have more than one source (below). Conflating trades with movement is the most
common confusion at this stage, and worth stamping out early.

## The book

The exchange keeps a live ledger of every resting order, organized by price. It's
called the **order book**, and pictured as a ladder:

```
price      resting SELL orders (offers/asks)
6251.00    ▓▓▓▓▓▓▓▓  412 contracts offered
6250.75    ▓▓▓▓▓     230 contracts offered
6250.50    ▓▓▓       118 contracts offered   ← best offer
           ─────────  ← the spread (0.25 here — one tick)
6250.25    ▓▓▓▓      165 contracts bid       ← best bid
6250.00    ▓▓▓▓▓▓    301 contracts bid
6249.75    ▓▓▓▓▓▓▓▓  388 contracts bid
price      resting BUY orders (bids)
```

Vocabulary, all of which you'll meet constantly:

- A resting buy order is a **bid**. A resting sell order is an **offer** (also
  called an *ask* — same thing).
- The highest bid is the **best bid**; the lowest offer is the **best offer**.
- The gap between them is the **spread**. On /ES it is almost always one tick
  (0.25 points) because the market is so heavily traded.
- The word **liquidity** just means "how much resting size is in the book." A
  liquid market has thick walls of resting orders; a thin one has sparse ones.

## What "buying volume" actually means

Here's a puzzle that trips up almost everyone: every trade has a buyer AND a
seller — one contract changing hands is one buy and one sell, always, by
definition. So how can anyone speak of "buying volume" or "selling pressure"?

The answer is the aggressor. In every trade, one side was resting (they set the
price and waited) and one side was aggressive (they crossed the spread to force the
trade NOW). The trade is labeled by **who forced it**:

- Aggressive buyer lifts a resting offer → counted as **buy-aggressor volume**
  ("buying volume").
- Aggressive seller hits a resting bid → counted as **sell-aggressor volume**
  ("selling volume").

That's the entire trick. "Buying pressure" never means more buyers than sellers —
that's impossible. It means **the buyers were the impatient ones**: they kept paying
up to trade immediately, while sellers were content to sit and let price come to
them. Impatience is information. It tells you which side *needs* the trade.

One more fact that makes /ES special: on CME futures the exchange itself tags every
trade with the aggressor side. Stock traders have to guess the aggressor from price
movement and get it wrong on a meaningful fraction of trades. On /ES it's stamped on
the record — which is why order-flow reading is more trustworthy here than nearly
anywhere else. (A small number of trades — at the open, after a halt — genuinely
have no aggressor and are tagged as such; our tooling keeps them in a separate
bucket rather than letting them pollute the count.)

## Why price moves

Price does not drift, float, or get pushed by sentiment rays. Price ticks up when
**the best offer empties** — with nothing left for sale at 6250.50, the next
resting offers, at 6250.75, become the best offer. That's the entire event we call
"price went up a tick." Downward moves are the mirror image.

Notice what that implies: **a trade and a price change are different events.**
Most trades just chip at the best level without emptying it — thousands of trades
produce only hundreds of ticks of movement. A trade is two parties doing business;
movement is a level *running out*.

And a level can run out in two different ways:

1. **It gets eaten.** Aggressive buyers consume every resting offer at the level.
   Movement by **aggression** — and it's loud: every contract consumed prints on
   the public record as a trade you can see and count.
2. **It gets abandoned.** The sellers *cancel* their resting offers and step away —
   news hits, or they lose their nerve. Not one contract trades, nothing prints,
   and yet the best offer is suddenly higher. Movement by **withdrawal** — silent,
   because a cancelled order leaves no trade behind.

Real moves are a blend of the two, but the mix is readable. A move the market
**paid for** — heavy aggression eating thick levels, lots of contracts printing —
is a move with fuel and proof behind it. A move the market was **given** — price
stepping through near-empty or fleeing levels on almost no trades — proves nothing
about anyone's conviction. Opening gaps and news spikes are the extreme case:
whole ladders of orders get pulled and price relocates almost without trading.

Same green candle either way. **Telling paid-for movement from given movement is,
in one sentence, what all of order-flow reading is for** — and it's why price
alone always needs volume (document 02) next to it.

## What the auction is trying to do

Steidlmayer (the Chicago trader whose framework becomes document 03) put it best:
the market's job is to **advertise price to find business**. The auction constantly
probes: is this price fair?

- Price probes **too high** → sellers get eager, buyers step back → business dries
  up on the buy side → price rotates back down. The probe *failed*: that price was
  rejected.
- Price probes a level and **business explodes there** — both sides willing to
  trade in size → the market has found a fair area and will oscillate around it.
  That price was *accepted*.

Two working definitions that carry through the whole series:

- **Balance** — the auction has found a fair area; price rotates around it in
  two-sided trade. Most of the time, most days, the market is in balance.
- **Imbalance** — one side has taken over and the auction is *searching*: price
  moves directionally, seeking the level where the other side will finally do
  business again.

Every day, every hour, the market is in one of those two states, and nearly every
tool in your toolkit is a way of asking "balance or imbalance, and where?"

## /ES nuts and bolts

| Fact | Value | Why you care |
|------|-------|--------------|
| Contract | E-mini S&P 500 future, CME Globex | The deepest, cleanest S&P order book in the world |
| Tick size | 0.25 index points | The rungs of the ladder; footprint rows are one tick each |
| Tick value | $12.50 per contract | 4 ticks = 1 point = $50/contract |
| Session | ~23 hours; day session (what we study) 8:30–15:00 Central | Our corpus and drills are day-session only |
| Typical day volume | On the order of 1–2 million contracts | Our reference day (July 2) traded 1.34M in the day session |

---

## Check yourself

*Questions only — no answers anywhere in this series. Bring yours to the open
Strader session, in your own words, and it will probe from there.*

1. A resting order and an aggressive order each give something up and get
   something in return. What, for each?
2. Every trade has exactly one buyer and one seller — so what can "buying volume"
   possibly measure?
3. Most trades don't move price at all. Why not? What exactly has to happen for
   price to tick up?
4. A price level can empty in two different ways. What are they, and which one
   leaves a trace on the tape?
5. Two identical-looking green candles: one heavily traded, one barely traded.
   What might each mean, and which would you trust?

**Next: [02 · Volume](02-volume.md) — the auction's honesty meter.**
