# Code Estate Plan — catalog, test, review, retire

*st-nujt · 2026-08-12 · Strader, from a 32-agent census of every authored code
file in both repos: per-file records, an invocation map built from ground truth,
adversarial verification of every dead-code candidate, and three analysis lenses
(coverage, fragility, cross-repo contracts). Machine-readable evidence committed
at `docs/audits/2026-08-12-code-estate/` — the catalog starts life populated.
Sibling of the Zgent Sync Plan (st-aski); companion A2A memo:
`docs/a2a/2026-08-12-strader-to-coo-code-estate-plan.md`.*

**The short version.** The daily gap-and-bug drip is not bad luck and it is not
volume — it is seven specific defect classes, each with a structural predictor
you can see in the code *before* the incident, recurring because nothing
mechanical prevents them. The worst of the seven: **verification machinery that
exists but nothing runs** — the live-parity acceptance check has never executed
(its own header says "NOT YET INSTALLED IN CRON"), COO's regression guard
against silent sync failures is itself never invoked, and no automation runs
either repo's test suite on the paths that matter. The estate is ~730 real
authored files once you subtract a 1,338-file virtualenv committed into COO's
git, two deprecated Gas City trees, and the vendored Schwab fork. Of those, 338
are live-path or in active development, 103 are now *confirmed* dead with search
evidence, and 115 sit ambiguous awaiting an owner's ruling. The plan: a
registry generated from this census, one wiring meta-test per repo so a guard
can never again be decoration, test anchors for the nine named trading-day
gaps, consumer-side pins on all ~14 cross-repo seams, and a standing
retirement protocol. Phase 0 beads are filed; two decisions are yours.

---

## The estate as measured

| | Strader | COO | Notes |
|---|---|---|---|
| Enumerated files | ~560 | ~1,600 | COO count inflated by a **committed virtualenv (1,338 files)** |
| Real authored code | ~420 | ~310 | after venv, Gas City, vendored fork |
| Active (depended or in dev) | ~230 | ~108 | wired to crons, skills, pipelines, supervisors |
| Test files | 96 (801 tests pass, ~62s) | **9, no runner, no CI** | |
| Confirmed dead (verified) | 22 | 81 | every verdict carries what was searched |
| Ambiguous (needs owner ruling) | 115 estate-wide | | referenced only by other dead candidates, etc. |
| Dormant (unwired but plausible) | 205 estate-wide | | mostly completed measurement campaigns |

Two special holdings: both repos carry **deprecated Gas City trees** (98 files,
fully dead by evidence — last event write 2026-06-12, zero live references) plus
the **104MB `gc` binary still on PATH**, whose settings carry
`skipDangerousModePermissionPrompt=true` and whose `dolt recover` contradicts
current beads-recovery doctrine. And Strader's `lib/schwab-py` fork is healthy
and load-bearing but last synced against upstream in ~2024 — its DEFENSE NOTE
hobble is verified only by convention (fixed by st-wwnv below).

## The seven defect classes (why a new bug surfaces daily)

Each class: what it is → the structural predictor → the mechanical prevention.
The full statement with all instances is in the audit's `lens-analyses.json`.

1. **Stale defaults encoding external state** (cancelled-OPRA default st-13pi,
   gate requiring a halted stream st-7av4, RTH-only belief st-a6zm). Predictor:
   a literal about an external system with no probe. Prevention: derive
   defaults from what the account/manifest actually holds; date-stamp doctrine
   claims.
2. **Silent success** (defective Schwab grant accepted st-r1b5, empty internals
   recorded as success st-kzhe, zepo-sync failures dropped, desk refresh
   silent-skip st-qx4). Predictor: success = "the call returned," `|| true`
   shells. Prevention: the st-kzhe principle — success is a property of the
   *artifact* (exists, parses, carries required fields), verified before the
   heartbeat is written.
3. **Unsupervised long-running processes** (sentinel died with the 08-11
   reboot; the 08-05 tmux death). Predictor: liveness depending on a tmux
   window or hand launch. Prevention: thin cron shims over the proven
   capture-supervisor engine — which relaunched capture in 4 seconds this
   morning while the unsupervised sentinel needed a human.
