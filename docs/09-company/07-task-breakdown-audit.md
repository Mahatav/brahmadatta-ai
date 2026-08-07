# Task Breakdown Audit

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Document | Company-workflow phase 4 deliverable — audit of the existing board |
| Author | `engineering-manager` seat |
| Date | 2026-08-07 |
| Audits | The 63-issue board built by the orchestrator during phase 1 |
| Status | **PARTIAL — board-level verification not executed. See §0.** |

---

## 0. Execution status — read this first

This audit was produced in a session with **no shell access**. The available tools were
file read/write/search only: no `gh`, no `git`, no network.

**Therefore, and stated plainly:**

- **No GitHub issue was created, edited, relabelled or reassigned.**
- **No branch, commit or pull request was made.**
- Sections 1–3 of the required audit that depend on reading the 63 issue bodies —
  per-issue coverage mapping, `Depends on #N` cycle detection, per-issue `parallel-safe`
  verification — **could not be executed** and are not presented as if they had been.

What *is* complete and does not depend on the board:

| § | Content | Status |
|---|---|---|
| 1 | Coverage criteria: nine demo steps × P0 items, and the four structural gaps visible in the plan itself | complete |
| 2 | Milestone-level parallelism audit, D1–D7, with the at-risk days named | complete |
| 3 | The shared-file collision map that makes `parallel-safe` checkable | complete |
| 4 | Long-running work inventory and which direction each handoff should point | complete |
| 5 | Sizing: which milestone deliverables are more than one shift, and how to split them | complete |
| 6 | Honest read on D1–D7 and the ordered cut list | complete |
| 7 | The worklist of issue edits to apply, ready to run | complete, **unapplied** |

§7 is written so a re-run with shell access can apply it mechanically.

**Evidence base for this audit:** `docs/09-company/01-vision-and-p0-cut.md` §2–§4,
`02-two-person-24h-cycle.md`, `03-seven-day-plan.md`, `.project/state.md`,
`.project/decisions.md` D-006…D-018, `docs/04-development/35-project-folder-structure.md`,
and the working tree at `main`.

**Working-tree observation, 2026-08-07.** Tracked, on `main`: `apps/control-api/` with
`config/`, `contracts/` (13 modules including `state_machine.py`, `authorization.py`,
`model_policy.py`, `verdict.py`, `schemas/evidence.py`) and `api/routers/missions.py`; and
`packages/ui-components/tokens.css`. **Absent from `main`:** any Astro application, any
`infrastructure/` content, any `demo/` content. Local branches `feat/control-api-scaffold`,
`feat/demo-target`, `feat/infra-nginx-compose` exist unmerged. D1 (ends Aug 7) requires all
four of Astro-through-nginx, a building demo C target, a frozen contract, and visual
references. On today's tree, one of those four — the contract — is landed on `main`.

---

## 1. Coverage

### 1.1 The nine steps against the P0 table

Every step of `01-vision-and-p0-cut.md` §3 and every row of §2's P0 table, mapped to the
milestone that must carry it and the artifact that must exist. The "issue" column is left
unfilled deliberately — filling it requires the board, and a guessed issue number is worse
than a blank.

