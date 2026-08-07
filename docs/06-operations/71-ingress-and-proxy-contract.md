# Ingress and Proxy Contract

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 1.0 |
| Status | Active — D1 |
| Owner | devops |
| Last updated | 2026-08-07 |
| Implements | issues #10, #11 · decisions D-013, D-018, D-019, D-020, D-021 |

Everything in this document is implemented by files under `infrastructure/`. Where the two
disagree, the files win and this document is the bug.

**nginx configuration is never hand-edited on a host.** It is committed, mounted read-only
into the container, and changed by a pull request. There is no other supported path.

---

## 1. The one thing that will break if you forget it

nginx buffers proxied responses by default. The mission event stream
(`GET /api/v1/missions/{id}/events`) is an infinite response, so with buffering on nginx
holds every frame waiting for an end that never comes. Nothing errors. No log line
appears. The Command Center simply never renders a mission event.

The signature is unmistakable once you know it: **SSE works when you talk to Django
directly on :8000, and dies the moment you go through nginx.**

`infrastructure/compose/nginx/includes/sse.conf` sets `proxy_buffering off`, and
`infrastructure/scripts/smoke-sse.sh` is the regression test. That script runs two cases:
the committed configuration, which must stream, and the same configuration with buffering
forced back on, which must fail. The second case exists so a green first case means
something.

**Test SSE through nginx. Never against the ASGI server directly.**

---

## 2. Topology

```
browser ──TLS──> nginx :8443 ┬─ /                             → Astro (dev server, or static build)
                             ├─ /api/…                        → control-api :8000  (buffered)
                             ├─ /api/v1/missions/*/events      → control-api :8000  (UNBUFFERED)
                             ├─ /static/…                     → Django static
                             └─ /admin…                       → dev: private nets only
                                                                finale: 404 at the proxy

                       control-api ─┬─ postgres :5432   (network `backend`, internal: true)
                                    └─ redis    :6379   (network `backend`, internal: true)
```

`nginx` is the only service that publishes a host port. The API is deliberately not
reachable except through the proxy, so nobody can accidentally test the event stream
without the thing that breaks it in the path.

---

## 3. What the control API must do

nginx's half of the contract is committed. The Django half is not, and without it the
proxy headers do nothing.

| Requirement | Why |
|---|---|
| `USE_X_FORWARDED_HOST = True` | Otherwise Django builds URLs from its own `Host`, not the browser's |
| `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` | Otherwise `request.is_secure()` is `False` behind the proxy and every absolute URL comes out `http://` |
| Listen on `0.0.0.0:8000` inside the container | A loopback-bound listener is unreachable from the nginx container. `config/asgi.py`'s docstring shows `127.0.0.1`, which is right for a bare-metal run and wrong in compose |
| ASGI callable at `config.asgi:application` | Named in `infrastructure/compose/images/control-api.Dockerfile` |
| `requirements.txt` at `apps/control-api/` | The image installs from it |
| Emit `X-Accel-Buffering: no` on the event stream | Redundant with `sse.conf` on purpose — belt and braces, so the stream survives a second proxy hop being added later. **Not currently sent** (measured 2026-08-07) |
| Emit `: keepalive` (or a comment frame) every ~15s on the stream | `proxy_read_timeout` is 3600s so an idle stream survives a long fuzzing phase; a heartbeat is what detects a genuinely dead TCP path long before that. **Already implemented** — the D1 stub stream sends `: heartbeat` |
| Allowed hosts must include `localhost` and the compose service names | nginx forwards the browser's `Host` verbatim |
| CSRF trusted origins must include `https://localhost:8443` | The dev browser origin is the nginx TLS listener, **not** `http://localhost:4321` |

nginx sets, on every proxied request:

```
Host              $http_host      # verbatim, WITH the port — $host would drop :8443
X-Real-IP         $remote_addr
X-Forwarded-For   $proxy_add_x_forwarded_for
X-Forwarded-Proto $scheme
X-Forwarded-Host  $http_host
X-Forwarded-Port  $server_port
```

