# Project State — Brahmadatta AI

| Field | Value |
|---|---|
| Repository | https://github.com/Mahatav/brahmadatta-ai (private) |
| Board | https://github.com/users/Mahatav/projects/3 |
| Deadline | **2026-08-20** · CEO target **2026-08-15** |
| Current phase | 5 — implementation, in closeout (D5/D6 done, D7 gate not yet run live) |
| Last updated | 2026-08-15 (reconciliation pass) |

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

**#154 — CLOSED, 2026-08-17.** All 7 of the 7 stub mission-lifecycle HTTP routers
(`create`, `list`, `get`, `preflight`, `start`, `pause`, `cancel`) are wired to the real
orchestrator/service layer, via PR #160 and PR #161. Full review chain on both
(engineering-manager APPROVE, cybersecurity CLEARED, QA PASS on #161's concurrency
properties specifically) — see the closing comment on #154 for the complete trail.
A real pre-existing bug (`orchestrator/transitions.py`'s `select_for_update().get()`
missing a `Mission.DoesNotExist` catch) was found by the CTO's design brief before code
was written, and fixed with a test proven to fail pre-fix and pass post-fix.

**#154 was the actual, complete blocker on #50.** Every module underneath the HTTP layer
was already real and tested; only the entry points weren't wired. That's no longer true.

**Next step: attempt a live #50 run.** Nothing else is known to block it — but this needs
re-verifying for real (fresh `.env`, Docker state, TLS certs) rather than assumed carried
over from the 2026-08-15 reconciliation pass, since state can drift between sessions.
Everything else in D7–D9 remains downstream: #57 (rehearsals) needs #50 to pass once;
#60 (freeze) needs #57.

## Open, owned by the CEO

1. **#59 — finale roster.** Who is physically present for the run, and the runbook's
   incident-lead/demo-operator/evidence-lead split. Registration and travel lead time
   apply once decided. Independent of #154/#50 — can be decided in parallel.

Closed since the last version of this file: #2 (deadline), #3 (competition rules), #8
(visual references), #63 (bisect stays cut) — all resolved earlier in the build and already
reflected in `docs/09-company/03-seven-day-plan.md`.
