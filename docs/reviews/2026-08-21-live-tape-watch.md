# Live F1–F4 Tape Watch — 2026-08-21

**Bead:** st-9bsi · **Instrument:** `scripts/live_effort_effect.py` +
`grade_atoms_developing()` · **Window:** 08:30–15:00 CT, 391 RTH atoms graded
live · **Session:** /ESU26 open 7695.75, high 7714.00, low 7676.75, close
7691.25 — 37.25-point range on 873,782 lots.

Second full watch, and the first run as a two-way conversation rather than a
narration. Steve issued two standing corrections mid-session; both are recorded
below because they changed the instrument as much as any code would.

---

## 1. The session in one line

An 08:30 rejection at 7695 on the day's heaviest non-auction bar, a flush to
7676.75 that was fully reclaimed, a 37-point grind to 7714.00 by 10:53 that ran
on *falling* delta, then four hours of two-sided absorption that closed four
points below where the day started fighting.

## 2. The conversion asymmetry — and a correction to what I said live

Points bought per 1,000 net contracts, bars with |delta| >= 300:

| period | buy bars | buy conv | sell bars | sell conv |
|---|---|---|---|---|
| 08:30–09:42 open + flush | 12 | **3.81** | 3 | 1.35 |
| 09:43–10:51 the grind up | 11 | 2.87 | 8 | **3.63** |
| 10:52–13:59 midday chop | 5 | 1.91 | 12 | **4.20** |
| 14:00–14:58 closing hour | 4 | 2.09 | 8 | **3.00** |
| **whole RTH** | | **2.82** | | **3.36** |

**I had this backwards in the live commentary.** Through the 10:00–10:06 fight
at 7695 I repeatedly framed it as sellers paying heavy delta and getting
nothing. Locally at that level that was true. Across the session it is not:
**buyers held the conversion edge only in the opening hour. From 09:43 onward
sellers converted better in every period — including the period when price rose
37 points.**

That inverts the explanation of the morning rally, and the better explanation is
the one Steve supplied unprompted: *"a range that is void of orderblocks
suggests a range that can be run thru."* Price rose 7695 → 7714 not because
buyers were efficient but because **nothing was there**. The tell was on the
tape at 10:41 — price closed +1.25 on `d−157`, rising on net selling, offers
pulled rather than bids hit. A void, not a bid.

**The largest delta prints almost all converted badly**, which is the same
finding from the other side:

| CT | vol | delta | net | pts/1k |
|---|---|---|---|---|
| 14:59 | 60,386 | **+2,546** | −4.75 | 1.87 |
| 10:34 | 4,507 | +1,851 | +2.25 | 1.22 |
| 10:39 | 3,488 | +1,218 | +4.00 | **3.28** |
| 08:49 | 4,647 | +1,151 | +2.25 | 1.95 |
| 10:51 | 2,820 | +1,040 | +1.50 | 1.44 |

Four of the five biggest buy imbalances of the day bought under 2 points per
thousand. Only 10:39 was paid properly — and it was paid the minute the 7700
supply cleared, which the live read caught in flight.

## 3. The gauge — one clean divergence, one clean non-ratification, one confirm

**Divergence at the high.** Cumulative TICK peaked **+4,799 at 10:46**. Score ran
+43 (10:45) → 0 (10:48) → **−18 (10:51)**. Price made its high at **10:53**.
Internals topped seven minutes before price.

**Non-ratification at 11:21.** The day's most violent minute — 14,403 lots,
11.25-point range, +556 TICK, gauge score **+61 "TICK climax"** — and
**cumulative TICK fell through it**, +3,101 → +2,852. A spike that leaves cum
TICK lower is a spike being sold. Price gave back 7.75 of its 11.25 points
inside the same minute.

**Confirmation at 14:50.** Cum TICK negative for the first time (−642), score
−15, on the best-converted sell bar of the day. This is the only moment all
session where OF and gauge pointed the same way with force.

Full arc: **+4,799 (10:46) → −1,298 (14:55) → −1,139 (14:58)**. A ~6,100-point
round trip while price travelled 37. ADD and VOLD never confirmed the damage —
VOLD climbed all day to +7.94B.

## 4. The decision stack, run live

Steve proposed it mid-session (captured on st-lrjf). Ran it once, at 11:50,
against the best-converted sell bar of the morning:

1. **Chop prior** — displaced. 2,876 lots against a 521–1,589 run rate.
2. **Conversion** — 538 sellers bought 2.75, twice any earlier sell.
3. **Persistence gate** — **failed on the next bar.** 11:51 halved to 1,319 and
   closed +0.50 higher.
4. **Gauge** — weak ratification only; cum TICK bleeding, minute scores flat.
5. **Travel** — void below, no shelf between 7677 and 7693.

Verdict was chop-not-displaced, and it held. **Without the persistence gate I
would have led with "sellers are finally converting."** That is the stack's
first save, on its first live use.

## 5. Two corrections to the live reads

- **RTH high was 7714.00 at 10:53, not 7711.50 at 10:51.** I sampled 10:51 and
  then jumped to 10:56, missing the actual high. It matters: the day got within
  **2 points of 7716**, not 5. Closer to the gate than I reported.
- **RTH low was 7676.75 at 08:54, not 7677.25 at 09:41.** The 08:54/08:55
  absorption pair closed 7679.50 twice with net 0.00 — the read stands — but the
  08:54 bar wicked to 7676.75. I was reading closes from a column that had no
  highs and lows in it.

Both are the same defect: reading a derived table instead of the bar.

## 6. Instrument problems

**6a. The baseline defect reproduced a third time.** RTH cell mix across 391
atoms: **F1 231 (59.1%), F2 160 (40.9%), F3 0, F4 0.** Zero F3 and zero F4 for a
third consecutive session. This is settled — the corpus dose-response filed to
COO on 2026-08-21 (`docs/a2a/2026-08-21-strader-to-coo-dev-baseline-dose-
response.md`) shows RTH's F3+F4 share tracking overnight share 79.0% → 48.7% →
2.2% → 0.3%. Nothing further to learn from another live day; the fix is st-dioq.

**6b. My own alert filter had the same class of bug four times.** A threshold on
close (`c >= 7695`) fires every bar while price *sits* there — it encodes a
state, not an event, so it narrated a level instead of announcing one. Retuned
three times before fixing it properly with hysteresis: fire once on entry,
re-arm only after price clears a band. That is the pattern
`scripts/orderflow_sentinel.py` already documents. Should have been copied, not
rediscovered.

## 7. Follow-ons

- **st-lrjf** — the decision stack and the strats-as-characters frame. Rung 1
  ("does PA fit an accepted strat") is `PlaybookEvaluator`, built and unwired
  since July. The stack is the live consumer it never had.
- **Order-block supply is the weak link.** It depends on Steve pasting zones and
  will fail hardest on his busiest days. Either mark once pre-session or derive
  candidates from corpus and have him correct them.
- **Conversion (pts per 1,000 net contracts) deserves to be emitted**, not
  computed by hand after the fact. It out-performed both delta and volume alone
  as a live read and it is one division.
