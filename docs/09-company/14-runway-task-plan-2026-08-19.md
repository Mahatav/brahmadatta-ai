# Backend/Infra Runway Task Plan — 2026-08-19

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Document | Company-workflow phase-5 deliverable — backend/infra task breakdown for the remaining runway |
| Author | `engineering-manager` seat |
| Date | 2026-08-19 |
| Scope | Backend/orchestration/infra critical path only. Command Center (`apps/command-center/`) and the reopened CUT UI items (`#25`/`#56`/`#52`/`#31`) are scoped separately by a ui-ux-designer/product-manager pass per D-086 — not duplicated here, only referenced where a dependency exists. |
| Builds on | `.project/state.md` (Reconciliation, 2026-08-19), `.project/decisions.md` D-085/D-086/D-087, GitHub issue `#207` |
| Status | Planning only. Nothing in this document has been implemented, and no agent should start execution from it without the sign-offs named in §0 and §1. |

---

## 0. Execution status — read this first

Produced in a session with **no `gh` / `Bash` / shell tool** — file read/write/search only,
same constraint `07-task-breakdown-audit.md` recorded on 2026-08-07. Consequences, stated
plainly:

- `#207`'s scoping (§1) is grounded in a direct reading of the actual code
  (`authorization/service.py`, `authorization/store.py`, `missions/models.py`,
  `contracts/state_machine.py`) — high confidence, not a guess.
- The 16-finding triage (§3) is grounded in `.project/state.md`, `.project/decisions.md`
  (D-060 through D-086), `.claude/COMPANY.md`'s hire-log, and two regression test files whose
  docstrings name their issue numbers directly. **Eleven of sixteen findings are identified
  with high confidence** (`#163`–`#165`, `#176`, `#177`, `#180`, `#181`, `#184`, `#198`,
  `#203`, plus reasoned structural candidates for three more). **Five could not be
  independently confirmed** (`#182`, `#191`, `#193`, `#194`, `#199`) — no `gh issue view` was
  available to read their bodies. These are triaged provisionally, flagged explicitly, and
  should be re-confirmed by whichever agent next has `gh` access before being treated as
  final. This is the same "a property is described as enforced only when a named test
  demonstrates it" discipline `.claude/COMPANY.md` §5 already holds this project to, applied
  to "an issue is characterized only when its actual body was read."
- No issue was edited, no PR opened, no branch touched, nothing implemented. This is a
  planning/staffing pass only, per this task's own explicit instruction.

---

## 1. `#207` scope and sizing

Full reasoning and the two options weighed: **`.project/decisions.md` D-087.** Summary:

**Recommended fix — mission-scoped claiming, not a release-path mechanism.** Drop the
cross-mission refusal in `authorization/service.py::create_mission_snapshot`. A digest already
indexed by another mission's `Artifact` row is a legitimate content-dedup hit (the disk-level
store, `authorization/store.py::ingest_from_path`, is already idempotent by content-hash and
was never the thing enforcing exclusivity) — this mission gets its own fresh `Snapshot` row
against the existing `Artifact`, the same way a same-mission replay already works three lines
above the current refusal. No schema migration. Keep a narrower, fail-closed check: refuse if
the existing artifact's `kind`/`size_bytes` disagree with what this mission's own hashing just
produced (a genuine hash-workflow contradiction, not the routine cross-mission case).

**Why not the release-path option.** It cannot satisfy the literal kill criterion
("reproduced twice consecutively") without releasing claims from the *success*-shaped terminal
states (`VERIFIED`/`REJECTED`) too, not just the failure-shaped ones — and doing that weakens
the tamper-evidence property (D-025) a finalized evidence bundle's referenced artifact is
supposed to have. It also needs either a new schema (release timestamp / claim-history table)
or a new hook in `orchestrator/transitions.py` — the more sensitive module in this codebase —
for a bigger, riskier change than the alternative.

