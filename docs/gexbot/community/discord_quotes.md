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

**Speaker:** Freddy Sarmiento `[PP]` — Moderator, Discord community member, NQ futures trader (the speaker in the [Trading with Gamma video](freddy_video.md))
**Time:** 12:23 PM
**Posted:** day after the Trading with Gamma video (2025-01-24)

> Gexbot Will help you ( as it helped me )… I think if you execute more like an algorithmic model, you'll be fine.. Jass emphasis on entering on the high net convexity, tight SL if price breaks that level against you but entering again of price moves on your bias.

### Three rules embedded

1. **Algorithmic execution** — already covered, [`freddy_video.md` §10](freddy_video.md).
2. **Enter on high net convexity** (= excess gamma) — already covered, [`freddy_video.md` §3](freddy_video.md) step 1–3.
3. **Re-entry after stop-out** — **new**, now slotted as [`freddy_video.md` §3 step 6](freddy_video.md).

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
