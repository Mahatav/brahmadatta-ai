# D7 Gate #50 — Live Run, 2026-08-17

**Verdict: FAIL.** First live attempt since #154 closed (all 7 previously-stubbed
mission-lifecycle HTTP routers now wired, PR #160 + PR #161, merged today). The
environment gates are now clean — two new infra bugs found and fixed this session — but the
run itself stops partway through step 5 of the nine-step demo and cannot go further through
the real HTTP API as it exists today. Full machine-readable detail in
`d7-gate-50-live-run-2026-08-17.json`; raw final mission state in
`d7-gate-50-live-run-2026-08-17-final-mission-state.json`.

## What passed

| Check | Status |
|---|---|
| Fresh `.env`, no placeholders, correct permissions | pass |
| `control-api` rebuilt `--no-cache` against today's `main` (`2dc1c72`) | pass |
| `app_env: "finale"` confirmed live (not a stale image) | pass |
| Postgres TLS (`brahmadatta.E005`) | pass, already fixed |
| `finale-up.sh` preflight + post-start assertions | pass |
| `manage.py check` | pass, clean |
| Migrations, including the new `0003_mission_idempotency_key` from #154 | pass |
| `POST /missions` → `authorize` → `snapshot` → `preflight` → `start` | pass, all real HTTP calls, real responses |

## Two new infra bugs found and fixed this session (both small, both in devops scope)

1. **`SNAPSHOT_SOURCE_ROOT` (`/demo/repositories`) was never mounted into `control-api`
   in either compose profile.** `source="git"` snapshot ingestion against a local demo
   target (`pktcfg`) had never actually worked containerized, dev or finale. Fixed with a
   read-only bind mount in both `docker-compose.finale.yml` and `docker-compose.yml`.
2. **`ARTIFACT_ROOT` pointed inside the finale image's read-only `/app`; repointing it at
   a named volume hit a second bug — the volume was root-owned against a non-root,
   capability-dropped container.** Fixed by setting `ARTIFACT_ROOT` to a new named volume
   and pre-creating/chowning both it and the (also latently broken, never-yet-exercised)
   `evidence` volume's mount points in `control-api.Dockerfile`, so Docker's volume-seeding
   behavior gives them the right ownership on first mount.

Both are documented in full, with exact tracebacks, in the JSON evidence file.

## The actual blocker — not fixed, reported

**Nothing in the real HTTP API, and nothing running automatically in the background, ever
advances a mission past `VALIDATING`.** `start_mission` moves `SNAPSHOTTED → VALIDATING`
and returns. The state machine (`contracts/state_machine.py`) legally permits
`VALIDATING → BASELINE` and every stage after it — and the actual stage code
(`workers/baseline/run.py`, `workers/fuzzing/`, `orchestrator/candidates.py`,
`orchestrator/verification.py`) is real, exists, and is unit-tested — but no caller
anywhere in the reachable HTTP surface (11 routers across `missions.py`, `evidence.py`,
`system.py` — read them all, checked) ever invokes `orchestrator.transitions.transition()`
again after `start`. `workers/baseline/run.py`'s own docstring says this outright: *"No
orchestrator or event bus exists yet (#12)... `emit_baseline_events` is what a caller — the
future orchestrator ... — calls."* That caller was never built. No Django signal, no
management command, no RQ/Celery consumer exists to be that caller either — the compose
file's `worker` service is unwired scaffolding (`django-rq` isn't even a dependency).

**Confirmed empirically, not just by reading code.** A mission driven live through
`create → authorize → snapshot → preflight → start` reached `VALIDATING` and was polled
every 10 seconds for 60 seconds, unattended. State, progress, and event sequence never
moved. `allowed_transitions` in the mission-detail response correctly still listed
`BASELINE` — the state machine says yes, nothing ever asks it. The identical gap recurs one
step further out: `cancel` correctly moves a mission to `CANCELLING` and genuinely triggers
teardown (a real `TEARDOWN_CONFIRMED` event), but `CANCELLING → CANCELLED` has the same
missing-final-transition problem, so the test mission used for this rehearsal is left
permanently in `CANCELLING`, not `CANCELLED`, in the database.

This is real, sizeable engineering work — the same shape and size as #154 itself — not a
small devops fix, and not something to route to another agent from here per this session's
instructions. Reporting back for staffing.

## Nine-step demo, actual outcome

1. Target chosen (`pktcfg`) — n/a, implicit in mission creation
2. Authorize + snapshot — **PASS** (real HTTP, real digest verification round-trip)
3. Baseline — **NOT REACHED as a real build.** `preflight` (a legality check, not a
   baseline run) passed; no code path from the HTTP API actually runs `configure`/`build`/
   `ctest` against the snapshot.
4. Finding — not reached
5. Patch — not reached
6. Verdict A (Verified) — not reached
7. Verdict B (Rejected) — not reached
8. Evidence — not reached
9. Teardown — partially exercised via `cancel` (see above); confirms the teardown
   *mechanism* itself is real and correctly reports zero compute leaked, but proves nothing
   about behavior under an actual running sandbox, because none was ever spawned.

## State of the stack

Left running: `brahmadatta-finale-{nginx,control-api,db,redis}`, all healthy, with both
infra fixes baked in and migrations applied. Reconstructable from scratch with:

```
docker compose --env-file .env -f infrastructure/compose/docker-compose.finale.yml \
  build --no-cache control-api
infrastructure/scripts/finale-up.sh
docker exec brahmadatta-finale-control-api python manage.py migrate --no-input
```

`docker ps -a` (finale containers only, full list in the JSON): `nginx`, `control-api`,
`db`, `redis` all `Up ... (healthy)`. No sandbox containers exist because no sandbox was
ever spawned — the strays check the acceptance criteria asks for is trivially satisfied,
not meaningfully tested.

## Recommendation

File a scoped follow-up (same review pattern as #154: backend-developer implementation,
engineering-manager + cybersecurity + qa-engineer review) to build the mission-stage driver
that actually calls the existing, tested stage code and then
`orchestrator.transitions.transition()` for each state `VALIDATING` through `EXPORTING`,
plus the missing `CANCELLING → CANCELLED` / `FAILED` finalization. Whether it is
synchronous-in-request, a poller, or a real queue consumer is a CTO/architecture call, not
this report's.
