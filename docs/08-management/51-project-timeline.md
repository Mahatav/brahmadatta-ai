# Project Timeline

| Week | Focus | Exit output |
|---|---|---|
| 1 | Freeze scope, Brahmadatta brand, architecture, UI system, and demo repositories | Approved P0 scope and screen map |
| 2 | Mission intake, state machine, event stream, database, and sandbox baseline | Live mission setup and baseline status in UI |
| 3 | Static evidence, Git analysis, and dashboard analysis rail | Normalized findings and bisect demo |
| 4 | Sanitizers, fuzzing, minimization, and live telemetry panels | Stable controlled reproducer in UI |
| 5 | Lightweight model, patch policy, diff view, and rejection gates | Tier 2 accepted and rejected examples |
| 6 | Heavy rented-GPU integration and teardown automation | Private escalation run and visible teardown |
| 7 | Evidence report, presentation mode, security and performance tests | Demo-quality release candidate |
| 8 | Full rehearsals, five-slide submission, fallback assets, and code freeze | Competition-ready package |

## Critical path

State machine → controlled reproducer → patch policy → clean verification → live dashboard → full rehearsal.

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
