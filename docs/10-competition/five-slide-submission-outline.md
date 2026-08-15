# Five-Slide Submission Outline

| Field | Value |
|---|---|
| Status | Final claim-audited draft |
| Last claim audit | `.project/evidence/d9-submission-claim-audit-2026-08-15.json` |
| Scope rule | Everything below must trace to code, evidence, or an explicit "not measured / cut" disclosure. |

## Slide 1 — Introduction, ideation, and brief description

**Title:** Brahmadatta AI — Autonomous Armor for Software

- Current tools report vulnerabilities but leave reproduction, root-cause analysis, patching, and proof to humans.
- Brahmadatta AI is a three-tier autonomous Cyber-Reasoning System.
- It gathers deterministic evidence first, uses local self-hosted AI only after algorithmic gates have narrowed the problem, and keeps every accepted verdict tied to executable proof.
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
- Control plane: Django API, persistent mission state, PostgreSQL, job queue, event streaming.
- Tier 1: CTest, Semgrep, compiler checks, Git bisect.
- Tier 2: AFL++/libFuzzer, sanitizers, and local CodeLlama-style patch candidate generation when deterministic evidence exists.
- Tier 3: designed escalation path only. It is not presented as live in the CPU/local-model MVP cut.
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
- Model-host lifecycle is leased, bounded, and torn down; rented GPU operation is a cut item unless a future rehearsal proves it.

## Slide 5 — Final deliverables and proof of concept

- Working end-to-end prototype.
- Controlled vulnerability autonomously confirmed.
- Minimized reproducer and first bad commit.
- Minimal patch with before/after diff.
- Passing compile, reproducer, regression, static, and renewed-fuzz gates.
- Incorrect patch automatically rejected.
- Exported evidence report.
- Visible local model-host lifecycle and teardown confirmation.

## Claim audit for submission

| Claim family | Submission wording | Evidence status |
|---|---|---|
| Product identity | Authorized defensive Cyber-Reasoning System for AI Kavach | Repository scope, runbooks, and authorization-first UI |
| Deterministic first | Baseline, static/git, fuzz, reproduce, verify before AI acceptance | D5/D6 evidence bundle and benchmark case set |
| Local AI only | Repository content is not sent to an external inference API | D5 model-serving evidence, D8 security checklist, finale egress checklist |
| Metrics | Targets are not presented as measured benchmark results | D8 benchmark case set and performance requirements |
| Rented GPU | Not claimed as live in this submission | P0 cut and D8 benchmark status |
| Final run | Not claimed complete until #50 passes | Finale readiness audit |
| Timed rehearsals | Not claimed complete until #57 records real timings | Finale readiness audit |

---

## Fixed MVP competition decisions

- **Product name:** Brahmadatta AI.
- **Product type:** an authorized, defensive Cyber-Reasoning System for the AI Kavach competition MVP.
- **Architecture:** three evidence-driven tiers: fast deterministic triage, destructive sandbox testing with lightweight patching, and heavy repository-level reasoning only when escalation is justified.
- **Interface:** a dense futuristic armor-command-center dashboard with a central mission core, live telemetry, drill-down panels, and operator controls. The visual language is original and does not copy third-party logos or branded interface assets.
- **Primary workflow:** authorize → ingest → baseline → analyze → correlate → stress-test → patch → verify → export evidence.
- **Compute:** CPU-first processing with self-hosted local model serving in the MVP cut. Repository content is not sent to an external inference API.
- **MVP target:** C/C++ repositories first; Python support is optional.
- **Verification rule:** a patch is never accepted on model confidence alone. The original reproducer, regression tests, static checks, and renewed fuzzing determine the verdict.
- **Safety boundary:** authorized repositories and isolated environments only; no public-target scanning, no exploit deployment, and no automatic production merge.

## Open decisions / next review

- Assign the final three-person team roles.
- Run and record the D7/D8 finale rehearsal gates on the final machine.
- Confirm the final competition demo repository and fallback recording.
