# Product Requirements Document (PRD)

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.2 Competition MVP |
| Status | Working draft |
| Owner | TBD |
| Last updated | 2026-08-06 |

## Product summary

Brahmadatta AI combines existing tests, static analysis, Git history, coverage-guided fuzzing, sanitizer evidence, self-hosted code models, and deterministic verification in one autonomous defensive workflow operated through the Brahmadatta Command Center.

## Primary users

- Competition operator running the live demonstration.
- Security engineer reviewing findings and evidence.
- Developer evaluating the generated patch.
- Jury member observing methodology, efficiency, precision, and scalability.

## Functional requirements

### Mission intake
- Accept an authorized Git archive or approved repository URL.
- Create and display an immutable snapshot hash.
- Record build, test, adapter, network, and resource policies.
- Block execution until authorization and preflight validation pass.

### Tier 1 — deterministic triage
- Build and test the unchanged repository to establish a baseline.
- Run Semgrep/compiler checks and normalize findings.
- Summarize dependencies and Git history.
- Run automated `git bisect` when a deterministic pass/fail command exists.

### Tier 2 — stress test and lightweight repair
- Run targets in disposable, unprivileged, resource-limited sandboxes.
- Use sanitizers and AFL++ or libFuzzer to produce concrete failures.
- Minimize a stable reproducer when possible.
- Route localized confirmed issues to a small self-hosted code model.

### Tier 3 — heavy reasoning
- Escalate only confirmed, complex, cross-file cases.
- Use a self-hosted heavy model on rented dedicated GPU infrastructure.
- Send only approved repository context through an internal model gateway.
- Enforce a hard time limit and guaranteed GPU teardown.

### Patching and verification
- Require a constrained unified diff.
- Block restricted files, generated artifacts, broad refactors, and excessive changed lines.
- Rebuild from a clean worktree.
- Re-run the original reproducer, regression suite, static checks, and renewed fuzzing.
- Return Verified, Rejected, Human Review Required, Failed, or Cancelled.

### Command-center UI
- Show the full mission state through the central Brahmadatta Core.
- Display live repository, static, Git, fuzzing, patch, verification, alert, and GPU telemetry.
- Stream updates without page refresh.
- Provide drill-down evidence drawers and a presentation mode.
- Provide safe pause, cancellation, and emergency GPU teardown.
- Never imply that model confidence equals verification.

### Evidence export
- Export Markdown and JSON reports.
- Include hashes, configurations, timelines, evidence, diffs, test results, model/tool versions, and resource usage.

## Non-functional requirements

- CPU-first operation; GPU use is explicit, measured, and capped.
- No external inference API for repository content.
- Network denied by default inside target sandboxes.
- Workflow is resumable, deterministic where possible, and fully auditable.
- Dashboard remains usable at 1440 × 900 and degrades to tabbed rails below 1280 px.
- Critical UI updates appear within two seconds of backend state changes.

## MVP launch gate

- One controlled vulnerability is autonomously discovered, reproduced, patched, and verified.
- One incorrect patch is automatically rejected.
- One Git regression is isolated through bisect.
- The live command center presents the workflow without manual database or terminal intervention.
- Rented GPU resources are visibly released after the run.
- The complete demonstration fits the competition time limit and tested resource envelope.

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
