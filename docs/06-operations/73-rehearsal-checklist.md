# Rehearsal checklist — infra checks that do not belong in per-PR CI

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Owner | devops, gate confirmed by cybersecurity |
| Status | Working checklist — first version |
| Related | SEC-R3 (`docs/09-company/08-security-review.md` §12.6, condition register row SEC-R3), #114 |

## Why this file exists

CI runs on every PR and has to stay cheap. Some properties can only be proven by booting
the real finale stack from a real image build, and Docker-in-CI on every PR is a cost the
CTO already cut once (see the header of `.github/workflows/ci.yml`). SEC-R3 drew the line:
the free, static half of a check goes in CI; the expensive, dynamic half becomes a
**rehearsal cadence** instead of disappearing. A recommendation that lives only as a
sentence in a security review is the same failure this whole file is here to prevent — "we
said we'd do it" is not evidence that it happened. Each item below has a command, an
expected result, and a place to paste the actual output.

This is the `docs/06-operations/` copy of the rehearsal gate — the operational,
run-this-and-paste-the-output version. `docs/10-competition/36-hour-finale-runbook.md`
already references "isolation egress smoke check" in its hour-by-hour plan; this file is
what that line item actually means, mechanically, from the infra side.

## When this checklist runs

- **Every rehearsal** of the finale stack (full boot, not a partial `docker compose up` of
  a subset of services).
- **Once before submission**, as its own recorded run, not reused from the last rehearsal.
- **After any change to:** `infrastructure/compose/docker-compose.finale.yml`,
  `infrastructure/compose/images/*.Dockerfile`, the `networks:` block of either compose
  file, or anything in `apps/control-api/config/settings/finale.py`.

## Checklist

Copy this table into the rehearsal log (or the PR/issue tracking that rehearsal) and fill
in the Result and Evidence columns. A checklist item with no evidence attached is a claim,
not a check — see the standing rule in `docs/09-company/*` about a property being enforced
only when a named check demonstrates it.

| # | Check | Command | Pass condition | Result | Evidence |
|---|---|---|---|---|---|
| R1 | Only nginx reaches off the host, proven from inside the RUNNING finale container | `infrastructure/scripts/finale-egress-evidence.sh` | `control-api` reaches nothing external (`hosted-inference-api`, `hosted-inference-api-2`, `cloud-metadata` all `reached: false`); `postgres-in-stack` reaches `true` (the negative control — if this is also false, the container itself is broken and every "denied" above proves nothing) | ☐ pass / ☐ fail | paste the script's final verdict line + JSON block |
| R2 | SSE survives the proxy on the FINALE profile specifically, not just the dev stub | Bring the finale stack up; from another machine or `curl --http1.1`, hit `/api/v1/missions/<id>/events` on a real or fixture mission and watch frames arrive incrementally over at least 10s | frames arrive spread over time, not all at once at connection-close | ☐ pass / ☐ fail | first-frame and last-frame timestamps |
| R3 | `nginx -t` against the finale config as actually mounted (not the standalone validator) | `docker compose -f infrastructure/compose/docker-compose.finale.yml exec nginx nginx -t` | `syntax is ok` / `test is successful` | ☐ pass / ☐ fail | command output |
| R4 | TLS material is the real cert for this box, not the dev self-signed cert | `docker compose -f infrastructure/compose/docker-compose.finale.yml exec nginx openssl x509 -in /etc/nginx/certs/server.crt -noout -subject -dates` | subject and expiry match what was provisioned for this rehearsal/submission, not `CN=localhost, O=Brahmadatta AI (development only)` | ☐ pass / ☐ fail | command output |
| R5 | `check --deploy` against the finale settings, live | `docker compose -f infrastructure/compose/docker-compose.finale.yml exec control-api python manage.py check --deploy` | no new warning since the last recorded run (QA's round-3 baseline: `SECURE_HSTS_SECONDS` and `SECURE_SSL_REDIRECT` warnings, both mitigated at nginx and tracked as informational — anything beyond that pair is new and gets triaged, not waved through) | ☐ pass / ☐ fail | command output |
| R6 | `UVICORN_FORWARDED_ALLOW_IPS` resolved to the real value, not a default nobody set | `docker compose -f infrastructure/compose/docker-compose.finale.yml exec control-api sh -c 'echo $UVICORN_FORWARDED_ALLOW_IPS'` and `cat /proc/1/cmdline \| tr '\0' ' '` on the container | matches the finale edge network's actual subnet; process args show that value, not `*` and not the dev default `127.0.0.1` | ☐ pass / ☐ fail | both outputs |

## R1 in full — what a pass and a fail look like

Pass (`finale-egress-evidence.sh`'s own output, condensed):

```
{
  "hosted-inference-api": {"reached": false, ...},
  "hosted-inference-api-2": {"reached": false, ...},
  "cloud-metadata": {"reached": false, ...},
  "internet-by-ip": {"reached": false, ...},
  "postgres-in-stack": {"reached": true, ...}
}
egress evidence: PASS — control-api reaches nothing external; the database control fired
```

Fail looks like any `"reached": true` on a target other than `postgres-in-stack`, or
`"postgres-in-stack": {"reached": false, ...}` — the second case means the container itself
is misconfigured or not actually running the finale profile, and every other "denied"
result in the same run is unfalsifiable and must be discarded, not recorded as a pass.

## What is NOT on this list, and why

- **`egress-test.sh`'s topology and live-network-probe checks** — these run in CI on every
  PR (`ingress` job) and do not belong here; re-running them at rehearsal is redundant with
  what CI already proved on the merge commit.
- **`smoke-sse.sh`'s four cases** — also CI, not rehearsal. R2 above is a different check:
  it proves the FINALE profile specifically (real TLS, real built image, real edge
  network), not the dev stub that `smoke-sse.sh` uses to stay buildless.

## Recording results

Paste the filled-in table (or a link to it) into the PR or issue for the change that
triggered the rehearsal, and into the rehearsal's own tracking issue if one exists. A
rehearsal with no recorded checklist did not happen, for the purposes of sign-off.
