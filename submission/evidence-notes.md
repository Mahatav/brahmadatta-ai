# Brahmadatta AI — AI Kavach submission: claim → repository evidence

Every substantive technical claim in the five slides, traced to a file, a decision record, or a
recorded evidence run in this repository. Compiled 2026-08-30 against `main` @ `0616e15`.

Scope rule (from `docs/10-competition/five-slide-submission-outline.md`): where a claim is a target,
a design intent, or a cut, it is marked as such on the slide — never presented as done.

---

## Slide 1 — Introduction, ideation, brief description

| Claim on slide | Evidence |
|---|---|
| Authorised, defensive Cyber-Reasoning System for AI Kavach | `CLAUDE.md` "What this is"; `docs/00-overview/00-product-identity.md`; `README.md` |
| Finds a memory-safety defect with its own fuzzing, patches with a self-hosted model, deterministic tools deliver the verdict | `docs/09-company/01-vision-and-p0-cut.md` §1, §3; `.project/evidence/d7-gate-50-live-run-2026-08-20-run6.md` |
| Three evidence-gated tiers | `CLAUDE.md` "Non-negotiable product rules"; `docs/09-company/06-architecture-spec.md` §1; `docs/10-competition/five-slide-submission-outline.md` slide 3 |
| The pipeline visibly *rejects* a plausible wrong patch | `.project/evidence/d6-verdict-loop-report.md`; `.project/evidence/d7-gate-50-live-run-2026-08-20-run6-evidence-bundle/extracted/report.md` (candidate `75383f61…` → REJECTED); `demo/repositories/pktcfg/README.md` "benchmark candidate patches" |
| Authorised repositories only; write-once authorization + server-verified snapshot hash | `docs/09-company/06-architecture-spec.md` §2.1 (`AUTHORIZED`, `SNAPSHOTTED` states), §5.1 (`Authorization` write-once, `Snapshot` "digest recomputed server-side and matched") |
| No public-target scanning, no exploit deployment, no automatic production merge | `CLAUDE.md` "Safety boundary"; `docs/09-company/01-vision-and-p0-cut.md` "Constraints reaffirmed" |
| Sandbox runs `--network none`; repo content never leaves for a hosted API — structurally enforced | `README.md` "Safety boundary"; `docs/09-company/06-architecture-spec.md` §4.1 (six layers: `internal: true` compose network, single-inference-client AST test, Django system check, typed gateway entrypoint, provenance record, live egress test); `packages/sandbox/container.py`; `.env.example`; D-015 (rented GPU cut) |

## Slide 2 — Detailed methodology

