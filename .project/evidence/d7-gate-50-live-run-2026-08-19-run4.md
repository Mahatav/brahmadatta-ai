# #50 D7 gate — live rehearsal, run 4 (2026-08-19/20)

Full machine-readable detail: `d7-gate-50-live-run-2026-08-19-run4.json`. Raw supporting
artifacts: `d7-gate-50-live-run-2026-08-19-run4-final-db-state.txt` (Job/PatchCandidate/
VerificationRecord/MissionEvent rows for the mission that produced both real verdicts, read
directly via a read-only Django-shell query — used instead of `GET .../events/replay`, which
500s on every mission this run, see blocker 4), and the two operator-candidate submission
responses (`...-patch-A-submission.json`, `...-patch-B-submission.json`).

## Headline

**#207's fix is confirmed live, four times over.** Every one of four separate missions this
run snapshotted the exact same already-claimed `pktcfg` digest and got `201 Created`
(mission-scoped reuse), never the `409 SnapshotArtifactClaimedError` run 3 (D-085) found.
This is the first time that fix has been exercised through the real HTTP mission-creation
path, not just read from source. **No database reset was needed or performed** — the task's
own hypothesis, that D-096/#207's landed fix made the previously-approved reset unnecessary,
is confirmed correct.

**BASELINE now passes live, through the real mission API, on every mission this run** — the
first time that's been true (run 3 only proved it via direct executor invocation).

**One real verdict achieved live: REJECTED.** A deliberately broken candidate (crash fix that
regresses a test) was submitted via the operator-candidate endpoint (D-090/D-091), dispatched
to `VERIFY`, and produced a real `VerificationRecord` with `regression_preserved: FAIL` (1 of
8 `ctest` cases failed) and overall verdict `REJECTED`. This is a real, live gate failure, not
a fixture or a mock.

**VERIFIED was not achieved.** The correct-fix candidate reached `VERIFY`, `COMPILE` passed,
`REGRESSION_PRESERVED` passed (8/8), but `REPRODUCER_ELIMINATED` came back `NOT_RUN` because no
reproducer artifact was ever persisted for the finding — a pre-existing architecture gap
(MINIMIZE/reproducer-persistence isn't wired into the automatic mission pipeline yet), not a
defect in the candidate or the gate logic. Verdict capped at `HUMAN_REVIEW_REQUIRED`. This is
the first rehearsal to reach `VERIFY` at all, so this gap was never previously observable live.

**Evidence export is broken.** Every mission that reaches `EXPORTING` this run crashes with
`TypeError: contracts.schemas.common.ArtifactRef() argument after ** must be a mapping, not
str`, reproduced twice (run 4d, run 4e). No evidence bundle was ever produced, so the "export
and read back as a fresh consumer" criterion could not be attempted.

**Teardown: PASS, zero strays** — `docker ps -a` after full teardown is byte-for-byte the same
as the pre-run baseline.

## Three genuinely new blockers found this run, one already fixed

1. **PATCH_GENERATE (live model) crashes with `IndexError`** inside
   `orchestrator/patch_generate_executor.py::_model_gateway_root()` — its
   `Path(__file__).resolve().parents[3]` assumes a directory depth that only exists on a
   bare-metal checkout; the container's flattened bind-mount layout has only 2 real parents.
   `services/model-gateway/` also isn't mounted/copied into either compose profile at all.
   **Not fixed** (application code — reported to backend-developer). Worked around by
   restarting the compose `worker` with `--kinds` excluding `PATCH_GENERATE` (a devops
   topology decision mirroring the existing D-073 kind-scoped-fleet pattern), so missions
   park cleanly in `PATCH` for the operator-candidate fallback instead of crashing forward.
2. **VERIFY's sandbox jail is missing `git`** — needed to apply the candidate diff before
   rebuild/retest. **Found and fixed this run**: added `git` to
   `infrastructure/compose/images/control-api.Dockerfile`'s shared `base` stage (same class
   of fix as PR #205's `cmake`/`build-essential` addition), rebuilt `control-api`/`worker`
   images, confirmed `git` present, confirmed VERIFY runs clean afterward on two more
   missions.
3. **EXPORT crashes with an `ArtifactRef` `TypeError`** on every mission that reaches it.
   **Not fixed** (application code — reported to backend-developer).
4. **`GET /missions/{id}/events/replay` 500s on every mission** whose event log contains a
   `triage_stub`-kind event — which is every mission that reaches `TRIAGE` (i.e. nearly all
   of them). `MissionEventSchema`'s discriminated union has no case for `{'kind':
   'triage_stub'}`. Pre-existing, newly confirmed with a concrete, 100%-reproducible repro.
   **Not fixed** (application code — reported).

## Nine-step demo, actual outcome

1. Target — pktcfg, PASS.
2. Authorize + snapshot — PASS, including four consecutive live confirmations of #207's fix.
3. Baseline — PASS, live, through the real mission API (first time).
4. Finding — PASS, real ASan heap-buffer-overflow from a real live FUZZ campaign.
5. Patch candidates — PASS via the operator-candidate endpoint (live model blocked by
   blocker 1).
6. Verdict A (Verified) — NOT ACHIEVED (capped at `HUMAN_REVIEW_REQUIRED` by a pre-existing
   gap, not a candidate or gate defect).
   Verdict B (Rejected) — PASS, real, live.
7. Evidence export — FAIL (blocker 3, `ArtifactRef` `TypeError`).
8. Evidence read-back — NOT REACHED.
9. Teardown — PASS, zero strays.

## Explicit gate verdict, posted to issue #50

**FAIL** — closer than any prior rehearsal (BASELINE live for the first time, #207 confirmed
live four times, one real verdict — REJECTED — achieved live for the first time, one new
blocker found and fixed on the spot), but the acceptance criteria are not fully met: VERIFIED
was not reached (blocked by a pre-existing reproducer-persistence gap, not this run's doing),
evidence export is broken (new blocker, reported not fixed), and evidence read-back was
therefore never attempted. Fallback recording: not attempted, as in every prior rehearsal —
this remains a standing human task, not something any coding-agent session can do.

## Timing

Approximately 100 minutes wall-clock — over this task's ~60-minute guidance, driven by three
sequentially-discovered new blockers (each only reachable once the previous one was resolved
or worked around), one image rebuild plus one reconfirmed docker-credential-helper stall on
this host, and one unexplained mid-session compose-stack recreation that required reapplying
the `db` bridge-network workaround and restarting the bare-metal `run_orchestrator`/
`fuzz-worker` processes. Reported honestly rather than cut short, per this task's own standing
instruction.