**Sizing.** Small. ~0.5 day backend-developer implementation + updated tests
(`api/tests/test_authorize_snapshot.py`) + one cybersecurity review round (~2–4h), since this
touches auth/verification-gate-adjacent code and SEC-27 was cybersecurity-authored (CLAUDE.md's
standing review requirement, not optional).

**This is a recommendation, not a closed ruling.** D-085 routed the actual technical call to
CTO/backend-developer. Task T-1 below is written to start once CTO signs off on D-087 (or
rules the other way, in which case T-1 is re-scoped before code is written) — flagged in §5 as
an open question, not assumed granted.

---

## 2. Sequencing: `#207` → rehearsal 4 → both verdicts → fallback recording

```
                 ┌─ T-1 #207 fix (backend-dev) ──────┐
                 │                                     ├─ T-2 cybersecurity review ─┐
                 │                                     │                             │
CTO sign-off ────┤                                     │                             ├─ T-7 rehearsal 4
 on D-087        │                                     │                             │  (devops-eng)
                 │                                     │                             │
                 └─ T-3 operator-candidate ────────────┴─ T-4 cybersecurity+EM ──────┘
                    endpoint (backend-dev,               review
                    parallel worktree)

USER go-ahead ──────────────────────────► T-5 (human decision) ──► T-6 dev-DB reset (devops)
 for dev-DB reset                                                        │
 [NOT YET GRANTED — flagged §5]                                          └──────────► T-7 (also
                                                                                       depends here)

T-7 rehearsal 4 PASS ──► #50 closed ──► T-16 three #57 rehearsals (devops-eng) ──► T-17 #60 freeze prep

Fallback recording ──► STANDING HUMAN TASK, not staffed to any engineering role (§4).
```

**Why the operator-supplied-candidate endpoint (T-3) is scheduled proactively, not left to a
gamble.** D-084/D-085 both confirmed no HTTP-reachable operator-supplied-candidate path exists
today, and `demo/repositories/pktcfg/patches/` already ships fixtures built for exactly this
(`candidate-a` → intended `Verified`, `candidate-b` → intended `Rejected`). Relying on the live
model to spontaneously produce both a correct and a plausible-but-wrong patch in the same run
is unreliable and non-reproducible — a poor fit for a project whose own kill criterion is about
reproducibility. D-008 already permits operator-supplied candidates, labelled as such — this is
finishing already-approved scope, not new scope, and with 10 days instead of 3 there is room to
build it before rehearsal 4 rather than discover the gap live a fourth time.

**Why rehearsal 4's acceptance check must include running the same fixture twice in a row,
untouched, in one session.** The Week 2 kill criterion is "reproduced twice consecutively." A
single successful rehearsal-4 run, on its own, does not prove `#207`'s fix actually closes the
gap — only that the reset unblocked one run. T-7's acceptance check below requires driving the
same `pktcfg` mission twice, back to back, with zero database action in between.

**The dev-DB reset go-ahead is a dependency, not an assumption.** Per D-085, the destructive
action was correctly refused by the acting session's own safety rules and is not this
engineering-manager's to grant either. **T-5 is listed as blocked on the user, explicitly, in
§5's open questions** — nothing downstream of it should be treated as scheduled until answered.

---

## 3. Task board

### Milestone A — `#207` fix and rehearsal 4

