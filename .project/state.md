# Project State — Brahmadatta AI

| Field | Value |
|---|---|
| Repository | https://github.com/Mahatav/brahmadatta-ai (private) |
| Board | https://github.com/users/Mahatav/projects/3 |
| Deadline | **≈2026-08-29** (D-086: runway corrected from the stale 2026-08-20 date, ~10 days from 2026-08-19) |
| Current phase | 5/7 — backend/orchestration pipeline D7-gate-complete; Command Center's full visual rebuild against the approved rev-2 spec (D-086 item 2) is **merged** (PR #231, D-113..D-119) — next up is `#57`'s three timed rehearsals |
| Last updated | 2026-08-21 — **Command Center visual rebuild merged to `main`** |

## #50 closed — the headline result

Six live rehearsals (D-084, D-085, D-098, D-099, D-105, D-112), each finding and closing
exactly one real blocker: mission-driver wiring (#168) → BASELINE toolchain → VERIFY's
missing `git` → PATCH_GENERATE's path/mount gap → evidence-export crash → PATCH_GENERATE's
bearer-token routing → the reproducer-persistence gap that had capped every verdict at
`HUMAN_REVIEW_REQUIRED` regardless of patch correctness (D-106/D-109, independently
cybersecurity- and QA-cleared, D-110/D-111).

Run 6 (D-112) reached **PASS on every acceptance criterion an engineering session can
execute**: one mission producing both a live `VERIFIED` and a live `REJECTED` verdict
against a real, self-discovered fuzzing finding (first `VERIFIED` in this project's
history), evidence bundle exported and independently re-verified (sha256, re-checked a
second time by the orchestrating session itself before closing the issue), zero-stray
teardown. Closed 2026-08-20, with one standing, named exception: **the fallback
recording is not something any coding-agent session can produce** — this remains
Mahatav's own next action, not an engineering gap.

## What's next

**Update, 2026-08-21: the Command Center visual rebuild (D-086 item 2) is done and
merged** — `main`@`4704d7e` (PR #231, squash of D-113 through D-119). The Core, Stage
Timeline, Findings/Evidence rail, Candidate Compare overlay, Verdict panel, resource
ledger and bottom-strip controls are all live against the approved rev-2 spec
(`docs/09-company/04-design-system.md`), independently QA-approved against the real
running stack (not mocks) after two rejection rounds (D-114, D-116) and a final pass
(D-119) that fixed a React SSR hydration mismatch and a Stage Timeline bug that hid 6 of
10 genuinely-completed stages behind a stale `QUEUED` badge — both found and verified via
a real curl-driven mission, not fixtures.

Per D-086's priority order, next is the three `#57` timed rehearsals against
`docs/10-competition/36-hour-finale-runbook.md`'s stage budgets (failure injection: GPU
unavailable, target fails to build, a stage hangs; `infrastructure/scripts/
finale-egress-evidence.sh` run and recorded each time), then the reopened CUT items in
D-086's stated order, then `#60` code freeze with a real reserve held at the tail. `#59`
(finale roster) is answered: Mahatav + team, combined demo-operator/incident-lead role.
`#229` (SSE malformed-event log line, low severity) parked as `tier:P2` backlog. `#230`
(worktree docker-compose collision gap left by PR #219) dispatched to a devops-engineer
pass, in flight. The hardening backlog from the earlier 16-finding triage
(`docs/09-company/14-runway-task-plan-2026-08-19.md` §3) remains open, lower priority
than `#57` per D-086's own ordering.

## What this update is

This session's prior work stopped mid-D3. A large amount of implementation landed after
that — much of it authored directly by Mahatav and/or another tool (commit branch prefix
`codex/…`), outside this orchestrator's own delegation, plus continued agent work through
D4–D6. This file had gone stale relative to the repo. Reconciled 2026-08-15 by reading
`git log`, `gh pr list`, `gh issue list --milestone`, and by actually re-running the D9
closure audit rather than trusting its last recorded result. Nothing here is re-litigated;
this is a status correction only.

## Milestone status, verified against the board

| Milestone | Open | Closed | Note |
|---|---:|---:|---|
| D1 — Foundations | 0 | 10 | done |
| D2 — Spine | 0 | 11 | done |
| D3 — Baseline | 0 | 14 | done |
| D4 — Instrumentation | 0 | — | done (folded into D5 delivery) |
| D5 — The finding | 0 | 6 | done |
| D6 — The loop | 0 | 4 | done |
| D7 — Evidence & freeze | **1** | 1 | **#50 open — see below** |
| D8 — Hardening & rehearsal | **1** | 4 | #57 blocked on #50 |
| D9 — Submission & freeze | **3** | 2 | #33, #59, #60 — see below |
| RESERVE (Aug 16–20) | 0 | 0 | untouched |
| CUT | 18 | 1 | as designed; one item pulled back and closed |

## The one thing that actually gates everything else: #50

**#50 — "GATE: full minimum-viable-demo run, unattended" — is open, not closed.**

Its last recorded audit (commit `da162ff`, run by Mahatav directly, 2026-08-14) found the
gate **blocked**: that session had no `.env` and no Docker access, so `finale-up.sh` and the
nine-step unattended run could not be attempted, let alone pass. The fallback recording
(`fallback-demo-d6.html`) exists and is hash-verified — the insurance policy is real even
though the primary path hasn't been proven.

**Reconciled today, with this machine's Docker access — pushed all the way to actually
attempting the live run, per the CEO's explicit go-ahead:**

1. `npm run finale:audit` failed honestly on the first pass: `.env` had unfilled
   `REPLACE_ME` placeholders and `REDIS_PASSWORD` was unset. Generated real local secrets
   (gitignored, never committed) and re-ran clean.
2. Brought up `docker-compose.finale.yml` for real. **Found a bug the audit couldn't see**:
   the running `control-api` image was built 2026-08-07, a full day before the SEC-03 fix
   (finale.py pinning `APP_ENV`) landed 2026-08-08. `docker compose up` reuses a cached
   image by default, so the container was silently running yesterday's code — `/api/v1/system/health`
   reported `app_env: "development"` under the *finale* compose file. Forced a clean
   rebuild (`--no-cache`); confirmed fixed (`app_env: "finale"`).
3. **Found a second, previously-undiscovered gap**: `manage.py check` — now actually
   reachable, since the stale image had been masking it too — failed on
   `brahmadatta.E005`: the finale profile requires an encrypted `DATABASE_URL`, and nothing
   in the compose setup configured Postgres to speak TLS at all. Did not weaken the check.
   Built a TLS-enabled Postgres image (`infrastructure/compose/images/postgres-tls.Dockerfile`,
   cert baked in at build time — bind-mounting a key with correct ownership into a Postgres
   container is unreliable from a macOS host), wired `docker-compose.finale.yml`'s `db`
   service to build from it, added `?sslmode=require` to `DATABASE_URL` for this rehearsal.
   `manage.py check` now passes clean; migrations applied for real.
4. **With every infra and config gate now genuinely green, attempted the actual mission
   creation call — `POST /api/v1/missions` — and hit `501 NOT_IMPLEMENTED`, tracked by
   #12.** #12 is closed and merged. Mapped every mission-lifecycle route: `authorize`,
   `snapshot`, `events`, and `events/replay` are genuinely wired to real service code.
   **`create`, `list`, `get`, `preflight`, `start`, `pause`, and `cancel` — seven of eleven
   — are still `NotImplementedYetError` stubs.** The orchestrator, candidates, verification,
   fuzzing and teardown modules underneath them are real and were tested at the unit/service
   level as each merged; the HTTP surface that would let an operator (or this audit) drive a
   mission through them from a cold start was never wired for the entry point and several
   steps after it.

**This is the actual, complete reason #50 cannot pass today.** Not environment (fixed,
twice), not the underlying engine (built and reviewed across D2–D6) — the API layer
connecting the two. Closing #12 without the routers actually calling into it is why this
was invisible on the board: every module's own tests passed, so its issue closed correctly
by its own acceptance criteria, and nothing forced an end-to-end HTTP check until this audit
attempted one.

**Wiring the seven remaining routers is real, sizeable implementation work** — this
reconciliation pass stops here rather than start it unprompted. The finale stack (rebuilt
image, TLS Postgres, migrated database) is left running and correctly configured for
whoever picks this up next.

## D9's other three open items, all correctly blocked on #50 rather than stalled

- **#57** (three full timed rehearsals) — cannot start until #50 passes; a rehearsal of a
  gate that hasn't itself passed once proves nothing.
- **#59** (finale roster — who is physically present) — blocked on a CEO decision, not
  engineering. Options and a recommendation were given in the phase-1 CEO draft
  (`docs/09-company/01-vision-and-p0-cut.md` §5.3); never answered.
- **#60** (code freeze) — blocked on #57 passing, a release tag, a tested rollback, and
  tightened branch protection. None of those are meaningful before #50/#57 are real.

## What's actually done, verified rather than assumed

D1 through D6 are closed on the board and the corresponding code is on `main`: Astro +
Django scaffold, the frozen API contract, the `pktcfg` demo target with its rejection
asymmetry, the mission state machine and persistence layer, the sandbox jail
(`packages/sandbox/`), the model gateway with recorded-transcript replay, the C/C++
toolchain adapter with ASan/UBSan, the SSE event stream, the authorize/snapshot endpoints,
the fuzzing campaign runner, patch policy enforcement, clean-worktree verification, mission
teardown, and the Command Center dashboard shell. Each went through at least one review
round (security, QA, or both) before merging — this file does not re-summarize those
rounds; see `docs/09-company/08-security-review.md` and `11-qa-report.md` for the full
history.

## The critical path now

**#154 closed 2026-08-17** (PR #160 + PR #161, full review chain: backend-developer x2,
engineering-manager, cybersecurity, qa-engineer). All 11 mission-lifecycle HTTP routers are
now genuinely wired. **#50 was attempted live the same day, the first attempt since #154
landed, and still FAILS** — for a different, deeper reason than #154 fixed. Full evidence:
`.project/evidence/d7-gate-50-live-run-2026-08-17.{json,md}`.

