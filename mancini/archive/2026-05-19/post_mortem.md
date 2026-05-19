# Post-Mortem: May 18 Forecast vs Monday May 19 Action

## Range Context
- **May 18 forecast range**: 7421 support — 7472 resistance (key levels inside: 7435, 7458)
- **Monday actual range**: 7374 low — 7451 high
- Range shifted ~50 pts lower than forecast center. The 7421-7472 range broke down Sunday evening.

## Key Level Scorecard

| Level | Tier | Forecast Role | Monday Result |
|-------|------|---------------|---------------|
| 7472 | KEY major R | Range ceiling | Not tested — price never got above 7451 |
| 7458 | KEY major R | Key resistance inside range | Not reached |
| 7449 | minor R | First resistance | **Hit** — Monday high was 7450+ |
| 7442 | minor S | Top of support stack | Traded through, acted as resistance zone |
| 7435 | KEY major S | Range anchor, shelf of lows | **Below range** — not relevant to Monday's action |
| 7421 | KEY major S | Range floor, Friday daily low | Swept Sunday evening; Monday traded well below |
| 7414 | minor S | | Traded through both directions |
| 7410 | minor S | | Traded through both directions |
| 7398 | major S | Wednesday daily low | **Key level of the session** — Failed Breakdown triggered here Sunday evening (swept to 7375, recovered 7398 by 4:15AM, ripped to 7450+) |
| 7390 | minor S | | Traded through on sell |
| 7383 | minor S | | Support zone held during afternoon |
| 7377 | major S | Deep support | **Became the session's anchor** — multi-touch shelf (9-10 touches), failed breakdown at 3PM launched rally to 7421 |
| 7364 | major S | | Not tested (low was 7374) |

## Assessment

**What worked:**
- The 7398 major support was the session's defining level — Mancini flagged it Friday as "the big Wednesday daily low from which we ripped into this weeks highs" with a highly actionable Failed Breakdown setup
- The support stack below 7421 (7398, 7377, 7364) provided the roadmap for the sell-off and bounce zones
- 7449 resistance capped the rally precisely

**What shifted:**
- The forecast range of 7421-7472 was already stale by Monday's open — Sunday evening's sell to 7375 broke the range floor by 46 points
- The new effective range became 7377-7451, which is exactly what the May 19 email confirms

**Lesson for Strader:**
The published key levels from the bull/bear case (7421, 7435, 7458, 7472) were above Monday's action zone. The actual session pivots came from the deeper support stack — 7398 and 7377. When the range breaks, the key-level overlay is less useful than the full S/R array. This argues for keeping `alwaysShowKey` off by default and relying on the radius filter to surface what's near price.
