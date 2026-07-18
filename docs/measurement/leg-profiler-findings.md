# Structural Leg Profiler — Findings [st-bg4]

*2026-07-18. Study spec: bead st-bg4 (COO design-of-record under Leg Profiler Spec, co-coui).*

## What was tested

LuxAlgo's closed-source "Structural Leg Profiler" claims four things: ATR-thresholded
swing legs are meaningful structure; each leg's volume point of control (POC — the
price where the most volume traded during that leg) acts as a magnet/reaction level
when price returns to it ("naked POC"); delta divergence inside a leg warns of the
leg's end; and volume anomalies near a leg's extreme mark reversals.

We reimplemented the indicator deterministically (`market/measurement/legprofiler.py`)
and scored those claims against the tick corpus: 257 tape days — 23 full-session
days, 233 late-day (1:00–3:00 CT) days, 1 morning-only — at three swing
multipliers (1.5 / 2.0 / 3.0, ATR period 14, 1-minute bars). Every level is scored
only from its leg's confirmation time; the repaint audit passed with zero violations
across all runs.

One structural advantage over the TradingView original: our per-bucket delta is true
per-trade aggressor delta from the tape's side field. The original approximates delta
from lower-timeframe bar closes (`request.security_lower_tf`). Anything the original
claims about delta, we tested with better data than it has.

## Verdict — which claims survive

| Claim | Verdict | Read |
|-------|---------|------|
| Naked leg-POC is a reaction level | **DEAD** | Bounces no more often than a random level from the same leg |
| Delta divergence precedes leg end | **Marginal** | Small lift in full sessions, nothing late-day |
| Volume anomaly at the extreme marks the turn | **SURVIVES (reframed)** | Strong — but only the real-time variant (H3b) is honest |
| Leg segmentation itself | Useful scaffold | Legs are a clean way to anchor profiles; no edge claimed or tested per se |

## H1 — Naked POC: no edge

At every multiplier, in both collections, a returning touch of a leg's untested POC
"bounced" (moved 2 pts back away before penetrating 2 pts through, within 15 min) at
essentially the same rate as a matched random control level drawn from the same leg:

| Collection | Mult | POC bounce | Control bounce | z |
|-----------|------|-----------|----------------|---|
| full RTH | 1.5 | 59.0% (1094/1855) | 58.7% (1015/1729) | +0.16 |
| full RTH | 2.0 | 59.4% (530/893) | 60.5% (518/856) | −0.50 |
| full RTH | 3.0 | 60.9% (213/350) | 62.0% (194/313) | −0.30 |
| late day | 1.5 | 59.5% (3225/5424) | 58.8% (2803/4764) | +0.64 |
| late day | 2.0 | 60.0% (1519/2532) | 59.8% (1390/2326) | +0.17 |
| late day | 3.0 | 58.1% (490/843) | 60.8% (480/789) | −1.11 |

The ~60% bounce rate itself is just intraday mean reversion — *any* recently-traded
price shows it. The POC adds nothing on top. This is the indicator's flagship visual
(those projected dashed lines) and it does not survive contact with the data.

**What this means for the desk:** don't treat leg-POC lines as levels. Prior-session
POC / session profile nodes (the st-7d6 layer) remain separately scored territory —
this result is about *intraday per-leg* POCs only.

## H2 — Delta divergence: marginal, session-scope only

A leg extending to a new extreme while cumulative aggressor delta fails to confirm
does precede leg termination slightly more often than a confirmed extension — but
only in full-RTH sessions at fine granularity, and the lift is a few percentage
points:

| Collection | Mult | Divergent → terminal | Confirmed → terminal | z |
|-----------|------|---------------------|---------------------|---|
| full RTH | 1.5 | 86.1% (1166/1354) | 82.8% (2115/2553) | +2.65 |
| full RTH | 2.0 | 65.0% (883/1358) | 61.8% (1470/2380) | +1.98 |
| full RTH | 3.0 | 39.7% (482/1213) | 38.1% (656/1722) | +0.90 |
| late day | 1.5 | 86.4% (3101/3588) | 87.1% (5676/6516) | −0.97 |
| late day | 2.0 | 69.1% (2534/3667) | 68.9% (4214/6113) | +0.17 |
| late day | 3.0 | 46.9% (1297/2767) | 44.5% (1846/4152) | +1.98 |

