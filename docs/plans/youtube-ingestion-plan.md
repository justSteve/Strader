# YouTube Ingestion — the Plan

**YouTube Ingestion Plan** (`st-eww7`) · 2026-08-30 · Strader

Every number below is **measured** — read off the code, the 137 archived runs,
and `LESSONS.md` on 2026-08-30, confirmed by yt-analyst directly. Section 2
onward is **proposed**; none of it is built yet.

---

## 1. What exists today

Two paths. They do not join.

### Path A — captions (Strader-local)

`scripts/fetch_youtube_transcript.py` → `docs/gexbot/transcripts/`

Auto-captions via `youtube_transcript_api`; writes raw `.json` plus a `.txt`
with `[MM:SS]` markers. Language-aware — prefers `--lang`, falls back to
whatever track exists, and records which, because several GexBot-community
sources publish Spanish captions only and an English-only default reported
those as "no transcript". 5 transcripts landed.

**It is deaf to the screen.** Every footprint layout, DOM column, ticket
number and chart annotation is invisible to it.

### Path B — vision (`DReader/yt-analyst`)

**Correct characterization, and this matters for the plan: it is not an
ingestion pipeline.** It is a human-in-the-loop interrogation CLI with
unusually rigorous verification doctrine. `yta.py` has three subcommands —
`ask`, `frames`, `index` — and no orchestration above them. The "pipeline" is
doctrine in `yt-analyst/CLAUDE.md` that a Claude session follows by hand.

Two different byte paths:

- **`ask`** downloads nothing. The canonical `watch?v=ID` URL goes to Gemini
  as a `file_data` Part; Google fetches and samples server-side, at low
  resolution. Clipping is `start_offset` / `end_offset` — Gemini samples and
  bills only that window. Output is forced JSON: `summary`, `claims[]` (each
  with `t`, `kind` ∈ `onscreen_text | visual | spoken | inferred`, `claim`,
  `verbatim`), `uncertainties[]`.
- **`frames`** downloads for real — `yt-dlp --download-sections` on that window
  only, pinned to avc1/mp4 (the default selector picked VP9/webm whose section
  clip had a zero-length video track), then `ffmpeg -vf fps=N` to jpegs at
  1920×1072.

**That asymmetry is the whole point.** Gemini sees a low-res server-side
sampling; the frame check sees actual pixels. Two independent vision systems.

Per video, on disk: `CARD.md` (curated above `## Run log`, machine-appended
below), `runs/<ts>/{request,response}.json`, `frames-MMSS-MMSS/`. Versioned
product is `CARD.md`, `INDEX.md`, `LESSONS.md`, `playlists/*.md`; `runs/` and
`frames-*/` are gitignored working data.

**Corpus:** 19 videos, 3 channels, 6h 02m, 137 runs, all cards closed.

| Channel | Videos | Runtime | What it is |
|---|---:|---:|---|
| Smart Money Decode X | 10 | 2h 20m | zero-to-advanced structure series |
| Carmine Rosato | 8 | 3h 31m | the 8-episode Trading Orderflow Series |
| tastylive | 1 | 11m | wide butterfly technique |

One orphan: `sPqeW4j-8Zk`, 2 runs, no card.

### The bridge, today

Hand-written. Desk read the Carmine playlist synthesis and wrote memo
`20260828T214201__Desk__orderflow-baseline-v1-carmine` — 24 claims `OFB-01..40`
plus 5 gaps — which produced **Carmine Register Filed** (`st-snd8`) and the
curation pass (`st-byxz`). Neither is done; `knowledge/sources/` does not exist.

**And there is no handoff contract.** yt-analyst says so plainly: nothing there
was designed to be consumed programmatically. What exists is a stable
convention, not a commitment.

---

## 2. The plan

### 2.1 yt-analyst is the engine. Strader builds no second one.

Path B sees the screen and carries frame-level verification. Duplicating it
here is a second thing to maintain and a second place for provenance to rot.
Strader is a **consumer**, not a peer producer.

Path A demotes to **audio-only material** — podcasts, talking heads, anything
where nothing load-bearing is on screen. The Bear Trap skew podcast (`st-lks`,
47:08) is exactly that. It stays; it stops being the default.

**Routing rule:** claim on the screen → `yta.py`. Claim in the speech →
captions. In doubt → one wide pass, ~$0.02.

### 2.2 The handoff contract is a claim register, not a memo