| Step | P0 items | Milestone that must carry it | Artifact that must exist |
|---|---|---|---|
| 1 Target | — | D1 | `demo/repositories/<target>/` — CMake + CTest C library, seeded heap-buffer-overflow, green baseline |
| 2 Authorize + snapshot + sandbox | P0-1, P0-2 | D2 | `contracts/authorization.py` (landed) + ORM record + `POST /missions` authorize path + rootless container runner with egress denied |
| 3 Baseline | P0-4, P0-5 | D3 ⚑ | C/C++ adapter (configure/build/ctest), baseline worker, pass/fail counts persisted and rendered |
| 4 Finding | P0-6, P0-7, P0-8 | D4 → D5 ⚑ | ASan/UBSan build profile, libFuzzer harness, crash capture, minimizer, 5/5 replay from clean |
| 5 Patch | P0-9, P0-10 | D6 ⚑ | `contracts/model_policy.py` (landed) + policy enforcer + local CPU model gateway |
| 6 Verdict A — Verified | P0-11 | D6 ⚑ | Fresh-worktree verifier, gate matrix record, `Verified` |
| 7 Verdict B — Rejected | P0-11 + D-008 | D6 ⚑ | The crash-only bad-patch **fixture**, provenance field, `Rejected` |
| 8 Evidence | P0-12 | D4 (schema) → D7 (export) | `contracts/schemas/evidence.py` (landed) + evidence models + Markdown/JSON exporter |
| 9 Teardown | P0-14 | **unplaced — see 1.2(a)** | Sandbox reaper + teardown-confirmed state surfaced in the UI |
| — | P0-3 event stream | D2 | State machine (landed as contract) + SSE endpoint + persisted event log |
| — | P0-13 screen set | D2 (spec) → D3/D5/D6 (build) | Mission core, stage timeline, findings list, diff view, verdict panel |
| — | P0-15 fallback | D7 — **wrong day, see 1.2(b)** | A playable recording of the full run |

### 1.2 The four structural gaps

These are gaps in the **plan**, visible without reading a single issue. Each one needs an
issue that the milestone table does not currently imply exists.

**(a) P0-14 teardown has no home.** `03-seven-day-plan.md`'s milestone table names it in no
day. It is step 9 of the demo, a hard constraint under §2, and a scored criterion. It is
also not a D7 task: the reaper that guarantees no orphaned sandbox survives a crashed
mission has to be written *with* the sandbox on D2, or it is written under gate pressure on
the last day. **Needs a D2 issue** ("sandbox teardown and orphan reaper") and a D7 issue
("teardown confirmed in the UI and in the evidence bundle").

**(b) The fallback recording is scheduled on the single most compressed day, which is the
exact failure D-011 exists to prevent.** D-011's reasoning is that week 8 "puts the insurance
policy in the same week as rehearsals, submission, and code freeze — the week most likely to
be compressed, meaning the fallback is precisely what gets dropped." The seven-day plan then
puts it on D7, alongside the unattended-run gate and the report exporter. It also cannot
start until the demo works, so it is strictly serial behind the D7 gate it is insurance
against. **Needs resequencing to rolling capture from D5** — record whatever works at the end
of each day from D5 onward, so a partial fallback always exists and D7's version is a
re-record, not a first take.

**(c) The rejected-patch fixture is a demo-target asset scheduled as a D6 gate task.** Step 7
needs a hand-authored crash-only patch (clamp the parse length to zero) that eliminates the
reproducer and fails regression. That is content authored against the target, and it belongs
with the D1 target work where it can be validated early — not on the critical path of a gate
day. **Needs a D1 issue**, owned with the target.

**(d) D-008's provenance requirement has no acceptance criterion anywhere.** "Any code path
that records an operator-supplied candidate as model-generated is a bug" is a product rule
with no test behind it. **Needs to be an acceptance check on the patch-candidate model
issue**, not a review comment: a `provenance` field, non-nullable, and a UI/report assertion
that the string "operator-supplied candidate" is rendered for that case.

**One stale blocker.** `.project/state.md` lists #8 (visual references) as a hard CEO blocker
on all UI work, and phase 3 as blocked on it. D-017 (2026-08-06) and D-018 (2026-08-07) both
supply the references in detail — two named references, confirmed typefaces, a construction
system, and the non-figural constraint. **#8 is answered and should be closed**, with the two
decision records cited. Leaving it open means UI work is nominally blocked by a question that
has been answered twice.

---

## 2. The parallelism audit

This is the part that matters most, so the reasoning is shown.

### 2.1 Which direction the clock actually runs

From `02-two-person-24h-cycle.md`: within any calendar day **Raunak works first and Mahatav
works second.** India's 09:00–18:00 IST falls in Kelowna's night, finishing ~3.5 hours before
Kelowna's 09:00 PDT. This has two consequences that should drive every sequencing call:

