# Success Metrics

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.1 |
| Status | Working draft |
| Owner | TBD |
| Last updated | 2026-08-06 |

## Purpose

Define and operationalize success metrics for the Brahmadatta AI competition MVP. Rows below
are targets until the benchmark case set in `.project/evidence/d8-benchmark-case-set.json`
has a measured run attached.

| Metric | MVP target | Publication status |
|---|---:|---|
| Confirmed-finding precision on chosen benchmarks | ≥80% | Target — not measured |
| Reproducer elimination for accepted patches | 100% | Enumerated on BD-001-A; not a percentage benchmark |
| Regression preservation for accepted patches | 100% | Enumerated on BD-001-A; not a percentage benchmark |
| Verified patch rate on selected solvable cases | ≥50% | Target — not measured |
| Median time to first confirmed finding | ≤30 min | Target — not measured |
| Median confirmation-to-verdict time | ≤45 min | Target — not measured |
| Tier 3 escalation rate | ≤30% | Not applicable to the CPU/local-model MVP cut |
| Complete evidence reports | 100% | Target — not measured |
| Unauthorized target network calls | 0 | Target — guarded by topology tests; full benchmark pending |
| Unreleased GPU idle time after run | <10 min | Not applicable to the CPU/local-model MVP cut |

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
