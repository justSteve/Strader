# Orderflow Capture Checklist

*Steve's operator card for the GexBot Orderflow view. Companion:
`capture-protocol.md` (the repo-facing record). Updated 2026-08-06 [st-ygy1].*

---

## 1. Set once and SAVE (should already be right)

**Top bar / right panel:**

- Ticker: **SPX**
- Price overlay: **spot price** (not "es future")

**Each of the three panes:**

- Expiry: **latest** (today's expiry — not "next")
- **spot** toggle: ON
- **combine** toggle: OFF
- Window: **30min**

**Settings (gear icon):**

- Show Tooltips: **ON**
- Time Zone: **New York (UTC-4)**
- Price Transform: 1 x + 0 (leave alone)

## 2. The standing pane lineup (normal trading day)

Top to bottom, via each pane's metric dropdown:

| Pane | Metric | What it's telling you |
|---|---|---|
| Top | **convexity orderflow** | Spikes UP = someone is buying options — taking liquidity, betting on change → think *reversion*. Spikes DOWN = options being sold — liquidity provided → think *momentum, trend continues*. |
| Middle | **gex orderflow** | Which side just got expensive. Bar UP = call side (cost of upside lifted). Bar DOWN = put side (cost of downside lifted). |
| Bottom | **net convexity** | The day's vol mood as a running line. Climbing = option buying (vol being bid). Falling = option selling. |

## 3. Daily schedule — two captures

**Morning, ~9:40–9:45 AM:** capture the view exactly as configured above.

**Close, ~3:45–3:55 PM:**

1. Change the TOP pane's metric dropdown: convexity orderflow → **net vanna**
2. Capture.
3. Either swap the top pane back now or first thing next morning.

**Optional, after the close:** widen the window from 30min to the largest
choice so the whole session is in one frame, capture, set it back.

**Where to drop them:** `C:\Users\steve\zgent-bridge\` — any filename, I
rename and file them.

## 4. On-call — capture when you see any of these

These are the doctrine patterns in motion. When one shows up, grab a cap —
the timestamp is in the frame, no notes needed.

1. **The dump.** Bottom pane (net convexity, blue line) climbed through the
   morning, then collapses — loses half its height or more inside ~30
   minutes. Capture at the collapse, and again if price then breaks out
   (that's the "dump then ramp" — the principals call the post-dump long
   "juice to lean on").
2. **The brake.** Market has been trending steadily, and the TOP pane
   prints one up-spike that towers over everything else in the window.
   Someone is braking the trend by buying volatility.
3. **The two-signal setup.** The brake (top pane up-spike) AND a
   same-direction spike in the MIDDLE pane within the same few minutes —
   calls spiking while the market trends up, or puts spiking while it
   trends down. That's the canonical reversal setup. Highest-value capture
   there is.
4. **After a reversal.** If you took (or watched) a reversal off #3: the
   top pane should now print DOWN-spikes (options being sold = fuel for the
   new direction). Capture whether it does or doesn't — both answers matter.
5. **The last 10 minutes.** Unusually tall bars in either spike pane right
   before the close = late speculative positioning. Capture.
6. **Anything that makes you say "huh."** Capture it. Cheap to take,
   impossible to reconstruct.

## 5. The tooltip tour — COMPLETE ✓

All eight metrics captured 2026-08-06 (filed as `2026-08-06-1500-tooltip-*.png`
in the screenshots directory). Nothing left to do here — section kept for the
record. The Snipping Tool delay trick (5-second timer, hover during countdown)
remains the way to capture any future hover state ClipMate can't hold.

## 6. Reading the line colors (from the vendor's settings panel)

- **White jagged line** — spot price, always
- **Cyan / purple horizontal** — major long gamma / major short gamma
- **Green / red horizontal** — major call / major put
- **Orange** — zero gamma
- **Blue** — net convexity · **cyan** — aggregate dex, with **green/red**
  its call/put components · **green** — net gex

---

*This page lives at* `file://wsl.localhost/Zgent/var/moo/desk/desk-orderflow-capture-checklist.html`
*— refresh it there; I keep it current.*