These are **set**, not appended, so a client cannot spoof `X-Forwarded-Proto` to convince
Django that a plaintext request arrived over TLS.

---

## 4. Security headers

`docs/03-technical/23-security-plan.md` states controls, not header names. This is the
mapping. All are set with `always`, so they are present on 4xx and 5xx responses too.

| Header | Value | Control it implements |
|---|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | **Finale only** — see D-021 for why dev does not send it |
| `Content-Security-Policy` | dev / finale differ | "Prevent source leakage"; blocks exfiltration to a third-party origin from a compromised island |
| `X-Content-Type-Options` | `nosniff` | Evidence artifacts are served as data, never sniffed into script |
| `X-Frame-Options` | `DENY` | Clickjacking of operator controls (authorize, cancel, teardown) |
| `Referrer-Policy` | `no-referrer` | A mission id in a URL is not leaked to any outbound link |
| `Permissions-Policy` | all device APIs denied | The Command Center needs none of them |
| `Cross-Origin-Opener-Policy` | `same-origin` | Cross-origin window handles to the control plane |
| `Cross-Origin-Resource-Policy` | `same-origin` | Evidence artifacts are not embeddable elsewhere |
| `Cross-Origin-Embedder-Policy` | `require-corp` | **Finale only** — breaks Astro's dev-server assets |
| `X-Robots-Tag` | `noindex, nofollow, noarchive, nosnippet` | Vulnerability evidence is never indexed |

The dev CSP adds exactly three things, and each is itemised in
`includes/csp-dev.conf`: `'unsafe-inline'` and `'unsafe-eval'` on `script-src` for Astro's
HMR bootstrap and Vite's dev transform, and `ws:`/`wss:` on `connect-src` for the HMR
socket. None of them appears in `includes/csp-finale.conf`. If the finale build needs any
of them, that is a frontend bug, not a reason to relax the finale policy.

`style-src` keeps `'unsafe-inline'` in both profiles because Astro emits inline `<style>`
blocks for scoped component styles. Removing it needs either a nonce (which nginx cannot
generate without a third-party module) or `inlineStylesheets: 'never'` in the Astro
config. That is a frontend decision and is open.

**The ingress is authoritative** (D-020). The upstream's copies of every header above are
dropped with `proxy_hide_header`, because nginx's `add_header` appends and a response with
two conflicting `Referrer-Policy` values is not a security control. `X-Trace-Id` is passed
through untouched — the operator needs it to correlate a UI event with a log line.

### The nginx `add_header` trap

`add_header` is inherited from the enclosing block **only if the inner block declares no
`add_header` of its own**. A single `add_header Cache-Control ...` inside a `location`
silently drops every header set at server level. That is why every location in `conf.d.*`
that adds a header re-includes `security-headers.conf` and the CSP file. If you add a
location with an `add_header`, you must do the same.

---

## 5. Profiles

Both profiles use the same `nginx.conf` and the same `includes/`. What differs is which
`conf.d.*` directory is mounted, and which file lands at `/etc/nginx/profile/admin.conf`.

| | development | finale |
|---|---|---|
| compose file | `docker-compose.yml` | `docker-compose.finale.yml` |
| `conf.d` mount | `nginx/conf.d.dev/` | `nginx/conf.d.finale/` |
| `/etc/nginx/profile/admin.conf` | `nginx/profile/admin-allow.conf` | `nginx/profile/admin-deny.conf` |
| `/` | proxied to the Astro dev server (HMR) | static build from `/usr/share/nginx/html` |
| CSP | loosened for HMR | strict |
| HSTS | not sent | sent |
| `/admin` | private networks only | **404** |
| upstream resolution | at request time, via Docker DNS | at startup — an unresolvable upstream must stop the stack |
| control-api source | bind-mounted, `--reload` | baked into the image, read-only container |
| bind address | `127.0.0.1` only | all interfaces |

