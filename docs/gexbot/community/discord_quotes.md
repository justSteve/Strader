# GexBot Discord — actionable quotes

Append-only archive of Discord posts that Steve flags as operationally
relevant. Lower-confidence than vendor-published material — these are
practitioners (and sometimes principals) talking in chat, not formal
documentation.

## Source rules

- **Channel and date are mandatory.** Discord posts mutate (edits, deletes); the citation must let a future reader find the original even if it's gone.
- **Speaker role tag preserved.** `[PP]`, "Moderator", "Member" etc. — that's the speaker's authority signal in the Discord context.
- **Quote verbatim.** Discord posts are usually short enough to quote in full. Don't paraphrase the post itself; commentary goes below the quote.
- **Tag canonicity.** When a community member is quoting a principal (Jasper "Jass", John), the *content* may carry canonical weight even though the *medium* is community. Note this in the per-quote commentary.

## Layout

Each entry has: date, channel, speaker, role, verbatim quote, what's new
vs existing docs, where it gets slotted.

---

## 2025-01-25 — Freddy Sarmiento, #theory-questions

**Speaker:** Freddy Sarmiento `[PP]` — Moderator, Discord community member, NQ futures trader (the speaker in the [Trading with Gamma video](freddy_methodology.md))
**Time:** 12:23 PM
**Posted:** day after the Trading with Gamma video (2025-01-24)

> Gexbot Will help you ( as it helped me )… I think if you execute more like an algorithmic model, you'll be fine.. Jass emphasis on entering on the high net convexity, tight SL if price breaks that level against you but entering again of price moves on your bias.

### Three rules embedded

1. **Algorithmic execution** — already covered, [`freddy_methodology.md` §10](freddy_methodology.md).
2. **Enter on high net convexity** (= excess gamma) — already covered, [`freddy_methodology.md` §3](freddy_methodology.md) step 1–3.
3. **Re-entry after stop-out** — **new**, now slotted as [`freddy_methodology.md` §3 step 6](freddy_methodology.md).

### Why the re-entry rule matters

Without it, "tight SL" means most setups end as small losses and the
trader sees a poor hit rate. With it, the profile becomes "many small
losses + occasional larger wins" — which is the algorithmic profile
Sarmiento and Jasper both emphasize. The stop is for *timing risk*, not
for *thesis invalidation*: if your gamma read was right, getting wicked
out of the level once doesn't mean it stops being a magnet.

### Canonicity note

Freddy is paraphrasing Jasper ("Jass emphasis on…"), so the *content*
is canonical-by-attribution even though the *medium* is community. If
Jasper has stated this directly elsewhere (GexBot docs, a video, a
pinned Discord post), that source would supersede this paraphrase.
Worth a search next time we're crawling the Discord archive.

---

## 2025-01-27 — Freddy Sarmiento, #theory-questions

**Speaker:** Freddy Sarmiento `[PP]` — Moderator
**Time:** 10:43 AM
**Reply to:** Guido (Discord member)

