# Authentication and Authorization Plan

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.1 |
| Status | Working draft |
| Owner | TBD |
| Last updated | 2026-08-06 |

## Purpose

Define and operationalize authentication and authorization plan for the Brahmadatta AI competition MVP on rented GPUs.

| Role | Permissions |
|---|---|
| Operator | Create authorized projects, submit snapshots, start/cancel own runs, view sanitized results |
| Reviewer | View assigned source snippets, patches, and complete evidence |
| Administrator | Manage users, policies, quotas, model endpoints, workers, and retention |

Use short secure sessions or bearer tokens, MFA for administrators where available, and separate service credentials. Every artifact request checks project membership and role. Target sandboxes receive only one-time job credentials and never receive database, model, storage-listing, or provider credentials. Audit sign-in, authorization acceptance, run start/cancel, sensitive artifact access, role changes, policy changes, and export.

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
