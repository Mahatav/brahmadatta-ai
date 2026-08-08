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
MODEL_SERVICE_NAMES=small-model.internal
MODEL_GATEWAY_MODE=live
MODEL_TRANSCRIPT_ROOT=services/model-gateway/transcripts
TIER3_BASE_URL=http://kimi-k3.internal:8000/v1
TIER3_MODEL_NAME=kimi-k3
RUN_MAX_USD=<approved-cap>
TIER3_MAX_MINUTES=20
GPU_IDLE_SHUTDOWN_MINUTES=10
ARTIFACT_RETENTION_DAYS=14
```
Never commit `.env`. Provider credentials are injected through protected secrets and never passed to target sandboxes.

### `MODEL_SERVICE_NAMES` — read this before debugging a refused endpoint

Note the example above: `SMALL_MODEL_BASE_URL=http://small-model.internal:8000/v1` needs
`MODEL_SERVICE_NAMES=small-model.internal` beside it. Without the declaration the endpoint
is **refused at startup**, and that refusal is the rule working.

Under D-051 the endpoint policy permits, with no declaration at all:

- loopback — `127.0.0.0/8`, `::1`, `localhost`, `host.docker.internal`
- RFC 1918 — `10/8`, `172.16/12`, `192.168/16`
- IPv6 unique-local — `fc00::/7`, less `fd00:ec2::/32`

Everything else is an explicit declaration in `MODEL_SERVICE_NAMES`, comma-separated. That
includes compose service names (`small-model`) and anything ending `.internal`, `.local`,
`.svc` or `.test`.

Those four suffixes used to pass on the suffix alone and no longer do, because nobody owns
those namespaces — `evil.internal`, `sneaky.svc`, `redirector.local` and
`api.openai.com.evil.test` all passed the previous check. **Declaration grants trust, not
the suffix.** The reserved documentation ranges (`192.0.2.0/24`, `198.51.100.0/24`,
`203.0.113.0/24`) are refused for the same reason in the other direction: not globally
routable and inside our trust boundary are different properties, and only the second one is
the question being asked.

A declared name is still checked. If it resolves to an address outside the boundary the
call is refused — `services/model-gateway/gateway/endpoint_policy.py`, and the 60-case
table behind it is `infrastructure/scripts/testing/endpoint-policy-bypass-table.py`.

### `MODEL_GATEWAY_MODE` has no default

`live` calls the self-hosted model; `replay` serves a recorded transcript (#82). Unset is a
startup error rather than "live", because the choice decides whether the system later says
"model-generated" or "model output recorded &lt;date&gt;, replayed" about its own output,
and D-049 rules that the system does not make a provenance claim by staying silent.

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