| Claim | Evidence |
|---|---|
| Nine-step pipeline: authorize → ingest → baseline → analyze → correlate → stress-test → patch → verify → export evidence | `CLAUDE.md` "Mission workflow"; `docs/09-company/01-vision-and-p0-cut.md` §3; `docs/09-company/06-architecture-spec.md` §2 |
| Unattended after a single operator `start` (five operator actions: create → authorize → snapshot → preflight → start) | `docs/09-company/06-architecture-spec.md` §2.4; `.project/evidence/d7-gate-50-live-run-2026-08-20-run6.md` ("unattended after each operator action", 47.75 s orchestrator-driven) |
| Baseline: configure → build → CTest, pass/fail counts recorded as the regression denominator (pktcfg 8/8) | `workers/baseline/run.py`, `workers/baseline/dispatch.py`; `adapters/cpp/`; run 6 bundle `report.md` "tests=8/8 passed"; `demo/repositories/pktcfg/tests/` (8 CTest cases) |
| Analyze: Semgrep (offline vendored C/C++ ruleset) + compiler-warning parsing → structured findings; git-history summary | Semgrep: `adapters/semgrep/` (ruleset `brahmadatta-c-cpp-2026-08-24`, `rules/c/dangerous-functions.yaml`, 5 rules), `workers/static_analysis/`, D-155 (`JobKind.ANALYZE` replaces the TRIAGE stub), commit `ad509a5`. Compiler warnings: `adapters/cpp/compiler_diagnostics.py`, D-153, commit `38de8a0` (`-Wall -Wextra -Wshadow -Wconversion`, parsed during BASELINE). Git history: `workers/git_analysis/`, `apps/command-center/src/components/GitHistoryBisectPanel.tsx`, D-158, commit `2f2f1e6` |
| Stress-test: ASan/UBSan + libFuzzer in a locked-down container; sanitizer-confirmed heap-buffer-overflow with a stack trace; crash dedup | `adapters/cpp/sanitizer.py`, `adapters/cpp/fuzzing.py`, `workers/fuzzing/`; `packages/sandbox/container.py`; crash dedup: D-150, commit `e8df7c6`; run 6 bundle `report.md` "engine=libFuzzer … crashes_found=1 … sanitizers=address" |
| Minimise to a reproducer that replays 5/5 from a clean build; persisted durably | `.project/evidence/d5-reproducer-gate.json` (5/5 replays); `workers/replay/`; D-106/D-109 (durable `Reproducer` row — `FUZZ` copies real crash bytes out of the sandbox); run 6 headline ("a real, durable `Reproducer` row for that finding") |
| Patch: self-hosted CodeLlama 7B gets crash report + localised source; patch policy (single file, allowlist, changed-line cap) must pass before compile | Model: `CLAUDE.md` (codellama:7b-instruct via local Ollama, D-121); `services/model-gateway/`, `apps/control-api/orchestrator/patch_generate_executor.py`. Policy: `docs/09-company/06-architecture-spec.md` §4.2 point 9; `demo/repositories/pktcfg/patches/candidate-p-policy-rejected-out-of-scope.patch` |
| Verify — every policy-passing candidate, identical gate sequence; verifier is provenance-blind | `apps/control-api/orchestrator/verification.py`; `docs/09-company/06-architecture-spec.md` §2.3 (fan-out), §4.2 point 7 (`run_verification` signature takes no `PatchCandidate`), test `test_verifier_is_provenance_blind` |
| Five gates: COMPILE · REPRODUCER_ELIMINATED · REGRESSION_PRESERVED · STATIC_DELTA · RENEWED_FUZZING | `apps/control-api/contracts/verdict.py` (`GateMatrix` fixed arity); run 6 bundle `gate-matrix.json` / `report.md` |
| Verdict derived from the gate matrix, never from confidence | `docs/09-company/06-architecture-spec.md` §4.2 (`derive_verdict(gates)` one argument; `GateStatus` four-valued enum, no numeric field; `extra="forbid"`; `VerificationRecord` re-derives and refuses); `.project/evidence/d6-verdict-loop-gate.json` |
| One correct patch → VERIFIED; one plausible crash-only patch → passes compile, eliminates the crash, fails a regression test (six assertions in the tab-expansion case) → REJECTED | `.project/evidence/d6-verdict-loop-report.md`; run 6 bundle `report.md` (`280d8894…` VERIFIED 3/5, `75383f61…` REJECTED, `REGRESSION_PRESERVED: FAIL`, "1 of 8 tests failed"); `demo/repositories/pktcfg/README.md` (`test_tab_expansion.c` labelled `asymmetry`, "six of its fourteen checks fail") |
| An overfit patch that fools every static gate is caught by renewed fuzzing | `demo/repositories/pktcfg/patches/candidate-d-overfit-single-input-fix.patch` + `corpus/seed-literal-tab.bin`; D-152 (`#40` renewed-fuzzing gate built), commit `ade1f2c`; `apps/control-api/orchestrator/verification.py::_run_renewed_fuzz` |
| Export: report.md / report.json / manifest.json / gate-matrix.json / tool-versions.json, content-addressed artifacts, sha256 manifest; teardown confirmed, zero strays | `apps/control-api/orchestrator/` EXPORT executor; `docs/09-company/06-architecture-spec.md` §5.3; run 6 bundle `.project/evidence/d7-gate-50-live-run-2026-08-20-run6-evidence-bundle/` (5 files, sha256-verified); `d7-gate-50-live-run-2026-08-20-run6-docker-ps-a-after-teardown.txt` |
| Nothing escalates a tier on a guess | `CLAUDE.md`; `docs/09-company/01-vision-and-p0-cut.md` §1; `docs/10-competition/five-slide-submission-outline.md` slide 4 |