- **Raunak → Mahatav handoff latency is ~3.5 hours.** Pipeline output produced by Raunak is
  consumable by Mahatav the same working day. This is the good direction and the pipeline→UI
  dependency runs along it naturally.
- **Mahatav → Raunak handoff latency is ~0 hours.** Mahatav's shift ends at 18:00 PDT, and
  Raunak's begins at 09:00 IST — 21:30 PDT. Effectively immediate.
- **The expensive direction is Mahatav needing something from Raunak that Raunak has not
  started.** That is a full 24-hour round trip, not 12.

**Corollary for long-running jobs:** they should be started at the **end of Mahatav's shift**
by default, because Raunak picks them up almost immediately. Started at the end of Raunak's
shift they idle for 3.5 hours before anyone reads them.

### 2.2 Day by day

| Day | Raunak has unblocked work | Mahatav has unblocked work | Verdict |
|---|---|---|---|
| **D1** | Demo C target, build/test green, toolchain | Astro shell, Django scaffold, contract freeze | **OK** |
| **D2** | Rootless sandbox, egress deny, orchestrator against the frozen state machine | Django models + migrations, authorize endpoint, P0 screen-set spec | **OK, with a migration-collision hazard — see §3** |
| **D3** ⚑ | Adapter + baseline worker → ctest counts | *Wiring only, if §2.3 is done. Nothing, if it isn't.* | **AT RISK for Mahatav** |
| **D4** | ASan/UBSan profiles, libFuzzer harness | Evidence models, analysis rail, exporter skeleton | **OK — the healthiest day** |
| **D5** ⚑ | Crash capture, minimizer, 5/5 replay | *Almost nothing on the gate path* | **AT RISK for Mahatav — the worst day on the board** |
| **D6** ⚑ | Model gateway, patch policy enforcement, verifier | Verdict panel, gate matrix rendering, provenance, dual-verdict report | **OK** |
| **D7** ⚑ | Unattended-run hardening | Report export, fallback, competition materials | **AT RISK — serialized behind the gate** |

### 2.3 D3 — the fix

The D3 gate is "cold start → `BASELINE_PASSED` with real ctest counts, on screen". The counts
originate in Raunak's baseline worker. If Mahatav's stage-timeline and mission-core panels are
also *built* on D3, he spends the first half of his shift waiting for an event payload that
does not exist yet.

**Fix: a recorded event fixture, produced on D2, is the contract Mahatav builds against.**
Concretely — a committed JSON-lines file of the exact SSE envelope sequence for a successful
baseline run (`contracts/schemas/envelope.py` already defines the shape), plus a management
command that replays it into the SSE endpoint. Mahatav builds and styles both panels on D2
against the replay; D3 becomes swapping the replay source for the live orchestrator. This
also gives QA a deterministic UI test input, and it costs Raunak about an hour on D2 because
the envelope schema is already frozen.

This is the single highest-leverage change in this audit.

### 2.4 D5 — the fix

D5's gate is entirely Raunak's: sanitizer-confirmed crash, minimized input, 5/5 replay from
clean. Mahatav has no gate-path work at all. Left alone he loses a full day of a seven-day
build, which is 14% of the schedule.

**Fix: D5 is Mahatav's evidence-and-insurance day, and it should be stated as such.** Load it
deliberately with:

1. The Markdown/JSON evidence exporter (P0-12) — currently implied at D7, pulled forward.
2. Rolling fallback capture (gap 1.2(b)) — the capture rig plus the first partial recording.
3. The findings list and diff view panels, against the same fixture mechanism as §2.3.
4. The five-slide submission draft (D-012's principle: draft early, revise, never author
   under deadline).

None of these depend on D5's crash landing. All of them are on the critical path for D7.

### 2.5 D7 — the fix

D7 stacks three serial things on one day: the unattended run must pass before the fallback
can be recorded, and the report exporter is needed by both. §2.4 moves the exporter to D5 and
the fallback to rolling capture from D5, which converts D7 from three-serial to
one-serial-plus-a-re-record. Do that and D7 stops being a coin flip.

