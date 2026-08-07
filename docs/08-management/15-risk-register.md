# Risk Register

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.1 |
| Status | Working draft |
| Owner | TBD |
| Last updated | 2026-08-06 |

## Purpose

Track technical, safety, schedule, resource, and competition risks with owners and mitigations.

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Kimi K3 cannot fit available rented cluster | High | High | Feasibility test first; reserve capacity; smaller self-hosted fallback for pipeline continuity |
| Adapter tuning exceeds the time/resource envelope | Medium | High | Tune small model first; treat Kimi adapter as optional |
| Target does not build | High | High | Strict baseline validation and prebuilt demo fixture |
| Fuzzer cannot reach defect | Medium | High | Harness templates, seeds, dictionaries, static-guided targeting |
| Patch overfits reproducer | Medium | High | Full regression, negative cases, static checks, renewed fuzzing |
| Model changes unrelated files | Medium | High | Path allowlist, diff cap, policy rejection |
| Sandbox attacks host/control plane | Medium | Critical | Unprivileged disposable isolation, egress deny, limits, separate credentials |
| Source leaks through logs/provider | Low/Med | Critical | Self-host models, encryption, redaction, private networking |
| GPU lease remains active unexpectedly | Medium | High | Wall-clock and lease caps, alerts, one heavy run, auto-stop |
| Cloud is incorrectly called air-gapped | Medium | High | Use accurate cloud-isolated wording |
| Competition target differs | High | High | Adapter interface, offline assets, diagnostics, known demo |

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
