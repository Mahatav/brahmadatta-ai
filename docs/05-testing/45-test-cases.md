# Test Cases

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.1 |
| Status | Working draft |
| Owner | TBD |
| Last updated | 2026-08-06 |

## Purpose

Define and operationalize test cases for the Brahmadatta AI competition MVP on rented GPUs.

- **TC-001:** run blocked without authorization.
- **TC-002:** baseline failures are distinguished from new regressions.
- **TC-003:** patch touching restricted path is rejected before execution.
- **TC-004:** accepted patch removes the controlled reproducer failure.
- **TC-005:** crash-removing patch is rejected when functional tests regress.
- **TC-006:** localized defect routes to Tier 2 first.
- **TC-007:** Kimi request cancels at lease limit and cleanup runs.
- **TC-008:** target outbound connection is blocked and logged.
- **TC-009:** prompt injection in source cannot alter tool permissions.
- **TC-010:** modified evidence artifact fails hash verification.

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