### 2.6 Summary — the days at risk

**D3 and D5 leave Mahatav waiting on Raunak; D7 serializes both of them behind one gate.**
D3 is fixed by an event fixture built on D2. D5 is fixed by loading it with the evidence and
insurance work. D7 is fixed by both of the above. No day leaves Raunak waiting on Mahatav —
the ownership split and the clock direction happen to favour him, and nothing here needs to
change on his side.

---

## 3. Making `parallel-safe` checkable

`02-two-person-24h-cycle.md` rule 2 is unambiguous: "`parallel-safe` means it — no shared
files." The label was applied at board-creation time, before any of these files existed, so
it cannot have been verified against them. It is currently a claim, not a fact.

**The rule that makes it checkable.** Any two issues that both touch a file in this list are
**not** parallel-safe, whatever the label says:

| Collision surface | Why it collides | Who touches it |
|---|---|---|
| `apps/control-api/contracts/**` | The frozen seam. Every schema change lands here. | both |
| `apps/control-api/config/settings/base.py` | Every new app, setting, or worker config appends here. Already carries orchestrator config, admin blocking, DB. | both |
| `apps/control-api/api/routers/__init__.py` | Every new endpoint registers on the same ninja instance. | Mahatav, mostly |
| `apps/control-api/**/migrations/` | **The worst one.** Two model authors on the same day produce a forked migration graph that neither discovers for 12 hours. | both |
| `infrastructure/compose/*`, nginx conf | Sandbox networking and ingress both edit it. | both |
| `packages/ui-components/tokens.css` | Every UI issue touches it until tokens stabilize. | Mahatav |
| `demo/repositories/<target>/**` | The fuzz harness and the bad-patch fixture both live in the target. | both |

**Two standing rules that follow, and are cheaper than re-labelling:**

1. **One migration author per day.** Whoever is adding models that day says so in the daily
   handoff; the other person does not run `makemigrations`. A forked migration graph is a
   guaranteed lost morning at this compression.
2. **The contract seam is frozen after D1 and changed only by agreement**, which
   `02-two-person-24h-cycle.md` already says. Add the mechanical half: a contract change is
   its own issue, never a side effect of a feature issue, and it is never `parallel-safe`.

---

## 4. Long-running work — what the second timezone is for

Wall-clock-bound rather than attention-bound. Per §2.1, the default is **start at the end of
Mahatav's shift, label `handoff:to-raunak`**, because that handoff has near-zero latency.

| # | Job | Day started | Direction | Where output lands |
|---|---|---|---|---|
| L1 | **Model artifact download + local CPU serving warm-up** | **D4 at the latest** | `handoff:to-raunak` | Local model cache path, recorded in the issue |
| L2 | Fuzz campaign on the parser harness | D4 end of shift | `handoff:to-raunak` | Corpus + crash dir, path in the issue |
| L3 | The 10-attempt patch generation run (the D6 supporting threshold: ≥3/10 policy-passing, compiling) | D5 end of shift | `handoff:to-raunak` | JSON run log with all 10 candidates and their policy outcomes |
| L4 | Full regression sweep + 5/5 reproducer replay from clean builds | D5, D7 | `handoff:to-raunak` | ctest output archived to the evidence dir |
| L5 | Unattended end-to-end run, twice consecutively | D7 overnight | `handoff:to-raunak` | Run transcript + exported bundle |
| L6 | Sandbox base image + C toolchain image build | D2 | `handoff:to-raunak` | Local image tags, recorded |

**L1 is the one that most reliably kills a schedule and is missing from every plan document
in this repo.** If the model weights are first fetched on D6, D6's gate is lost to a download
and there is no recovering it. D-015 cut the rented GPU, so the model runs on local CPU —
which means a multi-gigabyte fetch, a quantization step, and a first-token latency measurement
that nobody has done. It must happen on D4.

Every one of L1–L6 needs, in its issue body: *what to start at end of shift*, *where the
output lands*, and *what the next person checks first*.

---

