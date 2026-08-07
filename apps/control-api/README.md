# Control API

Django + django-ninja control plane for Brahmadatta AI. Runs under ASGI; nginx fronts
it in every deployed profile (issue #10).

Status at D1: **the contract is frozen, the pipeline is not built.** Every endpoint
except `GET /api/v1/system/health` returns `501 NOT_IMPLEMENTED` with a real error
envelope. The request and response schemas are final — that is what the Command
Center types against while the pipeline lands behind them.

## Layout

```
apps/control-api/
├── config/               # Django project: settings profiles, ASGI, URLs
│   └── settings/         # base · development · finale · test
├── contracts/            # THE FROZEN CONTRACT — no I/O, no Django models
│   ├── enums.py          # mission states, stages, event types, error codes
│   ├── authorization.py  # the authorization record
│   ├── state_machine.py  # legal transitions + the authorization gate
│   ├── verdict.py        # gate matrix -> verdict derivation
│   ├── model_policy.py   # no hosted third-party inference endpoints
│   ├── checks.py         # the above, enforced as Django system checks
│   └── schemas/          # request/response schemas + the event envelope
├── api/                  # HTTP surface: routers, auth, trace ids, error envelope
└── tools/export_openapi.py
```

## Running it

```bash
cd apps/control-api
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env          # then fill it in; .env is gitignored
.venv/bin/python manage.py check
.venv/bin/uvicorn config.asgi:application --host 127.0.0.1 --port 8000
```

* OpenAPI document — <http://127.0.0.1:8000/api/v1/openapi.json>
* Interactive docs — <http://127.0.0.1:8000/api/v1/docs>
* Health — <http://127.0.0.1:8000/api/v1/system/health> (unauthenticated)
* Django admin — <http://127.0.0.1:8000/django-admin/> (development profile only)

Generate a secret and an operator token:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## Profiles

| Profile | `DJANGO_SETTINGS_MODULE` | Admin | Notes |
|---|---|---|---|
| development | `config.settings.development` | on | DEBUG on, local hosts |
| finale | `config.settings.finale` | **forced off** | `CONTROL_API_ADMIN_ENABLED=true` cannot re-enable it; nginx blocks the path as a second layer |
| test | `config.settings.test` | off | in-memory SQLite, no PostgreSQL needed |

## Tests

```bash
.venv/bin/python -m pytest
```

No PostgreSQL required — the suite runs on in-memory SQLite and never touches a
mission table, because there are none yet (schema is the database-engineer's, D2).

## What the schemas enforce structurally

Four product rules are expressed in types rather than in comments. Each has tests
that fail if the property is removed:

| Rule | Where | Test |
|---|---|---|
| A verdict derives only from deterministic gates; model confidence cannot gate anything | `contracts/verdict.py`, `VerificationRecord` | `contracts/tests/test_verdict.py` |
| No stage runs without an active authorization record | `contracts/state_machine.py` | `contracts/tests/test_state_machine.py` |
| No inference endpoint may be a hosted third party | `contracts/model_policy.py`, `contracts/checks.py` | `contracts/tests/test_model_policy.py` |
| Sandbox egress cannot be requested | `SandboxPolicy.network: Literal["deny"]` | `api/tests/test_http_surface.py` |

## Changing the contract

1. Change the schema.
2. `.venv/bin/python tools/export_openapi.py`
3. Regenerate the frontend types (see `packages/schemas/README.md`).
4. Update `docs/03-technical/21-api-specification.md` in the same PR.

`contracts/tests/test_openapi_dump.py` fails if step 2 is skipped, and the Astro
build fails if step 3 is skipped. That is deliberate: a contract document that lies
is worse than none.
