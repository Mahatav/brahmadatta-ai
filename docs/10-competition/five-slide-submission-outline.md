# Five-Slide Submission Outline

## Slide 1 — Introduction, ideation, and brief description

**Title:** Brahmadatta AI — Autonomous Armor for Software

- Current tools report vulnerabilities but leave reproduction, root-cause analysis, patching, and proof to humans.
- Brahmadatta AI is a three-tier autonomous Cyber-Reasoning System.
- It gathers deterministic evidence first, uses lightweight AI for localized repairs, and escalates only confirmed complex cases to a heavy self-hosted model.
- Goal: find one real defect, patch it, and prove the fix without breaking existing behavior.

## Slide 2 — Detailed methodology

`Authorize → Snapshot → Baseline → Static/Git → Fuzz/Reproduce → Correlate/Bisect → Patch → Clean Verify → Evidence`

Emphasize:
- Original crash or failing test becomes the proof target.
- Git bisect narrows the root cause.
- Failed patches loop back or are rejected.
- Verification is deterministic and independent of model claims.

## Slide 3 — Technology stack and architecture

- Brahmadatta Command Center: React + TypeScript futuristic mission-control UI.
- Control plane: FastAPI, persistent state machine, PostgreSQL, job queue, event streaming.
- Tier 1: CTest, Semgrep, compiler checks, Git bisect.
- Tier 2: AFL++/libFuzzer, sanitizers, small self-hosted code model.
- Tier 3: bounded heavy-model escalation on rented dedicated GPUs.
- Isolation: rootless containers, network denied, encrypted artifacts.

Use the three-tier architecture diagram and dashboard layout.

## Slide 4 — Salient features and novelty

- Evidence-first compute routing.
- Git-aware root-cause localization.
- Concrete fuzzing reproducer before repair.
- Minimal-diff patch policy.
- Deterministic verification matrix.
- No external inference API for repository content.
- Live Brahmadatta Core makes every stage, decision, and resource visible.
- GPU escalation is temporary, measured, and automatically torn down.

## Slide 5 — Final deliverables and proof of concept

- Working end-to-end prototype.
- Controlled vulnerability autonomously confirmed.
- Minimized reproducer and first bad commit.
- Minimal patch with before/after diff.
- Passing compile, reproducer, regression, static, and renewed-fuzz gates.
- Incorrect patch automatically rejected.
- Exported evidence report.
- Visible rented-GPU utilization and teardown confirmation.

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