## 5. Sizing — what is more than one shift

Judged against the milestone table, since the issue bodies were unreadable. Each of these is
one line in `03-seven-day-plan.md` and more than one shift of work.

| Milestone line | Why it is oversized | Split into |
|---|---|---|
| D2 "rootless sandbox with egress denied" | Rootless runtime + worktree mount + network policy + resource caps + teardown + a test that *proves* egress is denied | (a) rootless runner with mounted worktree; (b) egress-denied network policy **with a test that attempts egress and asserts failure**; (c) teardown + orphan reaper |
| D3 "cold start → BASELINE_PASSED" | Not an issue — an integration of five. Hides its own slippage completely. | (a) adapter configure/build; (b) ctest invocation + count parsing; (c) baseline worker persisting counts; (d) **a named cold-start rehearsal issue**, checked by whoever's shift ends the day, per cycle rule 4 |
| D4 "evidence database" | Models + migrations + writers for baseline/finding/patch/verdict + exporter | (a) evidence models + migration; (b) writers per record type; (c) exporter (moved to D5 per §2.4) |
| D6 "one Verified and one Rejected from a single operator action" | Three distinct pieces plus a gate | (a) fresh-worktree verifier + gate matrix record; (b) model gateway + patch policy enforcement; (c) bad-patch fixture + provenance (fixture itself moves to D1 per 1.2(c)) |
| D7 "demo unattended; report exports; fallback recorded" | Three issues and two of them serial | (a) unattended-run hardening; (b) report export (moved to D5); (c) fallback re-record (rolling from D5) |

---

## 6. The honest read on D1–D7

**No — not as specified.** Three reasons, in order of weight.

**1. D1 is not landed and D1 ends today.** On `main` there is a Django contracts package.
There is no Astro application, no `infrastructure/`, no `demo/`. Three feature branches exist
unmerged. D1's four deliverables are Astro-through-nginx, a building demo target, a frozen
contract, and visual references; one is on `main`, two are on branches, one (references) is
answered in D-017/D-018 but its issue is still open. A one-day slip on D1 is a one-day slip on
a gate at D3.

**2. D3 asks for a full-system integration on day three.** `BASELINE_PASSED` from a cold start
with real ctest counts on screen requires nginx, Astro, Django, the ORM, the orchestrator, the
sandbox and the C toolchain adapter all working *together*. That is the hardest kind of
milestone — every component's first integration, simultaneously, under a gate, with a 12-hour
question latency between the two people who own the halves.

**3. The plan already says so.** `03-seven-day-plan.md`: "aggressive to the point of being
unlikely as specified, and the plan should be run knowing that rather than discovering it on
day five." D-014 records the same caveat. This audit agrees with both and adds that the D5
idle-day and the D7 serialization are two further reasons that were not previously named.

### The cut order

Applied top-down, each cut taken only when the day it protects is actually at risk. Issue
numbers are deliberately absent — see §0 — so these are named by capability, and §7 says how
to resolve them to numbers.

| # | Cut | What it buys | What it costs |
|---|---|---|---|
| **1** | **Fuzzer reach → direct harness on the vulnerable function.** Adopt the plan's own D5 fallback as the *starting* position, today, not as a contingency. | Most of D5's risk. The harness confirms and minimizes rather than discovers. | The claim shrinks from "our fuzzer found it" to "our harness confirms and minimizes it" — a smaller claim that is true. This is `03-seven-day-plan.md`'s own recommendation. |
| **2** | **Astro, if the shell is not up by end of D1.** Serve the Command Center from Django templates plus the same client islands behind the same nginx. | Removes a whole build toolchain from the D3 gate's critical path. | Loses Astro's islands ergonomics. Note that D-017/D-018's visual language is flat colour, hairline rules and monospace type — it does not need a framework. D-013 is a CEO decision, so **this cut is CEO's to approve, not mine.** |
| **3** | **Rootless, not isolation.** Keep egress denial, resource caps and teardown; if rootless podman fights the host, run a standard container with `--network none` and a non-root user, and record the deviation on the issue. | A potentially open-ended infrastructure fight on D2. | Weakens hardening, not the safety boundary. **`cybersecurity` holds a veto here** — flagged, not decided. |
| **4** | **Second verdict slips D6 → D7.** `Verified` on D6, `Rejected` on D7. | D6 gate becomes achievable. The Rejected path reuses the identical pipeline, so it is cheap once Verified works. | The dual-verdict shot — the actual differentiator — lands a day later. Do not cut it, only move it. |
| **5** | **P0-13 five panels → three.** Mission core, stage timeline, verdict panel. | Roughly a shift of Mahatav's D5/D6. | Findings list and diff view come out of the exported report instead of the UI. |
| **6** | **The live demo itself.** If D7's unattended run fails, the recording is the entry. | Everything. | Which is exactly why rolling fallback capture starts D5 and not D7 (§1.2(b)). |

