# Performance Requirements

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.1 |
| Status | Working draft |
| Owner | TBD |
| Last updated | 2026-08-06 |

## Purpose

Define and operationalize performance requirements for the Brahmadatta AI competition MVP on rented GPUs.

| Stage | Target | Hard cap |
|---|---:|---:|
| Snapshot/validation | 2m | 5m |
| Baseline build/test | 8m | 15m |
| Static triage | 3m | 10m |
| Initial fuzzing | 20m | 45m |
| Reproducer minimization | 5m | 15m |
| Git bisect | 10m | 25m |
| Small-model candidate | 2m | 5m |
| Kimi K3 candidate | 10m | 20m |
| Final verification | 15m | 30m |
| Evidence export | 30s | 2m |

MVP concurrency: one heavy request and two CPU/sandbox jobs. Record wall time, CPU/GPU seconds, peak memory, storage, context/output tokens, and GPU lease duration.

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