Late-day (Steve's butterfly window): essentially nothing — a two-point sliver at the
coarsest setting only. The CVD-divergence intuition is
not wrong, but at 1-minute/leg scale it is too weak to act on alone. It stays a
background confirmation input, exactly as the playbooks already use it.

## H3 — Volume anomaly at the extreme: the one that survives

As literally specified, H3 ("anomalies in the final 20% of the leg's range mark
reversals") confirms overwhelmingly — but the specification has built-in hindsight:
"final 20% of the range" is only knowable after the leg ends, and legs end at their
extremes by construction, so late bars sit near the final range mechanically.

So we added **H3b**, the real-time-scorable version: *among bars that extend the
leg's extreme (knowable at bar close), does an anomaly-volume extension (> 2× the
trailing 20-bar average) precede leg termination more often than a normal-volume
extension?*

| Collection | Mult | Anomalous extension → terminal | Normal-vol extension → terminal | z |
|-----------|------|-------------------------------|--------------------------------|---|
| full RTH | 1.5 | 96.9% (313/323) | 81.8% (4325/5290) | +6.98 |
| full RTH | 2.0 | 87.3% (268/307) | 59.0% (2571/4356) | +9.81 |
| full RTH | 3.0 | 61.2% (148/242) | 34.7% (1075/3096) | +8.22 |
| late day | 1.5 | 97.3% (1644/1689) | 83.9% (11457/13656) | +14.75 |
| late day | 2.0 | 87.6% (1298/1481) | 63.3% (7050/11144) | +18.63 |
| late day | 3.0 | 66.2% (627/947) | 38.8% (2739/7062) | +16.05 |

The honest version survives, everywhere, at every parameter setting. At the middle
multiplier: when a bar pushes to a fresh leg extreme on anomaly volume, the leg is
over within 5 bars about **88%** of the time, vs about **60–63%** for a
normal-volume push — a 24–28-point lift, and it is largest exactly in Steve's
late-day window. (One caveat on magnitude: "terminal" includes the extension bar
being the final pivot itself — a volume climax often *is* the turn bar. That is the
claim working as intended, not leakage: the flag is knowable at bar close.)

**What this means for the desk:** a volume spike *while price is pushing to a fresh
leg extreme* is the tape event worth respecting — it is the exhaustion/absorption
read Steve already makes on the footprint, now with a measured base rate. It is a
probabilistic lean, not a gate (standing rule: no pre-drop filtering).

## Parameter sensitivity

Effects were checked at multipliers 1.5 / 2.0 / 3.0. H1's null and H3b's direction
hold at every setting; H2's small lift is confined to full-RTH at 1.5–2.0 plus a
sliver late-day at 3.0 — pattern of a fragile effect. No conclusion above is an
artifact of a single parameter choice.

## Collections

Late-day and full-RTH results are reported separately throughout (window truncation
biases leg statistics — a 2-hour window censors long legs and truncates naked-POC
projection at 15:00). Days holding both a morning and a late-day pull merge into a
contiguous full-RTH span and are classified as such.

## Leg Profiler × footprint charts (Steve's question)

The fit is direct: **a per-leg profile is a footprint column whose boundary is
structural instead of clock- or volume-based.** A footprint bar is (price × bid/ask
volume) per fixed bar; the leg profile is the identical cell structure aggregated
between two swing pivots. Same data, same rendering shape — different time boundary.

Concretely, on the drill chart (which is a footprint):

- A confirmed leg's profile could render as one wide footprint-style column spanning
  the leg's bars, delta-colored per bucket — the "where was the volume in this move"
  read at a glance.
- The study says: draw **no naked-POC lines** off those columns (H1 dead), but *do*
  highlight extension bars whose volume spikes (H3b) — that is a footprint-native
  event: it shows up as a suddenly fat column at a fresh extreme.
- H3b is, in effect, a measured version of the exhaustion read Steve already
  practices on footprints. The leg segmenter's contribution is defining *which*
  extreme matters (the developing leg's) without eyeballing.

Proposed follow-up (separate bead): overlay leg boundaries + H3b highlights on the
orderflow drill HTML so drill reps train against the measured event, not the dead one.

## Reproduce

```
.venv/bin/python3 -m pytest tests/market/measurement/test_legprofiler.py -q
.venv/bin/python3 scripts/measurement/legprofiler_study.py            # replay corpus
.venv/bin/python3 scripts/measurement/legprofiler_study.py --summarize
```

Store: `data/measurement/legprofiler_study.jsonl` (append-only; last row per
(day, mult) wins). Core: `market/measurement/legprofiler.py`.