> Hi Guido, apologies for my late reply.. busy morning as you saw.
>
> Yes I don't look QQQ at all, instead I look at SPX for a bigger picture and SPY to confirm directional moves. ( I used to trae ES by looking at SPY, simply because SPX is mainly used for institutions to hedge, while SPY is directional… I believe both, retails and institutions use SPY; if you have a look the documentation in gexbot, they mention something similar for gamma in SPY.. - I don't use QQQ because I want to quickly get in, with a tight SL and look for nice moves… not home runs, but moves that could give me more than 1-3 ratios, take profits in 50% or more and leave a runner.
>
> --Was it difficult to trust Jass´s concept "try not to think directional"? -- Not at all, as a trader, you need to flexible, and with all the bunch of technical analysis tool, it is difficult; but with gamma is simple and easy i think… have a look today for instance; NQ rallies, I was long when the market opened, gamma confirmed my view, then I had a gamma target ( max gamma excess at 21606 when NQ was at 21,332…. then what happened? we hit Max negative gamma at 21,417( I took profits 50%, left a runner) and the large top side target - Max gamma at 21,606 shifted to 21,051…is that a shift in sentiment? 100% yes… so took small profits on my last 50% and gamma level a 21,203 confirmed the downtrend….
> I look classic to see if we are above zaro [sic — zero] gamma or below.

### What's new vs existing docs

1. **SPX/SPY/QQQ nuance** — refines [`freddy_methodology.md` §7](freddy_methodology.md): SPX = positioning (institutional hedge), SPY = directional confirmation. Not "SPX institutional, SPY retail." Both audiences use SPY; the distinguishing feature of SPX is the *hedging* use case. Slotted into §7.
2. **R:R discipline** — explicit numbers: ≥1:3 ratio, 50% off at first level, runner to next. Slotted into [§3](freddy_methodology.md).
3. **Gamma profile SHIFT = sentiment signal** — when GexBot's max-gamma computation relocates (e.g., topside 21,606 → 21,051), that's the regime change. **NEW** — slotted as [§11](freddy_methodology.md).
4. **Zero gamma line** as regime delimiter — above = mean-reverting, below = amplifying. The "classic" view name is a likely GexBot UI reference not yet in our canonical docs. **NEW** — slotted as [§12](freddy_methodology.md).
5. **"Try not to think directional"** — Jasper's framing. Reinforces algorithmic-execution discipline ([§10](freddy_methodology.md)).

### Worth following up

Freddy mentions GexBot documentation about gamma in SPY ("if you have a
look the documentation in gexbot, they mention something similar"). We
haven't surfaced that in the canonical files yet — worth a search of
the docs site.

---

## 2025-01-28 — Freddy Sarmiento, #theory-questions

**Speaker:** Freddy Sarmiento `[PP]` — Moderator
**Time:** posting time not captured

> hi there,,, thanks for your message.
>
> From a fundamental trading perspective, I want to interact with the market in key levels, I guess all methodologies, technical analysis, quant analysis, etc, want the same, so with excess of gamma, you know institutions interact with the market in those key levels, and on those levels the market finds, a mean reverting situation or trend continuation, why? because these institutions came into the options market with volumes that are big; so you have two options: or trade in between excess of gamma levels, where the probability to get into a range, consolidation etc... and hit stop losses more often... or wait for the excess of gamma levels, where there is an "imbalance" of gamma and convexity in those levels are a key component...as Jass mentioned, convexity is a key concept option traders understand well... and that convexity is key for us Futures traders too.... ( convexity is the non-linear relationship between the underlying price and the options, measured by gamma).

### What's new vs existing docs

1. **Explicit convexity definition** — "non-linear relationship between the underlying price and the options, measured by gamma." Folds into [§1](freddy_methodology.md) as the definition for "high net convexity."
2. **Binary choice framing** — between-levels (range, stops) vs at-levels (imbalance, edge). Sharper than the video's framing of the same idea. Folded into [§1](freddy_methodology.md).
3. **Trend-continuation as the other outcome at gamma levels** — the video emphasizes mean reversion; this notes gamma levels also produce trend continuation. Worth verifying when this distinction matters operationally (likely: positive gamma regime → mean reversion at levels; negative gamma regime → trend continuation through levels — consistent with §12 zero-gamma regime read).

### Canonicity note

Freddy attributes the convexity emphasis to Jasper again ("as Jass
mentioned"). Same canonical-by-attribution pattern as 2025-01-25.

---

## 2025-01-29 — Freddy Sarmiento, #theory-questions

**Speaker:** Freddy Sarmiento `[PP]` — Moderator
**Time:** 7:05 AM

> think of this gamma levels as pivots, where you put a tight sl and look for a good move in your favour.... the difference with other methodologies / technical analysis, etc, is that here, we see what really moves the market, institutions interacting with the market, in specific levels with volumes that create an impact....

### What's new vs existing docs

Two framing additions, no new mechanics:

1. **"Gamma levels as pivots"** — a useful one-word handle for the mental model. Pivots in trader vocabulary = levels around which sentiment turns and risk is defined. Marries §3 (tight SL around the level) with §11 (the level is where regime can flip).
2. **The differentiator from TA** — explicit statement that TA shows pattern recurrence, gamma shows institutional footprint. Adds to [§10](freddy_methodology.md) (algorithmic execution) and [§1](freddy_methodology.md) (why these levels at all). Not "gamma instead of TA" — "gamma is what the institutions actually did; TA is the trace of what the institutions did, post-hoc."

No new operational rules. Both points fold into existing sections as
brief addenda rather than new sections.