4. **Guards on hand-maintained lists that rot** (the datastream gate needed
   three semantic corrections in five days; surface_liveness patterns;
   conftest's live-surface list). Predictor: a guard containing a literal list
   whose population is defined elsewhere. Prevention: registry-derived checks,
   or a meta-test diffing the list against the population.
5. **Copy-mirrored duplicates drifting** (continuation_meter's bucket edges
   copied not imported; two Mancini fetchers; two desk renderers; May-frozen
   mock Schwab client). Predictor: the words "mirror" or "keep in sync" in a
   comment. Prevention: import the constant; fixture-diff tests for
   cross-language twins; canonical rulings with the loser deleted.
6. **Cross-repo contracts held by absolute paths and comments** (~14 seams;
   two already broke live — the stale desk page and the steves-desk window
   adopt gap st-b9pf, both confirmed). Predictor: a `/root/projects/<other-repo>/`
   path in code; a tmux name two scripts must agree on; a sourced lib behind a
   blanket gitignore — COO's `tmuxMOO/lib/moo-theme.sh`, a live dependency of
   every desk pane, **exists nowhere in version control**. Prevention: the
   consumer's test suite pins the producer's interface.
7. **Built-but-never-wired verification** (live-parity; check-dolt-schema-skew
   lost its only invoker; regime.py tested but wired to nothing; COO's tests
   orphaned entirely). Predictor: a guard whose activation needs a second,
   hand-performed step recorded nowhere machine-checkable. Prevention: the
   wiring meta-test below, and "wired" as a bead close-condition.

One cross-class chokepoint: the **Schwab refresh token** — one credential,
seven-day human-in-loop renewal, six trading-day surfaces hanging off it,
health checked once daily against an intra-day failure mode. (This morning's
expiry was handled — you re-authed at 05:06 and I verified the new grant live —
but the *class* stands.) Fix: token-health assertion at point of use in every
Schwab-dependent cron wrapper, and the st-6gs3 corpus-fallback pattern for
every degradable surface.

---

## The standing machinery

### 1. The registry (catalog)

`docs/audits/2026-08-12-code-estate/census.json` is the catalog, populated:
per-file purpose, wiring, last commit, author mix, test anchors, outputs,
status, evidence. Standing rules:

- **Every active-depended file must carry**: an owner, its wiring, a test
  anchor, and (for long-running processes) a liveness hook. The census says
  which fail that bar today; the Phase-0 beads close the worst.
- **The census is code, not a one-off**: a `tools/estate_census.py` re-runs the
  mechanical parts (enumerate, git-date, wiring grep, status diff vs registry)
  weekly via cron; its diff — new unregistered files, wiring that vanished,
  active files whose tests disappeared — lands in the tap-in briefing.
- New code lands with a registry entry in the same commit (checkable: the
  weekly diff flags violations).

### 2. The wiring meta-test (one per repo)

A test asserting every `scripts/cron/*.sh` (and every checked-in guard) appears
in the live crontab, a runner, or an explicit deferred-list carrying a bead ID.
This single test catches the live-parity class forever — a guard that isn't
wired fails the suite instead of decorating the repo. COO's twin catches
check-dolt-schema-skew and the orphaned test suite.

### 3. Test tiering and runners

- **Tier 1 — trading-day-critical** (datastream gate, corpus collectors and
  write spine, Mancini chain, Schwab gate + token, desk delivery, live
  watchers): every file gets its named minimum anchor — the audit specifies
  each (golden files, artifact-property regression tests, contract fixtures) —
  no aspirational full coverage.
- **Close the CI seam**: CI currently *names one file to skip the rest* of the
  corpus suite — the live streamer, Schwab stream, and source-deleting
  compaction tests run only on remembered local pytest (st-tbxk).
- **Runners**: nightly cron runs Strader's full suite (~62s); COO gets
  `tests/run-all.sh` on its 22:30 pulse cadence (delegated).
- **Honest greens**: the May-17 entity/indicator stratum pins a superseded
  architecture — 801-green overstates live coverage. Decision 2 below.

### 4. Contract pins (the ~14 seams)

Consumer pins producer: `tests/contracts/test_coo_seams.py` asserts every COO
path Strader hardcodes exists and keeps its interface (st-1idb) — unskippable,
unlike the current test that skips exactly when the contract breaks. Plus the
shared window-name/desk-slug manifest, `/var/moo/desk` as the one canonical
desk path (migrating the two `/tmp` holdouts), the corpus-cron ownership
handback ("temporary since 2026-07-01"), and COO-side gitignore carve-outs so
moo-theme.sh survives a re-clone. A2A receipt mechanics come from the sync plan
(st-75z0) — the channel these fixes travel over must not be the one that fails
silently.

### 5. The retirement protocol

- **Confirmed-dead (103)**: delete in tranches, git is the archive. Strader's
  22 go first (st-sl1f) — with `corpus_poll.py` handled as a **loud stub, not
  a delete**, because it is actively dangerous while callable (double-writes
  the live corpus per its successor's own warning). COO's 81 travel via the
  A2A memo.
- **Ambiguous (115)**: owner rules within two weeks; unruled items default to
  the dead tranche. The verdicts file lists each with its evidence.
- **Dormant (205)**: stay, registry-marked with a reactivation note (most are
  completed measurement campaigns whose rerun-on-corpus-growth design is
  intentional). A dormant file whose twin drifts (acuity_run2 vs speak_replay)
  gets a drift assert or a merge.
- **Deprecated**: both Gas City trees + the 104MB binary — Decision 1.

### 6. Definition of done

A bead that authorizes a guard, collector, or cron closes only when the thing
is **wired, anchored, and registered**. Enforcement lives in the bd-close-gate
hook (COO's — delegated ask), not in memory.

---

## Phase 0 — beads filed today, ranked

| Bead | What | Why first |
|---|---|---|
| st-hrwe | Install live-parity cron + freshness assert | cheapest risk reduction in the audit |
| st-swkk | Sentinel: supervisor shim + liveness pattern + contract test | only session-critical watcher with zero restart path; died yesterday |
| st-bpzd | Corpus write-spine tests (writer.py, gexbot_stream, internals) | irreplaceable tape behind zero direct tests |
| st-uawp | Share the session gate with the 1 Hz poller | quota-burn guard covers one of two paid collectors |
| st-1idb | Cross-repo seam tests + window/slug manifest | two seams already broke live |
| st-tbxk | CI seam: corpus suites into CI + nightly runner | most dangerous suites are the excluded ones |
| st-wwnv | Schwab gate machine-checks (factory refusal + hobble assert) | hard boundary, currently convention-verified |
| st-sl1f | Dead tranche 1: loud-stub corpus_poll.py, delete 22 | one actively dangerous callable in the set |

Registry codification (`tools/estate_census.py` + weekly cron + meta-tests) is
the follow-on bead once Phase 0 lands.

## Decisions that are yours

1. **Gas City final deletion.** Both `.gc` trees, and the 104MB `gc` binary on
   PATH (not in git — this one is genuinely irreversible). Evidence says fully
   dead; the binary's settings include a dangerous permission bypass, and its
   recovery verb contradicts beads doctrine. My read: delete all three, after
   an archive tarball to `/var/moo/backups/`.
2. **The May-17 test stratum.** ~10 green suites pin a superseded entity/
   indicator architecture (GEX math frozen pre-GexBot-live). Delete with their
   targets, or mark legacy so `801 passed` stops overstating. My read: delete —
   the sync plan's single-home law applies to code too.
3. **COO's committed virtualenv** (1,338 files) — rm + gitignore, no history
   rewrite. COO-side; in the A2A memo. Nod needed only because it's their tree.
4. **Ratify the COO delegation bundle** (in the A2A memo): tests/run-all.sh on
   the pulse, desk-html/desk-register smoke tests, gitignore carve-outs,
   schema-skew preflight rewire, corpus-cron handback, venv purge, steves-desk
   adopt fix (st-b9pf), bd-close-gate wiring condition.

## What success looks like

Rerun `estate_census.py` weekly and this full audit in mid-September. Targets:
zero unwired guards (was: at least 6), zero unsupervised long-runners (was: 4+),
Tier-1 anchor coverage 100% (was: 9 named critical gaps), confirmed-dead count
0 (was: 103), ambiguous 0 (was: 115), every cross-repo seam carrying a
consumer-side pin (was: ~1, and it skipped). The "new gap every day" feeling
should be replaced by the weekly sweep finding them first.
