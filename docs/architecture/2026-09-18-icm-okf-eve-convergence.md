# ICM, OKF and vercel/eve — does the convergence hold, and where are the shared seams

Bead st-0sd0 · 2026-09-18 · architecture only. Every claim is **measured** (a command, a `file:line`, or a URL fetched this session) or **reasoned**. A README sentence is a claim of intent, not a measurement of behaviour.

## For Steve, five lines

1. The convergence holds on motivation, not on mechanism: all three say a folder of plain files should replace framework code so a human can read the system at a glance — but ICM steers a *model*, eve steers a *runtime*, and OKF steers *neither* (it is a data format with no agent in it).
2. OKF is not local convention. It is Google Cloud's Open Knowledge Format (spec v0.2 on GitHub, blog 2026-06-12); this enterprise runs a v0.1 profile with its own extensions, and two of those extensions collide by name with v0.2.
3. Four seams survive: the typed front-matter header as the address (`id` = file stem), a generated `context/` folder as a projection of the bundle, `file-id + lines @ commit` as the one cite, and the checker that fails a run when quoted words are not in the cited file. The append-only log and "written by code" survive as *practices*, not shared interfaces.
4. The honest counter: neither ICM nor eve fills the three holes the COO plan found in ICM (no runner, no source list, no citation convention). eve supplies a runner and a skill loader; it supplies no source list and no citation check, so the checker stays ours.
5. First move, smallest: finish the header migration (st-ts3o) — 2 of 45 bundle files validate today — then generate the lane's manifest from the loader (st-apxk). Adopt eve's *conventions* only if an agent must ever run outside Claude Code; do not adopt eve itself now.

The talk: no fetched source contains "we've replaced a team of agents with a folder." Candidates in §1.4; none is about eve.

---

## 1. Motivation, side by side

