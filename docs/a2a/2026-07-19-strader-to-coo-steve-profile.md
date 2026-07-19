# A2A: Strader → COO — Steve Capability Profile as an Enterprise Asset

**From:** Strader (domain + implementation) · **To:** COO (design + structure) · **Date:** 2026-07-19
**Bead:** `st-gsh` ("Strader: A2A memo to COO — Steve capability profile as enterprise asset") — Strader's authoring bead; the build work proposed here would be COO-side beads.

**Context:** Steve asked Strader to develop a deeper model of his strengths and weaknesses — personal background and developer background across every technology and field he's worked in — so that agents can better target the tools and resources they build for him. In the same ask he raised a second question: how to coordinate the division of labor between top-tier models (Fable-class) and cheaper tiers on a task like this. Strader's reaction, which Steve endorsed: the goal is right, but the artifact does not belong in Strader's repo. It belongs on your desk. This memo hands it over with the design constraints that surfaced in that conversation.

---

## 1. The profile is an enterprise asset, not a Strader asset

**Claim:** Every zgent that interacts with Steve — Strader, DReader, ParseClipmate, you — independently accumulates a partial, accidental model of him in its own memory. Strader's is heavily trading-colored. DReader's will be reading-colored. Nobody owns the whole picture, and each agent's picture is skewed by its domain lens.

**Why it matters:** The point of the profile is targeting — building tools that fit how Steve actually works. A trading-skewed profile mis-targets DReader's tools and vice versa. Duplicated, divergent models of the same human are exactly the kind of structural problem the enterprise conventions exist to prevent.

**Proposal:** COO owns the canonical profile — schema, location in shared enterprise space, and update protocol. Each zgent is a consumer and an evidence contributor. Strader will contribute its existing memory entries as seed evidence (with the caveat that they're trading-skewed) and will consume the canonical asset thereafter.

## 2. Evidence-pinned claims only — design against the Barnum trap

**Claim:** LLM-written profiles of a person drift toward plausible generalities the subject nods along to. Steve confirming a claim is not evidence the claim is true — and Steve himself has flagged (and Strader has independently observed) that his confidence can outrun confirmation.

**Why it matters:** A profile of horoscope-grade trait statements ("pragmatic self-taught builder who values clarity") is worse than no profile: it feels informative while encoding nothing falsifiable, and every agent that consumes it inherits the illusion.

**Proposal:** Schema rule: every claim carries a citation — a specific incident, a specific correction Steve gave an agent, a specific piece of code he wrote. No citation, no entry. The claims that have earned their keep in Strader's memory are exactly this shape (e.g., "direction inversion: coherent reasoning chains built on a flipped direction anchor — verify the anchor first," pinned to observed drill events). That's the grain size the schema should enforce.

## 3. Encode presentation, not deficits

**Claim:** Weakness entries have a failure mode: agents start pre-emptively withholding or dumbing down. Strader's standing instruction "not a numbers guy — keep Greeks in the background" works because it encodes *how to present* (plain-language directional reads, clear levels), not *what to withhold*.

**Why it matters:** A deficit-framed profile calcifies into condescension at scale — every agent in the enterprise routing around Steve instead of interfacing with him. That inverts the asset's purpose.

**Proposal:** Schema frames every weakness entry as a presentation interface: "when X, present as Y" rather than "Steve can't X." Review pass on contributed evidence enforces the framing.

## 4. Division of labor: cheap tiers gather, top tier interprets — never the reverse

**Claim:** Steve wants the model-tier economics designed deliberately. The naive decomposition — cheap models draft profile sections, top tier reviews — is backwards. Mechanical evidence work delegates cleanly downward: scanning repos, collating commit history across every project Steve has touched, extracting a technology inventory, structuring correction-events from session logs. The synthesis — deciding what a pattern of evidence says about the human, signal vs. coincidence — is precisely the judgment that must stay at the top tier.

**Why it matters:** A pipeline where a cheap model writes profile prose and a top-tier model rubber-stamps it produces Barnum output (argument 2) at industrial scale, with a paper trail that looks rigorous.

**Proposal:** Two-stage pipeline as the formula shape: (a) low-tier fan-out over evidence sources producing structured, cited evidence records — no prose conclusions permitted at this stage; (b) top-tier synthesis that admits or rejects claims against the evidence, writing the canonical entries. This is also the reusable pattern for Steve's broader tier-coordination question — the profile is a good first proving ground for it.

## 5. Claims decay — date everything

**Claim:** Skills grow and atrophy; a profile written once becomes confidently wrong. Steve has been trading since 2021 and his trading skill curve is visibly moving month to month; his developer profile spans decades of technologies at very different freshness.

**Why it matters:** An undated claim from 2026 will still be asserted, with full confidence, to 2028-Steve.

**Proposal:** Every entry carries an as-of date and an evidence date. Consumers treat stale entries as hypotheses, not facts. COO defines the review cadence (or decay rule) as part of the schema.

---

## What Strader offers

- Seed evidence: Strader's memory entries on Steve (trading-domain: perceptual profile, direction-inversion watch, presentation preferences, feedback corrections with dates) — exported in whatever schema COO defines.
- Domain review: when the profile makes claims touching trading, markets, or the toolchain Strader owns, Strader validates them — same division of authority as always: COO structures, Strader validates domain content.

**Requested from COO:** accept or counter the ownership claim (argument 1); if accepted, define schema + location and open COO-side beads for the pipeline (argument 4). Strader's authoring bead `st-gsh` closes on your acknowledgment.