### Django admin, blocked at the proxy

`profile/admin-deny.conf` returns **404, not 403**. A 403 confirms something is there; a
404 is indistinguishable from a route that never existed. `^~` is used so the prefix beats
every regex location in the block and cannot be bypassed by a later match.

This is defence in depth, not the only control. There are three locks and all three are
required:

1. `config.settings.finale` does not mount the admin site.
2. `CONTROL_API_ADMIN_ENABLED=false` in the finale environment.
3. The proxy returns 404.

Blocking a route at the proxy does nothing for anyone who can reach the container directly.

Verified 2026-08-07 against a running finale-profile proxy: `/admin/`, `/admin`,
`/adminlogin` and `/django-admin/` all returned 404 while `/api/v1/system/health`
returned 200.

---

## 6. TLS

**Development** — self-signed, generated by `infrastructure/scripts/gen-dev-certs.sh` into
`infrastructure/compose/nginx/certs/`. That directory is gitignored twice: the repository
`.gitignore` refuses `*.pem` and `*.key` everywhere, and `certs/.gitignore` ignores
everything but itself. Accept the browser warning once. Regenerate with `--force`.

**Finale** — two paths, decided by whether the finale host has a public DNS name.

*If it does:* certbot writes to a host directory bind-mounted at the same container path,
and `conf.d.finale/` already serves `/.well-known/acme-challenge/` from
`infrastructure/compose/certbot-webroot`. Issue the certificate **the day before**, not on
the day.

*If it does not* — a closed competition LAN being the likely case — the finale runs the
same self-signed material, with the certificate fingerprint recorded in
`docs/10-competition/36-hour-finale-runbook.md` so the warning can be explained rather
than apologised for. A browser trust warning during a live demo is bad. A failed ACME
challenge five minutes before it is worse.

Both listeners are 8080/8443, not 80/443, because the container runs as uid 101 and cannot
bind a privileged port. If judges must type a bare hostname, put a host-level
80→8080 / 443→8443 forward in front; do not run the ingress as root to save a redirect.

---

## 7. Rollback

Every artifact here is a file in git and an image pinned by digest. Rollback is a checkout
and a restart; there is no state in the ingress.

```bash
# 1. nginx configuration only — the common case, ~2 seconds, no downtime.
git checkout <last-good-sha> -- infrastructure/compose/nginx/
docker exec brahmadatta-nginx nginx -t          # ALWAYS test before reloading
docker exec brahmadatta-nginx nginx -s reload

# 2. Whole ingress container.
git checkout <last-good-sha> -- infrastructure/compose/
docker compose -f infrastructure/compose/docker-compose.yml up -d --force-recreate nginx

# 3. Whole stack, keeping the database.
git checkout <last-good-sha> -- infrastructure/
docker compose -f infrastructure/compose/docker-compose.yml up -d --force-recreate

# 4. Whole stack, discarding the database. DESTRUCTIVE — this deletes mission and
#    evidence records. Never during a finale run.
docker compose -f infrastructure/compose/docker-compose.yml down -v
docker compose -f infrastructure/compose/docker-compose.yml up -d
```

`nginx -t` before `nginx -s reload`, every time. A reload with a broken configuration
leaves the old workers serving, which looks like the change silently did nothing.

Verify a rollback landed:

```bash
curl -sk https://localhost:8443/api/v1/system/health
infrastructure/scripts/smoke-sse.sh
```

---

## 8. Monitoring and logs

At this scale — one operator, one host, a 36-hour finale — there is no metrics stack and
no alert routing, and pretending otherwise would be `docs/06-operations/67-*` fiction. What
exists:

| What | Where | Read it with |
|---|---|---|
| nginx access log | JSON, one line per request, into the `nginx-logs` volume | `docker exec brahmadatta-nginx tail -f /var/log/nginx/access.log` |
| nginx error log | `/var/log/nginx/error.log` | same |
| API log | container stdout | `docker compose -f infrastructure/compose/docker-compose.yml logs -f control-api` |
| Service health | compose healthchecks | `docker compose -f infrastructure/compose/docker-compose.yml ps` |
| Ingress liveness | `GET /healthz` on 8080 | `curl http://localhost:8080/healthz` |
| API + database health | `GET /api/v1/system/health` | reports database reachability |

The access log line carries `trace_id`, read from the API's `X-Trace-Id` response header,
which is what joins an nginx line to an API line to a mission event.

Three things worth watching by eye during a finale run, because none of them is alerted:

1. `upstream_time` on the SSE route climbing — the stream is stalling.
2. Any 502 on `/api/` — the ASGI process died and uvicorn's reloader is not running in
   the finale profile.
3. `docker compose ps` showing anything not `healthy`.

---

## 9. Secrets

No credential is committed, ever. `.gitignore` refuses `.env`, `.env.*` (except
`.env.example`), `*.pem` and `*.key`, and the `secrets-guard` job in
`.github/workflows/ci.yml` fails the build if a tracked file matches those patterns or
contains a private-key block.

Injection, per environment:

- **development** — `cp .env.example .env`, fill in, never commit. Compose reads it via
  `--env-file` for interpolation and `env_file:` for the container environment.
- **CI** — no `.env` at all. Every job sets inline only what it needs, and none of those
  values is a credential. No repository or environment secret is required by any current
  job.
- **finale** — `.env` written on the box by hand from a password manager, mode 0600, owned
  by the operator account. Not generated, not copied off a laptop, not in the repository.
  The finale compose file uses `${VAR:?message}` so a missing value stops the stack with a
  named error instead of starting with a default.

Development TLS keys are generated locally and never leave the machine.

---

## 10. Infrastructure cost

**$0/month at launch scale and at 10× launch scale.**

Not a rounding — there is no rented infrastructure. D-015 cut the GPU lease entirely and
the small model runs locally on CPU; the whole stack is five containers on a developer
laptop, and the finale runs the same five containers on whatever machine is in the room.
The only cost lines that exist at all:

| Line | At launch | At 10× | Assumption |
|---|---|---|---|
| Compute | $0 | $0 | Laptop / competition-provided host. One concurrent operator is an explicit non-goal to exceed |
| Container images | $0 | $0 | Docker Hub public images, pinned by digest |
| CI | $0 | $0 | GitHub Actions on a private repository, well inside the free tier; the heaviest job is ~2 minutes |
| TLS certificate | $0 | $0 | Self-signed, or Let's Encrypt if the finale host has a public name |
| Domain | $0 | $0 | None registered; the finale is reached by IP or hostname on the local network |

"10×" here means ten concurrent missions, not ten thousand users. At that point the
binding constraint is host CPU for sanitizer builds and fuzzing, not anything billable —
the honest answer is "buy a bigger machine", and that is a CEO decision that does not exist
yet. **No number in this table is a forecast of a paid service, because there is no paid
service.**

---

## 11. Known gaps

Listed so the next shift does not rediscover them.

- `apps/command-center/` does not exist. The Astro service in `docker-compose.yml`, the
  `static` target in `images/command-center.Dockerfile`, and the finale `dist` mount are
  **unverified** — none of them has ever been built or run.
- `docker-compose.finale.yml` has never been brought up. Its configuration validates and
  its nginx profile is tested, and that is all.
- The queue worker is opt-in and its command is a guess until a framework is chosen
  (D-018).
- Django static is proxied in dev and served from a shared volume in the finale; the
  finale path needs `STATIC_ROOT = /app/staticfiles` and a `collectstatic` step, which is
  not yet wired.
- No integration job runs the stack in CI. CI validates configuration and tests SSE against
  a stub. A full compose-up smoke test is worth adding once the frontend exists.
