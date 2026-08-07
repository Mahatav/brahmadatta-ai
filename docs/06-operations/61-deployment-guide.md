# Deployment Guide

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.1 |
| Status | Working draft |
| Owner | TBD |
| Last updated | 2026-08-06 |

## Purpose

Define and operationalize deployment guide for the Brahmadatta AI competition MVP on rented GPUs.

1. Select signed/tagged release and verify checksums.
2. Confirm provider account, capacity, quotas, region, private networking, and encrypted storage.
3. Deploy DB, queue, API, orchestrator, artifacts, and dashboard.
4. Deploy restricted CPU workers and verify no cloud metadata/egress.
5. Start small-model GPU and register its private endpoint.
6. Start Kimi K3 cluster only in scheduled windows using a validated recipe.
7. Run clean, Tier 2, cancellation, export, and access-control smoke tests.
8. After use, stop models, terminate GPUs, delete temporary disks/snapshots, revoke temporary credentials, and confirm teardown and final resource ledger.

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