Honesty note carried on the slide's footnote intent: in the recorded unattended run (run 6) **both**
candidates were operator-supplied via the `POST` operator-candidate endpoint (`test_operator_candidate_submission.py`,
D-090), labelled `OPERATOR_SUPPLIED` in the bundle. The self-hosted model's own generation reliability
is evidenced separately (10/10, below). This matches the P0-cut honesty constraint (`docs/09-company/01-vision-and-p0-cut.md`
§3, D-008): the gates are real either way; provenance is never inflated.

## Slide 3 — Technology stack / architecture / flow

| Element | Evidence |
|---|---|
| Command Center: Astro 7 + React 19 islands, one shared SSE stream, SVG Core | `apps/command-center/package.json` (`astro ^7.2.2`, `react 19.1.1`, `@nanostores/react`); `apps/command-center/src/components/` (`BrahmadattaCore.tsx`, `MissionCommandCenter.tsx`, `StageTimeline.tsx`, `VerdictPanel.tsx`, `FindingsRail.tsx`, `CandidateCompareOverlay.tsx`, `ResourceLedger.tsx`, `AnalysisRail.tsx`, `FuzzingReportPanel.tsx`, `GitHistoryBisectPanel.tsx`); `apps/command-center/src/lib/events/`; D-113…D-119 (visual rebuild), commit `4704d7e` |
| Ingress: nginx, TLS, `proxy_buffering off` on SSE | `infrastructure/compose/nginx/`; `docs/06-operations/71-ingress-and-proxy-contract.md`; `docs/06-operations/72-sse-buffering-measurements.md`; CI job `ingress` in `.github/workflows/ci.yml` |
| Control API: Django 5.2 · django-ninja 1.6 · Pydantic 2 · uvicorn ASGI · generated OpenAPI in CI | `apps/control-api/requirements.txt` (`Django==5.2.17`, `django-ninja==1.6.2`, `pydantic==2.13.4`, `uvicorn[standard]==0.52.1`); `apps/control-api/api/`; CI job `openapi-contract` |
| Persistence: PostgreSQL 16 · Django ORM + migrations · content-addressed artifact store (sha256, mode 0600) | `apps/control-api/missions/` (models + migrations); `.github/workflows/ci.yml` (`postgres:16-alpine` service); `docs/09-company/06-architecture-spec.md` §5.1–§5.2 |
| Orchestration: explicit 18-state persistent mission state machine · Postgres-backed job queue (`SELECT … FOR UPDATE SKIP LOCKED`), no broker | `apps/control-api/contracts/state_machine.py`; `apps/control-api/orchestrator/queue.py`; `docs/09-company/06-architecture-spec.md` §2.1 ("Eighteen. Thirteen live, five terminal"), §3.1; D-122 (`run_orchestrator` a supervised compose service), commit `fb8efed` |
| Worker: single process, JobKind dispatch (BASELINE · ANALYZE · SANITIZER_BUILD · FUZZ · MINIMIZE · CORRELATE · PATCH_GENERATE · VERIFY · EXPORT · TEARDOWN); never transitions state | `apps/control-api/orchestrator/` executors; `workers/`; `docs/09-company/06-architecture-spec.md` §1.1 table, §3.1 |
| Isolation: rootless Docker Compose · subprocess `Jail` + `ContainerJail` (`--network none`, `--cap-drop ALL`, non-root, read-only rootfs, no docker socket) · live egress-denial test | `packages/sandbox/` (`container.py`, `README.md`, `tests/test_container_jail.py` — 28 tests, real Docker); D-024 (container-runtime substitution, eight binding conditions); D-162/D-163 (`ContainerJail` wired into BASELINE and VERIFY, `#181`/SEC-57), commit `79caac6`; `infrastructure/scripts/egress-test.sh`, `finale-egress-evidence.sh` |
| Model: self-hosted CodeLlama 7B-instruct (Ollama), loopback/internal-only, bearer-token sidecar; gateway is the only inference client | `CLAUDE.md` (D-121); `services/model-gateway/gateway/`; D-075/SEC-57 (`model-host-auth` bearer sidecar), D-107/D-108 (bearer-token threading); `.project/evidence/d5-model-serving.json` (loopback-only, policy-enforced); `tests/architecture/` single-inference-client test |
| Verification: 5-gate matrix · `derive_verdict(matrix)` — no confidence argument | `apps/control-api/contracts/verdict.py`; `docs/09-company/06-architecture-spec.md` §4.2 |
| "15 deployable units → 4 application processes" | `docs/09-company/06-architecture-spec.md` §1.2 ("Net: 15 deployable units in the pack → 4 application processes here") |
| Finale/roadmap — live-model patch inside the full run (dev-VM RAM-bound today) | `.project/evidence/d7-gate-50-live-run-2026-08-20-run6.md` §"Two new blockers" ("model requires more system memory (8.4 GiB) than is available (7.0 GiB)", "resourcing constraint on this specific Docker Desktop VM … not a code or config defect") |
| Finale/roadmap — Semgrep + renewed-fuzzing gates in a full live mission (built + reviewed 24–29 Aug, not yet in a full rehearsal) | D-152, D-155, D-168; commits `ade1f2c`, `ad509a5`, `f326022`. Run 6 (2026-08-20) predates these; its bundle logs `STATIC_DELTA`/`RENEWED_FUZZING` as `NOT_RUN` with a disclosed reason |
| Finale/roadmap — ContainerJail default for every stage, every deployment (wired 29 Aug, rolling out) | D-162/D-163, commit `79caac6`; `README.md` "Safety boundary" ("a real, deliberate opt-in still being rolled out to every deployment, not the default everywhere yet") |
| Tier 3 — heavy repository reasoning: designed path only, unnamed; rented GPU cut entirely | `docs/10-competition/five-slide-submission-outline.md` slide 3; D-015 (rented GPU cut, 2026-08-06); `docs/09-company/01-vision-and-p0-cut.md` §6.4 (no heavy model named) |

