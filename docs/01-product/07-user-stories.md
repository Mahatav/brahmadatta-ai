# User Stories

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.1 |
| Status | Working draft |
| Owner | TBD |
| Last updated | 2026-08-06 |

## Purpose

Define and operationalize user stories for the Brahmadatta AI competition MVP on rented GPUs.

## Intake
- As an operator, I must confirm authorization before a run starts.
- As a reviewer, I can see the immutable snapshot hash and policy used.

## Discovery
- As a security engineer, I see baseline failures separately from new evidence.
- As a developer, I see deduplicated static findings, a minimized reproducer, and any first bad commit.

## Patching
- As an operator, I see why Tier 2 or Tier 3 was selected.
- As a developer, I receive a constrained unified diff limited to approved files.

## Verification
- As a reviewer, I compare before/after reproducer behavior and regression results.
- As an operator, I receive a clear verified, rejected, or needs-review verdict.

## Operations
- As an administrator, I cap GPU time/lease duration and safely cancel a run.

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
