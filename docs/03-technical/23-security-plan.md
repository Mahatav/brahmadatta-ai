# Security Plan

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.1 |
| Status | Working draft |
| Owner | TBD |
| Last updated | 2026-08-06 |

## Purpose

Protect the control plane, rented infrastructure, model services, repository data, and target sandboxes.

## Objectives
Prevent target code from reaching the host, control plane, model service, credentials, or public networks; prevent source leakage; constrain models; preserve evidence integrity.

## Controls
- Unprivileged disposable sandbox, no privileged mode, host mounts, Docker socket, or cloud metadata.
- Outbound network denied by default.
- CPU, RAM, disk, process, file-size, syscall, and wall-clock limits.
- Private service networks and least-privilege service identities.
- Signed/pinned images and verified model artifacts.
- Models receive allowlisted redacted context and return structured diffs only.
- Patch policy blocks restricted paths, excessive changes, binary files, and configuration/credential edits.
- Input snapshot, reproducer, diff, configuration, and report are hashed.
- Provider credentials stay outside workers and model prompts.

## Threats explicitly tested
Sandbox escape attempt, cloud-metadata access, prompt injection in source comments, model request to change policy, unauthorized repository submission, secret/log leakage, and orphaned rented GPU resources.

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