## Slide 4 — Salient features & novelty

| Claim | Evidence |
|---|---|
| Evidence-gated escalation — nothing reaches the model until deterministic tiers produce a confirmed, minimised finding | `docs/09-company/06-architecture-spec.md` §2.2 (state order: CORRELATE precedes PATCH); `docs/09-company/01-vision-and-p0-cut.md` §1 |
| No confidence path — `derive_verdict()` one argument; a VERIFIED record over a failing gate cannot be constructed | `apps/control-api/contracts/verdict.py`; `docs/09-company/06-architecture-spec.md` §4.2 points 1–4; `tests/security/test_no_score_on_verdict_path.py` (arch spec §4.2 point 8) |
| Provenance-blind verifier | `docs/09-company/06-architecture-spec.md` §4.2 point 7; `test_verifier_is_provenance_blind` |
| Overfit caught by renewed fuzzing of the patched build | `demo/repositories/pktcfg/patches/candidate-d-overfit-single-input-fix.patch`; D-152; `demo/repositories/pktcfg/README.md` "The overfit fix (#40)" |
| Disclosure as a feature — an unrun gate is as loud as a failure; the verdict carries its denominator | `docs/09-company/06-architecture-spec.md` §5.4 ("VERIFIED — 3 of 5 gates ran"); `docs/09-company/04-design-system.md` §2.1/§5 (`--bd-state-not-run`, "NOT RUN" rendering rule, DS-03); run 6 bundle `report.md` verdict lines |
| Repository content never reaches a hosted API — enforced three ways (internal-only network, single-inference-client source test, boot-time system check) | `docs/09-company/06-architecture-spec.md` §4.1 L1/L2/L3; `apps/control-api/contracts/` model-policy check; `tests/architecture/` |
| Rootless isolated execution; egress denial proven by a live DNS+TCP test | `packages/sandbox/tests/test_container_jail.py`; `infrastructure/scripts/egress-test.sh`; CI job `ingress` "only nginx has egress (C4)" |
| Operator-visible Command Center reads the same stream that produces the evidence bundle | `apps/command-center/src/lib/events/`; `docs/09-company/04-design-system.md` §2.6 (no fabricated telemetry — "every progress indicator steps only when an event arrives on the stream") |
| CPU-first; rented GPU cut entirely; process-level model-host lease with confirmed teardown | D-015; `.project/evidence/d5-model-host-lifecycle.json`; run 6 teardown evidence |
| 4 application processes vs 15; Postgres SKIP LOCKED instead of a broker; no Redis, no S3, offline Semgrep ruleset | `docs/09-company/06-architecture-spec.md` §1.2; `adapters/semgrep/rules/` (vendored, offline) |
| ~48 s full pipeline, unattended | `.project/evidence/d7-gate-50-live-run-2026-08-20-run6.md` ("Mission wall-clock time, orchestrator-driven pipeline only … **47.75 seconds**, unattended") |
| ~0.3 s fuzz to seeded defect | run 6 bundle `report.md` ("mode=LIVE_CAMPAIGN … runtime=0.3s executions=4400 crashes_found=1"). Earlier: `.project/evidence/d5-live-fuzzing.json` (1,878 executions, under half a second) |

