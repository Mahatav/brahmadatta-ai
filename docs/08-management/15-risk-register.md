# Risk Register

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.2 |
| Status | Owners and firing triggers assigned (#62) |
| Owner | See per-row `Owner` column below |
| Last updated | 2026-08-24 |

## Purpose

Track technical, safety, schedule, resource, and competition risks with owners and mitigations.

Every row below has a **firing trigger**: a command, a query, or a grep — never "watch for
X" (see `#62`). At the end of each shift, whoever owns a fired trigger writes it into the
daily handoff with the command output attached; a trigger that fired and was not written
down is treated as one that did not fire. Rows already covered by a day/CI gate
cross-reference it rather than restating it in weaker language. Owners follow the current
agentic-company work split (`.claude/COMPANY.md`) — the pipeline/sandbox/target class of
risk routes to `backend-developer`/`cybersecurity`, the API/UI/evidence-bundle/judge-facing
claim class routes to `devops-engineer`/`qa-engineer`/`cto`, mirroring the original
human-owner split (Raunak: pipeline, sandbox, target; Mahatav: API, UI, evidence bundle,
judge-facing claims) this issue was written against on 2026-08-07, before the team was
staffed as an agentic company. All trigger commands below were executed for real in this
session (see D-145) — none are asserted from a grep/glob check alone.

### The eleven original rows

| # | Risk | Likelihood | Impact | Status | Owner | Firing trigger — verified | Mitigation |
|---:|---|---:|---:|---|---|---|---|
| 1 | Kimi K3 cannot fit available rented cluster | High | High | **Capacity risk RESOLVED-obsolete (D-015 cut the rented cluster entirely).** Residual **claim risk stays ACTIVE**: nothing may re-introduce Kimi K3 into code or judge-facing material. | `cto` | `grep -rn "Kimi" --include='*.py' apps services packages workers adapters` **and** `grep -ril "kimi" docs/10-competition .project/evidence/*/report.md .project/evidence/*/extracted/report.md` — both 0 matches expected. Verified 2026-08-24: both 0 matches, real. | Feasibility test first; reserve capacity; smaller self-hosted fallback for pipeline continuity — superseded by D-015; the only live mitigation now is the two greps never firing. |
| 2 | Adapter tuning exceeds the time/resource envelope | Medium | High | **RETIRED — no owner assigned.** No fine-tuning, LoRA, or adapter-tuning work is in scope (D-015, P2-1). Assigning an owner to watch nothing is worse than recording it as gone; re-open (with an owner) only if a fine-tuning issue is filed against the current plan. | — (none; see Status) | `grep -riE "lora|peft|fine-tun|adapter_config" -r services/model-gateway` — 0 matches expected. Verified 2026-08-24: 0 matches, real. | Tune small model first; treat Kimi adapter as optional — superseded by D-015; not tuning anything. |
| 3 | Target does not build | High | High | ACTIVE | `backend-developer` | `pytest adapters/cpp/tests/test_toolchain.py adapters/cpp/tests/test_pipeline.py` returns non-zero. Verified 2026-08-24: **15 passed**, real run. | Strict baseline validation and prebuilt demo fixture |
| 4 | Fuzzer cannot reach defect | Medium | High | ACTIVE | `backend-developer` | `BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN=1 pytest workers/fuzzing/tests/test_real_campaign.py::test_real_libfuzzer_campaign_finds_the_seeded_heap_overflow -q` returns non-zero. **The env var is required** — without it the test silently SKIPs (opt-in gate, since it builds a real image and runs a real container) rather than proving anything; a bare `pytest ...` invocation is not a valid check of this trigger. Verified 2026-08-24: with the env var set, **1 passed** against a real Docker daemon and a real libFuzzer campaign; without it, confirmed SKIPPED with `HAS_DOCKER=True OPTED_IN=False`. | Harness templates, seeds, dictionaries, static-guided targeting |
| 5 | Patch overfits reproducer | Medium | High | ACTIVE | `qa-engineer` | `pytest apps/control-api/orchestrator/tests/test_verification.py::test_reproducer_eliminated_but_regression_failed_is_rejected -q` returns non-zero. Verified 2026-08-24: **1 passed**, real run. | Full regression, negative cases, static checks, renewed fuzzing |
| 6 | Model changes unrelated files | Medium | High | ACTIVE | `backend-developer` | `pytest apps/control-api/orchestrator/tests/test_patch_policy.py::test_path_allowlist_violation_is_named_before_verification apps/control-api/orchestrator/tests/test_patch_policy.py::test_empty_allowlist_is_not_a_silent_pass -q` returns non-zero. Verified 2026-08-24: **2 passed**, real run. | Path allowlist, diff cap, policy rejection |
| 7 | Sandbox attacks host/control plane | Medium | Critical | ACTIVE — `cybersecurity` holds the veto | `cybersecurity` | `pytest packages/sandbox/tests/test_jail.py::test_path_outside_the_jail_is_refused packages/sandbox/tests/test_jail.py::test_symlink_escape_is_refused -q` returns non-zero. Verified 2026-08-24: **2 passed**, real run. | Unprivileged disposable isolation, egress deny, limits, separate credentials |
| 8 | Source leaks through logs/provider | Low/Med | Critical | ACTIVE | `cybersecurity` | Two channels, both must stay clean (the original issue's `tests/security/test_single_inference_client.py` no longer exists in this tree — moved/superseded by the finale egress audit, D-089): (a) network channel — `bash infrastructure/scripts/finale-egress-evidence.sh` prints `finale egress evidence: PASS`; (b) bundle-content channel — `pytest apps/control-api/orchestrator/tests/test_evidence_bundle.py::test_poisoned_detail_is_redacted_by_assemble_evidence_bundle_itself -q`. Verified 2026-08-24, both real: (a) live PASS — control-api container reached 0/4 external targets (`api.openai.com`, `api.anthropic.com`, cloud metadata IP, `1.1.1.1`) while postgres stayed reachable as a positive control; (b) **1 passed**. **Prerequisite found during verification**: a fresh clone/worktree needs `bash infrastructure/scripts/gen-postgres-cert.sh` run once before (a) — the finale `db` image build fails on a missing TLS cert otherwise. Not documented anywhere before this entry; flagged for `docs/06-operations/73-rehearsal-checklist.md`. | Self-host models, encryption, redaction, private networking |
| 9 | GPU lease remains active unexpectedly | Medium | High | **ACTIVE — restated for D-015, not obsolete.** Under D-015 there is no rented GPU; the same shape of risk now applies to the **model-host and sandbox lease**: a terminal mission must release every resource it started. | `backend-developer` | `pytest apps/control-api/orchestrator/tests/test_teardown.py::test_docker_sandbox_reaper_reports_a_failed_removal_as_not_released apps/control-api/orchestrator/tests/test_teardown.py::test_terminal_states_are_teardown_boundaries -q` returns non-zero. Verified 2026-08-24: **2 passed**, real run. | Wall-clock and lease caps, alerts, one heavy run, auto-stop |
| 10 | Cloud is incorrectly called air-gapped | Medium | High | ACTIVE — reworded per D-089's successor concern (the finale host genuinely has no internet at demo time; the claim must not outrun what is actually verified) | `devops-engineer` | Three checks: `bash infrastructure/scripts/finale-egress-evidence.sh` PASS; `bash -n infrastructure/scripts/finale-up.sh` exits 0; `grep -rilE "air.?gapped\|cannot reach the internet\|fully offline" docs/10-competition .project/evidence/*/report.md .project/evidence/*/extracted/report.md` — 0 matches expected (judge-facing wording guard, restored from the original issue text). Verified 2026-08-24, all real: egress evidence live PASS (see row 8); `bash -n` exit 0; grep 0 matches. | Use accurate cloud-isolated wording; per D-089, the finale-profile network closure is now empirically verified, not merely claimed — the grep still guards against overclaiming it in the wrong scope (e.g. the whole system, not just the finale profile) |
| 11 | Competition target differs | High | High | ACTIVE — technical half only; see Mitigation | `backend-developer` | `pytest adapters/cpp/tests/test_detect.py -q` returns non-zero. Verified 2026-08-24: **5 passed**, real run. This is a proxy for "our adapter's own coverage boundary is what we think it is" — it cannot detect an organizer announcement of a different target/language/build system, which is an external event with **no code trigger** (the original issue is explicit: "no technical mitigation exists; the recorded fallback is the mitigation"). | Adapter interface, offline assets, diagnostics, known demo; fallback is the recorded submission material (#49), not a code path |

### Three rows added by the CTO technical review (`05-cto-technical-review.md` §7) — present in the full issue #62 text, missing from an earlier partial draft of this table

| # | Risk | Likelihood | Impact | Status | Owner | Firing trigger — verified | Mitigation |
|---:|---|---:|---:|---|---|---|---|
| 12 | The CPU-served small model cannot produce a policy-passing, compiling patch | Medium | High | ACTIVE | `backend-developer` | `pytest apps/control-api/orchestrator/tests/test_patch_generate_executor.py::test_exhausting_every_attempt_walks_from_patch_to_human_review_through_the_real_dispatcher apps/control-api/orchestrator/tests/test_patch_generate_executor.py::test_policy_rejected_diffs_are_recorded_but_do_not_count_as_accepted apps/control-api/orchestrator/tests/test_patch_generate_executor.py::test_every_rung_failing_records_one_generation_failure_and_moves_on -q` returns non-zero — a regression guard on the attempt-counting/threshold mechanism. Verified 2026-08-24: **3 passed**, real run. The original numeric threshold ("fewer than 3 of 10 policy-passing and compiling candidates") is a **manual benchmark result** (#61, BD-001-M), not a CI-enforced number — still open per this doc's own "Replace estimated performance targets with benchmark results." **Separately found, not fixed here** (out of this doc's scope, flagged for `backend-developer`/model-gateway owner): `test_live_backend_built_by_this_module_gets_401_from_the_sidecar_without_the_fix` in the same file currently FAILS — it asserts `urllib.error.HTTPError` but the live code path now wraps that in `gateway.errors.LiveGenerationError`, a stale assertion, not a regression this session introduced or touched. | Tune small model first; #37/#38 replay-mode proving the loop before the model arrives |
| 13 | SSE wedges the control API under ASGI — thread-pool exhaustion with no error in any log | Medium | High | ACTIVE — day-1 spike risk now has a standing regression test | `devops-engineer` | `bash infrastructure/scripts/smoke-sse.sh` — must print `SSE smoke: PASS` for all 4 cases, including the 2 negative controls that inject a violation and require the stream to break. Verified 2026-08-24: **real PASS**, all 4 cases, against the committed nginx config (case 2 confirms `proxy_buffering on` really does stall — proves case 1 can fail; case 4 confirms `proxy_read_timeout 5s` really does drop the idle connection — proves case 3 can fail). | `proxy_buffering off` on the SSE location (already committed, `infrastructure/compose/nginx/includes/sse.conf`); this script is the CI-gated regression test for it (`.github/workflows/ci.yml`, "SSE survives the proxy") |
| 14 | A mission reaches terminal `VERIFIED` with no verification record | Medium | Critical | ACTIVE | `backend-developer` | `pytest apps/control-api/contracts/tests/test_state_machine.py::test_no_verdict_state_without_a_verification_record apps/control-api/orchestrator/tests/test_verdict_completeness.py::test_a_verdict_state_is_refused_against_an_empty_database -q` returns non-zero. Verified 2026-08-24: **4 passed** (3 parametrized + 1), real run. This is the current name for the test the original issue cited as `test_cannot_enter_verified_without_a_verified_record` (renamed since 2026-08-07; confirmed via `.project/decisions.md`). | Verdict states are refused without a matching verification record in the same transaction; `cybersecurity` reviews any PR touching this path |

---

## Fixed MVP competition decisions

- **Product name:** Brahmadatta AI.
- **Product type:** an authorized, defensive Cyber-Reasoning System for the AI Kavach competition MVP.
- **Architecture:** three evidence-driven tiers: fast deterministic triage, destructive sandbox testing with lightweight patching, and heavy repository-level reasoning only when escalation is justified.
- **Interface:** a dense futuristic armor-command-center dashboard with a central mission core, live telemetry, drill-down panels, and operator controls. The visual language is original and does not copy third-party logos or branded interface assets.
- **Primary workflow:** authorize → ingest → baseline → analyze → correlate → stress-test → patch → verify → export evidence.
- **Compute:** CPU-first processing with self-hosted models (`codellama:7b-instruct` via a local Ollama container, D-121). **Rented GPU was cut entirely (D-015, 2026-08-06)** — this line previously said "on rented GPU infrastructure," which is the pre-D-015 plan this section had not been updated to reflect; corrected here per `CLAUDE.md`. Repository content is not sent to an external inference API.
- **MVP target:** C/C++ repositories first; Python support is optional.
- **Verification rule:** a patch is never accepted on model confidence alone. The original reproducer, regression tests, static checks, and renewed fuzzing determine the verdict.
- **Safety boundary:** authorized repositories and isolated environments only; no public-target scanning, no exploit deployment, and no automatic production merge.

## Open decisions / next review

- ~~Assign the final three-person team roles.~~ Superseded — the project is staffed as a
  dynamic agentic company (`.claude/COMPANY.md`), not a fixed three-person team.
- ~~Lock the rented GPU provider and tested model-serving recipe.~~ Superseded — D-015 cut
  rented GPU entirely; the committed recipe is CPU-only `codellama:7b-instruct` via Ollama
  (D-121).
- Replace estimated performance targets with benchmark results. Still open for row 12's
  "fewer than 3 of 10" patch-generation threshold specifically — see row 12 above.
- Confirm the final competition demo repository and fallback recording.
