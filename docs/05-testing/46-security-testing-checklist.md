# Security Testing Checklist

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.1 |
| Status | D8 run recorded |
| Owner | Security reviewer |
| Last updated | 2026-08-14 |

## Purpose

Define and operationalize security testing checklist for the Brahmadatta AI competition MVP on rented GPUs.

Run record: `.project/evidence/d8-security-checklist-2026-08-14.json`.

| Checklist item | 2026-08-14 status | Evidence |
|---|---|---|
| Authorization and object-level access checks pass | Pass | Full control API pytest |
| Unprivileged sandbox cannot access host/container socket/cloud metadata | Pass | Sandbox tests; Docker-dependent runtime checks passed where available |
| Target egress and resource limits are enforced | Pass with not-run item | `infrastructure/scripts/egress-test.sh` passed; finale in-container probe not run because `.env`/`DATABASE_URL` are absent |
| Commands are allowlisted and injection-safe | Pass | Control API/orchestrator policy tests |
| Logs/reports redact secrets and bounded source | Pass | Command Center render-safety check |
| Models have no provider, DB, storage, or deployment credentials | Pass | Secret scan found only an intentional dummy fixture token |
| Source prompt injection cannot change policy | Pass | Model endpoint and patch policy tests |
| Diff policy blocks restricted/excessive changes | Pass | Patch policy tests |
| Artifact links are short-lived and role-checked | Pass | Evidence endpoint tests |
| Images/dependencies/model artifacts are pinned and verified | Pass | Compose topology, benchmark artifact, Python audit, JS audit |
| Cancellation releases processes, disks, and GPUs | Pass | Teardown and model-host lifecycle tests |
| Evidence hashes verify | Pass | JSON evidence validation |

## D8 Required Follow-Up

The rehearsal operator must still run `infrastructure/scripts/finale-egress-evidence.sh` from a
checkout with `.env` populated and paste the output into the finale runbook. This checklist
records that it was not run in this local pass.

## Approved Evidence-Bundle Wording

Judge-facing wording is **"hash-manifested, tamper-evident against the manifest supplied with
the bundle"**. Do not describe the bundle as signed or tamper-proof.

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