## Slide 5 — Final deliverables

| Claim | Evidence |
|---|---|
| Full nine-step pipeline end-to-end in 47.75 s wall-clock, live, unattended, through the real HTTP API | `.project/evidence/d7-gate-50-live-run-2026-08-20-run6.md` + `.json`; D-112 |
| Self-discovered, ASan-confirmed heap-buffer-overflow in an authorised C target, with a durable deterministic reproducer | run 6 headline; `demo/repositories/pktcfg/README.md` (seeded defect: two-pass sizing/writing mismatch on a literal tab byte, CWE-787/CWE-131) |
| Two verdicts from one mission — one VERIFIED (first end-to-end in project history), one REJECTED on a real regression failure, same gate matrix | run 6 bundle `report.md` (mission `d6897640…`, `280d8894…` VERIFIED, `75383f61…` REJECTED); `.project/state.md` "first `VERIFIED` in this project's history" (D-112) |
| Exported evidence bundle — snapshot hash, crash report, minimised input, both diffs, both gate matrices, both verdicts — sha256-manifested and independently read back | `.project/evidence/d7-gate-50-live-run-2026-08-20-run6-evidence-bundle/` (`manifest.json`, `report.md`, `report.json`, `gate-matrix.json`, `tool-versions.json`); run 6 md §"Nine-step demo" step 8 "PASS — independently checksum-verified, 5/5 files, read in full" |
| Confirmed teardown, zero stray containers | `.project/evidence/d7-gate-50-live-run-2026-08-20-run6-docker-ps-a-after-teardown.txt` |
| Self-hosted CodeLlama 7B: 10/10 generation attempts returned schema- and policy-valid candidates | `.project/evidence/d6-model-generation-attempts.json`; `.project/evidence/d6-verdict-loop-report.md` ("10 of 10 live CodeLlama attempts returned schema-valid patch candidates") |
| Command Center rebuilt to the approved spec | D-113…D-119, commit `4704d7e`; independently QA-verified against a live mission (D-114/D-116/D-118) |
| ≈900+ automated tests; CI gated on a real PostgreSQL; egress denial proven live | D-168 (2026-08-29: "822 total … 798 passed" in `apps/control-api`; "121 passed" adapters/workers; "73 passed" `packages/sandbox`); `.github/workflows/ci.yml` (`postgres:16-alpine` service, BUG-022 note); CI job `ingress` |
| Expected competition output: a reproducible C/C++ pipeline → confirmed finding, minimal patch, deterministic verdict, portable offline-auditable evidence bundle | `docs/10-competition/source-and-feasibility-notes.md` "Feasibility position"; `docs/09-company/01-vision-and-p0-cut.md` §3 |
| Finale: live-model patch in the full run (finale hardware clears the dev-VM memory ceiling) | run 6 md §"Two new blockers" (8.4 GiB vs 7.0 GiB available on the Docker Desktop VM; D-110 hit the identical wall) |
| Finale: Semgrep + renewed-fuzzing gates inside a full live mission | D-152, D-155 (built 2026-08-24, after run 6) |
| Finale: ContainerJail default for every stage, every deployment | D-162/D-163 (`ContainerJail` in BASELINE/VERIFY, 2026-08-27/29); `README.md` rollout note |
| Finale: three timed rehearsals with failure injection (GPU-unavailable, target won't build, stage hangs) | `#57` (open); `docs/09-company/01-vision-and-p0-cut.md` §7; `docs/10-competition/36-hour-finale-runbook.md`; `.project/state.md` "next is the three `#57` timed rehearsals … failure injection: GPU unavailable, target fails to build, a stage hangs" |
| Finale: a real open-source C target with a known historical CVE, alongside the purpose-built one | `docs/09-company/01-vision-and-p0-cut.md` §5.4 option C; fuzzer already generalised beyond `pktcfg` in dogfooding against LAVA-M base64, Magma libpng, stb_image (D-167, commit `f326022`) |
| Finale: human-recorded fallback demonstration | `.project/evidence/fallback-demo-d6.html` + `fallback-demo-d6-manifest.json` (hash-verified D6 recording exists); run 6 md acceptance criterion — "**Fallback recording exists as a complete playable file** — NOT attempted … a standing human-only task" |
| Finale-criteria tie-in (performance / speed / precision / functionality / scalability) | `docs/10-competition/source-and-feasibility-notes.md` "Final evaluation emphasizes performance, speed, precision, functionality, and scalability"; scalability — `SKIP LOCKED` queue (`orchestrator/queue.py`), stateless restartable processes (arch spec §3.3), adapter generalised beyond the demo target (D-167) |

---

## Things deliberately NOT claimed (and why)

- **No hosted-LLM / rented-GPU capability.** D-015 cut rented GPU entirely (cost, external dependency,
  schedule risk); it is not reopened. Tier 3 is presented as a designed escalation path only, with no
  model named.
- **The full unattended run with live-model patch generation** has not happened — the recorded run 6
  used operator-supplied candidates because the model exceeds the dev VM's RAM. Slides 3 and 5 state
  this as a finale item, not a done capability.
- **`git bisect`** is built and tested (`workers/git_analysis/`, D-149) but is an operator-triggered
  capability, deliberately not part of the automatic mission pipeline (D-151), and meaningfully
  invokable today only against the seeded `pktcfg` history fixture. It is not presented as part of the
  nine-step methodology.
- **Success-metric numbers** (precision %, patch-success rate, escalation %) are not quoted — there is
  no benchmark case set with a denominator (`docs/09-company/01-vision-and-p0-cut.md` §6.1;
  `.project/evidence/d8-benchmark-case-set.md`). Only measured quantities appear: 47.75 s pipeline,
  0.3 s / 4,400-execution fuzz to the seeded defect, 5/5 reproducer replays, 10/10 valid generations,
  8/8 baseline tests, 1 of 8 regression tests failing the bad patch, ~798 + 121 + 73 passing tests.