| ID | Role | Goal | Spec ref | Acceptance check | Depends on | Status |
|---|---|---|---|---|---|---|
| T-1 | backend-developer | Implement D-087's recommended fix in `authorization/service.py::create_mission_snapshot` | D-087, D-025, SEC-27 | Existing cross-mission-claim test in `api/tests/test_authorize_snapshot.py` flips from asserting `409` to asserting success/reuse; new test asserts the kind/size-mismatch case still raises `SnapshotArtifactClaimedError`; a local two-mission-same-digest scripted test passes without any DB reset | CTO sign-off on D-087 | todo |
| T-2 | cybersecurity | Review T-1's PR — confirm removing the exclusivity check is safe given SHA-256 preimage resistance, confirm the metadata-consistency replacement is real and tested | CLAUDE.md security-review rule, SEC-27 | Explicit CLEARED/BLOCKED verdict recorded on the PR and in `.project/decisions.md` | T-1 | todo |
| T-3 | backend-developer (2nd, parallel worktree) | Operator-supplied-candidate HTTP endpoint: accept a caller-supplied patch, label it `PatchProvenance.OPERATOR_SUPPLIED` (D-008), feed it into the existing frozen-candidate-set (`orchestrator/candidates.py`) and `VERIFY` path unmodified | D-008, D-084, D-085, `contracts/schemas`, `api/routers/` | A local (non-mocked) test drives `demo/repositories/pktcfg/patches/candidate-a...` and `candidate-b...` through the endpoint against a real `BASELINE`-passed mission and gets real `VERIFIED`/`REJECTED` verdicts respectively, via the unmodified `VERIFY` executor | none — can start Day 1, parallel to T-1 | todo |
| T-4 | cybersecurity + engineering-manager | Review T-3 — new HTTP surface touching `PATCH`/`VERIFY`, D-008-permitted but previously unbuilt | CLAUDE.md security-review rule | Explicit verdicts recorded from both reviewers | T-3 | todo |
| T-5 | **human — CEO/Mahatav, not an engineering role** | Explicit go-ahead for a scoped, disposable dev-Postgres reset before rehearsal 4 | D-085's own safety-classifier finding | A recorded yes/no in `.project/decisions.md` or direct instruction | none | **blocked — not yet asked/answered, flagged §5** |
| T-6 | devops-engineer | Execute the scoped dev-DB reset (targeted deletion of the stale `Artifact`/`Mission` rows from runs 2–3, or `docker compose down -v` against the disposable volume) | D-085 | Confirmed via `psql`/`manage.py shell` read that the prior runs' digests no longer have a claim; `docker ps -a` clean before/after | T-5 | blocked |
| T-7 | devops-engineer | Rehearsal 4 — full 9-step live `#50` attempt; explicitly run the **same** `pktcfg` mission twice consecutively, zero DB action between; attempt both verdicts (live model, falling back to T-3's endpoint) | `#50`, D-085 | Both consecutive runs reach at least `BASELINE_PASSED` unattended; both `VERIFIED` and `REJECTED` produced and visible at least once this session; evidence file written (`.project/evidence/d7-gate-50-live-run-2026-08-2x-run4.{json,md}`); explicit PASS/FAIL posted to `#50` | T-1, T-2, T-3, T-4, T-6 | blocked |

### Milestone B — hardening (the 16-finding triage, §5 detail), mostly Day 1–4, parallel to Milestone A

| ID | Role | Goal | Acceptance check | Depends on | Status |
|---|---|---|---|---|---|
| T-8 | database-engineer | Unique constraint on `Job(mission, kind)` (`#176`, SEC-42) and `Finding(mission, fingerprint)` (D-083 §4's flagged gap, same shape) in one migration, mirroring the existing `IntegrityError`-catch pattern (D-064, D-083 §4) | Migration applies clean; a concurrency test (same shape as `#168` T0's SKIP LOCKED attack) proves the constraint rejects a real duplicate under concurrent writers, not just declares one in `Meta` | none | todo |
| T-9 | backend-developer or devops-engineer | Singleton guard for `manage.py run_orchestrator` (`#177`, SEC-43) — a Postgres advisory lock acquired at startup, second instance refuses to start | `missions/management/commands/run_orchestrator.py` | Starting a second instance while one runs exits non-zero within 5s with a clear message; first instance's ticking is unaffected; test proves it | none | todo |
| T-10 | backend-developer | Snapshot workspace garbage collection (`#180`) | Workspace dirs for terminal missions are cleaned on a schedule or at `TEARDOWN`; a test proves disk usage does not grow unbounded across N sequential missions against the same fixture — directly relevant given T-7's repeated-run design | none | todo |
| T-11 | backend-developer / compiler-toolchain-engineer (owns `Jail`) | Root-cause and fix the intermittent `PermissionError` in `Jail._kill_group` (`#184`) | Likely a race against an already-exited child (needs `ESRCH`/`ProcessLookupError`-tolerant handling); a regression test that forces the race (kill an already-reaped process group) passes reliably across repeated runs, not once; cybersecurity re-review since it's sandbox-teardown code | none | todo |
| T-12 | engineering-manager (bookkeeping) | Confirm `#198` (SEC-54) and `#203` (QA-01) are already closed by landed regression tests | Run `tests/architecture/test_worker_executor_modules_import_boundary.py` and `apps/control-api/orchestrator/tests/test_fuzz_only_kinds_shell_drift.py` locally, confirm green, close both issues referencing the test names | none | todo (~15 min, no dev needed) |
| T-13 | backend-developer | Per-stage `isolation_mode` recording, threaded from `BaselineOutcome`/`FuzzingOutcome` through to `EvidenceBundle`, replacing the single deployment-level constant D-080 §3.3 flagged | `orchestrator/evidence_bundle.py`, `orchestrator/evidence_export.py`, `missions/models.py` (`BaselineReport` has no such column today) | A mission whose `BASELINE` ran under `Jail` and whose `FUZZ` ran under `ContainerJail` (the real posture since D-072/D-073) produces an evidence bundle whose isolation fields reflect that per-stage truth, not one deployment-wide guess; test proves it against a mocked mixed-mode mission | none, coordinate with whoever owns `evidence_bundle.py` post-`#168` | todo |
| — | (no action) | `#181` — accepted, same class as the settled Jail-vs-ContainerJail posture note | Comment-and-close as accepted risk; no engineering time | — | no action |
| — | (deferred, not scheduled) | `#163`–`#165` (needs a body-read pass, §3.4); the two lower-value D-080 disclosures (`Export.idempotency_key` not persisted, `include_artifacts` NOTE.txt-only); `MINIMIZE` real implementation (D-083 §2, explicitly off the `JOB_BACKED_STATES` dispatch path today) | — | — | deferred |
| — | (unconfirmed) | `#182`, `#191`, `#193`, `#194`, `#199` | Needs a `gh issue view` pass before final priority; see §3.5 | — | needs confirmation |

### Milestone C — `#57` rehearsals and `#60` freeze prep

| ID | Role | Goal | Depends on | Status |
|---|---|---|---|---|
| T-16 | devops-engineer | Three full timed rehearsals per `#57`'s own acceptance criteria | T-7 (PASS) | blocked |
| T-17 | devops-engineer + engineering-manager | Release tag, tested rollback, tightened branch protection (`#60`) | T-16 | blocked |

**Dependency order for the orchestrator to execute.** T-1 and T-3 run in parallel (isolated
worktrees, same pattern `#168`'s T-tasks used). T-8/T-9/T-10/T-11/T-12 run fully in parallel to
Milestone A, on separate files, no shared-file collisions with T-1/T-3 (confirmed: T-1/T-3 touch
`authorization/`, `api/routers/`, `contracts/schemas/`; T-8 touches `missions/models.py` +
migrations; T-9 touches `run_orchestrator.py`; T-10/T-11 touch workspace/sandbox teardown code;
T-13 touches `evidence_bundle.py`/`evidence_export.py` — six genuinely independent surfaces).
T-7 is the single serialization point: nothing in Milestone C can start before it passes.

---

## 4. Standing human task — not staffed to any engineering role

**Fallback recording.** No agent this session, or any prior session, has screen-recording
capability (stated explicitly in D-084, D-085, and every rehearsal write-up before them). The
existing `fallback-demo-d6.html` predates `#168`'s entire executor set and is stale against the
now-much-more-complete pipeline (D-086 item 5). This needs a human — Mahatav or whoever is on
the finale roster (`#59`, still open) — with real screen-recording tooling, run against a real
passing mission once `#50` is green. **Not scheduled as engineering time anywhere in this
plan**, flagged here so it does not silently fall off the board the way it has implicitly for
three rehearsals running.

---

## 5. Day-by-day sequencing (backend/infra side only)

Runway is ~10 days from 2026-08-19 (≈2026-08-29), per the user's direct correction to this
session — not the 2026-08-20 date `state.md`/`03-seven-day-plan.md`/`CLAUDE.md` were written
under (D-086). Per D-086's own instruction, holding a genuine reserve at the tail rather than
repeating the original plan's mistake of a reserve that sat inside a deadline that turned out
to be wrong.

- **Day 1 (2026-08-19/20).** T-1, T-3 start in parallel. T-8, T-9 start in parallel (independent
  files, no reason to wait). T-12 closed same day (15 minutes). **T-5 escalated to the user
  immediately** — do not wait for Milestone A to be "ready" to ask, since it gates T-7 and
  answers can take longer than the code does.
- **Day 2.** T-2, T-4 reviews land; T-1/T-3 merge if clear. T-10, T-11 start. T-6 executes if T-5
  is answered by now.
- **Day 3.** T-7, rehearsal 4. If it passes cleanly: proceed. If it finds a fourth distinct
  blocker — consistent with the pattern of every rehearsal so far, each of which found exactly
  one new real blocker — treat that as expected, not a plan failure, and loop: fix, re-attempt.
  T-13 continues in the background; it is an evidence-bundle honesty gap, not a
  pipeline-advancement blocker, so it does not gate T-7.
- **Day 4.** Buffer for rehearsal-4 iteration if Day 3 found a new blocker. T-13 wraps. Whoever
  next has `gh` access runs the title-confirmation pass on `#182`/`#191`/`#193`/`#194`/`#199`
  and `#163`–`#165` named in §3.4/§3.5, so the hardening backlog is fully triaged rather than
  partially triaged for the rest of the runway.
- **Days 5–7.** T-16, the three `#57` timed rehearsals, once `#50` is genuinely green. Runs
  concurrently with the Command Center phase-5 pass (D-086 item 2 — not this document's scope,
  but the gate that determines when the reopened CUT items, `#25`/`#56`/`#52`/`#31`, and the
  conditionally-reopened `#40`, can start staffing per D-086's own explicit rule).
- **Day 8.** T-17 (tag, rollback test, branch protection) starts once the three `#57` rehearsals
  are clean. If CTO has confirmed `#40` (renewed-fuzzing gate after patch) is genuinely cheap
  now that `T2`/`FUZZ` exists (D-086's own gating condition on that item), a small backend task
  can land here — not sized in this document, since it is conditional on a CTO call this plan
  does not make.
- **Days 9–10.** Reserve, genuinely held, not pre-spent. Fallback recording (§4) should happen
  as soon as a good, real, passing run exists to record — ideally inside days 5–8, not pushed to
  the reserve window by default.

---

## 6. Blockers

| Blocker | Owning role | What unblocks it |
|---|---|---|
| `#207`'s technical fix is a recommendation (D-087), not a ruling | CTO | CTO reviews D-087, rules for/against mission-scoped claiming; T-1 starts (or is re-scoped) on that ruling |
| Dev-DB reset for rehearsal 4 | user (Mahatav) | Explicit yes/no on T-5; nothing in Milestone A's T-6/T-7 proceeds without it |
| Five findings unidentified without `gh` access (`#182`, `#191`, `#193`, `#194`, `#199`) | whoever next has shell/`gh` tooling | A `gh issue view` pass to confirm titles before their §3 provisional triage is treated as final |
| `#163`–`#165` (sandbox residuals) sized without reading their bodies | cybersecurity | Same `gh` pass; confirm none is rated HIGH/CRITICAL before deferring past the finale |
| Command Center readiness against the current API surface is unverified | ui-ux-designer/frontend-developer (separate pass, D-086 item 2) | Not this plan's scope, but T-7 passing and this backend surface stabilizing is a precondition for that pass to have something real to wire against — flagged as a cross-role dependency, not duplicated here |
| `#59` finale roster | user (Mahatav) directly | Real names and logistics; unrelated to the backend critical path but blocks `#60`-adjacent operational planning |

---
