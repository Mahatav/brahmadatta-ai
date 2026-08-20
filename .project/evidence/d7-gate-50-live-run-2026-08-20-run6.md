# #50 D7 gate — live rehearsal run 6 (2026-08-20)

Seat: devops-engineer. Full machine-readable detail: `d7-gate-50-live-run-2026-08-20-run6.json`,
`d7-gate-50-live-run-2026-08-20-run6-evidence-bundle/` (extracted, checksum-verified),
`d7-gate-50-live-run-2026-08-20-run6-docker-ps-a-after-teardown.txt`, plus the raw API
request/response artifacts alongside this file.

## Headline

**All four blockers named by D-098/D-105 as still open before this run are now closed and
confirmed live**: #207 (artifact-claim deadlock), the BASELINE toolchain, VERIFY's missing
`git`, the evidence-export `ArtifactRef` crash, PATCH_GENERATE's missing bearer token, and —
the big one — the reproducer-persistence gap that had capped every prior verdict at
`HUMAN_REVIEW_REQUIRED` regardless of patch correctness (D-106/D-109/D-110/D-111).

This run drove **one real mission** (`d6897640-8212-45d8-9914-b3e0d1ae0c52`) through the real
HTTP API, unattended after each operator action, and it produced:

- a real, live, self-discovered `Finding` (ASan heap-buffer-overflow, real `FUZZ` campaign)
- a real, durable `Reproducer` row for that finding (D-106/D-109's fix, confirmed live)
- **both required verdicts, from the SAME mission**: candidate A → `VERIFIED`
  (`REPRODUCER_ELIMINATED: PASS` against the real, self-discovered reproducer — the first
  time this project's D7 gate has ever reached `VERIFIED`, in any rehearsal), candidate B →
  `REJECTED` (`REGRESSION_PRESERVED: FAIL`)
- a real evidence bundle, exported and **independently read back**: bytes pulled directly out
  of the artifact store (not trusted from the `202`), sha256 recomputed and matched against
  both the API's own reported digest and the bundle's internal manifest (5/5 files), and
  `report.md` read in full as a reviewer who did not build this system — genuinely complete,
  honest about substitutions, honest about what did not run, honest about unmeasured resource
  fields
- confirmed teardown: zero `brahmadatta-*` containers, zero registered `brahmadatta` compose
  projects, zero stray host processes, after a 60-second settle-wait

**Mission wall-clock time, orchestrator-driven pipeline only** (authorize → baseline → fuzz →
correlate → patch → verify ×2 → export → teardown, not counting this session's own manual
API-call pacing): **47.75 seconds**, unattended.

## Interpretation call made this run: "both verdicts... in that single run" means one mission

Re-read `docs/09-company/01-vision-and-p0-cut.md` §3 (the CEO doc's own nine-step demo
description) rather than assuming D-098/D-105's own two-sibling-missions shape was the
intended reading. §3 describes one sequence on one target; step 7 says the second candidate
"goes through the *identical* pipeline"; step 8 says the evidence bundle contains "both diffs,
both gate matrices, both verdicts" — one bundle. D-090 (the operator-candidate endpoint) was
explicitly built to support exactly this shape and already had unit-test coverage for it
(`test_operator_candidate_submission.py`) — but no prior *live* rehearsal had ever actually
driven it this way through the real HTTP API against a real, live-discovered finding. This
run does. Chosen as the more rigorous reading, consistent with the source document's own
literal text, and it is what this run achieved.

## Two new, small blockers found and fixed live (both infra/config, not application code)

1. **Stale `SANDBOX_FUZZ_IMAGE` digest** in both `.env` and `apps/control-api/.env` — pointed
   at an image digest that no longer existed locally (config drift from an earlier session's
   build). Fixed by re-running `infrastructure/scripts/build-fuzz-image.sh` and updating both
   files to the real current digest. Confirmed live: the next mission's `FUZZ` job succeeded
   immediately after.
2. **`MODEL_ENDPOINT` left unset**, so the live-model `PATCH_GENERATE` call fell back to
   `SMALL_MODEL_BASE_URL` (`http://model-host:11434`, no `/api` suffix) instead of the coded
   default (`http://127.0.0.1:11434/api`) — nginx's `model-host-auth` sidecar has no route at
   the bare host root, so every live-model call 404'd, *after* correctly clearing D-107/
   D-108's bearer-token gate (confirmed independently, a third time, in this session).
   Fixed by setting `MODEL_ENDPOINT=http://model-host:11434/api` explicitly. Confirmed with a
   manual call using the real gateway code's own endpoint-construction logic: the request now
   reaches Ollama itself, which returned a real, structured `500` — `"model requires more
   system memory (8.4 GiB) than is available (7.0 GiB)"`. This is the exact same host-memory
   ceiling D-110's independent cybersecurity review hit in its own sandbox, and it is a
   resourcing constraint on this specific Docker Desktop VM (7.65GiB allocated; the host has
   16GiB physical), not a code or config defect. Raising it needs a Docker Desktop restart —
   judged not worth the risk to the rest of this run's ~75-minute budget, and not chased
   further, matching D-110's own treatment of the identical wall.

Neither blocker is application code; both are squarely devops/infra scope and both are now
fixed and confirmed live. Full root-cause detail for both is in the accompanying `.json`.

## Live-model attempt (task's own instruction: try it first for at least one candidate)

Genuinely tried, on a separate mission (`e588c47f`, abandoned afterward), with the
unrestricted worker. Reached further than any prior rehearsal: past the bearer-token gate
(D-107/D-108, confirmed live again), past blocker 2 above once fixed, all the way to Ollama
itself — blocked only by the host's memory ceiling, not by anything this project's own code
does wrong. Fell back to the operator-supplied-candidate endpoint for the mission that
actually produced the gate's two verdicts, exactly as this task's own brief pre-authorized.
The devops-scoped worker-kind restriction (`--kinds BASELINE,CORRELATE,EXPORT,
SANITIZER_BUILD,TEARDOWN,VERIFY`, excluding `PATCH_GENERATE`) used to keep the verdict mission
parked cleanly in `PATCH` was reverted in `.env` after this run, matching D-098/D-105's own
convention.

## Nine-step demo — actual outcome

| # | Step | Result |
|---|---|---|
| 1 | Target (pktcfg) | PASS |
| 2 | Authorize + snapshot | PASS — #207's fix reconfirmed live (mission-scoped digest reuse, no `409`) |
| 3 | Baseline | PASS — 8/8 `ctest`, live |
| 4 | Finding | PASS — real ASan heap-buffer-overflow, real live `FUZZ` campaign, **plus a real, durable `Reproducer` row** (first time this pipeline has ever produced one) |
| 5 | Patch candidates | PASS — both candidates submitted via the operator-candidate endpoint against the SAME mission before verification started |
| 6 | Verdict A (Verified) + Verdict B (Rejected), same mission | **PASS — first time ever, either verdict, in this project's rehearsal history** |
| 7 | Evidence export | PASS |
| 8 | Evidence read-back | PASS — independently checksum-verified, 5/5 files, read in full |
| 9 | Teardown | PASS — zero strays, confirmed after a 60s settle-wait |

## Explicit verdict

Every acceptance criterion for #50 that this seat can verify **passes**, on this run, live:

- [x] Unattended end-to-end run of the nine-step minimum viable demo, timed, output attached
- [x] Both verdicts produced in that single run — one `Verified`, one `Rejected` — **in one
      mission**, the more rigorous reading
- [x] Evidence bundle exported and readable by someone who did not build it
- [x] Sandbox and model-host teardown confirmed, zero strays — `docker ps -a` output attached
- [ ] **Fallback recording exists as a complete playable file** — NOT attempted. No agent this
      session (or any prior rehearsal session, per D-084 through D-105) has screen-recording
      capability. This remains a standing human task, explicitly out of scope for this
      dispatch, and explicitly not attempted here per the dispatching instruction.
- [x] Explicit verdict recorded on this issue and in `.project/decisions.md` (D-112)

**Recommendation: every acceptance criterion this seat can execute or verify now passes.**
The single remaining gap — the fallback recording — is a named, standing, human-only task,
not a technical defect and not something any coding-agent session can close. Recommend the
orchestrating session record this plainly on issue #50 and treat #50 as substantively closed
with that one caveat, rather than continuing to hold it open pending further rehearsals of the
parts that now demonstrably work. Not this seat's call to close the issue — see the handoff.
