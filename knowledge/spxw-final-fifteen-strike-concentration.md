---
type: reference
title: "SPXW Final-Fifteen Strike Concentration"
description: "Measured 2026-08-30: in the last fifteen minutes the 32 SPXW strikes within ±40 points of ES carry about three quarters of all SPXW print volume, while quote traffic spreads across the whole surface. Narrowing the strike set is a quote-schema lever, not a trades lever."
timestamp: 2026-09-04T12:35:00-05:00
metadata:
  bead: st-lrqq
  filed_on: "Desk ruling 20260830T134948 §2 — the section its 14:07 correction left standing"
  source_memo: "bridge Desk/_archive/20260830T092159__Strader__opra-quote-costs-measured.md"
  source_measurement: "docs/measurement/final-fifteen-2026-08-30.md and siblings (st-byif, st-ro04)"
  window: "14:45–15:00 CT, 274 sessions 2025-05-27 .. 2026-08-14, Databento OPRA billable bytes as the volume proxy"
---

**The fact.** In the final fifteen minutes of the cash session, the 32 SPXW strikes
within ±40 points of ES carry about **three quarters** of all SPXW trade prints.
Quote traffic does not concentrate the same way: every listed strike quotes all
session, so the quote surface is wide and flat while prints pile up at the money.

**Measured, not assumed.** It surfaced on 2026-08-30 while quoting Databento OPRA
pull costs (st-byif, st-ro04). Cutting the symbol set from the full SPXW surface
to the ±40 band shrank a `cbbo-1s` quote pull to **0.24%** of the full-surface
bytes, a 410× cut, but shrank a `trades` pull only to **73%**. The band already
holds most of the prints. Cost was exactly linear in bytes with no minimum charge,
so bytes stand in for record count cleanly.

**Why it holds.** 0DTE activity in the last minutes is a fight over the strikes
the index can still reach; strikes it cannot reach are dead to prints but still
quoted by the market makers. That will stay true after these prices change.

**How to apply.**

- Pulling **quotes** (`cbbo-1s`, `tcbbo`, MBP): narrow to the ±40 band first. It
  is the whole lever.
- Pulling **trades**: do not expect narrowing to save anything material. Buy the
  surface or buy the band, the bill is about the same.
- Reading **final-fifteen print flow**: the ±40 band is where nearly all of it
  lives. A strike outside it with real prints is the exception worth a look.

**Caveats.** One window (14:45–15:00 CT), one proxy (billable bytes), one corpus
span. Re-measure if the 0DTE strike ladder or SPXW listing density changes
materially. Entitlement state for any pull lives in [[entitlements-registry]],
never here.
