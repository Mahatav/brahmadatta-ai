# Development Setup Guide

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 1.0 |
| Status | Active |
| Owner | devops |
| Last updated | 2026-08-07 |

## Purpose

Get a working development environment from a clean clone.

> **Corrected 2026-08-07 (issue #11).** The previous version of this page did not work.
> It called `alembic` (the project uses Django ORM migrations, not Alembic), `make`
> targets (there is no Makefile), and a compose service named `object-store` (it does not
> exist — D-015 removed the rented infrastructure that needed it). Every command below was
> run from a clean clone on 2026-08-07; where something is not yet runnable, it says so
> instead of pretending.

## Prerequisites

| Tool | Version | Check |
|---|---|---|
| Docker Engine + Compose v2 | 25+ / v2.24+ | `docker version && docker compose version` |
| Python | 3.12 | `python3.12 --version` |
| Node | 22 | `node --version` |
| Git | any recent | `git --version` |

Everything else runs in a container. Nothing here reaches an external inference API, and
nothing should be pointed at a public system.

## Setup

```bash
git clone git@github.com:Mahatav/brahmadatta-ai.git
cd brahmadatta-ai

# 1. Environment. .env is gitignored; never commit one.
cp .env.example .env
#    Then replace every REPLACE_ME value. Generate secrets with:
#    python3 -c "import secrets; print(secrets.token_urlsafe(64))"

# 2. Self-signed TLS for the local ingress (gitignored; regenerate any time).
infrastructure/scripts/gen-dev-certs.sh

# 3. Bring the stack up. This preflights first and refuses to start rather than
#    letting Docker create root-owned directories for app folders that do not exist yet.
infrastructure/scripts/dev-up.sh
```

Once up:

| | URL |
|---|---|
| Command Center | `https://localhost:8443/` (self-signed — accept the warning once) |
| API | `https://localhost:8443/api/v1/` |
| OpenAPI | `https://localhost:8443/api/v1/openapi.json` |
| Event stream | `https://localhost:8443/api/v1/missions/<id>/events` |
| Django admin | `https://localhost:8443/admin/` — development only; 404 in the finale profile |
| nginx liveness | `http://localhost:8080/healthz` |

**Reach the API through `https://localhost:8443`, not the container port.** The API
publishes no host port on purpose: server-sent events behave differently through the proxy
than against the ASGI server directly, and testing the direct path tests nothing. See
[`docs/06-operations/71-ingress-and-proxy-contract.md`](../06-operations/71-ingress-and-proxy-contract.md).

### Status on 2026-08-07

`infrastructure/scripts/dev-up.sh` with no arguments starts nginx, control-api, PostgreSQL
and Redis, and this was run end to end. The Astro dev server does **not** start, because
`apps/command-center/` does not exist yet — the script names that as a blocker rather than
failing obscurely. Until the frontend lands:

```bash
infrastructure/scripts/dev-up.sh db redis control-api
```

The queue worker is opt-in until a queue framework is chosen (D-018):

```bash
DEV_UP_WORKER=1 infrastructure/scripts/dev-up.sh
```

## Checks

There is no Makefile. Run the same things CI runs:

```bash
# Python — lint, format, types
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
ruff format --check .
ruff check .
mypy --config-file mypy.ini apps infrastructure/scripts

# Python — tests
pip install -r apps/control-api/requirements.txt
cd apps/control-api && pytest -q && cd -

# Frontend — lint and types
npm ci
npm run lint
npm run typecheck        # skips loudly until apps/command-center exists

# Infrastructure
docker compose -f infrastructure/compose/docker-compose.yml config --quiet
infrastructure/scripts/nginx-validate.sh     # nginx -t, both profiles
infrastructure/scripts/smoke-sse.sh          # SSE survives the proxy
infrastructure/scripts/egress-test.sh        # only nginx can reach off-host (C4)
infrastructure/scripts/finale-egress-evidence.sh  # the same, proven from inside the container
infrastructure/scripts/openapi-contract-check.sh
shellcheck infrastructure/scripts/*.sh
actionlint
```

**CI runs two of these: `pytest` and the OpenAPI dump check.** The CTO cut D1's CI scope on
the grounds that lint and type-check matrices are cost with no gate behind them this week.
The configuration is all still here and all still green — running the block above before you
push is what keeps it that way, and it takes about a minute.

`ruff check --fix` and `ruff format` resolve most findings automatically.

## Database migrations

Django ORM migrations, not Alembic:

```bash
docker compose -f infrastructure/compose/docker-compose.yml exec control-api \
  python manage.py migrate
```

## Teardown

```bash
docker compose -f infrastructure/compose/docker-compose.yml down       # keep data
docker compose -f infrastructure/compose/docker-compose.yml down -v    # DELETE the database
```

## Troubleshooting

| Symptom | Cause |
|---|---|
| SSE works with `curl` against :8000 but the dashboard shows nothing | You are bypassing nginx. That is the whole trap — see `includes/sse.conf` |
| `blocked: .env is missing` | `cp .env.example .env` |
| Browser refuses the certificate | Expected. Self-signed. Accept once, or regenerate with `gen-dev-certs.sh --force` |
| nginx will not start | `infrastructure/scripts/nginx-validate.sh` shows the parse error |
| Django builds `http://` URLs | `USE_X_FORWARDED_HOST` / `SECURE_PROXY_SSL_HEADER` are not set — section 3 of the ingress contract |
| A port is already bound | Only 8080 and 8443 are published, on 127.0.0.1 |
| A container cannot reach the internet | Working as designed (C4). Only nginx has a route off the host. If `npm ci` needs to run, that is the `command-center-deps` service's job |
| `MODEL_ENDPOINT points at 'small-model' and it is a single label that is not declared` | Working as designed (D-051). Loopback and the private ranges need no declaration; a *name* does. Add it to `MODEL_SERVICE_NAMES` in `.env` — see the model-routing block in `.env.example` |
| `... carries a private suffix, but nobody owns those namespaces` | Same rule. `.internal`, `.local`, `.svc` and `.test` no longer pass on the suffix alone, because `evil.internal` and `api.openai.com.evil.test` used to. Declare the exact host in `MODEL_SERVICE_NAMES` |
| `MODEL_GATEWAY_MODE is not set. It has no default` | Deliberate. `live` and `replay` make different claims about where a patch came from, so the gateway does not choose for you (D-049). Set one |

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
