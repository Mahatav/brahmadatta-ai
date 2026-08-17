# D7 Gate #50 — Live Run 2, 2026-08-17

**Verdict: FAIL, but the specific blocker changed and moved forward.** This is the second
live attempt at the D7 gate today, run immediately after #168 (all 7 mission-stage
executors), #189 (fuzz-worker topology + pinned fuzzing image), and #201 (model-host
bearer-token auth) were merged in this session. Full machine-readable detail in
`d7-gate-50-live-run-2026-08-17-run2.json`; full raw terminal transcript in
`d7-gate-50-live-run-2026-08-17-run2-transcript.log`.

## The headline result: #168's blocker is closed

The first rehearsal today reported: *"nothing in the real HTTP API, and nothing running
automatically in the background, ever advances a mission past `VALIDATING`."* That is no
longer true. With `manage.py run_orchestrator` ticking and `manage.py run_worker` polling
(compose `worker` profile, plus a bare-metal `fuzz-worker` per D-073), a mission driven
through `create → authorize → snapshot → preflight → start` advanced **automatically and
unattended**: `VALIDATING → BASELINE` within one orchestrator tick (~1s), a real `BASELINE`
job was claimed and executed by the worker against the actual `pktcfg` snapshot, and on
that job's terminal result the orchestrator correctly drove `BASELINE → FAILED` and ran
teardown — all with **zero HTTP calls after `start`**. This is real, caller-driven stage
execution, confirmed empirically (event log, all `trace_id=orchestrator-tick`), not just
by reading code.

## What passed

