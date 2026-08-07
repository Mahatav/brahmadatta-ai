# Decision Log

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.1 |
| Status | Working draft |
| Owner | TBD |
| Last updated | 2026-08-06 |

## Purpose

Define and operationalize decision log for the Brahmadatta AI competition MVP on rented GPUs.

| Date | Decision | Reason | Revisit trigger |
|---|---|---|---|
| 2026-08-06 | Use three tiers | Efficiency and trust | Routing benchmarks fail |
| 2026-08-06 | Rent GPUs | Avoid hardware purchase | Capacity/availability failure |
| 2026-08-06 | No external inference API | Source confidentiality | Not for MVP |
| 2026-08-06 | C/C++ first | Strong fuzz/sanitizer proof | Challenge language differs |
| 2026-08-06 | Verify every patch | Model output is not proof | Never |
| 2026-08-06 | Cloud-isolated, not air-gapped | Accurate claim | On-prem hardware available |

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