A memo is prose a person must re-read. The register is what Strader can operate
on. Each source arrives as:

`knowledge/sources/<slug>.md` — front matter `type: register`, `status: source`,
citing the bead. One numbered row per claim.

**`status: source` is load-bearing: a register records what somebody else says,
not what we do.** Nothing is a rule until Steve promotes it.

### 2.3 Every claim carries provenance and a verification grade

Non-negotiable, and §4 is why. Per claim: video id + `MM:SS`; `kind`
(`onscreen_text` / `visual` / `spoken` / `inferred` — an inference is not a
reading); and **verified how** — `frames` / `arithmetic` / `parity` / `cross-episode`
/ `unverified`.

yt-analyst's own ask, and I agree with it: **a finding that reaches
`knowledge/` stripped of its verification grade is worse than no finding.**

### 2.4 We do not consume `runs/`

Gitignored, machine-local, pre-curation, and explicitly unverified raw model
output. Pulling findings from there bypasses every check in §4. Cards and
playlist syntheses only.

### 2.5 Curation annotates against our own stack

Second pass, per claim: **converge | diverge | extend | silent** against
`recognizer.py`, the scorer's footprint columns, and `knowledge/` canon, with
the citation.

- **Convergence inside our own canon is a finding**, not a no-op — if OFB-20
  reversal-first is already encoded under another name, that is worth knowing.
- **Divergence goes to Steve.** Never merged, never averaged.
- **Any number we supply where the source gives none is OUR synthesis, labelled
  so.** Carmine calls a delta outlier "just an OUTLIER in the data" and names
  no threshold; whatever we adopt is Strader's.
- **Silent stays silent.** A source saying nothing about regime conditioning
  has not endorsed ours.

### 2.6 Promotion is Steve's

`status: source` → doctrine is one decision and it is his. The register makes it
cheap: a numbered claim, its verification grade, our annotation — yes or no.

---

## 3. Cost and throughput

Model `gemini-flash-latest`; **all 137 runs answered by it, zero fallbacks.**

**Whole corpus to date: 3,357,826 prompt + 194,673 output tokens ≈ $1.49.**
19 videos, 6h02m, two full playlists, for a dollar and a half.

| shape | n | mean prompt tokens |
|---|---:|---:|
| wide (no clip) | 21 | 97,164 |
| clipped | 116 | 11,356 |

**The rate is 91 tokens per second of video — min = median = max = 91** across
all 19 default-knob wide passes. Not "about". A wide pass is exactly
predictable: 11-minute video ≈ 60K ≈ $0.018; a 1–3 min zoom is 7–25K, about
half a cent.

**`--fps` scales cost linearly; `--resolution` is inert** on the URL path
(default = `low` = `high` = 5,699 tokens exactly on the same window; `--fps 5`
= 21,539 exactly). Fits `tokens ≈ seconds × (66·fps + 32)`. **And 1 fps was
more accurate** — it read every cell of a dense table correctly while 5 fps
fragmented the claims. Cheapest config = most accurate config.

**Operational rules that cost real money to learn:**

- **Never ask for verbatim transcription on a wide pass.** One 21-minute video
  hit Gemini's `RECITATION` filter: `finish_reason=RECITATION`, `text=None`,
  **119K prompt tokens billed, nothing returned.** Reworded to "in your own
  words" → full answer. Verbatim belongs only on clipped 1–3 minute windows,
  where it has never once tripped.
- Throughput that works: wide passes sequential with 20 s gaps, zooms 3–4
  concurrent, frames sequential. Ten videos fully carded in one session.

**Ingestion cost is not the constraint.** The constraint is verification and
curation labour. Budget in claims curated, not videos ingested.

---

## 4. The error profile — what we must not trust

This is the section that earns the whole document, and it is the part I want
carried into `knowledge/` accurately. **There is no single hallucination rate.
The error rate is strongly conditional on what is being read.**

| Content type | Measured |
|---|---|
| Prose slides, structure, teaching content, paraphrase | high reliability across all 19 videos |
| Hand-lettered grids | 28/28 rows digit-perfect |
| **Dense numeric grids from real platform chrome** | **~20–25% of rows wrong** — 4/21 and 5/21 on two bid×ask ladders (swapped rows, an invented `1466×2315`, a dropped row) |
| **Time & Sales tape** | **6 of 14 rows carried a wrong digit** — row order and structure stayed correct |

