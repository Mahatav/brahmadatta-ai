# Database Schema

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.1 |
| Status | Working draft |
| Owner | TBD |
| Last updated | 2026-08-06 |

## Purpose

Define and operationalize database schema for the Brahmadatta AI competition MVP on rented GPUs.

## Core tables
- `users(id, email, role, created_at)`
- `projects(id, owner_id, name, authorization_statement, language_adapter)`
- `repository_snapshots(id, project_id, commit_sha, archive_sha256, artifact_uri)`
- `runs(id, project_id, snapshot_id, state, policy_json, final_status, timestamps)`
- `findings(id, run_id, tool, category, severity, file_path, fingerprint, reproducible, evidence_json)`
- `reproducers(id, finding_id, artifact_uri, test_command, minimized, expected_failure_json)`
- `patch_candidates(id, finding_id, tier, model_name, diff_uri, files_changed, lines_changed, policy_status)`
- `verification_runs(id, patch_id, reproducer_pass, regression_json, static_json, fuzz_json, accepted, rejection_reason)`
- `resource_usage(id, run_id, component, cpu_seconds, gpu_seconds, peak_memory_mb, estimated_cost_usd)`
- `audit_events(id, run_id, actor_id, event_type, sanitized_details, created_at)`

Store structured summaries in the database and large source/log/diff artifacts in encrypted object storage.

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