That run: fixed two small, newly-discovered devops-scope environment bugs on the spot
(`demo/repositories` was never mounted into `control-api` in either compose profile, so
local-target snapshot ingestion had never worked containerized; `ARTIFACT_ROOT` pointed
inside the finale image's read-only filesystem, and the volume fallback was root-owned
against a non-root, capability-dropped container — both fixed in
`infrastructure/compose/docker-compose.finale.yml`, `docker-compose.yml`, and
`infrastructure/compose/images/control-api.Dockerfile`; see decisions.md #4). With those
fixed, drove a real mission through `create → authorize → snapshot → preflight → start`
against `pktcfg` over the real HTTP API and confirmed, empirically (60s of unattended
polling, zero state change) and statically (full grep of every router, the transitions
module, and the worker packages), that **nothing — no HTTP endpoint, no background
process, no signal, no queue consumer — ever advances a mission past `VALIDATING`.** The
state machine legally permits `VALIDATING → BASELINE` and every stage after it, and the
actual stage-execution code (`workers/baseline/run.py`, `workers/fuzzing/`,
`orchestrator/candidates.py`, `orchestrator/verification.py`) is real and unit-tested — it
simply has no caller. `workers/baseline/run.py`'s own docstring names this directly: the
"future orchestrator" that was supposed to call it was never built. The identical gap
recurs at `CANCELLING → CANCELLED` (teardown runs for real, but nothing finalizes the
mission afterward).

**This is the actual, complete reason #50 cannot pass today.** Not environment (fixed,
three times now across two sessions), not #154's own scope (#154's acceptance criteria
correctly stopped at `start` and never claimed more) — a missing mission-stage driver that
connects the state machine to the already-built pipeline code. Sizeable, scoped engineering
work of the same shape as #154 itself; not attempted in the #50 rehearsal per its explicit
instructions, reported instead.

