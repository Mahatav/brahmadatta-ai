# D8 Security Checklist Run

Issue: #53  
Recorded: 2026-08-14 22:04 PDT  
Status: passed for static/local checks; finale in-container egress probe not run because `.env`
is absent and the finale compose profile requires `DATABASE_URL`.

## Commands

| Check | Result |
|---|---|
| `cd apps/control-api && .venv/bin/python -m pytest -q` | passed |
| `python3 -m pytest tests/architecture/test_import_direction.py tests/architecture/test_compose_topology.py -q` | 20 passed, 3 skipped |
| `infrastructure/scripts/egress-test.sh` | PASS: app networks denied; nginx reached out as the control |
| `cd apps/control-api && .venv/bin/python -m pip_audit -r requirements.txt -r requirements-dev.txt --format json` | no known vulnerabilities |
| `npm audit --json` | 0 vulnerabilities after root lockfile update |
| `cd apps/command-center && npm audit --json` | 0 vulnerabilities after Astro stack update |
| Secret scan over tracked files | one intentional dummy token fixture only |

## Not Run

`infrastructure/scripts/finale-egress-evidence.sh` did not run because this checkout has no
`.env`, and `docker compose -f infrastructure/compose/docker-compose.finale.yml config` fails
until `DATABASE_URL` is supplied. The rehearsal runbook still owns the full in-container proof.

## Wording

The evidence-bundle integrity wording is:

`hash-manifested, tamper-evident against the manifest supplied with the bundle`

Do not describe the evidence bundle as signed or tamper-proof.