So: small-font platform chrome degrades digits. On clean hand-lettered content
the failure mode changes to **omission** — it silently skipped three other
ladders in one video, including the one carrying the narrated number.
**Legibility drives row errors; coverage drives whole grids going missing.**

**Rule: any ladder or tape over ~10 rows is frames-only.**

### The named failure modes

Each confirmed 2–3× independently.

- **Glyph confusion — `$5` reads as `60`.** `0p ($5806)` → `"Tp (6080)"`;
  `RESISTANCE ($5730)` → `"RESISTANCE (60720)"`. **ES prices in 2024–25 all
  begin with 5, so this hits every price label on every chart in the Carmine
  corpus.** Any level number from that series is suspect until frame-checked.
  Two siblings in the same corpus: **`$` reads as `1`** on journal input boxes
  (`$ 5631.0` → `1 5631.0`, and the same prefix rendered elsewhere as invented
  ↑/↓ arrows); and **cross-chart axis bleed** — a price range Gemini reports for
  one chart actually belongs to a different chart minutes away. **So a price
  label can be wrong in its digits *and* attached to the wrong chart.** Frame
  provenance has to establish both, not just the number.
- **Derived numbers presented as on-screen values.** "Max Profit 850 / Max Loss
  650" computed from the host's spoken "$6.50"; the ticket read 740 / −760.
  **These pass arithmetic by construction** — the one case where arithmetic
  verification is worthless and only frames work.
- **Occlusion truncation, unflagged.** `Daily Avg: 1,475,6…` behind a webcam
  bubble reported as `1,475` — off by three orders of magnitude, no uncertainty
  raised. On one channel a watermark hides the last word of every right-aligned
  line and Gemini *invents* it.
- **Regularization.** It repairs an inconsistent on-screen sequence into the
  pattern it expects and reports the repair as transcription. A ladder printing
  `$100.00` came back `$100.15 → +10¢ → $100.25`. Anything stepped, laddered,
  numbered or branching is exposed. **This is derived-numbers' sibling and it
  shares the poison: a regularized sequence is internally consistent by
  construction, so arithmetic ratifies it.** Heuristic that has held: **a
  sequence that closes too neatly is suspect.**
- **Fabricated chrome.** A complete TradingView header — `ES • 1 • CBOE / O
  5834.00 H … Volume 24.49K` — none of it on screen. Headers, legends and
  footers are where it invents plausible filler.
- **AI-generated chart pastiches are never flagged.** On a channel whose
  "TradingView" charts are illustrations (garbled chrome, non-monotonic axes,
  OHLC with L > H) it invents exchange names and axis values and never says the
  chart is incoherent. **Cheap tell for a new channel: pull one frame of any
  chart — if the price axis is not monotonic, that channel's charts are decor
  and no `visual` claim from them is citable.**
- **Prior-knowledge leak on identity.** Channel names complete from priors —
  "InvestiTrade" for a channel with no wordmark; one logo returned six different
  ways. **Channel identity comes from yt-dlp metadata plus one frame, never
  from Gemini.**
- **`uncertainties` flags are honest; their stated reasons are fabricated.**
  "Occluded by red text" where no red text existed. Trust the flag, never quote
  the explanation.
- Timestamps run 2–5 s early on animated slide builds. Pad +5 s after a slide
  stamp, ±10 s generally.
- Wide-vs-zoom disagreement: **neither shape is privileged**, 1–2 across three
  instances. Two reads that differ ⇒ pull frames.

### The four verifiers, cheapest first

1. **Arithmetic / structural.** Points × contracts × $50 = P&L; P&L ÷ risk = R.
   **On footprints, parity is decisive and it is ours:** delta = ask − bid and
   volume = ask + bid share parity, so "−583 beside volume 1498" is impossible
   with certainty — the pixels read −538. This is a Strader-native verifier and
   it should be applied to every footprint claim in the OFB register.
2. **Cross-episode consistency.** A series reuses slides and trades. The same
   Oct 3 2024 trade appears in three episodes with identical fields — free
   verification, no API call.
3. **Frames.** ±10 s around the claim. 1,467 frames across 154 windows for this
   corpus.
4. **An Opus subagent as second reader**, given a numbered checklist and a
   ~25-call budget. Nine of them on one playlist: 5.5–10 min each, and **every
   single one surfaced a finding the parent session had missed.** Without the
   call budget one hung for ~60 minutes with zero output.

