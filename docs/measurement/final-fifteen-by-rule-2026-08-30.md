# Final-fifteen by 14:45 rule state

final-fifteen rows 286 · lens rows at 14:45 286 · joined on 286 days

BASE RATE, all 286 joined days
| measure | >=5 | >=10 | >=15 | >=20 |
|---|---|---|---|---|
| close moved | 155 (54.2%) | 64 (22.4%) | 24 (8.4%) | 8 (2.8%) |
| window touched | 258 (90.2%) | 123 (43.0%) | 59 (20.6%) | 17 (5.9%) |

## The R1-R7 combination rules, scored on the final fifteen

Coverage is how often the rule speaks at 14:45. Lift is the touch>=10 rate
against the base rate on the same joined days — the number that says whether
the state selects for a move at all.

| rule at 14:45 | call | fires | touch>=5 | touch>=10 | touch>=15 | touch>=20 | close>=10 | lift on touch>=10 |
|---|---|---|---|---|---|---|---|---|
| R1 flush | down | 27 (9.4%) | 96.3% | 29.6% | 7.4% | 0.0% | 7.4% | -13.4 pts |
| R2 launch | up | 26 (9.1%) | 92.3% | 46.2% | 19.2% | 7.7% | 19.2% | +3.1 pts |
| R3 pinned | pin | 5 (1.7%) | 100.0% | 60.0% | 20.0% | 0.0% | 40.0% | +17.0 pts  *(story, not a base rate)* |
| R4 bought | up | 22 (7.7%) | 90.9% | 68.2% | 31.8% | 18.2% | 45.5% | +25.2 pts |
| R5 sold | down | 26 (9.1%) | 88.5% | 46.2% | 19.2% | 3.8% | 19.2% | +3.1 pts |
| R6 lost | down | 2 (0.7%) | 100.0% | 50.0% | 0.0% | 0.0% | 0.0% | +7.0 pts  *(story, not a base rate)* |
| R7 taken | up | 4 (1.4%) | 100.0% | 50.0% | 0.0% | 0.0% | 0.0% | +7.0 pts  *(story, not a base rate)* |
| _(no rule fires)_ | — | 174 (60.8%) | 88.5% | 40.2% | 22.4% | 5.7% | 23.0% | -2.8 pts |

## Direction — when a rule speaks, does the final fifteen go its way?

A directional rule is only tradeable if the move it names is the move that
happens. Scored on days the final fifteen moved at least 5 points either way;
days quieter than that are 'flat' and count against neither side.

| rule | call | fires | went its way | went against | flat (<5pt) | edge |
|---|---|---|---|---|---|---|
| R1 flush | down | 27 | 8 (29.6%) | 7 (25.9%) | 12 | +4 |
| R2 launch | up | 26 | 12 (46.2%) | 2 (7.7%) | 12 | +38 |
| R3 pinned | pin | 5 | stayed inside 5pt on 1 (20.0%) | — | — | — |
| R4 bought | up | 22 | 8 (36.4%) | 7 (31.8%) | 7 | +5 |
| R5 sold | down | 26 | 7 (26.9%) | 5 (19.2%) | 14 | +8 |
| R6 lost | down | 2 | 0 (0.0%) | 0 (0.0%) | 2 | +0  *(story)* |
| R7 taken | up | 4 | 1 (25.0%) | 1 (25.0%) | 2 | +0  *(story)* |

## The footprint solo call at 14:45

| fp call | days | touch>=10 | close>=10 | went its way (>=5pt) | went against | edge |
|---|---|---|---|---|---|---|
| down | 39 | 48.7% | 23.1% | 11 (28.2%) | 12 (30.8%) | -3 |
| pin | 207 | 41.1% | 22.2% | — | — | — |
| up | 40 | 47.5% | 22.5% | 16 (40.0%) | 5 (12.5%) | +28 |

## Arrival, conditioned on the rule speaking

Item 1 found the big moves arrive late. If a rule state pulled the arrival
EARLIER it would be worth more than its hit rate alone suggests, because an
early move leaves time value on the option. Median minutes after 14:45 to the
first 10-point touch, on the days that touched.

| state | days touching >=10 | median first-touch min | vs base (9.00) |
|---|---|---|---|
| R1 flush | 8 | 11.63 | +2.63 |
| R2 launch | 12 | 6.97 | -2.03 |
| R3 pinned | 3 | 14.75 | +5.75 |
| R4 bought | 15 | 9.08 | +0.08 |
| R5 sold | 12 | 8.95 | -0.05 |
