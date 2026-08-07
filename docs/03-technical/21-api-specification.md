# API Specification

## Mission API

- `POST /api/v1/missions` — create a mission draft.
- `POST /api/v1/missions/{id}/snapshot` — upload or import an immutable repository snapshot.
- `POST /api/v1/missions/{id}/preflight` — validate authorization, commands, adapter, and limits.
- `POST /api/v1/missions/{id}/start` — start the autonomous workflow.
- `GET /api/v1/missions/{id}` — current state, phase, progress, and summary metrics.
- `GET /api/v1/missions/{id}/events` — ordered event stream through SSE.
- `POST /api/v1/missions/{id}/pause` — pause after the current safe boundary.
- `POST /api/v1/missions/{id}/cancel` — cancel and clean resources.

## Evidence API

- `GET /api/v1/missions/{id}/findings`
- `GET /api/v1/missions/{id}/findings/{finding_id}`
- `GET /api/v1/missions/{id}/git-bisect`
- `GET /api/v1/missions/{id}/fuzzing`
- `GET /api/v1/missions/{id}/patches`
- `GET /api/v1/missions/{id}/patches/{patch_id}/verification`
- `GET /api/v1/missions/{id}/evidence`
- `POST /api/v1/missions/{id}/export`

## Infrastructure API

- `GET /api/v1/system/health`
- `GET /api/v1/system/workers`
- `GET /api/v1/system/gpu-leases`
- `POST /api/v1/system/gpu-leases/{id}/teardown` — operator-confirmed emergency teardown.

## Event schema

```json
{
  "mission_id": "uuid",
  "sequence": 142,
  "timestamp": "ISO-8601",
  "phase": "STRESS_TEST",
  "status": "RUNNING",
  "severity": "INFO",
  "message": "Minimized sanitizer reproducer created",
  "evidence_refs": ["artifact://..."],
  "metrics": {"coverage_percent": 78.6}
}
```

## Error codes

`INVALID_AUTHORIZATION`, `UNSUPPORTED_REPOSITORY`, `PREFLIGHT_FAILED`, `BASELINE_BUILD_FAILED`, `BASELINE_FLAKY`, `SANDBOX_POLICY_VIOLATION`, `NO_REPRODUCIBLE_FINDING`, `PATCH_POLICY_REJECTED`, `MODEL_CAPACITY_UNAVAILABLE`, `GPU_LIMIT_EXCEEDED`, `VERIFICATION_FAILED`, `SAFE_CANCELLATION_IN_PROGRESS`.

## API rules

- All mutations are idempotent or carry an idempotency key.
- Every response includes a trace ID.
- Raw secrets and unrestricted source archives are never returned to the browser.
- The UI uses sanitized evidence endpoints and signed short-lived artifact links.

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