**ICM** — measured (abstract, https://arxiv.org/abs/2603.16021, Van Clief & McDermott, v2 2026-03-18): "Current approaches to AI agent orchestration typically involve building multi-agent frameworks that manage context passing, memory, error handling, and step coordination through code … for sequential workflows where a human reviews output at each step, they introduce engineering overhead that the problem does not require. This paper presents Model Workspace Protocol (MWP), a method that replaces framework-level orchestration with filesystem structure. Numbered folders represent stages. Plain markdown files carry the prompts and context … Local scripts handle the mechanical work that does not need AI at all." Paper §3.2 (fetched): "Stage sequencing is the folder numbering. Context scoping is the folder hierarchy. State management is the files on disk." §5.2 excludes real-time multi-agent loops, high concurrency and mid-pipeline branching. The problem named: framework code is the wrong tool for *sequential, human-reviewed* pipelines.

**OKF** — measured: the enterprise sweep (`command grep -r` over `/root/projects` for "OKF spec|Open Knowledge Format|reference parser") finds no pointer to a spec, but `COO/tools/okf/graduate-memory.py:32` says "OKF v0.1 requires all four. Google's reference parser rejects a file missing any of them", and the web resolves it: `GoogleCloudPlatform/knowledge-catalog/okf/SPEC.md` (fetched), v0.2, §13 "v0.2 supersedes OKF v0.1"; Google Cloud blog 2026-06-12, McVeety and Hormati (fetched). Spec §1: knowledge should be "Readable by humans without tooling, Parseable by agents without bespoke SDKs, Diffable in version control, Portable across tools, organizations, and time"; "There is no schema registry, no central authority, and no required tooling"; "`type` is the only always-required key"; `index.md` is for "progressive disclosure: letting a human or agent see what is available before opening individual documents." Blog: the problem is knowledge scattered across "mutually incompatible surfaces"; the fix is "a shared markdown library … your agents take on the drudgery of reading and updating their own files, while your team curates the content and manages it like code." Nothing about orchestration, stages or pipelines.

**eve** — measured (README, fetched): "a filesystem-first framework for durable AI agents" where "core agent capabilities live in conventional locations, so projects are easier to inspect, extend, and operate"; Apache-2.0, public beta, 5.3k stars. Blog "Introducing eve", 2026-06-17 (fetched): the problem was "every team was building and rebuilding the same plumbing before their agent could do anything, and none of it carried over"; the fix, "at a glance, the tree tells you what an agent is, what it does, where it lives, and when it acts on its own"; "Agents have a shape … every generation of software earns its abstractions once enough people have built the same thing the hard way." `AGENTS.md` (fetched raw): "You author an agent as a directory on disk — instructions, skills, tools, connections, channels, subagents, and schedules are all files." "Derive names from file paths." The problem named: repeated plumbing and uninspectable agents; the fix is a *framework* — the opposite of ICM's "no framework" — whose authoring surface is a directory.

**1.4 Coincidence versus appearance** (reasoned from the quotes). Genuinely shared: the tree must be legible to a human without tooling; version control is the audit trail; markdown carries what a model reads. Only apparent: ICM is anti-framework, eve is "Next.js for agents"; OKF is about what agents *read*, not what they do — it enters ICM only as Layer 3 `references/` and eve only as `skills/`. Steve's "returning to Folders and Files" is true of the authoring surface in all three and false of eve's execution substrate: sessions are durable workflows checkpointed per step, persisted locally "on disk under `.eve/.workflow-data`" and on Vercel Workflow in production (measured, execution-model doc).

**The talk.** Not identified. Candidates (each fetched or from search results; each fetch confirmed no mention of eve): (a) Jake Van Clief — ICM's first author — "How I Structure Folders to Replace AI Agents", 23 min, 2026-03-10, on his Clief Notes page (skool.com; no video link there), "the three layer routing system … how naming conventions replace databases"; (b) YouTube "Stop Building AI Agents. Use This Folder System Instead." (id MkN-ss2Nl10; page would not render, channel and date unconfirmed); (c) Kieran Klaassen, "The Folder Is the Agent", Every, 2026-04-13 — "Just by changing the folder and not the model, I have a different agent", 44 folder-agents with file-based dispatch; (d) The CodeFlow Team, "we replaced our multi-agent middleware with a folder", dev.to 2026-04-19 — FCoP, four roles coordinating through `TASK-{date}-{seq}-{sender}-to-{recipient}.md` filenames. If Steve's memory is of (a) or (b), the talk is ICM's own author, and the "team of agents" replaced is the multi-agent framework of the abstract.

---

## 2. The mechanism each uses

| | ICM | OKF spec | OKF as run here | eve |
|---|---|---|---|---|
| A **file** is | a stage contract (`CONTEXT.md`), reference material, or an output artifact | one concept: YAML front matter + body | same, header extended | one capability: `tools/x.ts` = tool `x`, `skills/x.md` = skill `x` |
| A **folder** is | a stage (`01-`, `02-`…) with `references/`, `output/` | a bundle with its own `index.md` | `knowledge/`, `knowledge/sources/` | a capability *kind* (`tools/`, `skills/`, `channels/`, `schedules/`, `subagents/`) |
| **Naming** carries | order (zero-padded prefix), artifact type | reserved `index.md`, `log.md` | same, plus `id == stem` | the public name, derived from path |
| **Enforced by code** | nothing — "no code enforcer; relies on human adherence" (repo README, fetched) | nothing — "no required tooling" | `canon.py` closed vocabularies, `id == stem`, cites and `supersedes` resolve; lane drift refusal; verbatim checker | discovery, naming, typed tool schemas, step checkpoints, `load_skill` |
| **Relies on the model** | reading layers 0→1→2 in order, honouring the Inputs table's section scoping, running audits | reading `index.md` first | which cite to hang a label on; admitting UNSOURCED | calling `load_skill`; following `instructions.md` |
| **Load-bearing** | the numbered folder and the Inputs/Process/Outputs table | `type`, reserved names | `id`, `type`, `status`, `cite` | path→name and the step checkpoint |
| **Decorative** | CLAUDE.md "where am I", checkpoint tables | `tags`, `resource` | `owner`, `lineage.commit` (validated, consumed by nothing measured) | `research/` notes |

Measured supports for the local column: `strader/entities/canon.py` (VALID_TYPES, FILE_STATUSES, `_ID_RE`, `resolve()`, `_check_supersedes`) with 19 tests in `tests/strader/entities/test_canon.py`; `footprint-icm/bin/excerpts.py:130` "canon moved, re-pin"; `footprint-icm/bin/checker.py:90` `check_cite` over `common.normalize`; `footprint-icm/bin/run_stage.sh:32,71-72` — parent scan for `CLAUDE.md AGENTS.md .claude`, then `claude -p --setting-sources "" --tools "" --strict-mcp-config`; 67 tests under `tests/footprint_icm/`. Trial: 12/12 model calls passed the checker, planted test caught both days (`docs/reviews/2026-08-29-footprint-icm-trial.md:26`).

Two things the table shows. First, **"name derived from path"** is a rule in eve (`AGENTS.md`), in the lane, and in the local header (`id == stem`) — but not in the published OKF spec, where only `type` is required. The address scheme is ours, not Google's. Second, two measured divergences between the local bundle and v0.2: `knowledge/index.md:1-3` and `log.md:1-3` carry `type: convention` front matter, where v0.2 §8 allows a root `index.md` only `okf_version` (v0.1's rule unknown — not fetched); and v0.2 renamed `timestamp` → `generated.at` and made `sources` the citation key, while the local header keeps `timestamp` and uses `sources:` for *register ids* (`canon.py`, "sources: [OFB-31]"). Same key, different meaning — know it before pointing a v0.2 tool at this bundle.

