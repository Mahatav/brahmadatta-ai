# MVP Scope Document

## In scope

- Single-team, single-operator competition deployment.
- Brahmadatta Command Center desktop dashboard.
- One persistent orchestrator, event stream, and job queue.
- C/C++ adapter supporting CMake/Make and CTest.
- Baseline build and regression testing.
- Semgrep and compiler/static checks.
- Sanitizer builds and AFL++ or libFuzzer.
- Crash capture, deduplication, minimization, and regression-test conversion when practical.
- Git summary and automated `git bisect`.
- Small self-hosted code model on one rented GPU.
- Limited heavy-model escalation on a short-lived rented GPU cluster.
- Patch policy, clean verification, evidence database, Markdown/JSON report, and safe teardown.
- Presentation mode and a pre-recorded fallback demonstration.

## Out of scope

- Public multi-tenant SaaS.
- Billing, subscriptions, commercial launch, or customer support operations.
- Legal-policy documents.
- Public-network scanning or unauthorized systems.
- Automatic merge or production deployment.
- Full pretraining of a frontier model from scratch.
- Every language, binary-only targets, distributed global fuzzing, or formal mathematical proof.
- Mobile editing experience.

## Required demo scenarios

1. **Memory-safety defect:** fuzzing produces a sanitizer-confirmed crash and minimized reproducer.
2. **Git regression:** automated bisect identifies the first bad commit.
3. **Verified repair:** a minimal patch removes the reproducer and preserves regression behavior.
4. **Rejected repair:** a tempting crash-only patch fails a regression gate and is rejected.
5. **Resource control:** heavy-model GPUs start only on escalation and are torn down at mission completion.

---

## Fixed MVP competition decisions

- **Product name:** Brahmadatta AI.
- **Product type:** an authorized, defensive Cyber-Reasoning System for the AI Kavach competition MVP.
- **Architecture:** three evidence-driven tiers: fast deterministic triage, destructive sandbox testing with lightweight patching, and heavy repository-level reasoning only when escalation is justified.
- **Interface:** a dense futuristic armor-command-center dashboard with a central mission core, live telemetry, drill-down panels, and operator controls. The visual language is original and does not copy third-party logos or branded interface assets.
- **Primary workflow:** authorize → ingest → baseline → analyze → correlate → stress-test → patch → verify → export evidence.
- **Compute:** CPU-first processing with self-hosted models on rented GPU infrastructure. Repository content is not sent to an external inference API.
- **MVP target:** C/C++ repositories first; Python support is optional.
- **Verification rule:** a patch is never accepted on model confidence alone. The original reproducer, regression tests, static checks, and renewed fuzzing determine the verdict.
- **Safety boundary:** authorized repositories and isolated environments only; no public-target scanning, no exploit deployment, and no automatic production merge.

## Open decisions / next review

- Assign the final three-person team roles.
- Lock the rented GPU provider and tested model-serving recipe.
- Replace estimated performance targets with benchmark results.
- Confirm the final competition demo repository and fallback recording.