Everything else in D7–D9 is downstream of this: #57 (rehearsals) needs #50 to pass once;
#60 (freeze) needs #57. Nothing else on the board is close to gating; this is the one thing.

**#168 filed 2026-08-17** for the driver gap. CTO design brief (D-061) and
engineering-manager staffing plan (D-062) both done — see `.project/decisions.md`. Key
finding: this is finishing issue #12, not new design; an architecture spec (D-024/D-026)
and a migrated `Job` model already exist with zero callers. Staffing of the Day-1 parallel
tracks (T0 orchestrator tick loop, T0b snapshot extraction, T1/T5/T7 executors) is the
active next step.

**Update, same day, after T0/T0b/T7 landed:** T0 (orchestrator tick loop + dispatch,
PR #171) and T0b (safe snapshot extraction, PR #170) merged to `main`. T7 (`JobKind.TEARDOWN`
executor + R3 transition policy, PR #173) also merged — but its own engineering-manager
review round found, and required the PR description corrected to state honestly, that **it did
not actually close the `CANCELLING` half of #50's repro**: `orchestrator.queue.
JOB_BACKED_STATES` still excluded `MissionState.CANCELLING`, so no `TEARDOWN` job was ever
enqueued and `dispatch_terminal_jobs` never had one to route — the `CANCELLING → CANCELLED`
policy was correct and fully tested in isolation, but unreachable from any live path. A mission
that entered `CANCELLING` on `main` still hung there forever after #173 merged, identically to
this file's own evidence above. **Branch `fix/168-t7-cancelling-dispatch` closes that specific
gap**: `CANCELLING` is now a row in `JOB_BACKED_STATES` (D-069), a real end-to-end test drives a
mission through cancel → real enqueue → real worker-executed `TEARDOWN` job → real
`dispatch_terminal_jobs` → genuine `CANCELLED` (and, separately, `FAILED` on a real teardown
failure) against real Postgres — see D-069 and this branch's PR for full test output. A latent,
newly-reachable exception-safety bug in `_run_teardown_after_commit` (an uncaught
`TeardownFailedError` from a synchronous teardown failure could have crashed the whole tick's
dispatch pass) was found and fixed alongside it, same PR, same decision record.

**This does not, by itself, close #50.** T1 (`BASELINE` executor, PR #174) and T5 (`VERIFY`
executor, PR #175) are both still open, not merged; T2/T3/T4/T6 (`FUZZ`/`CORRELATE`/
`PATCH_GENERATE`/`EXPORT`) are not yet staffed or filed against #168 as of this update. A
mission still cannot run the full happy path unattended until those land — this update only
corrects the record on the one piece (`CANCELLING`) that is now genuinely wired, so this file
does not overstate #50's status while the rest of #168 is still in flight.

## Open, owned by the CEO

1. **#59 — finale roster.** Who is physically present for the run, and the runbook's
   incident-lead/demo-operator/evidence-lead split. Registration and travel lead time
   apply once decided. Unrelated to the gate blocker — can be decided in parallel.

Closed since the last version of this file: #2 (deadline), #3 (competition rules), #8
(visual references), #63 (bisect stays cut), #154 (2026-08-17) — all resolved earlier in
the build (or today, for #154) and already reflected in
`docs/09-company/03-seven-day-plan.md` / the evidence file above.

## Reconciliation, 2026-08-19 — everything since this file's last update

This file went stale again: an entire autonomous session landed between the last update
above and today, none of it reflected here. Reconciled by reading `git log`, `gh pr list`,
`gh issue list`, and `.project/decisions.md` (now D-085 plus D-060 through D-084) rather
than trusting this file's own account of where things stood.

**#168 (mission-stage driver) is closed.** All 7 executors (T1–T7) merged and reviewed:
`#175` (T5/VERIFY), `#186` (T3/CORRELATE), `#187` (T6/EXPORT, two rounds of cybersecurity
findings — SEC-48/49/50 — fixed and independently re-confirmed), `#188` (T2/FUZZ+MINIMIZE),
`#196` (T4/PATCH_GENERATE), plus prerequisite topology work `#189`/`#192` (pinned fuzzing
image, closed) and `#197`/`#201` (fuzz-worker split topology + model-host bearer auth,
D-073/D-075). GitHub Actions CI was down for a billing reason for most of this window;
every merge was gated on real local test runs (several with a second, independent
reviewer re-running the same tests) instead, per an explicit user decision to not block on
it — not a lowered bar, a different one.

