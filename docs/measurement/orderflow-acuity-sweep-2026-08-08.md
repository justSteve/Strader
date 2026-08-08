# Orderflow acuity sweep — 2026-08-08 [st-yirc]

63 hist days at 1s resolution (2026-05-07 .. 2026-08-06); detector run at the live 75s cadence; 1s arrays as ground truth. Skipped thin days: none.

## A. What the 75s poll actually observes (instantaneous prints)

| print magnitude | 1s prints (all days) | seen by 75s poll | coverage |
|---|---|---|---|
| cvr_ge1000 | 9887 | 164 | 1.7% |
| cvr_ge300 | 50412 | 736 | 1.5% |
| cvr_ge500 | 26086 | 384 | 1.5% |
| gex_ge1000 | 12147 | 218 | 1.8% |
| gex_ge300 | 64574 | 959 | 1.5% |
| gex_ge500 | 32330 | 486 | 1.5% |

## B. Baseline config, events/day over the archive

- **spike**: median 21, p90 28, max 32
- **netcvx**: median 18, p90 29, max 40
- **two**: median 3, p90 6, max 8
- **re-arm chatter across all days**: 0

## C. VTURN lead-lag vs the 1s spot path

247 VTURN events. Spot's 30-min-forward low came >1 min AFTER the VTURN in 217/247 (87.9%) — the 2026-08-07 'flow led price' observation tested across the archive.
- median time from VTURN to the spot low: 12.5 min
- median rebound off that low within 30 min: 11.2 pts (p25 6.1, p75 16.0)

## D. TWO_SIGNAL forward spot deltas

215 TWO_SIGNAL events (109 put-side).
- +5m: median +0.6 pts, mean -0.0, n=182
- +15m: median +0.5 pts, mean -0.0, n=133
- +30m: median -0.3 pts, mean -0.7, n=109

## E. Close signature (final 120s of RTH)

- max |cvroflow|: median 11170, p90 32732, max 106571
- max |gexoflow|: median 11621, p90 35091, max 107316
- zcvr net change: median -4336, p90 16435, max 126452

## F. Threshold grid (75s cadence, all days)

| floor | mult | drop | spikes/day med | netcvx/day med | two-signals total | chatter |
|---|---|---|---|---|---|---|
| 100 | 1.3 | 1000 | 41 | 29 | 436 | 0 |
| 100 | 1.3 | 1500 | 41 | 18 | 436 | 0 |
| 100 | 1.3 | 2500 | 41 | 10 | 436 | 0 |
| 100 | 1.6 | 1000 | 24 | 29 | 238 | 0 |
| 100 | 1.6 | 1500 | 24 | 18 | 238 | 0 |
| 100 | 1.6 | 2500 | 24 | 10 | 238 | 0 |
| 100 | 2.0 | 1000 | 15 | 29 | 143 | 0 |
| 100 | 2.0 | 1500 | 15 | 18 | 143 | 0 |
| 100 | 2.0 | 2500 | 15 | 10 | 143 | 0 |
| 150 | 1.3 | 1000 | 34 | 29 | 363 | 0 |
| 150 | 1.3 | 1500 | 34 | 18 | 363 | 0 |
| 150 | 1.3 | 2500 | 34 | 10 | 363 | 0 |
| 150 | 1.6 | 1000 | 21 | 29 | 215 | 0 |
| 150 | 1.6 | 1500 | 21 | 18 | 215 | 0 |
| 150 | 1.6 | 2500 | 21 | 10 | 215 | 0 |
| 150 | 2.0 | 1000 | 13 | 29 | 132 | 0 |
| 150 | 2.0 | 1500 | 13 | 18 | 132 | 0 |
| 150 | 2.0 | 2500 | 13 | 10 | 132 | 0 |
| 250 | 1.3 | 1000 | 21 | 29 | 248 | 0 |
| 250 | 1.3 | 1500 | 21 | 18 | 248 | 0 |
| 250 | 1.3 | 2500 | 21 | 10 | 248 | 0 |
| 250 | 1.6 | 1000 | 14 | 29 | 166 | 0 |
| 250 | 1.6 | 1500 | 14 | 18 | 166 | 0 |
| 250 | 1.6 | 2500 | 14 | 10 | 166 | 0 |
| 250 | 2.0 | 1000 | 10 | 29 | 111 | 0 |
| 250 | 2.0 | 1500 | 10 | 18 | 111 | 0 |
| 250 | 2.0 | 2500 | 10 | 10 | 111 | 0 |

Raw numbers: `data/derived/acuity-sweep/raw.json`. Measurement only — config unchanged pending review [st-yirc].

## G. Random-time control for section C (seed 20260808, 4 draws/day)

| statistic | VTURN sample (n=247) | random control (n=252) |
|---|---|---|
| spot low >1 min after event | 87.9% | 88.1% |
| median time to the 30-min-forward low | 12.5 min | 12.8 min |
| median rebound off that low | 11.2 pts | 13.0 pts |

**The VTURN lead-lag stats are indistinguishable from random timestamps.**
The 2026-08-07 "flow turned 11 minutes before the price low" observation is
what ANY randomly chosen moment looks like on the 1s spot path — a base-rate
illusion, not an edge. VTURN as currently defined (unconditioned, 75s
cadence) has no measured timing value. Any future claim for it must beat
this control, e.g. by conditioning on dump depth or absolute zcvr level.
