# Infrastructure and Hosting Plan

## Deployment shape

### Always-on control plane
- FastAPI control API and orchestrator.
- PostgreSQL metadata database.
- Redis or database-backed job queue.
- Encrypted artifact store.
- Command-center frontend.
- CPU workers for Tier 1 analysis and report generation.

### Disposable execution plane
- Unprivileged target sandboxes.
- Fuzzing and sanitizer workers.
- Temporary worktrees and minimized reproducer storage.
- Network denied by default.

### Rented GPU plane
- One single-GPU instance for the lightweight code model during active development and demonstrations.
- A short-lived multi-GPU cluster for heavy-model escalation tests only.
- Private networking between the control plane and model gateway.
- Temporary credentials, encrypted attached storage, and automatic idle shutdown.

## Required controls

- Infrastructure-as-code or repeatable scripts.
- Region and provider selected before model artifacts are uploaded.
- Provider metadata endpoint blocked from target sandboxes.
- Hard GPU lease timer and idle timeout.
- Model endpoint accessible only through the internal gateway.
- Teardown job runs on complete, rejected, failed, and cancelled terminal states.
- Dashboard visibly reports lease state, heartbeat, memory, utilization, and teardown confirmation.

## Competition deployment wording

The MVP is **cloud-isolated on rented infrastructure**, not physically air-gapped. The architecture is designed so that the same components can later be packaged for an on-premises air-gapped environment.

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
