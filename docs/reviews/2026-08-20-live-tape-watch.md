# Live F1–F4 Tape Watch — 2026-08-20

**Bead:** st-vts8 · **Instrument:** `scripts/live_effort_effect.py` +
`grade_atoms_developing()` (st-v0rj) · **Window:** 10:37–15:02 CT, 903 atoms
graded live · **Session:** SPX −66.16 (−0.86%) to 7641.82; /ESU26 7666.00,
low 7659.00.

This is the first full afternoon the live effort-vs-effect grader ran as a
watched surface rather than a print to a pane. What follows is what it showed,
what the tape actually did, and the two places the instrument's own baseline
got in the way.

---

## 1. The afternoon in one line

A 115-minute absorption range at 7670–7677 that looked like it would hold into
the close, broke at 14:45, faked a full recovery at 14:49, and then produced
every volume and delta record of the afternoon in the last fifteen minutes.

## 2. The range, 12:5x–14:43

| | |
|---|---|
| Boundaries | 7670.00 floor · 7675.25–7677.75 ceiling |
| Duration | ~115 minutes |
| Floor defences | 7 (13:59, 14:00, 14:02, 14:20, 14:31, 14:33, 14:42) |
| Ceiling stalls | 5 (13:48, 14:07, 14:15, 14:25, 14:39) |

The character was absorption, and the grader named it as such — F2 dominated,
with `effect_pct` collapsing to 5–49 on `effort_pct` in the 60s–80s. Three
prints carried the read:

- **14:00** — 3,157 lots, delta **−289**, price closed **+0.50**. Sellers
  dumped size at the floor and it was taken.
- **14:25** — 2,217 lots, effect **5**, net **0.00** at the ceiling.
- **14:52** — 3,933 lots, effort 94 / effect **5**, net **0.00**, grade 0.88 —
  the cleanest absorption print of the watch.

A recurring signature inside the range: price rose three separate times on
**flat delta** (13:42 d+8, 14:02 d−1, 14:15 d+1). Each lift came from sellers
withdrawing, not buyers pressing.

## 3. The break

| CT | vol | delta | net | rng | effort/effect | grade | note |
|---|---|---|---|---|---|---|---|
| 14:34 | 3,145 | −251 | −0.25 | 2.00 | 89 / 18 | 0.64 | probe to 7668.75, rejected same bar |
| 14:45 | 4,225 | −451 | −0.75 | 3.25 | 95 / 49 | 0.02 | floor gone, but still absorbed |
| 14:49 | 3,183 | +145 | **+3.25** | 3.50 | 90 / 95 | 0.80 | full V-return, +6.25 in three bars |
| 14:50 | **6,543** | −109 | −1.25 | 4.25 | **100** / 69 | 0.38 | closing flow arrives, two-sided |
| 14:54 | 9,050 | −588 | −3.50 | 5.50 | 100 / 96 | 0.92 | through 7665 |
| 14:55 | **12,777** | −891 | −3.75 | 6.50 | 100 / 97 | **0.94** | acceleration |
| 14:58 | 9,541 | **+1,201** | +2.50 | 3.50 | 100 / 92 | 0.83 | buyers take 7660.25 |
| 14:59 | **59,876** | +266 | +1.50 | 7.00 | 100 / 76 | 0.51 | auction: low 7659.00, reclaimed |

The 14:49 V-return is the trap in the sequence. It graded 0.80 — at that moment
the highest of the watch — and it was fully reversed within five minutes.
Grade magnitude marked *that the move was efficient*, not that it would persist.

## 4. Volume stopped buying displacement — then started again

Steve's read at 14:41 was "just not enough vol for the big moves." Measured
against the day, volume was mid-pack, not thin; what had failed was conversion.

| | avg vol | avg \|net\| | avg rng |
|---|---|---|---|
| whole day, heavy bars (≥2400) | 3,708 | **1.95 pts** | 3.88 |
| whole day, light bars (<1400) | 409 | 0.80 pts | 1.51 |
| since 13:40, heavy (≥2000) | 2,514 | **0.78 pts** | 1.95 |
| since 13:40, light (<1600) | 1,350 | 0.64 pts | 1.44 |

Per-minute volume by hour CT: 08:00 2,803 · 09:00 3,572 · 10:00 3,086 ·
11:00 1,643 · 12:00 1,691 · 13:00 1,875 · 14:00 1,847.

