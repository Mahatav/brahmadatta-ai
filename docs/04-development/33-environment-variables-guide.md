# Environment Variables Guide

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.1 |
| Status | Working draft |
| Owner | TBD |
| Last updated | 2026-08-06 |

## Purpose

Define and operationalize environment variables guide for the Brahmadatta AI competition MVP on rented GPUs.

```dotenv
APP_ENV=development
APP_SECRET_KEY=<secret>
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
ARTIFACT_STORE_URL=s3://...
SANDBOX_RUNTIME=podman
SANDBOX_NETWORK=deny
SANDBOX_CPU_LIMIT=4
SANDBOX_MEMORY_MB=8192
SANDBOX_MAX_SECONDS=5400
SMALL_MODEL_BASE_URL=http://small-model.internal:8000/v1
TIER3_BASE_URL=http://kimi-k3.internal:8000/v1
TIER3_MODEL_NAME=kimi-k3
RUN_MAX_USD=<approved-cap>
TIER3_MAX_MINUTES=20
GPU_IDLE_SHUTDOWN_MINUTES=10
ARTIFACT_RETENTION_DAYS=14
```
Never commit `.env`. Provider credentials are injected through protected secrets and never passed to target sandboxes.

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