A disagreement between our read and Gemini's is **never resolved silently** —
both versions go to Steve with the frame path.

### What the cheap filters do not buy

**Every zero-cost filter above validates the number.** Parity, arithmetic,
cross-episode consistency, the glyph tells — all of them are digit-level. So a
*correctly read* price attached to the wrong chart passes every single one of
them, and cross-chart axis bleed is precisely that failure.

**They bound to digit error. Attachment is established only by a frame at that
timestamp.** This is the shape of the gap our register had — digit filters and
no attribution check — and it is not specific to us: anyone inheriting figures
from these cards has the same hole unless they check what the number was
attached to.

---

## 5. What is not built

Being blunt, per yt-analyst's own accounting. Treating this as a dependable
ingestion pipeline today would misrepresent it.

| # | Gap | Whose |
|---|---|---|
| 1 | **No playlist automation.** Both playlists were driven by a session issuing parallel Bash calls by hand; those runners were never committed. Positions transcribed manually. | yt-analyst |
| 2 | **No caption capture at all.** yt-dlp is used only for frame sections. Every spoken word reaches a card via Gemini's *paraphrase* — so spoken numbers arrive as the presenter's rounding ("1700" for an on-screen 1775). Captions are free and exact. | yt-analyst |
| 3 | **No metadata capture.** Title / Channel / Uploaded / Duration are hand-entered, with `--dump-json` one flag away. | yt-analyst |
| 4 | **No idempotency.** Every `ask` is an unconditional API call; same URL + window + question re-bills in full. | yt-analyst |
| 5 | **No structured output.** Findings exist only as curated English prose. | see §7 |
| 6 | **No tests.** Zero for `yta.py`; the timestamp, header and video-id parsers are trivially testable and untested. | yt-analyst |
| 7 | **No verification ledger.** Which claims were frame-checked lives in prose. You cannot query "show me every unverified number". | both |
| 8 | **Verification is not enforced.** Every guardrail in §4 is doctrine a session chooses to follow; nothing in the code stops an unverified number landing in a card. | both |
| 9 | `knowledge/sources/` does not exist. | **Strader — blocking** |
| 10 | The `sPqeW4j-8Zk` orphan: write it up or delete the runs. | yt-analyst |

**Strader owes items 9 and the curation pass. Items 1–4, 6 and 10 are
yt-analyst's and are not ours to build.** Items 7–8 are the shared one, and §7
is where they get resolved.

---

## 6. The queue

| Source | Path | Bead | Note |
|---|---|---|---|
| Carmine orderflow series (8 eps) | ingested; register pending | `st-snd8` → `st-byxz` | the live one. Apply the footprint parity check, and triage every ES price label against §4's glyph bug — the cards mark which prices were frame-verified, so **use the marking as the filter, never the price**. Provenance must cover attachment as well as digits. |
| GEXBOT new tools, 2025-10-27 | **vision** | `st-qei0` | product update; may document Orderflow changes newer than the whole series. Bead currently says captions — re-route. |
| NQ Orderflow live, 2025-05-06 | **vision** | `st-qei0` | live session; the value is entirely on the screen. Transcript is already fetched and is not enough. |
| Concepts review (1:04:59) | vision, then captions | `st-qei0` | 3,899 s × 91 ≈ 355K tokens, ≈ $0.11 for the wide pass. Worth it once. |
| Operativa del día (Spanish) | vision | `st-qei0` | captions Spanish-only; Gemini reads the screen regardless of language. |
| Bear Trap skew podcast (47:08) | captions | `st-lks` | audio-only — Path A is correct here. |
| Smart Money Decode X (10 eps) | ingested | — | no Strader register; see §7. |

---

## 7. Decisions — ruled 2026-08-30

> **Steve ruled on all three, 2026-08-30 14:33 CT.** 1 — authorized, relayed to
> yt-analyst as his instruction with the consumption shape below. 2 — no SMDX
> register, recommendation taken. 3 — deferred, reminder carried by
> `st-frkh`, one-shot, firing on the next session that runs `yta.py` rather
> than on a date.