---

## 3. Shared extension points

Test applied: present as a *mechanism* in at least two of the three, and at least partly built here.

**E1. Typed front-matter header as the address.** OKF: `type` required, one concept per file. eve: skill front matter carries `description`, name is the path. Here: `id == stem`, `type`, `status`, `cite` validated by `canon.py`. ICM: none at file level. Survives on OKF + eve + local; the primitive is "the stem is the id, the front matter is the type".

**E2. A generated `context/` folder as a projection of the bundle.** The COO plan's claim (`2026-08-29-playbook-refactor-and-blotter-plan.md:46`: "one excerpt file per entity file, the same id in both, generated rather than copied"). ICM's Layer 3 `references/` is the slot; eve's `skills/` is the same slot at runtime level (a skill "adds instructions, never a new execution surface" — skills doc, fetched). Status: designed, not built — `manifest_gen.py` does not exist (measured; mentioned only in the two a2a memos and `canon.py`'s docstring) and `manifest.yaml` is still the hand list (measured, its header comment). Survives; it is what makes E1 useful.

**E3. `file-id + lines @ commit` as the universal cite.** Present in the lane (`excerpts.py` cuts from `git show <commit>:<path>`) and in the header (`cite:` resolved to whole-file lines so "they match `git show` and the manifest" — `canon.py`, `cites()`). ICM has no citation convention (paper: bibliography only; repo: none — both fetched). eve: none. OKF v0.2: a `sources` key, no line-range form. Survives as *our* convention the other two can adopt unchanged, because all three agree the thing cited is a file in git.

**E4. The checker that fails a run on a non-verbatim quote.** Only here (`checker.py:90`; 9 model-free tests). Absent from all three. Survives because it is the missing piece in all three and is small: anything that emits `LABEL/CLAIM` lines from a folder of excerpts — an eve skill's output as much as a `claude -p` stage — can be checked by it.

**E5. Numbered stage folders as a pipeline contract.** ICM: load-bearing. eve: absent (sequencing is the workflow engine). OKF: absent. Here: `20-classify/`, `40-compare/` exist but `run_day.sh` fixes the order in code, and the plan dropped ICM's folder-map and routing files (`…audit-lane-plan.md:245`, "this runner has no session to steer"). **Does not survive**; the numbers are documentation.

**E6. Append-only log as provenance.** OKF `log.md`; here since 2026-07-19; ICM's run archive; eve's append-only conversation history. Survives as a shared *practice*, not an interface: three logs with three subjects, none read by another.

**E7. "Written by code, never by a model."** Here it is the runner's property (`--tools ""` from a folder outside every repo). ICM cannot enforce it (no runner). eve inverts it: tools are the model's write surface, gated by approval. Survives only as the local runner's property.

**E8 (added). Path-derived names.** eve: "derive names from file paths". Local: `id == stem`; `.claude/skills/<name>/SKILL.md` with `name:` equal to the folder (measured: `mancini-parse/SKILL.md:2`). ICM: stage folder name is the stage. Survives; it is why one id can serve E1, E2 and E3.

**E9 (added). Progressive disclosure by description.** OKF `index.md`; eve `load_skill` exposes "each one's description to the model" and appends the body on demand, a flat `.md` skill's description defaulting to "the first non-empty … line of the body"; Claude Code skills identical; ICM's Inputs table names *sections* — the same move one level finer. Survives; the one place all agree on mechanism, not just intent.

Shared, one line each: **E1** stem is id, front matter is type · **E2** `context/` generated from the bundle, never copied · **E3** a cite is `id + lines @ commit` · **E4** the verbatim checker is the model-free gate · **E8** names from paths · **E9** description routes, body loads on demand.

---

## 4. What does not converge

**ICM's three holes are still holes.** The plan's finding (`…audit-lane-plan.md:105`, "ICM itself supplies no runner, no source list and no citation convention") matches the repo README (fetched: "no orchestration code, scheduler, or runner"). eve: *runner* yes — a durable workflow per session, checkpointed per step — but it runs a chat agent with tools, and no fetched eve doc has "stage N reads stage N-1's output file"; *source list* no — nothing marks which files may be cited or refuses one by status; *citation convention* no. eve fills one of three, and that one we replaced with ~70 lines of bash and a parent scan.

**OKF is a format; the enterprise treats it as an architecture.** The spec has no agent, runner, admissibility, `status` or `id`. Everything the lane depends on is the local extension — permitted (consumers "MUST NOT reject documents with unrecognized fields", fetched) — but "the substrate is already there, and it is OKF" (`…refactor-and-blotter-plan.md:46`) is true of the container only. The substrate that does work is `canon.py`.

