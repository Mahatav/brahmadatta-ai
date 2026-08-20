# #50 D7 gate — live rehearsal run 5 (2026-08-20)

**Seat:** devops-engineer
**Repo head at start:** `c63c47d` (main, includes D-103/D-104's PATCH_GENERATE `IndexError` fix + evidence-export `ArtifactRef` fix, and D-099's compose-project-name isolation fix)
**Full machine-readable record:** `d7-gate-50-live-run-2026-08-20-run5.json` (this file summarizes it)
**Evidence bundle actually produced and read back this run:** `d7-gate-50-live-run-2026-08-20-run5-evidence-bundle/`

## Headline

Both D-103 fixes hold up live: the `PATCH_GENERATE` `IndexError` is gone (the `gateway`
package now imports and executes inside the worker container), and the evidence-export
`ArtifactRef` crash is gone — this is the **first rehearsal ever to successfully export
and read back an evidence bundle**, the one acceptance criterion no prior run had ever
gotten far enough to test at all.

A **new, distinct blocker** immediately surfaced once the `IndexError` was fixed:
`PATCH_GENERATE`'s live-model path now reaches `model-host` but gets `HTTP 401
Unauthorized` from the `model-host-auth` bearer-token gate (D-075/SEC-50), because
`orchestrator/patch_generate_executor.py::_build_live_backend()` never threads
`GatewaySettings.model_host_bearer_token` into `OllamaCodeLlamaBackend(bearer_token=...)`
— a one-line call-site omission, confirmed precisely, reported to backend-developer, not
fixed here (application code, out of this seat's scope). Consistent with this task's own
expectation: "every rehearsal so far has found exactly one" new blocker.

## Nine-step demo, actual outcome

1. **Target** — pktcfg. PASS.
2. **Authorize + snapshot** — PASS x3 missions, including two more live reconfirmations
   of #207's mission-scoped-claim fix.
3. **Baseline** — PASS x3, live, real ctest 8/8 each time.
4. **Finding** — PASS x3, real ASan heap-buffer-overflow from a real live FUZZ campaign.
5. **Patch candidates** — PARTIAL: live-model path tried first (per this task's
   instruction), hit the new bearer-token blocker above; operator-candidate fallback
   used for both verdict shapes, as this task's own brief pre-authorized.
6. **Verdicts** — Rejected: PASS, real, live (second confirmation ever, after D-098).
   Verified: NOT ACHIEVED — capped at `HUMAN_REVIEW_REQUIRED` by the pre-existing,
   already-reported reproducer/minimized-crash-artifact-persistence gap (D-098
   recommendation 3), reconfirmed still open, not a new defect.
7. **Evidence export** — PASS, first time ever. Both a manual `POST .../export` call and
   the orchestrator's own automatic `EXPORT` job produced real, content-addressed
   `evidence_bundle` artifacts for both missions.
8. **Evidence read-back** — PASS, first time ever tested. `docker cp`'d the real artifact
   bytes out of the container's artifact store (not just the HTTP 200), extracted the
   tarball, independently recomputed every file's sha256 against the bundle's own
   manifest — 5/5 matched. `report.md` is genuinely coherent: full verdict, baseline,
   fuzzing stats, the finding, the one patch candidate's complete gate table, an honest
   "gates that did not run and why" section, and an honest disclosure that
   `include_artifacts=true` did not actually bundle raw artifacts because no generic
   `ArtifactRef`-to-bytes resolver exists yet — disclosed, not silently ignored.
9. **Teardown** — PASS. `docker ps -a` after teardown is identical to the pre-run
   baseline (`infra-postgres-1` plus 4 unrelated stopped containers from a different
   project; zero `brahmadatta-*`). `docker compose ls -a` shows zero `brahmadatta`
   compose projects registered at all — stronger than D-098/D-099's own teardown.
   Reconfirmed durable after a 60-second wait, per D-099's own lesson not to trust an
   instantaneous check. Zero stray `run_worker`/`run_orchestrator`/`run-fuzz-worker`
   host processes.

## Environment notes

- **New environment gotcha, not previously documented**: a pre-existing named `pgdata`
  volume from an earlier session carried a different `POSTGRES_PASSWORD` than this
  session's `.env`, crash-looping `worker`/`command-center` on password auth failure.
  Fixed non-destructively with a live `ALTER ROLE brahmadatta WITH PASSWORD ...` inside
  the running `db` container — no data lost, no volume reset, migrations and prior
  mission history all confirmed intact afterward.
- `POSTGRES_PORT`, `codellama:7b-instruct` pre-staging, `command-center-node-modules`
  chown, `db`'s internal-only-network loopback-publish quirk — all reconfirmed exactly
  as documented in D-084/D-085/D-098, no new findings there.
- This session ran from the **primary worktree** (not a linked worktree), so
  `dev-up.sh`'s new auto-isolation correctly left `COMPOSE_PROJECT_NAME` unset
  (`brahmadatta`, unmodified) — confirmed no other worktree had a colliding compose
  project running, before or after.
- `run_orchestrator` is still not wired into `docker-compose.yml` (D-100's own finding,
  unchanged this run) — started manually via `docker exec -d ... run_orchestrator`.

## Explicit gate verdict, posted to issue #50

**FAIL**, closer than any prior rehearsal. Genuinely new ground broken this run: the
evidence-export/read-back acceptance criterion — the one no rehearsal had ever been
able to test at all — is now fully confirmed working, end to end, with an independently
checksum-verified bundle. The `Rejected` verdict was reproduced live a second time. But
this is not a PASS: `VERIFIED` was still not reached (pre-existing gap, not this run's
doing, structurally blocks it for any fuzzing-discovered finding regardless of candidate
correctness), and a new, precisely-diagnosed blocker was found on the live-model
`PATCH_GENERATE` path (reported, not fixed, out of this seat's scope). Fallback
recording: not attempted, as in every prior rehearsal — a standing human task.

## Recommendation

1. **backend-developer**: fix the new bearer-token blocker in
   `orchestrator/patch_generate_executor.py::_build_live_backend()` — pass
   `bearer_token=settings.model_host_bearer_token` into `OllamaCodeLlamaBackend(...)`.
   This looks like a small, contained fix (the field and the settings value both already
   exist correctly; they are simply never connected at this one call site) and, once
   closed, should let the live-model path finally produce a real candidate end to end.
2. **CTO / backend-developer**: the reproducer-persistence product decision (D-098
   recommendation 3) is now the single largest remaining structural blocker to a genuine
   `VERIFIED` verdict — every other piece of the pipeline (baseline, fuzz, correlate,
   patch policy, verify, export, evidence read-back) has now been proven live, in this
   run or run 4. This is worth prioritizing over further blocker-hunting rehearsals.
3. This run's own scope is complete. Recommend the orchestrating session review this
   record and D-098/D-099/D-103/D-104 together before deciding whether to schedule a
   run 6 focused narrowly on the two items above, or to close #50 with these two named
   as the residual gap (not this seat's call to make).

**Final approval authority** — CTO / orchestrating session, per standing process.
