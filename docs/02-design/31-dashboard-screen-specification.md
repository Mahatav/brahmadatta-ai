# Dashboard Screen Specification

## Screen 1 — Mission Setup

Purpose: configure one authorized repository run.

Required controls:
- Repository archive or approved repository URL.
- Authorization confirmation.
- Immutable snapshot preview.
- Language/build/test adapter.
- Time, CPU, memory, storage, and GPU limits.
- Network policy, denied by default.
- Heavy-model escalation toggle and maximum lease time.
- Preflight validation and Start Mission actions.

Exit condition: the snapshot, commands, policy, and resource ceilings validate successfully.

## Screen 2 — Live Command Center

Purpose: monitor the autonomous workflow and intervene safely.

Primary elements:
- Central Brahmadatta Core with phase progress.
- Repository, static, fuzzing, patch, test, Git, alert, and GPU panels.
- Live event stream through server-sent events or WebSocket.
- Mission controls: pause after current stage, cancel safely, emergency GPU teardown.
- Click any panel to open a detailed evidence drawer.

## Screen 3 — Finding Detail

Sections:
- Severity, confidence source, location, analyzer, and deduplication group.
- Sanitizer trace or concrete failing test.
- Minimized reproducer.
- Related code slice and dependency graph.
- Suspected introducing commit and Git diff.
- Routing explanation and next stage.

## Screen 4 — Patch Review

Sections:
- Unified diff with changed-line count and restricted-file warnings.
- Model tier and exact context used.
- Patch rationale separated from evidence.
- Compile result, reproducer result, regression result, static delta, and fuzz delta.
- Verdict: verified, rejected, or human review required.
- No merge-to-production control in the MVP.

## Screen 5 — Evidence Report

Sections:
- Repository snapshot and configuration.
- Chronological mission timeline.
- Confirmed finding and reproducer.
- Git history and root-cause evidence.
- Proposed patch.
- Before/after verification matrix.
- Tool/model versions and prompts/schema hashes.
- CPU/GPU usage and teardown confirmation.
- Export to Markdown and JSON.

## Screen 6 — System and GPU Health

Sections:
- CPU worker pool.
- Sandboxes and active resource limits.
- Small-model server health.
- Heavy-model rented cluster status.
- GPU memory, utilization, queue, lease timer, and last heartbeat.
- One-click safe teardown with confirmation.

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
