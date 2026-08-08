# Orderflow edge tests, round 2 — 2026-08-08 [st-mvvf]

63 hist days at 1s. Controls are matched and use the same alignment rules as the tested events. Final 2 minutes of RTH excluded from event samples.

## 1. Two-signal at 1-second resolution

Aligned forward delta = reversal-aligned spot move (-sign(30-min trend) x forward delta); positive = the doctrine's predicted reversal happened.

| definition | n | aligned +15m med | %pos | aligned +30m med | %pos |
|---|---|---|---|---|---|
| p95x3 | 1090 | -0.12 | 50% | -0.02 | 50% |
| p95x6 | 236 | 0.59 | 55% | 1.58 | 59% |
| fix2000 | 137 | 1.03 | 63% | 1.13 | 65% |
| **random control** | 378 | -0.78 | 43% | -1.18 | 46% |

Canonical cut (p95x6, put-side, trend < -2 pts): n=51, aligned +15m med 2.54 (66% pos), +30m med 2.21 (64% pos).

## 2. Conditioned V-turn

| condition | n | med rebound | med fwd_30 | %fwd_30 pos |
|---|---|---|---|---|
| all VTURN | 247 | 11.16 | -0.2 | 49% |
| depth >= 3000 | 105 | 8.12 | 0.63 | 53% |
| depth >= 5000 | 46 | 5.97 | 1.11 | 64% |
| first 90 min | 42 | 16.94 | -0.02 | 50% |
| after first 90 min | 205 | 9.12 | -0.2 | 48% |
| **random control** | 252 | 14.65 | 1.38 | 58% |

## 3. Vanna thresholds (canonical: -800/-1000 $MM)

Vendor self-caveat applies: this layer is flagged 'still learning best practices'. Sign mapping of doc 'net -vanna' to the zvanna field is ambiguous; magnitude cuts are primary.

| partition | n days | med last-hour |drift| | med backtrack |
|---|---|---|---|
| peak |zvanna| last-1h >= 800 | 58 | 8.12 | 9.57 |
| peak |zvanna| last-1h < 800 | 5 | 6.39 | 12.62 |
| peak |zvanna| last-2h >= 1000 | 55 | 8.7 | 9.81 |
| peak |zvanna| last-2h < 1000 | 8 | 4.54 | 6.23 |

Directional (exploratory, sign-ambiguous): sign(zvanna)*drift med 4.16 pts, 59% positive, n=63; flip the sign convention to read the opposite claim.

Raw: `data/derived/acuity-sweep/edge-tests-raw.json`. Measurement only [st-mvvf].

## Robustness: day-clustering of the study-1 effect

| definition | events | days | day-mean positive | median day-mean |
|---|---|---|---|---|
| p95x6 | 236 | 52 | 29/52 (56%) | +1.07 pts |
| fix2000 | 137 | 15 | 12/15 (80%) | +1.21 pts |

fix2000 events exist only on high-volatility days (prints >= 2000 $MM);
the aligned effect is present on 12 of those 15 days, largest single
day-mean +26 pts (2026-06-05) — concentrated in regime, not in one day.

## Verdicts

1. **Two-signal (strong prints): SURVIVES CONTROL — candidate, not
   confirmed.** Monotone dose-response (p95x3 null -> p95x6 +1.6 ->
   fix2000 +1.1/+2.5 canonical cut) against a control tilted the other
   way (-1.2). Caveats: 15 effective days at the strongest definition,
   multiple definitions tried. Required next step: forward validation on
   days the archive adds from here (out-of-sample by construction), and
   a join against Steve's late-day trade windows.
2. **V-turn: RETIRED as a timing signal.** Conditioning on dump depth
   and time-of-day does not lift it above the random control (which
   itself beats most buckets).
3. **Vanna thresholds: NON-DISCRIMINATING as operationalized.** 58/63
   days peak above the 800 $MM last-hour bar — a filter that always
   passes filters nothing. Either the principals mean signed/sustained
   magnitude rather than peak |zvanna|, or the field-to-claim mapping
   differs. Parked pending the transcript study (st-qei0) for the
   precise definition. The below-bar days (n=8) do show visibly quieter
   closes, directionally consistent with the claim's spirit.

## ERRATUM (2026-08-08, discovered in round 3 [st-gkbo])

The study-1 table's n column counts events, but events within 30 min of
the close have no +30m outcome. For fix2000 only 23 of 137 events (15
days) have a measurable +30m delta — the fix2000 medians rest on that
smaller sample, and the "12/15 days" clustering claim covers only the
measurable days. p95x6 is mildly affected (165/236 measurable). The
dose-response conclusion stands on p95x6; treat fix2000 rows as
late-session-censored. Round 3 reports corrected counts.