So the 14:00 hour ran *above* both lunch hours. Earlier in the day 3,700 lots
bought ~2 points; from 13:40 to 14:44, 1.9× the volume bought 1.2× the
movement. Four minutes after the observation, the conversion returned and
every record of the afternoon printed.

**The read that would have helped is the ratio, not the level.** Volume alone
was never the signal; volume-per-point was.

## 5. GEX walked down with price all day

| CT | spot | major + | major − | gamma flip |
|---|---|---|---|---|
| 08:30 | 7708 | 7710 | 7700 | 7716 |
| 09:00 | 7686 | **7735** | 7640 | 7715 |
| 10:30 | 7687 | 7690 | 7640 | 7669 |
| 11:31 | 7673 | 7700 | 7665 | 7666 |
| 13:00 | 7663 | 7700 | 7640 | 7665 |
| 14:15 | 7654 | 7670 | 7650 | 7649.70 |
| 14:43 | 7650 | 7660 | 7640 | 7650.00 |

Two things worth carrying:

- **Major positive walked 7735 → 7660**, tracking spot rather than holding a
  level. It did not act as a magnet above price; it followed price down.
- **The gamma flip collapsed 7716 → 7650**, a 66-point move, and SPX crossed
  beneath it at ~14:43 — roughly two minutes before the break accelerated.
  The session low, SPX 7639.01, landed on the 7639.93 short-gamma level.

[ALERT] The 0DTE major positive **flickered 7660 ↔ 7670 between consecutive
80-second polls** for ~25 minutes (14:03–14:15). Read that field as a band
during compression, not as a settled strike.

## 6. Two instrument problems this session surfaced

### 6a. The day-relative baseline is overnight-dominated (COO's st-dioq)

Independently confirmed on a second day, and worse than the 08-19 figures:

| window | F1 | F2 | F3 | F4 |
|---|---|---|---|---|
| RTH 08:30–15:00 (n=391) | 219 | 172 | **0** | **0** |
| overnight <08:30 (n=510) | 244 | 123 | 57 | 86 |

RTH produced **zero F3 and zero F4 atoms all day**. Every F3/F4 in the session
came from the overnight book.

### 6b. The grade ranks thin overnight bars above the day's real moves

The ten highest developing grades of the session are all overnight or early
morning. The sharpest contrast:

| CT | vol | net | grade |
|---|---|---|---|
| 03:46 | **643** | −4.00 | **0.97** |
| 14:55 | **12,777** | −3.75 | **0.94** |

A 643-lot bar outranks a 12,777-lot bar that moved price nearly as far. This is
not a bug in `grade_atoms_developing()` — the causal percentile is doing exactly
what it is defined to do — it is the baseline underneath it. Any live grade
ranked against a full day that is 56% overnight will read a quiet 3 a.m. push as
more exceptional than the closing break.

**Consequence for the live surface:** the printed `effort_pct` in the 60s–80s
through the afternoon overstated how heavy those bars were in RTH terms. The
grader's *relative* movement within the afternoon stayed informative; its
*absolute* percentiles did not.

## 7. What the watch got right, and what it did not

**Right:**
- Named the absorption character of the range from the effort/effect divergence
  before the level structure made it obvious.
- Caught the flat-delta lifts — price rising on sellers withdrawing — three
  separate times, a distinction the price bar alone does not carry.
- Flagged the 14:45 break as *still absorbed* (effect 49) rather than as a
  breakout, which held for the four minutes until the V-return.

**Not right:**
- Graded the 14:49 V-return 0.80 and gave no signal that it was the last
  bounce. Efficiency and persistence are different properties; the grade
  measures only the first.
- Day-scope superlatives called live ("largest delta of the day") were
  afternoon-scope. Full-day deltas were −1,501 at 07:06, −1,200 at 09:19 and
  +1,040 at 11:34. A live watch resumed mid-session does not hold the morning
  in view unless it is asked to — worth a running day-max in the emission.

## 8. Follow-ons

- **st-dioq** (COO's) — the baseline fix. Second day of confirming evidence,
  now with the ranking inversion in §6b as a concrete failure case.
- **st-vmi7** — folding the live grade into the FP chart. This session is the
  argument for the qualitative shape: the load-bearing calls were sequence
  observations across bars, not per-bar grades.
- **New:** emit a running session max for volume and delta alongside each atom,
  so a mid-session watch cannot mis-scope a superlative (§7).