**Not cuttable, in any order:** the authorization gate, egress denial, teardown, gate-matrix
disclosure (D-009), and provenance labelling (D-008). Per D-006 every safety-boundary item
sits in P0 and is structurally uncuttable, and D-008/D-009 are integrity controls — a demo
that overstates what it did is worse than a demo that does less.

---

## 7. The unapplied worklist

Ready to run against the board. Each item states the check to make first, because none of
these were verified against issue bodies.

**A. Reconcile issue numbers.** `gh issue list --repo Mahatav/brahmadatta-ai --limit 100
--state open --json number,title,labels,milestone,body`. Everything below keys off that.

**B. Close as answered.** #8 (visual references) — answered by D-017 and D-018. Close with
both decision records cited.

**C. File the missing issues** (§1.2), in house format with acceptance checks:

1. *D2* — Sandbox teardown and orphan reaper. `owner:raunak`. Acceptance: a mission killed
   mid-stage leaves zero containers and zero volumes; asserted by a test.
2. *D7* — Teardown confirmed in the UI and in the evidence bundle. `owner:mahatav`.
   Acceptance: the exported bundle contains a teardown record; the UI shows it.
3. *D1* — Crash-only bad-patch fixture for demo step 7. `owner:raunak` (lives with the
   target). Acceptance: eliminates the reproducer, fails at least one regression test.
4. *D2* — **Recorded SSE event fixture + replay command** (§2.3). `owner:raunak`,
   `handoff:to-mahatav`. Acceptance: replay drives the stage timeline through a full
   successful baseline without the orchestrator running. **File this one first — it is what
   unblocks D3.**
5. *D5* — Rolling fallback capture rig + first partial recording. `owner:mahatav`.
   Acceptance: a playable file exists at end of D5, however partial.
6. *D4* — **Model artifact fetch and local CPU serving warm-up** (L1). `owner:raunak`,
   `handoff:to-raunak`. Acceptance: a first-token latency measurement recorded on the issue.

**D. Move.** Evidence exporter D7 → D5. Fallback recording D7 → rolling from D5. Bad-patch
fixture D6 → D1.

**E. Split.** The five oversized items in §5, into the sixteen issues named there.

**F. Verify `parallel-safe`.** For every issue carrying it, diff its named files against §3's
collision table. Remove the label on any issue touching `contracts/**`,
`config/settings/base.py`, `api/routers/__init__.py`, or a `migrations/` directory
concurrently with another labelled issue.

**G. Verify dependencies.** With the JSON dump, parse every `Depends on #N`, build the graph,
and check three things: no cycle; no edge from an earlier milestone to a later one; and every
issue whose acceptance check names an artifact owned by the other person has an explicit
dependency on the issue that produces it. The last is where missing edges hide.

**H. Label the long-running six** (L1–L6) with `handoff:to-raunak` and add the three required
body lines: what to start at end of shift, where output lands, what the next person checks.

---

*This document audits the board; it does not reprioritize it. Where it disagrees with the
seven-day plan — the fallback's scheduling, D5's loading, the two structural gaps — those are
raised as findings for the CEO and PM to rule on, not as changes made.*