**They disagree on what a folder is.** ICM: a moment in time. eve: a kind of thing. OKF: a topic. The estate has all three at once — `footprint-icm/20-classify/` (time), `.claude/skills/` (kind), `knowledge/` (topic) — and they are not interchangeable. Any proposal that flattens them into one tree is wrong.

**eve's durability is not the filesystem.** Authoring is files; execution state is the Workflow SDK's log (`.eve/.workflow-data`; Vercel Workflow in production — measured). ICM's §3.2 claims the opposite ("State management is the files on disk") and is honest that it does not scale.

**Two local claims not yet true.** `canon.py --report`, run this session: "2 entity file(s) validate; 43 do not; 2 reserved". The projection (E2) cannot be generated until st-ts3o lands. And `manifest.yaml` is hand-kept. Stage 0 of the refactor is one-third done: loader landed 2026-08-30 (`inbox.md:295,298`); st-ts3o and st-apxk open (`bd list`).

---

## 5. Integration proposal, smallest first

**Already the same thing under another name — leave alone.** `.claude/skills/<name>/SKILL.md` with `name`/`description` and on-demand load *is* eve's packaged skill. `knowledge/index.md` *is* OKF progressive disclosure and ICM Layer 1 for the bundle; regenerate it from headers once E1 lands (already planned). `docs/a2a/inbox.md` and the bridge inbox (timestamped `__From__topic.md` with `from/to/expects_reply` front matter, measured on the directive file) *are* FCoP's filename-as-protocol.

**Step 1 — finish the header (st-ts3o, open, Strader).** Touches 33 `knowledge/` headers and 9 `strader/playbooks/` records; `test_the_real_bundle_validates` goes green. Cost about a day: the counter (`…refactor-counter.md` §1) already assigns every type and status. This is E1. One ask for Steve, recommended Yes: rename the local `sources:` key (register ids) now, while two files carry it, so it never collides with v0.2's citation `sources`.

**Step 2 — generate the manifest (st-apxk, open, COO).** New `footprint-icm/bin/manifest_gen.py` from `Canon.lane_sources()` and `Entity.cites()`; `run_day.sh` step 4; delete `refused_files`. Acceptance already written (eight rows' `quote` strings reproduce; planted test passes). Half a day. This is E2 and E3 made real.

**Step 3 — make the checker a library.** Move `checker.py` and `common.normalize` to `strader/entities/cite_check.py`, re-export from the lane, no behaviour change; the 9 tests move. An hour. This is E4 offered to any future producer of LABEL/CLAIM lines — the curation worker the plan sketches (§4, "in the audit lane's mould") and the letter rows (st-jep1).

**Step 4 — write the convention down as an entity.** One `type: convention` file in `knowledge/`: stem is id; a cite is `id + lines @ commit`; a context folder is generated, never copied; a quote is checked by code. One file, one `log.md` line, one index row. Minutes. It puts E1/E3/E8 where agents read.

**Step 5 — eve, only on a real trigger.** Adopt it if and only if an agent must run *outside* Claude Code: scheduled, channel-driven, multi-turn, with approval on tool calls. Then steps 1-4 make it mechanical — `knowledge/` a read-only mount the skill cites, `.claude/skills/*` copied unchanged, `run_stage.sh` becomes a schedule (`schedules/` take "Markdown prompts with `cron` frontmatter", measured). What would be lost: `--tools ""` isolation as a one-flag property (eve's model always has `load_skill`) and `claude -p` on the Pro plan at no marginal charge (trial review, line 8). Cost today zero — every scheduled job is a timer in `COO/SCHEDULE.md` and none needs a chat runtime. Not now.

**Do not adopt**: ICM's workspace `CONTEXT.md` routing and Layer 0/1 files (dropped for a reason that has not changed); numbered folders as a contract (E5); any move to v0.2 field names before a v0.2 consumer exists.

---

## Could not verify

- The talk with "we've replaced a team of agents with a folder": no fetched source has the sentence; the closest YouTube page (MkN-ss2Nl10) would not render, so its channel and date are unconfirmed; the Clief Notes page gives Van Clief's 2026-03-10 title and description but no link.
- OKF v0.1 text: not on GitHub; whether it permitted front matter on `index.md` is unknown.
- The Google "reference parser" that `graduate-memory.py:32` cites: the knowledge-catalog README (fetched) names none, and the spec says no required tooling.
- The New Stack article: fetch returned the page shell only; its headline is from the search result.
- eve's production state store behind Vercel Workflow: not described in the fetched doc.
- ICM vs MWP: arXiv titles the paper "Interpretable Context Methodology", the abstract and the repo's `_core/CONVENTIONS.md` say "Model Workspace Protocol"; both sources treat them as one method, and I found no statement of which name is canonical.