| Check | Status |
|---|---|
| Fresh `.env` generated for the dev profile, no placeholders, correct permissions | pass |
| `docker compose config` valid | pass |
| `manage.py check` clean (after declaring `MODEL_SERVICE_NAMES=model-host`) | pass |
| Migrations, including `0003_mission_idempotency_key` | pass |
| `POST /missions → authorize → snapshot → preflight → start` | pass, all real HTTP calls |
| **Mission advanced `VALIDATING → BASELINE → FAILED` unattended, driven only by the orchestrator tick loop** | **pass — this is the #168 confirmation** |
| `GET .../evidence` on the (failed) mission — real, coherent, honest bundle | pass |
| Teardown (orchestrator's own FAILED-path teardown) | pass, `TEARDOWN_CONFIRMED`, `released=true` |
| Full stack teardown, zero strays | pass |

## One new small bug found and fixed live

`command-center-node-modules` (a fresh named Docker volume) is created root-owned by
Docker; `command-center-deps` runs as uid 1000 and could not `npm ci` into it (`EACCES`).
Fixed live with a one-off root container to `chown` the volume before retrying. Same
root-cause shape as the `ARTIFACT_ROOT`/`evidence` volume bug from the first rehearsal.
Not yet fixed at the compose/Dockerfile level — flagged as a follow-up, not landed here.

## Two environment findings, worked around for this run, not fixed in tracked files

1. **`model-host` cannot pull its own model** — its `backend` network is `internal: true`
   by design (C4), so `ollama pull` from inside it fails with a DNS resolution error, which
   is the isolation working correctly, not a bug. Worked around with a temporary,
   normally-networked container mounting the same named volume to pre-stage
   `codellama:7b-instruct` (~3.8GB, ~45s), matching the compose file's own comment that
   model pulls happen "explicitly on a prepared volume before the judged run." Never
   actually needed this run (see below), but ready.
2. **A container whose only network is `internal: true` never actually got its published
   host port forwarded, on this Docker Desktop host.** `db`'s `127.0.0.1:${POSTGRES_PORT}`
   publish (the mechanism D-073 relies on for bare-metal `fuzz-worker` to reach Postgres)
   showed up in `HostConfig.PortBindings` but never bound a real listener —
   `connection refused`. Reproduced independently with a bare test container on a fresh
   internal-only network. `nginx`'s otherwise-identical port publish works only because
   `nginx` also sits on the non-internal `external` network. Worked around for this run
   only (`docker network connect bridge brahmadatta-db`, not a tracked-file change).
   **Flagged for follow-up**: confirm whether this reproduces on the actual Linux finale
   host, since D-073's own text assumed this would "just work... the same way nginx
   already is," and that assumption was never actually exercised end to end before today.

## The actual blocker this run — not fixed, reported

**A new blocker, only exposed now that #168's caller-wiring gap is closed.**
`workers/baseline/run.py` uses `packages.sandbox.Jail`, not `ContainerJail`, for
`BASELINE`/`SANITIZER_BUILD` — by design, per the evidence bundle's own honest
`isolation_mode: SUBPROCESS_JAIL` / D-049 substitution note. `Jail` runs `cmake`/`make`/
`ctest` as a **direct subprocess of the worker process itself**, not inside a Docker
sandbox — so the compose `worker` service's own image needs a C/C++ toolchain installed.
It does not: `brahmadatta-worker` is built from `control-api.Dockerfile`, a pure
Python/uvicorn image (confirmed directly — `cmake: not found` inside the running
container). The `BASELINE` job failed in **0.034 seconds** with `configure_ok=false`,
`build_ok=false`, `error_code=BASELINE_BUILD_FAILED` — an immediate failure consistent
with a missing binary, not a real build attempt.

**Confirmed, not guessed.** Attempted a live `apt-get install cmake build-essential`
inside the running worker container as a diagnostic — it correctly failed too, because
the worker container has no route off the host at all (`backend` is `internal: true`,
the same C4 invariant that keeps repository content off any external inference API). The
isolation is working exactly as designed; the fix has to be baked into the image at
**build time**, mirroring `control-api.Dockerfile`'s own existing precedent for the
`ARTIFACT_ROOT` fix in the first rehearsal.

This blocks every real demo scenario, including both verdicts this issue's acceptance
criteria require — with `BASELINE` never producing a real pass, `FUZZ`/`PATCH_GENERATE`/
`VERIFY` are never enqueued, so neither `Verified` nor `Rejected` is reachable through
this compose stack as it exists today.

## Nine-step demo, actual outcome

1. Target — `pktcfg`, the only fixture under `demo/repositories/` (see note below)
2. Authorize + snapshot — **PASS** (real HTTP, real digest round-trip, identical snapshot
   hash to the first rehearsal — fixture unchanged)
3. Baseline — **REACHED and RAN FOR REAL this time** (a real subprocess build attempt, not
   a stub) — **and failed**, for the toolchain reason above
4. Finding — not reached (no `FUZZ` job enqueued; `BASELINE` never passed)
5. Patch — not reached
6. Verdict A (Verified) — not reached
7. Verdict B (Rejected) — not reached
8. Evidence — **PARTIALLY REACHED**: `GET .../evidence` returns a real 200 with a
   coherent, honest bundle (correctly empty findings/patches/verifications, and an honest
   `SUBPROCESS_JAIL_ISOLATION` substitution note) — the export machinery itself works,
   there is just nothing more to show for this particular failed mission
9. Teardown — **PASS**, real (`TEARDOWN_CONFIRMED`, `released=true`), driven automatically
   by the orchestrator's own FAILED-path handling, not by an operator `cancel` call this
   time

**Both verdicts in one run: not achieved.** Neither verdict was reached because `BASELINE`
blocks everything downstream — see above. `demo/repositories/pktcfg/patches/` already
ships exactly the fixture set this gate needs from a *single* target (a correct fix for
`Verified`, a crash-only fix for `Rejected`, plus a compile-failure and a policy-refusal
candidate) — but there is no HTTP-reachable "operator-supplied candidate" endpoint today,
and `PATCH_GENERATE` only ever calls the live model. Moot this run regardless, since
`BASELINE` never passed.

## Timing

- `create → authorize → snapshot → preflight → start`: ~31 seconds (mostly the operator
  script's own pacing between calls, not the API — each individual HTTP call was
  sub-second)
- `start` (202 accepted) to `FAILED` + teardown, fully unattended: **~1.2 seconds**
- Environment setup and debugging (fresh `.env`, three live infra findings, model
  pre-staging): approximately 70 minutes wall-clock, well over this task's ~45-minute
  container/fuzzing guidance — flagged plainly rather than undercounted. Most of that time
  was diagnosing the two Docker-Desktop-specific networking findings above, not the
  product code itself.

## State of the stack

Everything brought up for this run was torn down: `docker compose ... --profile worker
--profile model down` (all `brahmadatta-*` containers stopped and removed, all
project-scoped networks removed), the bare-metal `fuzz-worker` process killed, the
temporary `brahmadatta-model-prep` pre-staging container removed. `docker ps -a` after
teardown shows exactly the same five pre-existing, unrelated containers present *before*
this run started (`infra-postgres-1` and four stopped `good_marketer_web-*`/`ollama`
containers from a different project) and **zero** `brahmadatta-*` containers. `ps aux`
confirms no `run_worker`/`run_orchestrator` process survives. Zero strays.

## Fallback recording

**Not attempted and not claimed.** This session has no screen-recording/GUI capability.
The closest artifact produced is the full raw terminal transcript
(`d7-gate-50-live-run-2026-08-17-run2-transcript.log`) covering every command and its real
output for this entire run. The acceptance criterion "the pre-recorded fallback
demonstration exists, in full, as a playable file" is **not satisfiable by this session**
and needs a human with screen-recording tooling to produce separately — flagged here
explicitly rather than silently skipped or claimed as partial credit.

## Recommendation

File a scoped follow-up: add a C/C++ toolchain (`cmake`, `make`/`ninja`, `gcc` or
`clang` — `adapters/cpp/toolchain.py` names the exact requirement) to whichever target(s)
of `infrastructure/compose/images/control-api.Dockerfile` the compose `worker` service
builds from, rebuild, and re-run this exact mission to confirm `BASELINE` passes and the
pipeline reaches `STRESS_TEST`/`FUZZ`. Devops-scoped (same authority as the two on-sight
fixes already landed today), but sized as a real task rather than a same-session fix —
not attempted here given this run's time budget. Once `BASELINE` passes, the very next
question is the same "both verdicts, no operator-supplied-candidate HTTP path" gap named
above, which will need either a live model producing a spontaneously-bad candidate (D-008
already accepts the model doing this within its normal fan-out) or a small, explicitly
scoped operator-supplied-candidate endpoint if the model doesn't cooperate in time —
CTO/product call, not decided here.