**1. Authorize `yta.py export --json`? — AUTHORIZED.** Today Strader would have to screen-scrape
English prose out of `CARD.md` to get findings, which throws away the
verification grade exactly where §4 says it matters most. yt-analyst says a
`export --json` over the *curated* card sections — id, channel, playlist,
timestamped finding, verification method, source card path — is small work and
it would support building it, **but it will not widen its own tool's surface on
a peer's request; it wants your authorization.** That is the right call on its
part. Recommendation: **yes** — file it as a `dr-` bead. It is the difference
between a convention and a contract, and it closes gaps 7 and 8 at the same
time.

**2. Does Smart Money Decode X get a Strader register? — NO.** It stays in
DReader as reference. Structure/BOS/ChoCH material overlapping ground our canon
covers, and a register we do not curate is worse than no register. Nothing
queued; revisit only if a specific SMDX claim is wanted for a live question.

**The shape asked of the exporter** (input to yt-analyst, not a spec it owes
us): one record per curated finding, carrying `video_id`, `channel`,
`playlist` + position, `card_path`, the finding text and its timestamps,
`kind`, `verification` — with **the frame directory and timestamp where the
method is frames**, so the check is re-runnable rather than asserted — an
**`attachment`** field naming what the number was attached to, and
`card_status`. **The field asked for hardest is a stable finding id**: without
one our register must restate the finding text, and a restatement drifts while
an id does not. Everything else is recoverable; that one decides whether this
is a contract or a convention. Explicitly not requested: anything from `runs/`,
and any field that would need editing when something else changes.

**3. `dr-3b6` — DEFERRED, reminder requested.** `dr-3b6` — your Cherry
Bomb review bead, open since 2026-08-28 — carries three lessons yt-analyst
confirmed but never graduated into doctrine: paraphrase-never-verbatim on the
wide pass (the one that billed 119K tokens for nothing), grids over ~10 rows
are frames-only, and the parity check. It also holds two Gemini-vs-frames
adjudications and a pruning task. It declined to fold the three in on a peer
conversation, same reason it declined the exporter. *(Verified at source
2026-08-30: `dr-4c0` was filed for these first, then closed as a duplicate of
`dr-3b6`.)*

Carried here by `st-frkh`, because `dr-3b6` is a DReader bead our tap-in does
not read. **One-shot, and triggered by work rather than by a date** — it fires
on the next session that runs `yta.py` or starts ingestion work, because the
costliest open proposal is *paraphrase, never verbatim, on the wide pass* and
doctrine step 2 hands you the invocation that trips it. A reminder that arrives
as the money is about to be spent is worth more than a dated one. One plain
line, then the carrier closes.

---

## Appendix — the reusable asset, and why it is ours

`yt-analyst/LESSONS.md` is 405 lines of dated, independently-confirmed
observations of how a frontier vision model fails on dense financial
screenshots. The generalization that matters is sharper than "past YouTube":

**These are not video failures. They are dense-financial-screenshot failures.**
Small-font price glyphs, occlusion truncation reported as complete, fabricated
platform chrome, invented legend OHLC — none of it is specific to a video
frame. It applies to any chart image handed to a model, **including the
screenshots Steve pastes into this session**, which is a live path here and not
a hypothetical.

And a screenshot is the *harder* case, not the easier one: a hand-uploaded
image has no wide-pass/zoom structure to fall back on, so **the frame check is
the only check available** — there is no second sampling to disagree with.
Which makes the free filters disproportionately valuable there, because they
need no second image:

- **Footprint parity.** delta = ask − bid, volume = ask + bid, so the two must
  share parity. One line, no re-read.
- **The non-monotonic-axis tell.** If a chart's price axis does not increase
  monotonically, the image is decor and nothing read off its chrome is
  citable. **A one-glance test on any screenshot** — it was originally a
  channel-level judgment and generalizes down to the single image. **This is
  the one filter that needs no domain knowledge at all**: parity needs a
  footprint, "too neat" needs a sense of the expected pattern, but "is this
  price axis monotonic" is answerable by anyone looking at any chart — and it
  invalidates the whole image's metadata in one glance rather than one claim at
  a time. If a future session under time pressure applies exactly one thing
  from this, it should be that.
- **"Too neat is suspect."** Derived numbers and regularized sequences both
  pass arithmetic by construction; tidiness is the tell, not inconsistency.

This deserves its own `knowledge/` entry rather than a pointer, and it belongs
next to `feedback_never_guess_chart_readings` — that rule says crop and verify
or say "can't read", and this is the measured account of *why*, with the
mechanisms named. Filing it is a separate bead; flagged, not claimed.