**#50 was attempted live three times this session, each run closing exactly one real
blocker and finding the next:**
- **Run 2** (D-084): confirmed, empirically, that #168's fix works — a mission now
  advances `VALIDATING → BASELINE → FAILED → teardown` fully unattended, zero HTTP calls
  after `start`. Found a new blocker: the compose `worker` image had no C/C++ toolchain
  (`BASELINE` runs `cmake`/`make`/`ctest` as a direct subprocess via `packages.sandbox.Jail`,
  not `ContainerJail` — the rootless-container backend, #15, was never built), so `BASELINE`
  failed in 0.034s, `cmake: not found`.
- Fixed in `#205` (`build-essential cmake patch libasan8 libubsan1` added to
  `control-api.Dockerfile`'s shared base stage), cybersecurity-reviewed (CLEARED — doesn't
  worsen the already-known/accepted Jail isolation gap; `policy.py`'s own env allowlist
  already assumed a compiler on PATH).
- **Run 3** (D-085): confirmed the fix is real — a genuine `cmake configure && make &&
  ctest` cycle against `pktcfg` now passes inside the built image, first time ever. But a
  live mission couldn't reach it: `pktcfg`'s snapshot archive is byte-for-byte
  deterministic, so every mission hashes identically, and the content-addressed artifact
  claim (SEC-27) has no release path on any terminal state — the prior `FAILED` mission
  owns the digest permanently. **This directly conflicts with the project's own Week 2 kill
  criterion** ("reproduced twice consecutively") — as built, a second consecutive attempt
  against an unmodified fixture is structurally impossible without a database reset.
  Reported, not routed around (the fix requires a destructive dev-DB action, correctly
  outside a devops-engineer's or this orchestrator's unilateral authority) — filed as
  **`#207`**, decision on the actual fix (release path vs. mission-scoped claiming) owned
  by CTO/backend-developer. A live database reset + run 4 needs the user's go-ahead, not
  yet given.

**Both required verdicts (`Verified` + `Rejected`) have never been reached live.** Also
newly confirmed by run 2/3: `demo/repositories/pktcfg/patches/` already ships fixtures
designed to produce both (`candidate-a`, `candidate-b`), but there is no HTTP-reachable
operator-supplied-candidate endpoint anywhere — `patch_generate_executor.py` only ever
calls the live model. Getting both verdicts in one run likely depends on the live model
spontaneously producing both a good and a bad patch, or on adding that endpoint — not
decided or attempted yet.

**Fallback recording**: the D6 recording (`fallback-demo-d6.html`, referenced above) still
exists and was hash-verified as of the last check before this session. No agent this
session had screen-recording capability, so it was not re-attempted or re-verified — this
remains a human task, flagged plainly in all three rehearsal write-ups rather than faked.

**Command Center UI received zero attention this entire session** — confirmed by reading
`apps/command-center/src/` directly rather than assuming: it is NOT a blank slate (a real
Astro build exists, `dist/` is populated, and `src/components/` has `MissionCommandCenter`,
`AIParticleCore` — the radial Core — `LiveEventStatus`, `VerdictComparePanel`,
`ModelGatewayStatus`, `LocalRepositoryIntake`, `SystemStatus`: 18 source files), but nothing
in it has been touched since 2026-08-16, before this session's entire backend/orchestration
push. Whether it's wired to the now-much-more-complete API surface, and whether it can
actually render a live mission end to end, is unverified and is the most important open
question for the next phase of work.

**16 non-blocking findings remain open, filed during this session's review rounds**
(`#163`–`#207` range, `SEC-NN`/`QA-NN` labels, no milestone): concurrency/correctness gaps
(`#176` no unique constraint on `Job(mission,kind)`, `#177` no orchestrator singleton
guard), cleanup/hygiene (`#180` snapshot workspace GC, `#184` intermittent
`PermissionError` in `Jail._kill_group`), already-accepted-as-known isolation posture
(`#181`, same class as the extensively-discussed SEC-44/47 Jail-vs-ContainerJail gap — not
new information, tracked correctly), and several drift/robustness findings from the last
two PR review rounds (`#191`, `#193`, `#194`, `#198`, `#199`, `#203`, `#207`). None block
`#50`; all are real and worth scheduling, not clearing on sight.

**User-provided context update, 2026-08-19**: the deadline is 10 days out from today, not
the 3-day emergency compression this file and `docs/09-company/03-seven-day-plan.md` were
written under — those documents are stale on this point and need reconciling (not treated
as authoritative for pacing going forward). This materially changes the calculus on the
CUT milestone (18 open items — several UI/UX-shaped: `#25` analysis rail, `#26` git-history
panel, `#31` fuzzing telemetry panel, `#52` presentation mode, `#56` keyboard operability)
and is a CEO-scope call, not an engineering one — routed to the `ceo` role, not decided
here.

**Current phase, corrected**: still phase 5 (implementation) for the backend/orchestration
engine, which is now genuinely feature-complete for the D7 happy path modulo `#207`; but
the Command Center frontend has not yet had a phase-5 pass against the now-real API surface
at all. Both need to run concurrently for the remaining runway, not sequentially.
