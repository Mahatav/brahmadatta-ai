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
├── missions/             # Django models + migrations (#14)
├── orchestrator/         # the only writer of Mission.state (#12)
│   ├── transitions.py    # one transaction per transition, under the row lock
│   ├── candidates.py     # patch/verification writes + the D-046 candidate freeze
│   ├── repository.py     # persisted rows -> frozen contract schemas
│   └── events.py         # gap-free per-mission sequence allocation
└── tools/export_openapi.py
```

`contracts/` has no Django dependency and never will — it is imported by the OpenAPI
exporter, which must run without a database. `orchestrator/` is where the contract
guards are *called from*, and for two of them that call site is the enforcement rather
than a convenience. See `contracts/state_machine.py`'s module docstring.

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

No PostgreSQL required — the suite runs on SQLite. The `missions/` and
`orchestrator/` tests do write real rows and run real migrations.

`SELECT … FOR UPDATE` is a no-op on SQLite, so the tests demonstrate that the code
takes the lock and that the guards hold; they do **not** demonstrate behaviour under
two concurrent writers. That needs a PostgreSQL integration job and is not run here —
see the PR body and QA's §12.

Migrations, from empty:

```bash
DATABASE_URL=sqlite:///local.sqlite3 .venv/bin/python manage.py migrate
```

## What the schemas enforce structurally

Product rules expressed in types and in transaction scope rather than in comments.
Each row names the test that fails if the property is removed — a property is described
as enforced here only when a named test demonstrates it:

| Rule | Where | Test |
|---|---|---|
| A verdict derives only from deterministic gates; model confidence cannot gate anything | `contracts/verdict.py`, `VerificationRecord` | `contracts/tests/test_verdict.py` |
| No stage runs without an active authorization record | `contracts/state_machine.py` | `contracts/tests/test_state_machine.py` |
| No inference endpoint may be a hosted third party | `contracts/model_policy.py`, `contracts/checks.py` | `contracts/tests/test_model_policy.py` |
| Sandbox egress cannot be requested | `SandboxPolicy.network: Literal["deny"]` | `api/tests/test_http_surface.py` |
| No verdict state without a verification record | `contracts/state_machine.py` `assert_verdict_is_evidenced` | `contracts/tests/test_state_machine.py` |
| A substituted path cannot be claimed as the primary one | `DiscoveryMethod`, `FuzzingMode`, `IsolationMode`, `EvidenceSource`, `ModelProvenance.inference_mode` | `contracts/tests/test_verdict.py` |
| A verdict state is backed by *this mission's own* records, type-checked and de-duplicated | `contracts/state_machine.py` `assert_verdict_is_evidenced` | `contracts/tests/test_state_machine.py::test_guard_rejects_a_lookalike_without_a_gate_matrix`, `::test_another_missions_verification_does_not_justify_this_verdict` |
| The record set handed to that guard is *complete* | `orchestrator/transitions.py` — loaded under the mission row lock, never a parameter | `orchestrator/tests/test_verdict_completeness.py` |
| The candidate set closes when VERIFY begins | `Mission.verification_started_at`, `orchestrator/candidates.py` | `orchestrator/tests/test_candidate_freeze.py::test_cannot_add_candidate_after_verification_starts` |
| A paused mission resumes only into the state it paused from | `Mission.paused_from`, `contracts/state_machine.py` `assert_resume` | `orchestrator/tests/test_pause_resume.py` |
| The published OpenAPI dump does not depend on the interpreter | `tools/export_openapi.py` `CANONICAL_REASON_PHRASES` | `contracts/tests/test_openapi_dump.py::test_the_pinned_phrases_survive_a_renamed_stdlib_phrase` |

## Changing the contract

1. Change the schema.
2. `.venv/bin/python tools/export_openapi.py`
3. Regenerate the frontend types (see `packages/schemas/README.md`).
4. Update `docs/03-technical/21-api-specification.md` in the same PR.

`contracts/tests/test_openapi_dump.py` fails if step 2 is skipped, and the Astro
build fails if step 3 is skipped. That is deliberate: a contract document that lies
is worse than none.
