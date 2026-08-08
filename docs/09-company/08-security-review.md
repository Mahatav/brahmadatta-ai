# Security Review — Gate Pass

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Document | Company-workflow security gate. Threat model, findings, three rulings. |
| Reviewer | `cybersecurity` seat |
| Date | 2026-08-07 |
| Reviewing | PR #74; issue #78 (mine to close); the isolation substitution in `07-task-breakdown-audit.md` §6 cut 3; `infrastructure/` and `apps/control-api/` as they stand |
| Baseline | `main` at `180bd6f`; PR #74 at `fdc4033`; `apps/control-api/` and `infrastructure/` snapshotted from the live worktrees at **2026-08-07 07:25Z**, drift-checked clean at **07:36Z** |
| Supersedes | Nothing. `.project/decisions.md` is untouched — the orchestrator folds these records in. |

**No code was edited and no other role's files were changed.** Two implementation agents are
live in `apps/control-api/` and `infrastructure/`; this review was produced in an isolated
`git worktree` off `origin/main` and read their trees without writing to them.

Every command quoted below was executed in this session. Where a section was **not** run, it
says so in §7 rather than being left out.

---

## 0. Verdicts, up front

| Item | Verdict |
|---|---|
| **PR #74 — `demo/repositories/pktcfg`** | **PASS WITH CONDITIONS** — SEC-06 and SEC-09 before merge; SEC-10 before the repository is made public. Nothing in this PR blocks it. |
| **Issue #78 — egress** | **REMAINS OPEN. NOT CLOSED.** The invariant is not structural. Two findings, one Critical (SEC-01) and one High (SEC-02). Claim wording is constrained until both close — §5. |
| **Isolation substitution** — `--network none` + non-root instead of rootless Podman | **ACCEPTED, with eight binding conditions.** §6. |
| **Overall security posture of the reviewed surface** | **BLOCKED — one Critical open (SEC-01).** *(Lifted in §12.8 after SEC-01 was fixed and re-verified.)* |
| **PR #110 — `feat/state-machine`** | **PASS WITH CONDITIONS** — SEC-15, SEC-16 and SEC-18 before merge. No Critical open; the veto is not exercised. Full round-2 pass in **§13**. |
| **PR #111 — `feat/model-gateway`** | **PASS WITH CONDITIONS** — SEC-24 and SEC-25 before merge. Bypass table re-run by me: **gateway 0 of 60**, control-api 34 of 60. **#78 may close** once SEC-02 and SEC-19 are filed against #93 with an owner. Round-3 pass in **§14**. |
| **PR #119 — `feat/authorize-snapshot`** | **PASS WITH CONDITIONS** — SEC-26 (High) before any extraction stage is built on this; SEC-27, SEC-28, SEC-31 before merge; SEC-29, SEC-30 before #12/upload land. No Critical. Mission-row lock **verified serializing under real Postgres**, not just SQLite. Round-4 pass in **§15**. |

**SEC-01 is a critical finding and it blocks deployment of the finale stack.** It does not
block continued development, and it does not block PR #74. It blocks bringing
`docker-compose.finale.yml` up as the competition run, and it blocks the stronger form of the
no-external-inference claim in front of a judge. It is roughly half an hour of compose
configuration to fix, so this is a gate, not a schedule problem.

Only a written risk acceptance from the CEO, recorded in `.project/decisions.md`, overrides
this. The CTO may arbitrate the severity; the CTO cannot waive it.

---

## 1. Threat model, in one page

Written now because the pack's `23-security-plan.md` is a control list without an actor
model, and the three questions in front of me all turn on *who* we are defending against.

**Assets, ranked.**

1. The repository snapshot under analysis, and any prompt derived from it. This is the asset
   the product's central claim is about.
2. The integrity of the verdict. A `VERIFIED` that was not earned is worse than a crash — it
   is the one thing a defensive-security product cannot be caught doing.
3. Host and cloud credentials on the machine running the finale, including instance metadata
   if it is a rented VM.
4. Operator bearer tokens and the Postgres password.
5. Availability of the demo machine during a scored window.

**Actors.**

| Actor | Capability | In scope |
|---|---|---|
| **A1 — untrusted target code + fuzzer inputs** | Arbitrary native code execution inside the sandbox, arbitrary filesystem writes in its own tree, arbitrary syscalls | **Yes.** This is the actor P0-2 exists for. |
| **A2 — anyone on the venue network** | Unauthenticated HTTP/HTTPS to the published ingress on 8080/8443 | **Yes.** `docker-compose.finale.yml:54-55` publishes on all interfaces. |
| **A3 — a misconfiguration or a stray environment variable** | Sets a settings value nobody reviewed | **Yes.** This is what the Django system checks exist for and it is the actor behind SEC-02 and SEC-03. |
| **A4 — a future contributor or an agent** | Writes a code path the reviewer never sees | **Yes**, and it is the actor the "structural, not intentional" standard is written against. |
| **A5 — a reader of the repository once it is public** | Reads, copies, files reports | **Yes.** This is the actor PR #74 asks about. |
| **A6 — a targeted attacker with a Linux kernel or container-runtime 0-day** | Escapes a hardened container | **Out of scope** for a 14-day competition MVP running our own fixture. Named here so the isolation ruling in §6 is not mistaken for ignorance of it. |

**Attack surfaces.** (a) the ingress on 8443; (b) the control-api's *outbound* network — the
one this review is mostly about; (c) the sandbox boundary; (d) the git repository itself, once
public; (e) the settings/env surface.

**The two hard invariants, restated as testable propositions.**

- **I-1.** No process holding repository content can open a socket to a host outside the trust
  boundary. *Currently false — SEC-01.*
- **I-2.** No mission reaches a terminal verdict state without a verification record whose
  gates derive that verdict, for that mission. *Currently true for the verdict and the state;
  false for "for that mission" — SEC-07.*

---

## 2. Findings

Severity is mine. Each finding has a location, an exploit scenario, and a required fix.
Findings against `apps/control-api/` and `infrastructure/` are against **uncommitted work in
flight**; they go back to the owning developer through the engineering-manager and are not
fixed here.

### SEC-01 · **CRITICAL** · The control-api container has unrestricted internet egress

**Location** — `infrastructure/compose/docker-compose.finale.yml:113-115`; same shape at
`infrastructure/compose/docker-compose.yml:102-104` with the acknowledgement at
`docker-compose.yml:245-248`; the misplaced guard at
`apps/control-api/config/settings/base.py:131-137`.

```yaml
# docker-compose.finale.yml:113-115
    networks:
      - edge
      - backend
```

`backend` is `internal: true`. `edge` is an ordinary bridge with a gateway. A container on
`edge` has a default route. The compose file says so itself at `docker-compose.yml:245-248`:

> `control-api` sits on both networks and therefore still has egress; the hard egress denial
> that matters is the target sandbox's

That is the wrong process. The sandbox does not hold the snapshot. The control-api does.

**Executed proof.** A container on a plain compose-style bridge, versus `internal: true`,
versus `--network none`:

```
########## 1. bridge network 'edge' (== compose edge, what control-api is on) ##########
default via 172.22.0.1 dev eth0
172.22.0.0/16 dev eth0 scope link  src 172.22.0.2
--- egress test ---
wget: server returned error: HTTP/1.1 401 Unauthorized

########## 2. internal bridge network 'backend' ##########
172.23.0.0/16 dev eth0 scope link  src 172.23.0.2
--- egress test ---
wget: bad address 'api.openai.com'

########## 3. --network none ##########
  1: lo    inet 127.0.0.1/8 scope host lo
--- egress test ---
wget: bad address 'api.openai.com'
```

The `401 Unauthorized` in case 1 is the finding. It is not an error — it is OpenAI's server
answering. DNS resolved, TCP connected, TLS completed, an HTTP request was delivered to a
hosted inference provider and a response came back, from a container configured exactly as
`control-api` is.

**Exploit scenario.** The model gateway (#35) does not exist yet, so this is not exploitable
*today* by an external actor — it is a missing control, not a live breach, and I am saying
that plainly. What it means is that every one of the following reaches the internet with
nothing to stop it, the moment the gateway lands:

- a URL literal in a prompt-building code path that never reads `MODEL_ENDPOINTS`;
- an HTTP client that honours `HTTPS_PROXY` from the environment;
- an HTTP client following a 302 from an allowed local host to `api.openai.com` — the policy
  validates the URL it was given, not the URL it ends up at;
- a dependency's own telemetry or update check;
- any future agent-authored code that imports `httpx` and does the obvious thing.

The startup check (`contracts/checks.py:24-45`) constrains two settings values. It does not
constrain a socket. `SANDBOX_POLICY["network"] = "deny"` at `base.py:133` is a string in a
dictionary that the control-api echoes to the dashboard; it configures a sandbox runner that
has not been written, and it has never had any effect on the control-api's own networking.

**Required fix.** All three, and (1) is the one that makes the claim unconditional:

1. Remove `control-api` from `edge`. Put nginx and control-api on a *new* `internal: true`
   network (`ingress-internal`), keep control-api on `backend` for Postgres, and give the
   model host — when it exists — its own `internal: true` link. `edge` then carries nginx
   only, which is the only service that needs to be reachable from the host.
2. A test executed from **inside** the running control-api container that attempts egress to a
   public host and asserts failure, with the output pasted in the PR. Not `docker compose
   config`; a live `docker compose exec control-api python -c "..."`.
3. `curl`/`wget` are not in the runtime image; use a two-line Python socket check so the test
   does not depend on a debug tool being installed.

**Owner** — infra, issue #78. **Verification** — I re-run (2) myself before #78 closes.

---

### SEC-02 · **HIGH** · The model-endpoint allowlist accepts cloud metadata endpoints, and an IDNA homograph of `api.openai.com`

**Location** — `apps/control-api/contracts/model_policy.py:58-70` (`_host_is_private_ip`
returns `not address.is_global`), `:95` (`.internal` in `_PRIVATE_SUFFIXES`), `:99` (the
bare-label pass), `:82` (host taken from `urlparse` with no IDNA normalisation).

**Executed proof — the policy function:**

```
False  https://api.openai.com/v1
True   http://127.0.0.1:8080/v1
True   http://169.254.169.254/
True   http://[fd00:ec2::254]/latest/meta-data/
True   http://metadata.google.internal/computeMetadata/v1/
True   http://100.100.100.200/latest/meta-data/
True   http://metadata.internal/
True   http://openai/v1
True   http://api。openai。com/v1
False  http://API.OPENAI.COM/v1
False  https://api.openai.com./v1
True   https://my-llm-proxy.internal/v1
True   http://[::ffff:169.254.169.254]/
```

**Executed proof — the same four values through `manage.py check`, finale profile:**

```
########## A. hosted provider ##########
SystemCheckError: System check identified some issues:
ERRORS:
?: (brahmadatta.E001) SMALL_MODEL_BASE_URL points at 'api.openai.com' and it is a
known hosted inference provider. …

########## B. SMALL_MODEL_BASE_URL=http://169.254.169.254/ ##########
System check identified no issues (0 silenced).

########## C. SMALL_MODEL_BASE_URL=http://metadata.google.internal/computeMetadata/v1/ ##########
System check identified no issues (0 silenced).

########## D. SMALL_MODEL_BASE_URL=http://api。openai。com/v1 ##########
System check identified no issues (0 silenced).
```

**Executed proof — that (D) is not a curiosity:**

```
raw host repr: 'api。openai。com'
idna.encode (uts46): b'api.openai.com'
```

`idna` is already installed in the control-api virtualenv (3.18), and it is the library
`httpx` and `requests` both use to encode a hostname. UTS-46 maps U+3002 IDEOGRAPHIC FULL
STOP to `.`.

**Exploit scenarios, three, in severity order.**

1. **Homograph — the control designed to prevent exfiltration becomes the path to it.**
   `SMALL_MODEL_BASE_URL=http://api。openai。com/v1` passes `manage.py check`, so the API
   boots clean and the operator sees a green startup. `is_local_inference_endpoint` returns
   `True` because after `urlparse` the host contains no ASCII `.`, so it falls through to the
   bare-label branch at line 99. The HTTP client then normalises the same string to
   `api.openai.com` and posts the prompt — which contains repository source — to OpenAI.
   Every layer behaves as designed and the invariant is broken end to end.
2. **Cloud metadata — credential exfiltration on a rented VM.** `http://169.254.169.254/`
   (all major clouds), `http://metadata.google.internal/` (GCP, and it survives the CTO's
   proposed fix because it passes on the `.internal` suffix, not on link-local),
   `http://[fd00:ec2::254]/` (EC2 IMDS over IPv6, a ULA and therefore not global), and
   `http://100.100.100.200/` (Alibaba, CGNAT space). Any of these in `MODEL_ENDPOINTS` turns
   the model gateway into an SSRF primitive aimed at instance credentials, and the response
   would be handled as a model response — logged, and potentially written into an evidence
   bundle we then hand to a judge. `23-security-plan.md` lists "cloud-metadata access" as a
   threat to be explicitly tested; the endpoint allowlist currently permits it.
3. **Bare label.** `http://openai/v1` and `http://exfil/v1` pass. With a DNS search domain on
   the host — normal on a corporate or cloud network — a single-label name resolves to a
   public host.

Note that fixing only `is_link_local`, which is what the CTO review proposed, closes case 2a
and leaves 1, 2b, 2c and 3 open. That is why this is a separate finding at High rather than a
footnote on SEC-01.

**Required fix.** All four:

1. Normalise before deciding. Inside a `try`, `host = idna.encode(host, uts46=True).decode()`;
   reject the URL outright if that raises, or if the result differs from the input in
   anything other than case. A non-ASCII hostname is never valid for this setting.
2. Replace `not address.is_global` with an explicit deny list applied *before* the private
   check: `169.254.0.0/16`, `fe80::/10`, `100.64.0.0/10`, `fd00:ec2::/32`, `0.0.0.0/32`,
   `::/128`. Keep `is_global` afterwards as the outer allowlist; do not rely on it alone.
3. Reject any host whose leftmost label is `metadata`, and reject `metadata.google.internal`
   and `metadata.internal` by name.
4. Replace the bare-label pass at line 99 with an explicit allowlist of permitted compose
   service names, read from settings (`MODEL_SERVICE_NAMES`), defaulting to empty. "Any name
   with no dots" is not a boundary.

Add a table-driven test with every string in the executed-proof block above as a case,
asserting the expected verdict. It is fifteen lines and it makes this a regression instead of
a rediscovery.

**Owner** — control-api, issue #78. **Verification** — I re-run the table before #78 closes.

---

### SEC-03 · **HIGH** · The two finale-only system checks never run in the finale stack

**Location** — `apps/control-api/config/settings/base.py:28`
(`APP_ENV = env.get_str("APP_ENV", "development")`);
`apps/control-api/config/settings/finale.py` (never sets `APP_ENV`);
`infrastructure/compose/docker-compose.finale.yml:95-108` (environment block does not set
`APP_ENV`, and `env_file: ../../.env` supplies `APP_ENV=development`);
`apps/control-api/contracts/checks.py:51` and `:94` (both checks are `APP_ENV`-gated).

**Executed proof**, using the exact environment `docker-compose.finale.yml` produces:

```
DJANGO_SETTINGS_MODULE : config.settings.finale
settings.APP_ENV       : development
ADMIN_ENABLED          : False
DEBUG                  : False
system check messages  : [('brahmadatta.W003', 30)]

check_admin_disabled_in_finale fires? False
check_debug_off_in_finale fires?      False
```

And the live health endpoint, running the finale settings module, unauthenticated:

```
{"status": "ok", "service": "brahmadatta-control-api", "version": "0.1.0",
 "app_env": "development", …}
```

**Exploit scenario.** `checks.py` was written so that a stray environment variable cannot
produce an insecure finale — `Error` rather than `Warning`, deliberately, and the docstring
says so. In the finale stack those two checks are dead code. Today the admin and `DEBUG` are
independently hard-coded off in `finale.py:14,22-23`, so there is no exposure right now; what
is lost is the layer that was supposed to catch a *future* regression. The moment someone
re-adds `django.contrib.admin` to a shared `INSTALLED_APPS`, or makes `DEBUG` env-driven for
a debugging session on D6, the stack boots silently instead of refusing to start — which is
the exact scenario `brahmadatta.E002` and `E004` exist for.

Second, smaller, and on stage: `GET /api/v1/system/health` is unauthenticated (SEC-05) and
reports `"app_env": "development"` during the finale. That is a public surface stating
something untrue about the running system, next to a product rule that says every displayed
value is real telemetry.

**Required fix.** In `config/settings/finale.py`, alongside the existing hard-coded
`ADMIN_ENABLED = False`:

```python
APP_ENV = "finale"   # not env-driven, for the same reason ADMIN_ENABLED is not
```

and a test in `api/tests/test_settings_profiles.py` asserting
`load_profile("config.settings.finale").APP_ENV == "finale"` with `APP_ENV="development"` in
the environment. Mirror it for `config.settings.development`.

**Owner** — control-api.

---

### SEC-04 · **MEDIUM** · `client_max_body_size 0` plus an unsized `/tmp` tmpfs is an unauthenticated memory-exhaustion DoS on the ingress

**Location** — `infrastructure/compose/nginx/nginx.conf:65`;
`infrastructure/compose/docker-compose.finale.yml:44-47` and
`infrastructure/compose/docker-compose.yml:41-44` (`tmpfs: - /tmp`, no `size=`);
`infrastructure/compose/nginx/nginx.conf:22` (`client_body_temp_path /tmp/client_temp`).

**Exploit scenario.** `location /api/` includes `proxy-common.conf`, which leaves
`proxy_request_buffering` at its default of `on`. nginx therefore reads the **entire** request
body into `/tmp/client_temp` before it opens a connection to the upstream. `/tmp` is a tmpfs
declared with no `size=`, so it is backed by host RAM with no ceiling, and
`client_max_body_size 0` removes the only limit nginx would otherwise apply.

An unauthenticated `POST https://<finale-host>:8443/api/v1/missions` with a
multi-gigabyte body is written to host RAM before Django is ever consulted — and Django would
have returned `401` in microseconds, because `BearerTokenAuth` runs before any body parsing.
`docker-compose.finale.yml:54-55` publishes 8443 on all interfaces, so the actor is anyone on
the venue network, with one `curl`, during a scored window.

The comment at `nginx.conf:62-64` justifies the `0` on the grounds that the API returns a
better error than a bare 413. That reasoning does not hold, because the API never receives
the request.

**Required fix.**

- `client_max_body_size 64m;` at `http` level in `nginx.conf`, and a single override on the
  snapshot-upload location once it exists, sized to the documented maximum repository
  snapshot. The 413 is the correct answer for a body the ingress will not carry; the API's
  nicer error is for a repository the *analyser* will not accept, which is a different check
  at a different size.
- `tmpfs: - /tmp:size=256m` on the nginx service in both compose files.
- The same `size=` on the control-api service's `/tmp`.

**Owner** — infra.

---

### SEC-05 · **MEDIUM** · `/api/v1/openapi.json` and `/api/v1/docs` are unauthenticated in the finale, and the docs page fetches scripts from a third-party CDN

**Location** — `apps/control-api/api/api.py:48-49` (`docs_url="/docs"`,
`openapi_url="/openapi.json"`, unconditional across profiles);
`infrastructure/compose/nginx/conf.d.finale/brahmadatta.conf:85-88` (`location /api/` proxies
everything with no exclusion).

**Executed proof**, finale settings module, no `Authorization` header:

```
  /api/v1/openapi.json                                       HTTP 200
  /api/v1/docs                                               HTTP 200
  /api/v1/system/health                                      HTTP 200
  /api/v1/missions                                           HTTP 401
  /django-admin/                                             HTTP 404
  /admin/                                                    HTTP 404
  /api/v1/missions/{id}/events                               HTTP 401

{"openapi": "3.1.0", "info": {"title": "Brahmadatta AI Control API", …
```

```
=== external asset origins referenced by /api/v1/docs ===
https://cdn.jsdelivr.net/npm/swagger-ui-dist
https://django-ninja.dev/img/favicon.png
https://django-ninja.dev/img/favicon.svg
```

Credit where it is due: every business endpoint is `401`, `/admin/` and `/django-admin/` are
`404` under the finale profile, and the security headers are present on an unauthenticated
response. The authentication layer itself is fine.

**Exploit scenario.** Two, both A2.

1. The complete API surface — every route, parameter, schema, error code and the description
   block explaining what the system enforces — is readable by anyone who can reach 8443, which
   on the finale host is the whole venue network. That is free reconnaissance and it costs
   nothing to remove.
2. `/api/v1/docs` makes the operator's or a judge's browser fetch Swagger UI from
   `cdn.jsdelivr.net` and favicons from `django-ninja.dev`. The finale CSP
   (`csp-finale.conf:16`, `script-src 'self'`) blocks the script, so what actually renders is
   a broken page that is visibly attempting third-party requests — on a machine whose whole
   pitch is that it does not talk to anyone. It is not a data leak; it is a bad thing for a
   judge to open.

**Required fix**, both layers, matching the pattern `admin-deny.conf` already establishes:

- `config/settings/finale.py` sets `API_DOCS_ENABLED = False`, and `api/api.py` passes
  `docs_url=None, openapi_url=None` when it is false. The committed dump in
  `packages/schemas/openapi.json` is generated by `tools/export_openapi.py`, not by the live
  route, so nothing in the build depends on the endpoint existing.
- `conf.d.finale/brahmadatta.conf` gains, above `location /api/`:
  ```nginx
  location = /api/v1/openapi.json { return 404; }
  location ^~ /api/v1/docs        { return 404; }
  ```

**Owner** — control-api (layer 1) and infra (layer 2).

---

### SEC-06 · **MEDIUM** · `.gitignore` does not cover fuzzer output, and it silently ignores future crash reproducers

This is the direct answer to "does `.gitignore` actually cover crash artifacts and corpora".
**It does not, in both directions.**

**Location** — `demo/repositories/pktcfg/.gitignore:2` (`crash-*`) and `:3` (`!crash/`);
root `.gitignore:33-37` (`/fuzz-out/`, `/corpus/`, `crashes/`).

**Executed proof** (`git check-ignore --no-index -v`, so tracking status does not mask the
pattern):

```
demo/repositories/pktcfg/crash/crash-literal-tab.bin      -> .gitignore:2:crash-*   IGNORED
demo/repositories/pktcfg/crash/crash-newly-minimized.bin  -> .gitignore:2:crash-*   IGNORED
demo/repositories/pktcfg/corpus/seed-simple.bin           -> NOT IGNORED
demo/repositories/pktcfg/corpus/newfuzzfind.bin           -> NOT IGNORED
demo/repositories/pktcfg/fuzz-out/corpus-item-01          -> NOT IGNORED
demo/repositories/pktcfg/fuzz-out/leak-abc                -> NOT IGNORED
demo/repositories/pktcfg/fuzz-out/oom-abc                 -> NOT IGNORED
demo/repositories/pktcfg/fuzz-out/timeout-abc             -> NOT IGNORED
```

`!crash/` does not do what it looks like. A negation pattern ending in `/` re-includes a
*directory*; it does not re-include a file inside it that an earlier pattern already excluded.
`crash/crash-literal-tab.bin` is in the repository only because it is already tracked, and
tracked files are never ignored.

**Exploit scenario**, two, opposite in direction.

1. **The reproducer goes stale invisibly.** P0-8 is "crash capture + minimized input that
   reproduces deterministically from a clean build", and the evidence bundle hashes that
   input. Someone re-runs the minimizer on D4, writes `crash/crash-minimized-v2.bin`, and it
   never appears in `git status`. Their local demo passes against a file the repository does
   not have. That failure surfaces on the machine that does a fresh clone, which is the
   finale machine.
2. **Generated fuzzer output gets committed.** libFuzzer writes `crash-<sha>`, `leak-<sha>`,
   `oom-<sha>`, `timeout-<sha>` and `slow-unit-<sha>`; only `crash-*` is covered anywhere in
   the repository, and corpus growth is covered nowhere. A `git add -A` after a campaign
   commits every generated input. For `pktcfg` that is noise. The moment a mission runs
   against a target that is not `pktcfg` — which is the entire point of the product — those
   inputs are byte sequences derived from *that* repository's content, and committing them to
   a repository the CEO may make public is a source-leakage path with no review step in it.

**Required fix.**

`demo/repositories/pktcfg/.gitignore`, replacing all three lines:

```gitignore
build*/
fuzz-out/
# libFuzzer artifact names, at any depth
crash-*
leak-*
oom-*
timeout-*
slow-unit-*
# Corpus is curated, not generated: only the checked-in seeds belong here.
corpus/*
!corpus/seed-*.bin
# The one committed reproducer, re-included by exact name.
!crash/crash-literal-tab.bin
```

Root `.gitignore`, replacing lines 33-37 — drop the leading `/` so the patterns reach
`demo/**` and any future mission working directory, and add the artifact names the current
list misses:

```gitignore
fuzz-out/
crashes/
crash-*
leak-*
oom-*
timeout-*
slow-unit-*
*.sarif
```

with the same two `!` re-includes as above, placed after them.

Add to CI (#11): after any job that runs the fuzzer, `git status --porcelain demo/` must be
empty. That makes this a build failure rather than a habit.

**Owner** — demo-target for the local file, infra for the root file and the CI check.

---

### SEC-07 · **MEDIUM** · A `VerificationRecord` belonging to a different mission satisfies the verdict gate

**Location** — `apps/control-api/contracts/state_machine.py:239-246` (`assert_transition`
takes no mission identity); `:210-236` (`assert_verdict_is_evidenced` reads `record.verdict`
and never `record.mission_id`); `apps/control-api/contracts/schemas/evidence.py:261` (the
field exists and is required).

The #77 fix has substantially landed and it is good work: `assert_verdict_is_evidenced` raises
`VerificationRequiredError` on an empty record set, and `derive_mission_verdict` over the
records must equal `VERDICT_FOR_STATE[target]`, so `EXPORTING → VERIFIED` with no evidence is
now refused. `POSTURE_BY_STATE` at `contracts/enums.py:290,295` now maps both `CANCELLING`
and `CANCELLED` to `MissionPosture.CANCELLED`, closing the CTO's smaller item.

What remains is the identity check. `assert_transition` never learns which mission it is
transitioning, so it cannot tell a record for mission A from a record for mission B, and
neither can `assert_verdict_is_evidenced`.

**Exploit scenario.** A3/A4, not an external attacker. The orchestrator (#12) passes whatever
records it loaded. A `filter()` missing its `mission_id=` clause, a cached list reused across
a retry, or a copy-paste in the loop that walks candidate patches, yields a terminal
`VERIFIED` on the Brahmadatta Core justified by gates that ran against a different mission —
and nothing raises. This is the same "held together by the orchestrator doing the right thing"
that #77 was opened to eliminate, one level down, and #12 is still unwritten, so it is free to
close now.

**Required fix.**

```python
def assert_transition(
    current, target, authorization, now, mission_id: UUID, *,   # required, no default
    snapshot_sha256=None, verifications: Sequence[VerificationRecord] = (),
) -> None:
```

and in `assert_verdict_is_evidenced`, before deriving: reject any record where
`record.mission_id != mission_id`, with the offending ids in `details`. Two tests: a record
for another mission does not justify the state; a mixed set containing one foreign record is
refused rather than filtered.

**Note, not a finding.** `contracts/tests/test_state_machine.py:207` and five sibling tests
call `assert_transition(..., verification=...)` while the implementation exposes
`verifications=`, so six tests error with `TypeError`. That is mid-edit work in an
uncommitted tree at the moment I snapshotted it, not a defect, and I am recording it only so
nobody reads my `pytest` output below as a regression.

**Owner** — control-api, issue #77.

---

### SEC-08 · **LOW** · Dev nginx guards `/admin/`; Django serves the admin at `/django-admin/`

**Location** — `infrastructure/compose/nginx/profile/admin-allow.conf:16` (`location ^~
/admin/` with the RFC1918 allowlist at `:17-22`); `apps/control-api/config/urls.py:25`
(`path("django-admin/", admin.site.urls)`).

**Exploit scenario.** In the dev profile the IP allowlist protects a path Django does not
serve. `/django-admin/` does not match `^~ /admin/`, falls through to `location /`
(`conf.d.dev/brahmadatta.conf:126`), and is proxied to the Astro dev server — so the admin is
simultaneously unreachable *and* not covered by the control written for it. The finale is not
affected: `admin-deny.conf:19,25` blocks both `/admin` and `/django-admin`, and
`finale.py:23` removes the app from `INSTALLED_APPS` entirely, which I confirmed with the
`404`s in SEC-05's proof.

This is Low because there is no exposure today. It matters because the next person who finds
the dev admin broken will fix it by adding a proxy rule, and the natural place to add it is
not the file with the allowlist in it.

**Required fix.** `admin-allow.conf`: change `^~ /admin/` to `^~ /django-admin/`, keeping the
`allow`/`deny` block verbatim, and add a second location proxying `^~ /django-static/`
(matching `base.py:89`, `STATIC_URL = "/django-static/"`) so admin CSS loads. Leave
`admin-deny.conf` alone — blocking both prefixes there is correct.

**Owner** — infra.

---

### SEC-09 · **LOW** · The fixture's public header does not disclose the seeded defect

**Location** — `demo/repositories/pktcfg/include/pktcfg/pktcfg.h:1-4`;
`demo/repositories/pktcfg/src/parse.c:1-18`; `src/config.c:1`; `src/fuzz_entry.c:1-3`;
`fuzz/pktcfg_fuzz.c:1-3`; `tools/pktcfg_replay.c`.

The `README.md` disclosure is genuinely good — class, CWE, `file:line` for root cause,
allocation and crash site, trigger, overflow size, reproducer path, and an authorization
paragraph. `src/decode.c:1-10` also does it right, in the file that carries the bug.

Everything else does not. The public header — the file a GitHub code search or a
copy-and-paste lands on — says:

```c
/* pktcfg - a small parser for the PKTC binary configuration packet format.
 *
 * Purpose-built controlled demo target for Brahmadatta AI. See README.md.
 */
```

"Controlled demo target" does not tell a reader the code is deliberately unsafe.

**Exploit scenario.** A5. The repository goes public; someone lifts `include/pktcfg/` and
`src/` into another project because it is a compact, clean, warning-free C parser with tests.
They copy a heap buffer overflow, and nothing at the point of use warned them.

**Required fix.** A four-line banner at the top of `include/pktcfg/pktcfg.h` and every file
under `src/`, `fuzz/` and `tools/`:

```c
/* WARNING: DELIBERATELY VULNERABLE TEST FIXTURE — NOT FOR PRODUCTION USE.
 * This library contains an intentional heap-buffer-overflow (CWE-787/CWE-131)
 * seeded for Brahmadatta AI's own automated testing, and is authorized for that
 * purpose only. See README.md, "The seeded defect".
 */
```

Cheap, and it is the difference between "we disclosed it in a README" and "we disclosed it
where it would be read".

**Owner** — demo-target. **Condition on PR #74.**

---

### SEC-10 · **LOW** (**blocks publication, not merge**) · No repo-root `SECURITY.md` scoping the fixture out of vulnerability reports

**Location** — repository root. Verified on `main` at `180bd6f`: no `LICENSE`, no
`SECURITY.md`, no `.github/workflows/`. `gh repo view` confirms
`{"isPrivate":true,"licenseInfo":null,"visibility":"PRIVATE"}`.

**Exploit scenario.** A5. On the day the repository is opened, `demo/repositories/pktcfg`
becomes a publicly visible heap-buffer-overflow with a working reproducer in a repository
whose subject is *defensive security*. Two things follow, and both cost us during the
competition window:

- A researcher or a scanner reports it. Best case that is triage time we do not have in the
  D8-11 buffer. Worst case a public "vulnerability disclosure" appears against the project
  while it is being judged, and the headline reads badly regardless of the facts.
- If GitHub code scanning is ever switched on, this produces a permanent unresolvable alert
  on the repository, which is the wrong first impression for a judge who clicks the Security
  tab.

**Required fix**, before the repository is made public and before the URL is put in any
submission:

1. `SECURITY.md` at the root, with an explicit scope paragraph: `demo/repositories/**`
   contains deliberately vulnerable fixtures authored by this team for this system's own
   testing; findings in that path are expected, are documented in each fixture's README, and
   are not accepted as vulnerability reports. Findings anywhere else are — with a contact.
2. `demo/repositories/README.md`, one paragraph, saying the same thing at the directory a
   browser lands on before it reaches a fixture.
3. A root `LICENSE`. PR #74 asserts "no third party's code or intellectual property is
   involved", which I verified is true of the tree — but with no licence file the assertion
   has nothing behind it, and a public repository with no licence is ambiguous for exactly
   the reuse we want to discourage.

**Owner** — CEO (repository publication policy), drafted by demo-target.

---

### SEC-11 · **INFO** · `SANDBOX_RUNTIME` defaults to `podman`, which is not installed on the build host

`apps/control-api/config/settings/base.py:132` defaults to `"podman"`.
`which podman` → `podman not found`; `docker` is present at `/usr/local/bin/docker`.
Not a defect — recorded because it is the premise of the isolation question in §6, and
because a default that does not exist on the machine is a `FileNotFoundError` on D4 rather
than a decision.

---

## 3. Dependency audit — **executed**

`pip-audit` 2.10.1, run from an isolated virtualenv against both the declared requirements
and the actually-installed interpreter environment.

```
### pip-audit -r requirements-dev.txt (control-api, transitive) ###
No known vulnerabilities found

### pip-audit against the actually-installed control-api venv (pip freeze, 29 packages) ###
No known vulnerabilities found
```

Installed set: `Django 5.2.17`, `django-ninja 1.6.2`, `pydantic 2.13.4`, `psycopg 3.3.4`,
`uvicorn 0.52.1`, `pytest 9.1.1` and transitive dependencies. Every version in
`requirements.txt` and `requirements-dev.txt` is pinned with `==`; none floats.

**Dependency policy, set here** (SEC-P1…P4, requirements not findings):

- **SEC-P1** — every Python dependency pinned with `==`, in a committed requirements file. Met.
- **SEC-P2** — every container image pinned by digest, never by tag. **Met** — verified across
  `docker-compose.yml` and `docker-compose.finale.yml`: nginx, postgres, redis, node and the
  Python base in `control-api.Dockerfile` are all `@sha256:`.
- **SEC-P3** — `pip-audit -r requirements-dev.txt` runs in CI (#11) and fails the build on any
  advisory of High or above. **Not met** — there are no workflows in the repository at all.
- **SEC-P4** — no new runtime dependency lands without a `pip-audit` run pasted in the PR. Not
  yet in the PR template.

`packages/ui-components/` has no `package.json` and `apps/command-center/` does not exist, so
there is **no JavaScript dependency tree to audit yet**. When it lands, `npm audit --omit=dev`
under SEC-P3 as well; that is listed in §7 as not reviewed rather than passed.

---

## 4. Secrets — **executed**

`detect-secrets` 1.5.0, `--all-files`, across the PR #74 tree and the two in-flight trees.

```
############ PR #74 tree (demo target, all files) ############
files with findings: 0

############ control-api + infrastructure (in-flight, uncommitted) ############
files with findings: 5
apps/control-api/.env.example                 [('Basic Auth Credentials', 26)]
apps/control-api/api/tests/test_http_surface.py     [('Hex High Entropy String', 56)]
apps/control-api/api/tests/test_settings_profiles.py [('Secret Keyword', 47), ('Secret Keyword', 61), ('Basic Auth Credentials', 89)]
infrastructure/compose/docker-compose.yml     [('Basic Auth Credentials', 93)]
infrastructure/compose/nginx/certs/server.key [('Private Key', 1)]
```

Each triaged by reading the line:

| Hit | Verdict |
|---|---|
| `.env.example:26` — `postgresql://brahmadatta:REPLACE_ME@…` | **False positive.** Literal placeholder. |
| `test_http_surface.py:56` — `"abc123def456"` | **False positive.** A trace-id fixture. |
| `test_settings_profiles.py:47,61` — `DJANGO_SECRET_KEY="finale-profile-import-test-key-…"` | **False positive.** Deterministic test keys, which is what `config/settings/test.py` documents. |
| `test_settings_profiles.py:89` — `postgresql://user:pw@localhost:…` | **False positive.** A URL-parsing parametrize case. |
| `docker-compose.yml:93` — `brahmadatta-dev` | **Accepted.** A dev-only default on an `internal: true` network with no published port; the finale file requires `POSTGRES_PASSWORD` with `:?`. |
| `nginx/certs/server.key` | **Correctly ignored, not tracked.** See below. |

**Real secrets exist on disk and are correctly excluded.** The untracked repository-root
`.env` in the infra worktree carries a generated `DJANGO_SECRET_KEY`, a generated
`CONTROL_API_OPERATOR_TOKEN`, and a `POSTGRES_PASSWORD`. Confirmed excluded:

```
.env                                            -> .gitignore:22:.env
apps/control-api/.env                           -> .gitignore:22:.env
infrastructure/compose/nginx/certs/server.key   -> certs/.gitignore:5:*
infrastructure/compose/nginx/certs/server.crt   -> certs/.gitignore:5:*
```

`git status --short` in the infra worktree shows `?? infrastructure/` with no cert or `.env`
path, so a bulk `git add infrastructure/` will not capture them. The nested
`certs/.gitignore` (`*` plus `!.gitignore`) is the right construction — it survives someone
adding a `.crt`, which the root `.gitignore`'s `*.pem`/`*.key` would not.

**No secret is present in any tracked file. No credential appears in the logging
configuration** (`base.py:150-160` formats `%(message)s` only; `api/auth.py` never logs a
token and the docstring commits to it; `api/trace.py:22` validates an inbound trace id
against `^[A-Za-z0-9_-]{8,64}$` before it reaches a log line or a response header, which
closes header injection and log injection at the same time).

---

## 5. Ruling on issue #78 — the egress finding

**#78 stays open. I am not closing it.** Two findings sit under it: SEC-01 (Critical) and
SEC-02 (High). The issue's own acceptance criteria are the right ones; SEC-02 adds three
bypasses its second criterion does not currently name.

### 5.1 What makes the invariant structural rather than intentional

The distinction the CTO drew is the right one and it is worth stating precisely, because
"add more validation" is the wrong answer here.

A control is **intentional** when it depends on every future code path choosing to call it. A
control is **structural** when a code path that does not call it *cannot succeed*.

`assert_local_inference_endpoint` is intentional. It validates two settings values at startup.
Nothing forces the model gateway to route through it; nothing forces a future contributor to
put their URL in `MODEL_ENDPOINTS`; nothing catches a redirect, a proxy environment variable,
or a dependency's own outbound call. Hardening it — which SEC-02 requires anyway — makes it a
better intentional control. It does not make it structural.

Three things, in this order, make it structural. Only the first is sufficient on its own.

1. **The kernel refuses the socket.** Control-api on `internal: true` networks only, with an
   explicit route to the model host and Postgres and nothing else. Then a URL literal, a
   proxy variable, a redirect and an agent-authored `httpx.post` all fail identically, and
   they fail for a reason nobody can forget to implement. SEC-01's fix. **This is the one
   that converts the claim from conditional to unconditional.**
2. **One egress function, called on every request.** The model gateway exposes exactly one
   function that opens a socket; it calls `assert_local_inference_endpoint` per call, not per
   boot; it disables redirect-following; and it ignores proxy environment variables
   explicitly (`trust_env=False`). Plus a test that greps the tree for `httpx.`, `requests.`
   and `urllib.request` outside that module and fails on a hit. That is what makes "one
   audited egress path" a check rather than a sentence.
3. **The validator is correct.** SEC-02's four fixes. This is the *weakest* of the three and
   it is the only one currently implemented.

The system today has (3), imperfectly. It has neither (1) nor (2).

### 5.2 The honest claim wording, and whether the current claim is true

**Asked plainly: is `docs/00-overview/00-product-identity.md:53` — "Repository content is not
sent to an external inference API" — currently true?**

**As a statement about what the system has done: yes, trivially, and it is worth nothing.**
No repository content has been sent anywhere, because the model gateway does not exist and no
mission has run. Nothing has been sent to anything.

**As a statement about what the system prevents: no.** Nothing prevents it. The control-api
container reaches `api.openai.com` right now — I connected to it from a container configured
exactly as `control-api` is and OpenAI's server answered. The only thing standing between the
repository snapshot and a hosted provider is that nobody has written the code that would do
it, plus a string check that I bypassed three different ways in this session, one of which
(`http://api。openai。com/v1`) passes startup validation and resolves to OpenAI.

A judge hearing "repository content is not sent to an external inference API" will hear the
second reading. It is the only reading that means anything for a security product. So the
claim as it stands is one a reasonable listener would take as false.

**What we are entitled to say, today, and until SEC-01 and SEC-02 both close:**

> Model routing is constrained to a locally-served endpoint, enforced by a startup check that
> refuses to boot the control API against a hosted inference provider, and by a single
> audited egress path in the model gateway. Network-level egress restriction on the control
> plane is implemented but not yet verified end to end.

**What we may not say, in any of these forms, until SEC-01 closes and I have re-run the
in-container egress test myself:**

- "The system cannot reach the internet."
- "The system is network-isolated" / "air-gapped" / "sealed." (`24-privacy-and-data-handling-plan.md:15`
  already forbids the air-gap phrasing. That instinct was right; extend it.)
- "Repository content never leaves the machine."
- "It is impossible for source code to reach a third party."

**What we may say the moment SEC-01 closes and the in-container test output exists:**

> The control-plane process that holds the repository snapshot runs on a network with no
> default route. It can reach the database and the local model host and nothing else. This is
> enforced by the container network, not by configuration — here is the test that attempts
> egress from inside that container and fails.

That is a *stronger* claim than the one currently written, it is demonstrable on stage in
fifteen seconds, and it costs about half an hour of compose configuration. The gap between
those two paragraphs is the entire deliverable of #78.

### 5.3 Where the wording has to change

The phrase appears in roughly 85 documents. I am **not** requiring 85 edits — the phrase is
fine as a statement of *policy*, which is what most of those files are stating. What must
change is every place the claim is made **to an external audience as a statement of
enforcement**:

| File | Action |
|---|---|
| `docs/00-overview/00-product-identity.md:53` | Replace with the §5.2 permitted wording. |
| `docs/10-competition/five-slide-submission-outline.md` | Same, wherever the claim appears in slide copy. |
| The evidence-bundle Markdown/JSON report template (#51) | Render the permitted wording as a field, sourced from the actual enforcement state, not hardcoded. |
| Any spoken script for the finale | Same. |

Once SEC-01 closes, all four get the stronger sentence, and the identity doc gets it
permanently.

**Owner of the wording change** — CEO (it is a claim, not a control; issue #78 is already
labelled `needs:ceo`, correctly). **Owner of the controls** — infra for SEC-01, control-api
for SEC-02. **I hold the sign-off on #78 and will not give it on the wording alone.**

### 5.4 Decision record — D-023

**Decision** — The no-external-inference invariant is enforced at the container network layer,
not only by settings validation. Until it is, the evidence-facing claim is downgraded to the
§5.2 permitted wording, and the four stronger forms are prohibited.

**Options considered** —
(a) Harden `model_policy.py` only (fix link-local, metadata, IDNA, bare labels) and keep the
claim as written.
(b) Harden the validator **and** put control-api on no-default-route networks (SEC-01 +
SEC-02), and only then make the strong claim.
(c) Accept the risk, ship as is, keep the current wording, record a CEO risk acceptance.

**Pros and cons** — (a) is the cheapest and it is what the issue's second acceptance criterion
alone would deliver. It is not enough: I bypassed the validator three ways in one session
without trying hard, and the fourth bypass class — a redirect, a proxy variable, a URL that
never touches `MODEL_ENDPOINTS` — is not addressable by any amount of string checking. It also
leaves the claim resting on a control that a future agent-authored code path can simply not
call. (b) costs about half an hour of compose configuration plus a fifteen-line test table,
and it converts the product's single load-bearing claim from an assertion into a
demonstration — which is worth more on stage than it costs to build, because "here is the test
that fails" is exactly the kind of evidence this product is *about*. (c) is available to the
CEO and I am recording it as available, but it means presenting a defensive-security system
whose central safety claim is not enforced, to judges scoring safety. If the claim is
downgraded to §5.2's wording, (c) becomes survivable; if the strong claim is made anyway, it
is not, and that is the specific thing I am refusing to sign.

**Cost implications** — (b) is roughly half an hour of compose work, fifteen lines of
validator, twenty lines of test. No new service, no new spend.

**Security implications** — (b) closes the highest-severity finding in this review and removes
an entire class of future finding, including ones written by agents nobody reviews closely.

**Scalability implications** — none. One operator, one mission.

**Recommendation** — (b).

**Final approval authority** — **cybersecurity** for the severity and for the sign-off on
#78. **CEO** for the claim wording and for any risk acceptance under (c), recorded in
`.project/decisions.md`. **CTO** may arbitrate severity; the CTO cannot waive the Critical.

---

## 6. Ruling on the isolation substitution

The question, from `docs/09-company/07-task-breakdown-audit.md` §6, cut 3:

> Keep egress denial, resource caps and teardown; if rootless podman fights the host, run a
> standard container with `--network none` and a non-root user, and record the deviation.
> **`cybersecurity` holds a veto here.**

**Ruling: ACCEPTED, with eight binding conditions. I am not exercising the veto.**

### 6.1 The threat I am actually defending against

Stated plainly, because the answer depends entirely on it. The sandbox runs **untrusted target
code and a fuzzer**: a build of a C repository we did not necessarily write, then a libFuzzer
campaign driving that binary with millions of generated inputs, deliberately looking for
memory corruption. Actor A1 has native code execution inside the sandbox by design.

Ranked by likelihood × impact for a 14-day competition MVP:

| # | Threat | Rootless helps? | `--network none` helps? |
|---|---|---|---|
| 1 | **Egress from the sandbox** — a target that phones home, a fuzzer input that triggers a network call, or scanning a third party from our IP. Third-party scanning is a competition-disqualifying safety-boundary breach under `CLAUDE.md`, not just a security bug. | No | **Yes, completely** |
| 2 | **Cloud metadata access from the sandbox** (`169.254.169.254`) on a rented VM | No | **Yes, completely** |
| 3 | **Resource exhaustion** — a fuzzer eating the demo machine's RAM/disk/PIDs during a scored window | No | No — this is `--memory`/`--pids-limit`/`--cpus` |
| 4 | **Filesystem escape via a bind mount** — writing outside the mission worktree | Partly | No — this is mount hygiene |
| 5 | **Orphaned resources** after a crash (P0-14, a scored criterion) | No | No — this is the reaper |
| 6 | **Container escape to host root** via a runtime or kernel 0-day | **Yes — this is the one thing it buys** | No |

Rootless containers buy exactly one row: #6. They buy it by putting the container's `root`
inside a user namespace, so a runtime escape lands as an unprivileged host uid rather than as
host root.

Row #6 is real, and it is also the row where our actor is weakest. The target on D1-D7 is
`pktcfg` — a fixture we wrote, whose only defect is a three-byte adjacent heap write of the
ASCII space character, with neither the value nor the length under attacker control. There is
no exploitation primitive in it. An escape scenario requires an attacker who has both a
container-runtime 0-day and a way to get their code into our authorized target, which is A6,
which I put out of scope in §1 and am not smuggling back in here.

Meanwhile rows #1 and #2 — the ones the P0 table actually names — are answered by
`--network none` **more completely than by rootless Podman**, which by default gives a
container a working slirp4netns network with full egress. A rootless container with a network
is *worse* on the threats that matter here than a rootful container with no network
interface at all.

The P0 item is written as "Rootless isolated sandbox **with egress denied**". Egress denial is
the uncuttable half, and the substitution strengthens it. That is why the veto is not
warranted.

### 6.2 The eight conditions

Binding. The substitution is accepted **only** with all eight. Each is a line in the sandbox
runner, not a project.

1. **`--network none` on every sandbox container, no exceptions and no "just for this one
   run".** Verified by an executed test that attempts DNS and a TCP connect from inside the
   sandbox and asserts both fail, with the output in the PR. This is issue #15b's acceptance
   criterion and it is the criterion I check.
2. **`--user <fixed-high-uid>:<gid>`, never uid 0**, matching the `10001` pattern
   `control-api.Dockerfile:32-33` already establishes.
3. **`--cap-drop ALL` and `--security-opt no-new-privileges`.** The compose files already do
   this for every service (`x-hardening`); the sandbox runner must do it too, and it is not
   inherited.
4. **The Docker socket is never bind-mounted into any container** — not the sandbox, not the
   control-api, not a helper. Under a rootful daemon `/var/run/docker.sock` is
   root-equivalent, and it is the escape that actually happens in practice, unlike a kernel
   0-day. Add a test asserting no compose file and no runner invocation mounts it. This is
   the single condition that most nearly recovers what rootless would have bought.
5. **`--read-only` with the mission worktree as the only writable mount**, plus a sized
   `tmpfs` for build scratch. No host path outside the mission working directory, and
   anything the sandbox must not modify mounted `:ro`.
6. **Resource caps enforced by the runtime, not by the orchestrator's good intentions** —
   `--memory`, `--cpus`, `--pids-limit`, and a wall-clock kill. `SANDBOX_POLICY` in
   `base.py:131-137` already carries `cpu_limit`, `memory_mb` and `max_seconds`; they must be
   passed to the runtime, and `pids_limit` added.
7. **Teardown and an orphan reaper that run on crash and on cancel**, not only on the happy
   path — P0-14, a scored criterion, and `07-task-breakdown-audit.md` §1.2(a) already flags
   that it has no home in the plan.
8. **The deviation is recorded on issue #15b and in the evidence bundle, and the claim
   changes with it.** We say "container isolation with all capabilities dropped, no network
   interface, and a non-root user"; we do **not** say "rootless". Same discipline as D-008 and
   D-009: a smaller true claim beats a larger one we cannot demonstrate.

### 6.3 What I do not accept

Not as a substitution, not as a shortcut, not on D6 under gate pressure:

- Dropping egress denial for any run, including "just to fetch a dependency during the
  build". Dependencies are fetched into the image at build time or vendored; they are not
  fetched by the sandbox.
- `--privileged`, or adding back any capability without a written justification on the issue.
- Bind-mounting `/var/run/docker.sock` anywhere.
- Running the sandbox as uid 0 inside a rootful daemon **with** a network — that is the one
  combination that is materially worse than both alternatives.
- Treating condition 1 as satisfied by configuration review. It is satisfied by an executed
  test that fails to reach the network, or it is not satisfied.

### 6.4 Decision record — D-024

**Decision** — A standard (rootful-daemon) container with `--network none`, a non-root user,
`--cap-drop ALL`, `no-new-privileges`, a read-only root filesystem and runtime-enforced
resource caps is an **accepted substitute** for rootless Podman for the sandbox, subject to
the eight conditions in §6.2. Rootless remains preferred where it works without a fight.

**Options considered** —
(a) Veto the substitution; rootless Podman is required for P0-2.
(b) Accept unconditionally, as the audit's cut list proposes.
(c) Accept with binding conditions that recover the specific property rootless would have
provided.

**Pros and cons** — (a) is defensible on paper and wrong here. It puts an open-ended
infrastructure fight on D2, in front of the D3 baseline gate, to buy protection against an
actor (A6) that is out of scope, while the threats P0-2 actually names are already fully
answered by `--network none`. Podman is not even installed on the build host (SEC-11), so (a)
is a bet that an unattempted installation goes smoothly on the compressed day. (b) is not a
ruling; "record the deviation on the issue" is a note, not a control, and it silently drops
the socket-mount and capability questions that are where a rootful daemon actually gets
exploited. (c) costs six flags on one command line, keeps the D2/D3 path clear, and converts
the one property rootless was buying — no path to host root — into an explicit,
testable prohibition (condition 4) rather than a runtime side effect.

**Cost implications** — negative. (c) is cheaper than (a) by roughly a day of D2, and removes
a dependency on software not present on the build host.

**Security implications** — net positive on the threats in scope. `--network none` denies
egress and metadata access more completely than rootless Podman's default networking. The
residual risk is a container-runtime escape landing as host root rather than as an
unprivileged host uid; condition 4 removes the practical version of that, and A6 is out of
scope for this build.

**Scalability implications** — none.

**Recommendation** — (c).

**Final approval authority** — **cybersecurity.** This one is explicitly mine and I am
exercising it. The engineering-manager may sequence it; nobody else may relax the eight
conditions.

---

## 7. What I did **not** review

Silence here is not a pass. Every item below is unreviewed and must not be cited as cleared.

**Not reviewed because it does not exist yet:**

- **The model gateway (#35).** The single most security-relevant component in the system and
  the entire subject of SEC-01 and SEC-02. There is no code. Every statement I make about
  egress is about what the *container* permits, not about what the gateway does.
- **The orchestrator (#12)** and every runtime authorization decision it will make. Only the
  contract-level state machine was reviewed.
- **The sandbox runner (#14/#15a/#15b).** §6 rules on what it must do. Nothing has been built,
  so nothing was tested. `SANDBOX_POLICY` is currently a settings dict with no consumer.
- **The Astro Command Center (`apps/command-center/`).** Does not exist. **No frontend
  security review has been performed at all** — no XSS review, no review of how the API token
  is stored in the browser, no CSP validation against real page content, no review of how
  untrusted target source (file paths, compiler output, ASan stack traces, patch diffs) is
  rendered. That last one is a genuine XSS surface — attacker-influenced strings from a target
  repository rendered into a dashboard — and it is entirely unexamined.
- **JavaScript / npm dependency audit.** No `package.json` exists anywhere. `npm audit` was
  **not** run.
- **Database schema, ORM models, and migrations.** None exist. No SQL-injection review, no
  row-level authorization review, no review of what is persisted about a target repository.
- **The evidence exporter (#51)** and what a bundle contains. Redaction of the target
  repository's content in the exported report is unreviewed.

**Not reviewed because it is out of this pass's scope:**

- **Penetration testing of the running stack.** I probed the API on loopback and validated
  nginx configuration in a container. I did **not** bring `docker-compose.finale.yml` up —
  it cannot start, since `apps/command-center/dist` does not exist — so no header, TLS or
  routing behaviour was observed end to end through nginx. Everything in SEC-04, SEC-05 and
  SEC-08 about nginx is from configuration reading plus `nginx -t`, not from live traffic.
- **TLS cipher/protocol testing against a running listener.** `includes/tls.conf` was read;
  `testssl.sh` / `sslyze` were **not** run. TLS 1.2 is retained, which the file justifies.
- **The finale certificate story.** Self-signed material with a fingerprint in a runbook is
  the documented plan. I have not reviewed the runbook.
- **Host hardening of the finale machine** — OS patch level, SSH exposure, firewall, disk
  encryption. Not this repository, and not looked at.
- **Container image CVE scanning.** Images are digest-pinned (SEC-P2, met), but `trivy` /
  `grype` were **not** run against them. `trivy` is not installed on this host.
- **Semgrep / static analysis of the Python.** `semgrep` is not installed; **not run.** The
  Python review was manual reading of the auth, settings, checks, trace, state-machine and
  model-policy modules.
- **`config/env.py`** beyond `database_from_url` as quoted in the CTO review. Not read in
  full.
- **`contracts/schemas/evidence.py`, `authorization.py`, `verdict.py`** beyond the specific
  functions named in findings. The CTO reviewed the verdict derivation and I did not
  re-derive it.
- **`infrastructure/scripts/`** — `dev-up.sh`, `gen-dev-certs.sh`, `smoke-sse.sh`,
  `nginx-validate.sh`, `testing/sse-*.py`. Listed, not read. Shell scripts that run on a
  developer's machine are a real injection surface and this is a gap.
- **The `command-center.Dockerfile`.** Read only far enough to confirm it exists.
- **Competition rules on agent-authored code (#3)** and any disclosure obligation that follows
  from them. CEO-owned, still open, and it is a legal/eligibility question rather than a
  security one.

**Reviewed but with a caveat:**

- `apps/control-api/` and `infrastructure/` were snapshotted from live worktrees at
  **07:25Z** and drift-checked clean at **07:36Z**. Both are uncommitted work with agents
  active. Any finding may have been fixed between that snapshot and the time you read this;
  none of them can have been *introduced* by me, since I wrote to neither tree.
- `pytest` in the control-api tree reports **7 failures** at the snapshot: 6 in
  `test_state_machine.py` from the `verification=` / `verifications=` parameter-name mismatch
  described in SEC-07, and `test_openapi_dump.py::test_committed_dump_is_current`. These are
  in-flight, not findings, and I am recording them so the number is not mistaken for a
  regression I caused.

---

## 8. PR #74 — verdict and reasoning

### **PASS WITH CONDITIONS**

Conditions, in order of when they bind:

| # | Condition | Binds |
|---|---|---|
| C1 | **SEC-09** — the deliberately-vulnerable banner in `include/pktcfg/pktcfg.h` and every file under `src/`, `fuzz/`, `tools/` | **before merge** |
| C2 | **SEC-06** — `demo/repositories/pktcfg/.gitignore` rewritten as specified | **before merge** |
| C3 | **SEC-10** — root `SECURITY.md`, `demo/repositories/README.md`, root `LICENSE` | **before the repository is made public**, and before its URL appears in any submission. Does not block this merge. CEO-owned. |

Nothing in this PR blocks it. C1 and C2 are edits inside the PR's own file set and are a few
minutes each.

### The author's three questions, answered

**"Does a repository shipping a deliberately vulnerable parser plus a working reproducer need
anything beyond the README disclosure?"**

**Yes — three things, all cheap, none of which is "take it out".**

The README is the best disclosure I have read in this repository: class, CWE-787 and CWE-131,
`file:line` for root cause, allocation site and crash site, trigger condition, exact overflow
size, reproducer path, and an authorization paragraph that says who wrote it and why. It is
not the problem. The problem is that it is the *only* place the disclosure exists.

1. **Disclose at the point of use, not only in the README** (SEC-09). `src/decode.c:1-10`
   does this correctly and is the model. `include/pktcfg/pktcfg.h` — the file a code search
   lands on and the file someone copies — says "Purpose-built controlled demo target", which
   does not tell anyone the code is unsafe.
2. **Scope the fixture out of vulnerability reports at the repository root** (SEC-10). Without
   a `SECURITY.md`, the first thing that happens after the repo opens is a report, or a
   scanner alert, against a defensive-security project. That is a competition-window tax for
   zero benefit.
3. **Stop the directory growing uncontrolled fuzzer output** (SEC-06). This is the one that
   is actually about security rather than presentation, and it is covered below.

**"Do the crash artifact and corpus belong in git at all?"**

**These nine files: yes, unambiguously, and removing them would be the wrong call.**

- P0-8 is "crash capture + minimized input that reproduces deterministically **from a clean
  build**", and `23-security-plan.md` requires the input snapshot and reproducer to be hashed
  into the evidence bundle. A reproducer that is not in the repository cannot reproduce from
  a clean checkout, and cannot be hashed into a bundle a judge can verify. The crash file is
  a **first-class product artifact**, not build spill.
- They are not dangerous. I dumped every one:
  ```
  crash/crash-literal-tab.bin         22 bytes  504b54430101000007000300636f6c756d6e73610962
  corpus/seed-bad-magic.bin            8 bytes  5858585801000000
  corpus/seed-empty.bin                8 bytes  504b544301000000
  corpus/seed-escaped-tab.bin         29 bytes  504b54430101000007010a00636f6c756d6e73636f6c315c74636f6c32
  corpus/seed-escaped.bin             30 bytes  504b54430101000006010c0062616e6e65726c696e65315c6e6c696e6532
  corpus/seed-hex.bin                 27 bytes  504b54430101000003010c007261775c7834315c7830305c783432
  corpus/seed-multi.bin               54 bytes  504b544301030000040006006d6f646573747269637406000a00726567696f6e61702d736f7574682d31070001007265747269657333
  corpus/seed-simple.bin              22 bytes  504b544301010000040006006d6f6465737472696374
  corpus/seed-truncated.bin           20 bytes  504b544301010000040006006d6f646573747269
  ```
  Eight to fifty-four bytes of malformed configuration packet for a wire format that exists
  nowhere outside this repository. No shellcode, no ROP chain, no heap-grooming, no
  exploitation primitive of any kind. The defect writes the ASCII space character `0x20`
  three bytes past a heap allocation — an attacker controls neither the value written nor the
  length. There is no memory-safety weapon here to publish.
- The fixture is not reachable from product code. `grep -rn pktcfg apps/ infrastructure/
  packages/` returns nothing, and the `CMakeLists.txt` has **no `install()`, no
  `add_subdirectory`, no `FetchContent`, no `export()`** — a static library that nothing links
  and nothing can package.

**What does not belong in git is *generated* output, and today nothing stops it** (SEC-06).
libFuzzer writes `crash-<sha>`, `leak-<sha>`, `oom-<sha>`, `timeout-<sha>` and
`slow-unit-<sha>`, and grows the corpus directory; of those, only `crash-*` is ignored
anywhere in the repository, and corpus growth is ignored nowhere. Worse, the pattern that does
exist ignores the *wrong* thing: `crash-*` silently swallows any **new** reproducer written
into `crash/`, so a re-minimized input never appears in `git status` and the repository's copy
goes stale while the author's local demo passes. The `!crash/` line does not fix this — a
directory negation cannot re-include a file an earlier pattern excluded.

That matters beyond this fixture. The moment a mission fuzzes a target that is *not* `pktcfg`,
the generated inputs are byte sequences derived from that repository's content, and a
`git add -A` commits them to a repository the CEO may make public. That is the only real
source-leakage path I found in this PR's blast radius, and it is four lines of `.gitignore`.

**"Would anything here be a problem if the repo went public tomorrow?"**

Three things, none of them the vulnerability itself:

1. **SEC-09.** A clean, warning-free, tested C parser with no warning in its header is a thing
   people copy.
2. **SEC-10.** A vulnerability report or a code-scanning alert against a defensive-security
   project during a judged window, plus no `LICENSE`, which leaves the PR's own "no third
   party's IP is involved" assertion unbacked.
3. **SEC-06**, which becomes materially worse in a public repository.

What is **not** a problem, and I want this on the record so nobody over-corrects: publishing a
purpose-built vulnerable fixture with its reproducer, under a clear disclosure, for a system
that exists to find and fix such defects, is **normal and correct practice**. This is what
OSS-Fuzz targets, the Juliet suite, and every fuzzing benchmark corpus do. The alternative —
a demo whose reproducer cannot be verified by anyone else — is worse for a project whose
entire pitch is deterministic evidence.

### What I verified myself, rather than taking from the PR body

I do not sign off on a PR's own evidence block. Re-run in this session, from a clean worktree
at `fdc4033`, host toolchain (cmake 4.2.3, Apple clang 21.0.0, arm64):

```
=== ctest under ASan/UBSan ===
100% tests passed, 0 tests failed out of 8

Label Time Summary:
asymmetry    =   0.23 sec*proc (1 test)

=== reproducer ===
==94389==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x6020000000f4 …
WRITE of size 1 at 0x6020000000f4 thread T0
    #0 in emit_tab decode.c:31
    #1 in pkt_decode_into decode.c:136
    #2 in pkt_parse parse.c:114
    #3 in pktcfg_fuzz_one_input fuzz_entry.c:14
0x6020000000f4 is located 0 bytes after 4-byte region [0x6020000000f0,0x6020000000f4)
allocated by thread T0 here:
    #1 in pkt_parse parse.c:108
SUMMARY: AddressSanitizer: heap-buffer-overflow decode.c:31 in emit_tab
```

Green sanitized baseline, and the reproducer reproduces, at the `file:line` the README claims.

I also read `src/parse.c` and `src/decode.c` line by line looking for a **second, unintended**
defect, because that is the failure that would actually hurt: a fuzzer finding a crash that
neither candidate patch fixes, live, on D6. I found none. The framing checks hold —
`size - off` cannot underflow at `parse.c:80` because `off` never exceeds `size`;
`parse.c:93`'s arithmetic is guarded by the `PKT_ENTRY_HDR` check above it; every error path
frees through `pkt_config_free` with `cfg->count` correctly reflecting the entries actually
allocated. The tree is exactly as advertised: one seeded defect, in one function, with a
correct fix and a tempting wrong one. `detect-secrets --all-files demo/` returns **0 findings**.

That is unusually disciplined work and I would rather say so than only list conditions.

---

## 9. Decision records to fold into `.project/decisions.md`

I have not edited the log — implementation agents are live and would collide. The orchestrator
should append:

- **D-023** — The no-external-inference invariant is enforced at the container network layer,
  not only by settings validation. Until SEC-01 and SEC-02 close, the evidence-facing claim is
  downgraded to the §5.2 permitted wording and four stronger forms are prohibited. §5.4.
  *Authority: cybersecurity for the control and the severity; **CEO for the claim wording and
  for any risk acceptance.***
- **D-024** — A rootful container with `--network none`, a non-root user, `--cap-drop ALL`,
  `no-new-privileges`, a read-only root filesystem and runtime-enforced resource caps is an
  accepted substitute for rootless Podman, subject to eight binding conditions. §6.4.
  *Authority: **cybersecurity**, exclusively.*
- **D-025** — Dependency policy SEC-P1…P4: `==` pins, digest-pinned images, `pip-audit` and
  `npm audit` in CI failing on High, and an audit run pasted in any PR adding a runtime
  dependency. §3. *Authority: cybersecurity, with CI implementation on #11.*

---

## 10. Summary table

| ID | Severity | Title | Location | Owner | Blocks |
|---|---|---|---|---|---|
| SEC-01 | **CRITICAL** | control-api has unrestricted internet egress | `docker-compose.finale.yml:113-115` | infra (#78) | **finale deployment; the strong claim** |
| SEC-02 | HIGH | Allowlist accepts metadata endpoints and an IDNA homograph of `api.openai.com` | `contracts/model_policy.py:58-70,95,99` | control-api (#78) | closing #78 |
| SEC-03 | HIGH | Finale-only system checks never run in the finale stack | `settings/base.py:28`, `settings/finale.py`, `docker-compose.finale.yml:95-108` | control-api | — |
| SEC-04 | MEDIUM | `client_max_body_size 0` + unsized `/tmp` tmpfs = unauth memory-exhaustion DoS | `nginx/nginx.conf:65`, `docker-compose.finale.yml:44-47` | infra | — |
| SEC-05 | MEDIUM | `/openapi.json` and `/docs` unauthenticated in finale; docs fetch a third-party CDN | `api/api.py:48-49`, `conf.d.finale/brahmadatta.conf:85-88` | control-api + infra | — |
| SEC-06 | MEDIUM | `.gitignore` misses fuzzer output; silently ignores future reproducers | `demo/repositories/pktcfg/.gitignore:2-3`, root `.gitignore:33-37` | demo-target + infra | **PR #74 merge** |
| SEC-07 | MEDIUM | A cross-mission `VerificationRecord` satisfies the verdict gate | `contracts/state_machine.py:210-246` | control-api (#77) | closing #77 |
| SEC-08 | LOW | Dev nginx guards `/admin/`; Django serves `/django-admin/` | `profile/admin-allow.conf:16`, `config/urls.py:25` | infra | — |
| SEC-09 | LOW | Fixture's public header does not disclose the seeded defect | `demo/repositories/pktcfg/include/pktcfg/pktcfg.h:1-4` | demo-target | **PR #74 merge** |
| SEC-10 | LOW | No root `SECURITY.md` scoping the fixture out of vulnerability reports | repository root | CEO | **repository publication** |
| SEC-11 | INFO | `SANDBOX_RUNTIME` defaults to `podman`, not installed on the build host | `settings/base.py:132` | infra | — |

**Verdict: BLOCKED on the finale stack while SEC-01 is open. PR #74 is PASS WITH CONDITIONS
and is not blocked.**

---

*This review edits no other role's files, does not touch `.project/decisions.md`, and changes
no code. Every command quoted was executed in this session against the trees named in the
header, and the output is verbatim. Sections not executed are listed in §7.*

---

## 11. Addendum — 2026-08-07 07:45Z, after the infra branch committed

The infra agent committed while this review was being written. Re-checked, not assumed:

**Every file I filed a finding against is byte-identical to what I reviewed.** Verified by
`diff` of `feat/infra-nginx-compose` against my 07:25Z snapshot for
`docker-compose.finale.yml`, `nginx/nginx.conf`, `conf.d.finale/brahmadatta.conf`,
`profile/admin-allow.conf` and the root `.gitignore`. **SEC-01, SEC-04, SEC-05, SEC-06 and
SEC-08 stand unchanged.**

**One correction to §3.** §3 states there are no workflows in the repository. That was true of
`main` at `180bd6f`, which is what it says — but `.github/workflows/ci.yml` has since landed
on `feat/infra-nginx-compose` (commit `a987616`) and I had not seen it. Re-read:

- It has a **`secrets-guard` job** asserting no environment file, key or certificate is
  tracked, and no private key material sits inside a tracked file. That is good work and it
  independently enforces §4's result. Credit where due.
- It has **no dependency audit job.** `pip-audit` and `npm audit` appear nowhere.

**SEC-P3 therefore remains not met**, for the narrower reason that the workflow exists and
does not audit dependencies — not because no CI exists. The requirement stands: `pip-audit -r
requirements-dev.txt` and, once `apps/command-center/` exists, `npm audit --omit=dev`, both
failing the build on any advisory of High or above. Both are a five-line job in a file that
now exists.

The rest of that commit — `finale-up.sh`, `astro-check.mjs`, `certbot-webroot/`, the ingress
contract doc, and the remaining workflow jobs — landed after my snapshot and is **not
reviewed**. Add it to §7.

---

## 12. Re-verification — 2026-08-07 08:20Z · SEC-01 CLOSED

Run against **PR #87 head (`a853e80`) with PR #91's `infrastructure/`, `.gitignore`,
`.github/workflows/ci.yml` and `tests/` overlaid** — the combined tree I asked for. Executed,
not inspected.

### 12.1 SEC-01 — **CLOSED. Signed off.**

Ran their `infrastructure/scripts/finale-egress-evidence.sh` first. I read it before running
it, and it is built correctly: it execs into the **real running finale container** and opens a
socket rather than inspecting configuration, it carries a **control** (Postgres must still be
reachable, so "nothing is reachable" cannot pass as a broken container), it prints raw output
before the verdict, and it treats a parse failure as a failure rather than a pass.

```
== container identity and network attachments (from Docker, not from the compose file)
  networks: brahmadatta-finale_api brahmadatta-finale_backend
  user: app:app  read_only: true  privileged: false
  routing table inside the container:
    Iface  Destination  Gateway   Flags  ...  Mask
    eth1   000016AC     00000000  0001        0000FFFF
    eth0   00001FAC     00000000  0001        00FFFFFF

  { "cloud-metadata":         { "detail": "OSError: [Errno 101] Network is unreachable", "reached": false },
    "hosted-inference-api":   { "detail": "gaierror: [Errno -3] Temporary failure in name resolution", "reached": false },
    "hosted-inference-api-2": { "detail": "gaierror: [Errno -3] Temporary failure in name resolution", "reached": false },
    "internet-by-ip":         { "detail": "OSError: [Errno 101] Network is unreachable", "reached": false },
    "postgres-in-stack":      { "detail": "CONNECTED", "reached": true } }

  PASS no external target reachable from inside control-api
  PASS postgres IS reachable from inside control-api (the control: the container works)

finale egress evidence: PASS
```

**No `00000000` destination in the routing table. There is no default route.** `Network is
unreachable` is the kernel refusing, not a library declining — which is the whole distinction
between structural and intentional.

I do not sign off on someone else's target list, so I ran my own from inside the same
container:

```
  2606:4700:4700::1111            :443   blocked   OSError: [Errno 101] Network is unreachable
  8.8.8.8                         :53    blocked   OSError: [Errno 101] Network is unreachable
  1.0.0.1                         :80    blocked   OSError: [Errno 101] Network is unreachable
  169.254.169.254                 :80    blocked   OSError: [Errno 101] Network is unreachable
  fd00:ec2::254                   :80    blocked   OSError: [Errno 101] Network is unreachable
  100.100.100.200                 :80    blocked   OSError: [Errno 101] Network is unreachable
  metadata.google.internal        :80    DNS FAIL  (gaierror)
  cdn.jsdelivr.net                :443   DNS FAIL  (gaierror)
  pypi.org                        :443   DNS FAIL  (gaierror)
  github.com                      :443   DNS FAIL  (gaierror)

  db                              :5432  *** REACHED *** ('172.22.0.3', 5432)
  redis                           :6379  *** REACHED *** ('172.22.0.2', 6379)

  proxy vars in container env: NONE
```

**IPv6 is closed too**, all four cloud-metadata variants are closed, and there is no
`HTTP_PROXY`/`HTTPS_PROXY` in the container environment — the three things I would have used
to get around a fix that only removed the IPv4 default route.

**And the fix does not break the demo**, which I checked because a security fix that kills
ingress is not a fix:

```
  GET /api/v1/system/health  -> HTTP 200  (http/2)
  GET /api/v1/missions       -> HTTP 401
  GET /django-admin/         -> HTTP 404
  GET /admin/                -> HTTP 404
```

end to end through the published TLS listener, with `nginx -> control-api` returning a live
health body over the `api` network.

The topology is what I asked for, and one thing better: `api` (nginx↔control-api) and `edge`
(nginx↔Astro) are **separate** `internal: true` networks rather than one shared ingress
network, so giving the dev server a route out later cannot silently hand egress to the process
holding snapshots. I did not ask for that and it is the right call.

### 12.2 SEC-02 — **NOT FIXED. Every bypass still passes.** Downgraded to MEDIUM.

Run inside the built finale image, so this is the code that would ship:

```
  [ok  ] False hosted provider              https://api.openai.com/v1
  [ok  ] True  loopback (must pass)         http://127.0.0.1:8080/v1
  [FAIL] True  AWS/Azure/GCP metadata IP    http://169.254.169.254/
  [FAIL] True  EC2 IMDS over IPv6           http://[fd00:ec2::254]/latest/meta-data/
  [FAIL] True  GCP metadata by name         http://metadata.google.internal/computeMetadata/v1/
  [FAIL] True  Alibaba metadata (CGNAT)     http://100.100.100.200/latest/meta-data/
  [FAIL] True  bare 'metadata'              http://metadata.internal/
  [FAIL] True  IDNA homograph U+3002        http://api。openai。com/v1
  [FAIL] True  bare label                   http://openai/v1
  [FAIL] True  IPv4-mapped metadata         http://[::ffff:169.254.169.254]/
  [FAIL] True  unspecified addr             http://0.0.0.0:8080/

MISMATCHES: 10
```

**I am downgrading it HIGH → MEDIUM, and it is no longer a blocker.** Not because the code
improved — it is untouched — but because SEC-01's fix removed its exploit path. Set
`MODEL_ENDPOINTS` to the homograph today and the process still cannot open the socket. That is
precisely what defence in depth is supposed to look like when the outer layer holds, and it is
the strongest possible argument that fixing SEC-01 was the right priority.

It still has to be fixed, for two reasons that survive the network boundary:

1. **The compose topology is not the only way this runs.** `docs/04-development/31-development-setup-guide.md`
   documents a bare `uvicorn`/`manage.py runserver` on a laptop, which has a full default
   route. In that mode the validator is the *only* control, and it currently waves through
   the metadata endpoint and a homograph of `api.openai.com`.
2. **A control that returns the wrong answer is worse than no control**, because people build
   on it. `is_local_inference_endpoint("http://metadata.google.internal/")` returning `True`
   is a function whose name is a lie, and the next person to reuse it will not re-derive the
   four bypasses.

Fix is unchanged from §2 SEC-02: IDNA-normalise before deciding, explicit metadata/link-local
deny list rather than `is_global`, reject a leftmost `metadata` label, and replace the
bare-label pass with a settings-driven service-name allowlist — plus the table above as a
test.

### 12.3 Can #78 close?

**Yes — on one condition: SEC-02 is re-filed as its own issue, with an owner and a milestone,
before #78 is closed.** Not after.

#78's Critical is closed and verified. Its second acceptance box ("link-local, loopback-to-
elsewhere and metadata addresses are explicitly rejected by the validator") is not ticked and
must not be ticked. Closing an issue with a live unticked box and nothing tracking it is how
findings get lost, and this one has ten failing cases. With SEC-02 re-filed, #78 has done its
job and should close so the board reflects reality.

### 12.4 The claim — **the strong form is now defensible.** Wording for the CEO.

I pre-authorised a sentence in §5.2 conditional on this test passing. Every clause of it is now
true and I verified each one myself. **Approved for the identity doc, the slides, and the
evidence bundle:**

> The control-plane process that holds the repository snapshot runs on a network with no
> default route. It can reach the database and the local model host, and nothing else. This is
> enforced by the container network, not by configuration — and here is the test that attempts
> egress from inside that container and fails.

Two bindings on it, and they are not pedantry:

- **It is a claim about the finale stack, not about the software.** True of
  `docker-compose.finale.yml`. Not true of a bare `uvicorn` on a laptop. If anyone demonstrates
  from anything other than the compose stack, the claim lapses. Say *"the system as deployed"*,
  not *"the system"*.
- **"and the local model host" is currently vacuous** — there is no model host. When #35/#36
  land, the model host must be on an `internal: true` network and I re-run this test before
  the claim is made again. Until then the honest form of that clause is *"the database, and
  the local model host when it is running"*.

Everything I prohibited in §5.2 stays prohibited, with one narrowing: **"the system cannot
reach the internet" is now defensible about the control plane specifically** — `Network is
unreachable`, from the kernel — but **not about the stack as a whole**, because nginx is on a
routable network by design and a dev-only `npm ci` installer is too. Phrase it as *"the process
holding repository content cannot reach the internet"*. That is both stronger and true;
"the system cannot reach the internet" is weaker-sounding and false.

### 12.5 D-036 and D-037 against what I actually meant

**D-036 — satisfies condition 4, and exceeds it. Accepted without reservation.**

I asked that the runtime socket never be mounted and that a test assert it. D-036 does that and
adds `privileged`, host namespaces, host-root bind mounts, and `SYS_ADMIN`/`SYS_PTRACE`/
`SYS_MODULE`/`SYS_RAWIO`/`NET_ADMIN`/`ALL` capabilities, asserted structurally against both
compose files **and** by a text scan of every tracked file — which catches a
`docker run -v /var/run/docker.sock` inside a shell script or a workflow, a hole my condition
did not name and should have.

I negative-controlled it rather than trusting the green:

```
  injected a docker.sock bind mount into the nginx service
FAILED test_no_container_mounts_a_container_runtime_socket[docker-compose.yml]
FAILED test_no_tracked_file_mounts_the_docker_socket
2 failed, 6 passed
```

Two independent detections. The test is real. `8 passed` on the clean tree.

**D-037 — approximates what I meant. One residual, Low.**

The important half is right and is better than I specified: patterns now match at any depth,
the full libFuzzer artifact set is covered (`crash-*`, `leak-*`, `timeout-*`, `oom-*`,
`slow-unit-*`), plus `*.profraw`, `*.profdata`, `*.sancov`, `*.sarif`. `16 passed`.

The residual is the re-include shape. I specified **exact-name** negations
(`!corpus/seed-*.bin`, `!crash/crash-literal-tab.bin`); what landed is **directory-wide**
(`!demo/repositories/*/corpus/**`, `!demo/repositories/*/crash/**`). Those two directories are
therefore fully re-admitted, including generated output:

```
  demo/repositories/pktcfg/corpus/5a9fd3195d289986674f806c7274b7e8f27ddbe1 -> *** COMMITTABLE ***
  demo/repositories/pktcfg/corpus/crash-8f3a1c                             -> *** COMMITTABLE ***
  demo/repositories/pktcfg/crash/crash-8f3a1c                              -> *** COMMITTABLE ***
  demo/repositories/pktcfg/crash/leak-deadbeef                             -> *** COMMITTABLE ***
  demo/repositories/othertarget/corpus/abc123                              -> *** COMMITTABLE ***
```

That matters because **libFuzzer grows its corpus in place**: `./pktcfg_fuzz corpus/` writes
new interesting inputs into `corpus/`, which is the natural invocation and the one the README
implies. D-037's own title — "generated fuzzer output is not committable" — is not true of the
two directories it exempts. The test passes because its case list probes `fuzz-out/` and the
authored seeds, never a generated name inside `corpus/`.

**SEC-06-R (LOW)** — replace the four directory negations with:

```gitignore
demo/repositories/*/corpus/*
!demo/repositories/*/corpus/seed-*
!demo/repositories/*/crash/crash-literal-tab.bin
```

and add three cases to `test_fuzz_artifacts_are_ignored.py`:
`demo/repositories/pktcfg/corpus/5a9fd319…`, `demo/repositories/pktcfg/corpus/crash-8f3a1c`,
`demo/repositories/pktcfg/crash/leak-deadbeef` — all three asserted **ignored**.

### 12.6 CI — **yes, and the CTO's cut does not apply to what I am asking for**

Asked whether the egress test specifically has to go back into CI. It does, but that is not
the sharpest thing I found. This is:

```
  what pytest actually collects in CI:  testpaths = contracts/tests api/tests
  CI runs: cd apps/control-api && pytest -q   ->  tests/architecture/ is NOT collected
```

**`tests/architecture/` runs nowhere automatically.** That includes
`test_container_isolation.py` and `test_fuzz_artifacts_are_ignored.py` — the two files D-036
and D-037 cite as the reason those decisions are enforceable. Right now they are documentation
that happens to be executable. **D-036's test not running means condition 4 of §6.2 is not met,
and condition 4 is the condition under which I accepted the isolation substitution.** I am not
willing to leave that state.

I am **not** asking to reverse the CTO's two-job cut. That cut was argued on runner minutes
against lint matrices, type-check matrices and coverage gates, and it was a reasonable call.
It does not reach what follows, because what follows costs nothing.

**SEC-R1 — REQUIRED. CI collects `tests/architecture/`.** Measured on this tree:
`test_container_isolation.py` **0.09 s**, `test_fuzz_artifacts_are_ignored.py` **0.12 s**. No
Docker, no network, no build. One line added to the existing `pytest` job. A cost argument
cannot be made about 0.21 seconds, and without it two security decision records are
unenforced.

**SEC-R2 — REQUIRED. A static compose-topology test, in `tests/architecture/`.** SEC-01 —
the Critical — currently has **no automatic regression guard at all**. Nothing fails if
someone re-adds `- external` to `control-api` to make something work at 2am, which is exactly
how it got there the first time. `egress-test.sh` needs Docker, but **its topology half only
parses `docker compose config`** and ports to pure Python with PyYAML, which the architecture
tests already depend on. I wrote the check to prove the cost:

```
  docker-compose.finale.yml
    routable networks: ['external']
      external: members=['nginx']  OK
  docker-compose.yml
    routable networks: ['external']
      external: members=['nginx', 'command-center-deps']  *** VIOLATION ***

  elapsed: 11.1 ms  (no Docker, no network, no build)
```

Eleven milliseconds, and it immediately surfaced a second member of the routable network that
I would otherwise have missed. **`command-center-deps` is acceptable** — I read it: a
short-lived `npm ci` container that holds no repository content, is dev-only, exits before the
dev server starts, and the long-running `command-center` deliberately has no `external`. That
is a good design and the comment explaining it is correct.

But it is the point exactly: the difference between "a reviewed exception" and "drift" is
whether something checks. **Spec:** assert that the members of every non-`internal` network are
exactly an allowlist declared in the test — `{"nginx"}` for the finale file,
`{"nginx", "command-center-deps"}` for dev — with the reason for each exception in a comment,
and a docstring saying that changing the allowlist is a `cybersecurity` review, not a test fix.

**SEC-R3 — recommended, not required.** `finale-egress-evidence.sh` needs a full stack build;
Docker-in-CI on every PR is a real cost and I am not demanding it. Run it at **each rehearsal
and once before submission**, recorded in `docs/10-competition/36-hour-finale-runbook.md`. The
static guards above catch the regression that actually happens; this one catches the exotic
case (a host route, a stray `docker network connect`) and a rehearsal cadence is proportionate
to that.

So: the answer is **yes, the egress check goes back into CI — as the free static half.** The
expensive dynamic half stays a rehearsal gate.

### 12.7 `SECURE_PROXY_SSL_HEADER` in the development profile — reframed

The infra seat flagged that `SECURE_PROXY_SSL_HEADER` is set only in `finale.py:28` so
"development carries the same defect". I read it and **the defect is the other way round**,
which matters because fixing the stated version would be the wrong change.

Setting `SECURE_PROXY_SSL_HEADER` is dangerous only when nothing overwrites the header.
`includes/proxy-headers.conf:28` overwrites `X-Forwarded-Proto` on every request in both
profiles, so setting it is safe. **Not** setting it in development is a correctness bug:
`request.is_secure()` is `False` behind the TLS listener, `build_absolute_uri()` emits `http://`,
and the generated OpenAPI `servers` block carries the wrong scheme and port — which is the CTO's
C7 poisoning the frontend client. The infra seat has already written the test for it, and it is
the one failing test in the combined tree:

```
FAILED tests/architecture/test_ingress_contract.py::test_use_x_forwarded_host_is_enabled
  Add to apps/control-api/config/settings/base.py:
      USE_X_FORWARDED_HOST = True
      SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
```

**Ruling.** Both settings move to `base.py`, paired with the strict `ALLOWED_HOSTS` that is
what makes trusting a client-supplied Host safe. That is safe **because** control-api publishes
no host port and shares a network only with nginx. Owner: control-api, on #9. This is C7, not a
new finding, and the test that already exists is its acceptance criterion.

**The genuinely security-relevant half is one line away and was not flagged.**

**SEC-14 (LOW)** — `infrastructure/compose/images/control-api.Dockerfile:64`, the `dev` target:

```
     "--proxy-headers", "--forwarded-allow-ips", "*", \
```

The `runtime` target scopes this correctly (`:88`, `${UVICORN_FORWARDED_ALLOW_IPS:-127.0.0.1}`,
set to the `api` subnet by the finale compose file) and the Dockerfile comment at `:83-85`
explains exactly why `*` is wrong — then the `dev` target does it anyway. `*` means uvicorn
trusts `X-Forwarded-For` and `X-Forwarded-Proto` from **any** peer, so any container that
reaches control-api on the `api` network can forge the client IP into the access log and make
Django believe a plaintext request arrived over TLS. Low, because control-api has no published
port and only nginx is on that network — but the fix is to use the same
`${UVICORN_FORWARDED_ALLOW_IPS:-127.0.0.1}` form in the `dev` target and set it in
`docker-compose.yml`, which is a one-line change on a file that already has the correct pattern
eight lines below.

### 12.8 Status of every finding after re-verification

| ID | Was | Now | Note |
|---|---|---|---|
| **SEC-01** | CRITICAL | **CLOSED ✅** | Verified twice by me, from inside the running container. Ingress confirmed unbroken. |
| SEC-02 | HIGH | **MEDIUM, open** | Untouched; all 10 bypasses pass. Downgraded because SEC-01 removed the exploit path. Re-file as its own issue. |
| SEC-03 | HIGH | **HIGH, open** | `APP_ENV` still env-driven (`base.py:28`); neither `finale.py` nor `docker-compose.finale.yml` sets it. My `.env` is why health read `finale`. |
| SEC-04 | MEDIUM | **MEDIUM, open** | `client_max_body_size 0` unchanged; `tmpfs: - /tmp` still unsized. |
| SEC-05 | MEDIUM | **MEDIUM, open** | Confirmed live through nginx: `/api/v1/openapi.json` **200**, `/api/v1/docs` **200**, unauthenticated. |
| SEC-06 | MEDIUM | **LOW (SEC-06-R)** | D-037 fixed the important half. Residual: directory-wide re-includes re-admit generated output into `corpus/` and `crash/`. |
| SEC-07 | MEDIUM | **MEDIUM, open** | `assert_transition` still takes no `mission_id`. Tracked on #77. |
| SEC-08 | LOW | **LOW, open** | `admin-allow.conf:16` still `^~ /admin/`; `urls.py:25` still `django-admin/`. |
| SEC-09, SEC-10 | LOW | open | PR #74 conditions; unchanged. |
| **SEC-12** | — | **MEDIUM, new** | `tests/architecture/` is not collected by CI. D-036 and D-037 are unenforced. See SEC-R1. |
| **SEC-13** | — | **MEDIUM, new** | No static regression guard on the SEC-01 topology. See SEC-R2. |
| **SEC-14** | — | **LOW, new** | `--forwarded-allow-ips "*"` in the Dockerfile `dev` target. |

**Overall posture: no Critical open. The BLOCKED verdict of §0 is lifted.** The finale stack
is cleared for deployment on the egress axis, and the strong claim is approved with the two
bindings in §12.4. SEC-R1 and SEC-R2 are required to keep it that way; without them the
control that closed the Critical has nothing watching it.

**PR #91: APPROVED.** Its `infrastructure/` half is the best security work in the repository so
far — the topology fix, the separate `api`/`edge` split I did not ask for, D-036 with a test
that survives a negative control, and an evidence script honest enough to carry its own control
case. SEC-04, SEC-05, SEC-08 and SEC-14 are in its files and are all Medium or Low; they are
follow-ups, not merge blockers.

---

## 13. Round 2 — 2026-08-08 · PR #110 `feat/state-machine` · the mission state machine

Required by architecture spec §4.3 and D-045. This is the adversarial pass: I tried to reach a
terminal `VERIFIED` state improperly and to defeat the D-046 candidate freeze. The `qa-engineer`
seat is running the lock-dependent properties against real PostgreSQL in parallel — **I did not
reproduce their work and everything below is single-threaded**, which is the same limitation the
author declared. Every result in this section came from a command I ran in this session against
`origin/feat/state-machine` at `4db0212`, in an isolated worktree.

**Verdict: PASS WITH CONDITIONS.** No Critical. Three findings (SEC-15, SEC-16, SEC-18) are merge
conditions. SEC-15 becomes Critical the moment an HTTP route is wired to `record_verification`.

### 13.0 What the author got right, because it is most of the file

The round-1 hole is properly closed and I could not reopen it. Stated first because the rest of
this section is findings, and the ratio would otherwise mislead.

```
[BLOCKED]  A1 duck-typed object with .verdict          VerificationRequiredError
[BLOCKED]  A2 another mission's VERIFIED record        VerificationRequiredError
[BLOCKED]  A3 required gate NOT_RUN -> verdict         derive_verdict=HUMAN_REVIEW_REQUIRED
[BLOCKED]  A4 confidence=0.99 smuggled onto GateResult ValidationError
[BLOCKED]  B1 record_patch_candidate() after VERIFY started    CandidateSetFrozenError
[BLOCKED]  B5 re-verify the same candidate until it passes     IntegrityError
[BLOCKED]  C1 pause in VERIFY -> resume into BASELINE          InvalidStateTransitionError
[BLOCKED]  C2 stale paused_from lets a 2nd pause resume backwards  InvalidStateTransitionError
[BLOCKED]  C3 second BaselineReport for one mission            IntegrityError
```

C2 is worth naming: I specifically attacked `paused_from` as a stale value — pause in `BASELINE`,
resume, walk forward to `VERIFY`, pause again — on the theory that a marker set on the way in and
never cleared would let the second pause resume into the first pause's origin. It is cleared:

```
after resume, paused_from = None
after 2nd pause, paused_from = 'VERIFY'
```

`transitions.py:161-162` clears it on the way out, and `BaselineReport.mission` is a
`OneToOneField` underneath. **`paused_from` does prevent a mission resuming backwards into
`BASELINE` and writing a second baseline for one snapshot.** That is the denominator of the
"regression preserved" claim and it holds, at both layers, on this branch.

`derive_verdict` also holds against the confidence axis: `GateResult` is `extra="forbid"`, gate
status is a four-valued enum, and there is no numeric field on the path from evidence to verdict.
I found no route from a confidence value to a verdict.

### 13.1 A correction to the framing of BUG-004(c), which changes what the test has to prove

The brief — and D-045 — describe the uncatchable case as *"a set with a `REJECTED` record
dropped"*. Executed, that framing is wrong, and it matters:

```
  [VERIFIED, REJECTED]      -> VERIFIED
  [VERIFIED]                -> VERIFIED
  [VERIFIED, HUMAN_REVIEW]  -> HUMAN_REVIEW_REQUIRED
```

`derive_mission_verdict` (`contracts/verdict.py:215-222`) is **any-VERIFIED-wins**. Dropping a
`REJECTED` record therefore cannot change the mission verdict — it is a no-op, and a guard that
refused it would be refusing nothing. The drop that *does* change the answer is
`HUMAN_REVIEW_REQUIRED`, which outranks everything.

My first attempt at this attack passed its control case and I discarded it. The author's test is
not making that mistake: `test_a_dropped_rejection_cannot_reach_verified`
(`orchestrator/tests/test_verdict_completeness.py:85-126`) is **named** for the rejection case but
its body builds `VERIFIED` + a `NOT_RUN` regression gate — i.e. the `HUMAN_REVIEW` case, the one
that bites. The test is correct and the name is not. See SEC-23(c).

Anyone re-deriving this later should take the corrected rule: **the record whose removal reaches
`VERIFIED` is a `HUMAN_REVIEW_REQUIRED` one, not a `REJECTED` one.**

---

### SEC-15 · **HIGH** · `record_verification` never checks the patch belongs to the mission — this defeats D-046 through the sanctioned API

**Location** — `apps/control-api/orchestrator/candidates.py:216-267`, the write at `:253-256`.
`patch_id` arrives as a parameter and is assigned straight to the foreign key. Nothing compares
`PatchCandidate.mission_id` to `mission_id`.

**Why it matters more than a referential-integrity nit.** D-046 freezes *the candidate set of one
mission*. It does not freeze the set of candidates that can be *verified into* that mission,
because the verification writer never asks which mission a candidate came from.

**Exploit scenario, executed — no direct ORM writes, only the sanctioned orchestrator API:**

```
  mission A frozen at 2026-08-08 02:57:27.014369+00:00
  mission A verdict now: REJECTED
  record_verification(mission=A, patch=B's) -> ACCEPTED, record 024fa10d-4508-4dde-b29c-efb3c444fe61
    record.mission_id       = 828aa0ce-e296-41de-9dd9-8278d1434747
    record.patch.mission_id = b0431815-cf9d-4255-90f7-a3ad21f0f035
    -> they differ; nothing in record_verification compares them
  mission A verdict now: VERIFIED
  mission A terminal state: VERIFIED, verdict VERIFIED
  candidates belonging to mission A: 1 (all REJECTED); verification records on A: 2
```

Mission A's own candidate set contains exactly one candidate and it was `REJECTED`. Mission A is
frozen, so `record_patch_candidate` correctly refuses to add another. The attacker creates a
second mission — an ordinary operator action — adds a candidate there, and verifies *that*
candidate into mission A. Mission A reaches terminal `VERIFIED`.

**This is generate-until-pass with one extra step, and it needs no transition-table change, no
direct database write, and no convention broken.** It is the exact failure mode
`orchestrator/candidates.py`'s own module docstring says the file exists to prevent. Every guard
in the chain behaves as designed: `assert_verdict_is_evidenced` sees a real `VerificationRecord`
whose `mission_id` is A's, because the row genuinely was written against A.

The mission-binding check at `state_machine.py:422` is bypassed not by forging a record but by
**relabelling one at creation time** — the check reads the column the attacker got to set.

**Not Critical today, and here is the bright line.** The HTTP routers still return 501 (the
author declares this), so no network-reachable caller supplies `patch_id`. The attack needs
in-process access. **The moment a route calls `record_verification` with a `patch_id` taken from
a request body, this is Critical and I will rate it so** — that is the next PR, so fix it in this
one.

**Required fix** — inside the existing `transaction.atomic()` and under the same mission row lock,
before the write:

```python
patch = PatchCandidate.objects.get(pk=patch_id)
if patch.mission_id != mission.id:
    raise InvalidStateTransitionError(...)   # or a dedicated ContractError
```

Plus a named test — `test_a_candidate_from_another_mission_cannot_be_verified_into_this_one` —
that builds the two-mission shape above and asserts the refusal. A `unique_together`-style
constraint cannot express this; it has to be the check.

---

### SEC-16 · **HIGH** · The completeness guarantee is a property of one function, not a mechanism — and I reached `VERIFIED` past it

**Location** — `apps/control-api/contracts/state_machine.py:445` (`verifications: Sequence[...] =
()` on the public `assert_transition`), `apps/control-api/missions/models.py:98-155`
(`Mission.state` has no writer guard), `apps/control-api/orchestrator/transitions.py:150`.

**The brief asked me to judge this plainly, so: the defence is real but it is not a mechanism, and
it is one import away from being undone.**

What is genuinely mechanical: `transitions.transition` takes no verification argument, and
`test_transition_takes_no_verification_argument_from_its_caller` asserts its signature is exactly
`{mission_id, target, trace_id, reason, now}`. `test_the_records_are_loaded_by_mission_with_no_filter`
reads `load_verifications`'s source and fails on `.exclude(`, `verdict=`, `[:`, `.first()`,
`.last()`. Both are good tests and I could not defeat either.

What they guard is **one function and one loader**. They do not guard the surface that reaches
the same outcome without touching either. `assert_transition` is public, exported, and its
`verifications` parameter accepts whatever a caller assembles.

**Exploit scenario, executed. The control cases are in the output because without them this proves
nothing:**

```
  records in DB: ['VERIFIED', 'HUMAN_REVIEW_REQUIRED']
  [BLOCKED]  orchestrator.transitions.transition() -> VERIFIED  (VerificationRequiredError)
  [BLOCKED]  assert_transition(full set) -> VERIFIED            (VerificationRequiredError)
  [*** REACHED ***] assert_transition(pruned set: ['VERIFIED']) -> VERIFIED, then Mission.save()
                    mission is now state=VERIFIED verdict=VERIFIED with 2 records on disk,
                    one of them HUMAN_REVIEW_REQUIRED
```

The sanctioned path refuses. The honestly-fed guard refuses. The same guard, one record withheld,
permits — and `Mission.save()` then writes the terminal state with nothing objecting.

And the second half, which is why the first half is reachable at all:

```
  A7 CREATED -> VERIFIED via queryset .update()
     state=VERIFIED verdict=VERIFIED (no Mission.save/state guard exists)
```

**In this PR's favour, and I checked rather than assumed** — there is exactly one writer of
`Mission.state` in the tree today:

```
   ./orchestrator/events.py:68:        state=str(state or mission.state)     (a read)
   ./orchestrator/transitions.py:150:    mission.state = str(target)          (the write)
```

So the convention holds *right now*. The finding is that nothing makes it keep holding, and the
HTTP layer that will want to write state has not been written yet — which is the cheapest possible
moment to install the mechanism, and the last moment before three routers make it expensive.

`missions/models.py` already contains the idiom three times: `Authorization`, `Snapshot` and
`MissionEvent` each override `save()` to refuse. `Mission` — the model carrying the two rulings —
does not.

**Required fix**, either is acceptable and the second is a 20-line test:

1. A `Mission.save()` override that refuses a change to `state` unless it is invoked from within
   `transitions.transition` (a module-level context flag set under the row lock), matching the
   append-only idiom already in the file; **or**
2. An architecture test in `tests/architecture/` — now collected by CI, see SEC-12 below —
   asserting that `mission.state =` and `Mission.objects...update(state=` appear in exactly one
   file, `orchestrator/transitions.py`, and that `assert_transition(` appears in exactly one
   non-test file, the same one. That is the same structural-read technique
   `test_the_records_are_loaded_by_mission_with_no_filter` already uses, applied one level up.

Without one of these, the CTO's assessment is confirmed: **this is the one item a future refactor
can quietly undo, and no test fails when it does.**

---

### SEC-17 · **MEDIUM** · The D-046 freeze has no model-level backstop, in a file where three other models have one

**Location** — `apps/control-api/missions/models.py:454-492`. `PatchCandidate` has no `save()`
override. Its own docstring at `:458-460` says *"Inserting one is not a plain `save()`. Go through
`orchestrator.candidates.record_patch_candidate`"* — which is a comment, not a mechanism.

**Exploit scenario, executed:**

```
[BLOCKED]          B1 record_patch_candidate() after VERIFY started   CandidateSetFrozenError
[*** REACHED ***]  B2 PatchCandidate.objects.create() on a frozen mission
                     candidates 1 -> 2; no save() override on PatchCandidate
[*** REACHED ***]  B3 smuggled candidate flips the mission to VERIFIED
                     mission verdict REJECTED -> VERIFIED; terminal state VERIFIED
```

Lower than SEC-15 because it requires bypassing the sanctioned writer, where SEC-15 uses it. Same
outcome.

**Required fix** — `PatchCandidate.save()` re-reads `mission.verification_started_at` and refuses
when set, so the freeze is enforced by the model rather than by the caller that remembers to use
the recorder. Named test: `test_a_candidate_cannot_be_inserted_into_a_frozen_mission_by_any_path`.

I want to be fair to the author here: `record_patch_candidate` checks **both** halves — the column
*and* the record count via `assert_candidate_set_open` — with a comment explaining that they can
disagree. I attacked exactly that gap (write a verification without setting the column, then add a
candidate) and the second check caught it. That is good defensive work. It just lives in the
function rather than in the model.

---

### SEC-18 · **HIGH** · BUG-011 rated — the DSN silently discards `sslmode`, and `verify-full` is byte-identical to `disable`

**Location** — `apps/control-api/config/env.py:124-133`. `database_from_url` builds the Django
entry from `parsed.hostname/username/password/path` and never reads `parsed.query`.

**Executed:**

```
postgresql://u:p@db:5432/brahmadatta?sslmode=require
   -> OPTIONS: {"connect_timeout": 5}          sslmode reaching libpq: ABSENT
postgresql://u:p@db:5432/brahmadatta?sslmode=verify-full&sslrootcert=/etc/ssl/ca.pem
   -> OPTIONS: {"connect_timeout": 5}          sslmode reaching libpq: ABSENT
postgresql://u:p@db:5432/brahmadatta?sslmode=disable
   -> OPTIONS: {"connect_timeout": 5}          sslmode reaching libpq: ABSENT
postgresql://u:p@db:5432/brahmadatta
   -> OPTIONS: {"connect_timeout": 5}          sslmode reaching libpq: ABSENT
```

**All four DSNs produce byte-identical database configuration.** The operator's strongest possible
TLS statement and their explicit opt-out are the same string to this system.

**Exploit scenario.** With no `sslmode` in `OPTIONS`, libpq applies its own default, `prefer`:
attempt TLS, **fall back to plaintext without error if the server declines, and never validate the
certificate in either case**. An operator who writes `?sslmode=verify-full&sslrootcert=…` — the
setting that exists specifically to defeat an active man-in-the-middle — gets `prefer`. An
attacker positioned between control-api and PostgreSQL downgrades the connection and reads and
rewrites every row on the wire: authorization statements, verification records, the mission state
this PR exists to protect.

**HIGH, not Critical**, for the same reason SEC-02 was downgraded in §12.2: in the finale topology
control-api and postgres share a private network with no published port, so the MITM position
requires already being inside the boundary. That is a property of today's compose file, not of
this code, and it is the only thing holding.

**The severity is driven by the silence, not the bytes.** A control that accepts a
security-relevant configuration string and discards it is worse than one that does not accept it,
because the operator now believes something false and there is nothing to observe. That is the
same argument I made for SEC-02 in §12.2 and the same one D-049 makes about defaults pointing at
the weaker claim — inverted here, since the *stronger* claim is what silently degrades.

**Required fix** — fail closed, matching this repository's own idiom (`E001` stops the process):

1. Parse `parsed.query`. Map `sslmode`, `sslrootcert`, `sslcert`, `sslkey` into `OPTIONS`.
2. **Raise `ImproperlyConfigured` on any query parameter not in that allowlist**, rather than
   dropping it. A DSN parameter the system does not understand must refuse to boot, not be ignored.
3. A Django system check that raises `Error` when `APP_ENV=finale` and `sslmode` is absent or
   weaker than `require`, so the finale cannot start on an unverified database connection.
4. Named test `test_sslmode_reaches_the_driver` plus `test_an_unknown_dsn_parameter_refuses_to_boot`.

Until (1)–(4) land, `.env.example:32-34`'s warning must stay exactly where it is. It is the only
thing standing between an operator and a false belief, and the author was right to write it.

---

### SEC-19 · **MEDIUM** · The boot gate is wired to the looser of two egress implementations, so the invariant fails mid-mission instead of at startup

Routed to me by the orchestrator under D-050. **I verified it myself on this branch rather than
taking the report**; the finding is mine and so is the severity.

**Location** — `apps/control-api/contracts/checks.py:16`. `check_model_endpoints` — a Django
system-check `Error`, which stops the process — imports `assert_local_inference_endpoint` from
`contracts.model_policy`, the implementation D-050 is replacing.

**Executed, `manage.py check` on this branch:**

```
########## SMALL_MODEL_BASE_URL=https://api.openai.com/v1
SystemCheckError: (brahmadatta.E001) SMALL_MODEL_BASE_URL points at 'api.openai.com' …
########## SMALL_MODEL_BASE_URL=https://my-llm-proxy.internal/v1
System check identified no issues (0 silenced).
########## SMALL_MODEL_BASE_URL=http://169.254.169.254/
System check identified no issues (0 silenced).
########## SMALL_MODEL_BASE_URL=https://api.openai.com.evil.test/v1
System check identified no issues (0 silenced).
########## SMALL_MODEL_BASE_URL=http://metadata.google.internal/computeMetadata/v1/
System check identified no issues (0 silenced).
```

**Exploit scenario.** The process boots clean on a configuration the gateway will later refuse.
The operator gets a green `manage.py check`, starts a mission, and the egress invariant asserts
itself at call time — mid-run, on the demo night, with a mission part-way through a stage. A
strict check downstream of a loose boot gate is strictly worse than having only one of them,
because it converts a startup failure into a runtime failure while *also* teaching the operator
that startup validation means something.

D-028 requires this invariant to fail as early and as structurally as available. A boot gate wired
to the weaker of two co-resident implementations is the exact inverse. **Yes, this warrants its own
ID and I am giving it one.**

Note `https://api.openai.com.evil.test/v1` in that output: the boot gate admits a **globally
routable, attacker-controlled** host. That is not a strict-versus-loose difference, it is fail-open
on the primary invariant.

**Required fix** — when D-050's consolidation lands, `contracts/checks.py` imports the gateway's
implementation, and a test asserts there is exactly one such implementation in the tree. Filing
against `contracts/model_policy.py`'s internals would be filing against a file that is being
deleted; **the wiring is the finding, and it survives the replacement.** Owner: the seat landing
D-050. Not a condition on #110 — #110 did not introduce it — but it must not outlive #111.

**D-051, recorded here in the wording the CTO asked for, retiring the corresponding sentence in
D-028:** *"not globally routable" and "inside our trust boundary" are different properties, and
only the second one is the question being asked.* Nobody owns `.internal`; a private-suffix name
check proves neither property. Declaration grants trust, not the suffix. My §5 wording that leaned
on the suffix check is superseded by this sentence.

---

### SEC-20 · **MEDIUM** · `VerificationRecord.clean` is claimed twice and does not exist; a malformed `gates` blob wedges the mission past its own abort paths

**Location** — `apps/control-api/missions/models.py:8` (*"validated on write with the pydantic
schema instead — see `VerificationRecord.clean`"*), `:28` (*"Every one of them has a `clean()` that
runs the real validator, so a malformed blob fails on write rather than on read at 3am"*), and the
class at `:495-526`. PR body: *"`gates` is `jsonb` validated against the frozen `GateMatrix`
**on write and on read**"*.

**Executed:**

```
does VerificationRecord.clean exist? -> False
models.py methods defined on VerificationRecord: ['DoesNotExist', 'MultipleObjectsReturned',
 'id', 'mission_id', 'mission', 'patch_id', 'patch', 'gates', 'verdict', 'get_verdict_display',
 'started_at', ..., 'resource_usage', 'objects']

wrote row 62d3d410-… with gates={'not': 'a gate matrix'} and verdict=VERIFIED -> ACCEPTED
  (no ValidationError; the claimed on-write validator does not run)
```

There is no `clean()` and no `full_clean()` anywhere in `missions/models.py`. The on-**read** half
of the claim is true and is good design — `repository.load_verifications` re-derives the verdict
through the pydantic validator, so a row whose stored verdict disagrees with its stored gates
cannot be loaded. The on-**write** half is true only of `orchestrator.candidates.record_verification`,
which validates the schema before creating the row. The model permits anything.

**Exploit scenario — availability, and it is worse than "a bad row".** Because
`transitions.transition:100` loads the verification set *unconditionally*, on every transition,
before the guards:

```
  RAISES   repository.load_verifications(mission)              -> ValidationError
  RAISES   transition VERIFY -> EXPORTING                      -> ValidationError
  RAISES   transition VERIFY -> FAILED (the escape hatch)      -> ValidationError
  RAISES   record_patch_candidate (the freeze check path)      -> ValidationError

mission is stuck in VERIFY: every transition, including the abort paths,
goes through load_verifications() first.
```

One malformed row and the mission cannot be advanced, cancelled, or failed. `_ABORTS` exists
precisely so that *"getting out safely is never blocked by the bookkeeping"*
(`state_machine.py:224`) — and here it is blocked by the bookkeeping.

**Required fix — and explicitly *not* by weakening the load.** The unconditional load is the
mechanism that closes BUG-004(c) and must stay unconditional.

1. Add the `clean()` the docstrings already promise: run `VerificationSchema` over `gates` and
   `verdict`, called from `save()`. Same for the other JSON columns the module docstring makes the
   same claim about.
2. Make the abort targets survive a failed evidence load: in `transition`, if `target in _ABORTS`,
   a `ValidationError` from `load_verifications` must not prevent the transition. Getting out is
   never gated on evidence that is already unreadable.
3. Named tests: `test_a_malformed_gate_matrix_is_refused_on_write` and
   `test_a_mission_with_an_unloadable_record_can_still_be_failed`.

Until (1) lands, the module docstring at `:8` and `:28` and the PR body's "on write and on read"
are **claims with no implementation behind them**, which is the standing rule's exact subject.

---

### SEC-21 · **MEDIUM** · `record_verification` requires no authorization and no mission state, and its side effect is the D-046 freeze

**Location** — `apps/control-api/orchestrator/candidates.py:216-286`. The function takes the mission
row lock and writes, but never calls `assert_stage_can_run`, never loads an authorization, and
never reads `mission.state`.

**Executed** — mission in `CREATED`, its only authorization revoked:

```
[*** REACHED ***]  B6 write a VERIFIED record with no authorization, mission in CREATED
                     state=CREATED, authorization revoked, freeze now SET
```

**Two distinct consequences.** First, P0-1 says no stage may run without an active authorization,
and `VERIFY` is a stage; a verification record is the artifact that stage produces, and it was
written against a revoked one. `assert_transition` will still demand an active authorization to
*enter* a verdict state, so this does not by itself reach `VERIFIED` — but it puts evidence in the
bundle that no authorization covers, and the evidence bundle is the thing a judge reads.

Second, and more immediately: **the freeze is a side effect of an unguarded function.** Calling
`record_verification` on a mission in `CREATED` sets `verification_started_at`, which permanently
closes the candidate set before `PATCH` has run. That is a denial of service on the mission's own
purpose, from a call that no guard refuses.

**Required fix** — `record_verification` loads the authorization and calls
`assert_stage_can_run(MissionStage.VERIFY, authorization, now, snapshot_sha256)` under the lock it
already holds, and refuses unless `mission.state_enum is MissionState.VERIFY`. Named test:
`test_a_verification_cannot_be_recorded_without_an_active_authorization`.

---

### SEC-22 · **LOW** · The full unified diff of target source is copied into an append-only table that is also broadcast over SSE

**Location** — `apps/control-api/orchestrator/candidates.py:204-211`. The event payload is
`schema.model_dump(mode="json")` over the whole `PatchCandidate`.

**Executed:**

```
  PATCH_CANDIDATE_RECORDED payload keys: ['id', 'mission_id', 'finding_id', 'provenance',
   'model', 'diff', 'files_changed', 'lines_changed', 'policy_status', 'policy_detail',
   'rationale', 'created_at']
  payload['patch']['diff'] present: True
```

Up to 200 KB of the customer's proprietary source (a unified diff carries context lines) is
duplicated from `patch_candidate.diff` into `mission_event.payload`. `MissionEvent` overrides
`save()` to refuse edits (`models.py:254-259`), so **the copy cannot be redacted** — a customer
deletion or retention request cannot be honoured against it without deleting the audit trail that
the evidence bundle depends on. The same payload is what the SSE stream and the replay endpoint
serve.

Good news on the adjacent axis, which I checked because it was in the brief: **no artifact content
and no crash bytes reach the database.** `Artifact` is `sha256`-keyed with `size_bytes` and no blob
column (`models.py:548-565`), `Reproducer.artifact` is a JSON pointer, `GateResult.evidence_ref` is
an opaque `artifact://` pointer with a docstring forbidding inline return, and `ModelProvenance`
carries `prompt_sha256` — a digest — never the prompt. `Finding.sanitizer_report` and
`Finding.code_slice` are capped at 20 000 characters and do carry target-derived text, which is
defensible as the finding's substance. That is a well-designed persistence layer on the
data-minimisation axis and `diff` is the one place it leaks by duplication.

**Required fix** — emit `{"kind": "patch_candidate", "patch_id": …, "provenance": …,
"files_changed": …, "lines_changed": …, "policy_status": …}` and let the client fetch the diff from
the candidate endpoint under the same authorization. The event rail needs the fact, not the bytes.

---

### SEC-23 · **LOW** · Standing-rule sweep: three properties described as enforced, checked against their named tests

The rule is *a property is described as enforced only when a named test demonstrates it*. I held
this PR's body and its docstrings to it. The "NOT RUN / NOT DEMONSTRATED" section is honest and
thorough and is the baseline; these are the three claims that go beyond it.

**(a) `VerificationRecord.patch` uniqueness.** `models.py:503-505` claims *"Re-verifying a
candidate until it passes is the same failure D-046 closes at the other end, and the constraint
makes it a database error rather than a review question."* I tested it and **the property holds**
— `B5 re-verify the same candidate until it passes -> IntegrityError`. But there is no test named
for it in `orchestrator/tests/` or `missions/tests/`. A property demonstrated only by my review is
a property that survives until someone changes `OneToOneField` to `ForeignKey` for a plausible
reason. Add `test_a_candidate_can_only_be_verified_once`.

**(b) `gates` validated on write.** Claimed in two docstrings and the PR body; not implemented. See
SEC-20. This is the one that is not merely untested but false.

**(c) `test_a_dropped_rejection_cannot_reach_verified` is misnamed.** Its body exercises the
`HUMAN_REVIEW` drop, which is the case that bites. The name describes the `REJECTED` drop, which
under any-VERIFIED-wins cannot change the outcome and is therefore vacuous. The PR body's table
maps it to *"BUG-004(c) — dropping a `REJECTED` record"*, propagating the wrong claim into the
record. Rename to `test_a_dropped_human_review_record_cannot_reach_verified` and correct the table.
The test is right; only its label is wrong, which is precisely the failure the standing rule
exists to catch before it becomes doctrine.

**Not a finding, recorded for the CTO:** the author flipped `EvidenceBundle.isolation_mode` to
required-with-no-default under D-049's general rule and flagged that D-049 did not name it. From a
security standpoint the flip is **correct and I endorse it** — `ROOTLESS_CONTAINER` was the
stronger of the two postures and defaulting to it is overclaim-by-omission, the exact pattern
D-049 exists to end. The CTO owns the ruling; I am recording that reverting it would create a
finding.

---

### 13.2 Status of prior findings, re-checked on this branch

| ID | Was | Now | Evidence |
|---|---|---|---|
| SEC-01 | CRITICAL | **CLOSED** | Unchanged since §12. |
| **SEC-02** | MEDIUM, open | **open, unchanged here; closed by #111** | Re-ran the bypass table on `feat/state-machine`: **`MISMATCHES: 10`**, plus the D-051 case `https://api.openai.com.evil.test/v1` also admitted. D-050 replaces this implementation with the gateway's (0 of 60). **#111 is not merged**, so it is open on `main` today. Do not close it against #110. |
| SEC-07 | MEDIUM, open | **CLOSED ✅** | `assert_transition` now takes `mission_id` as a required keyword-only argument with no default (`state_machine.py:447`). I confirmed the guard cannot be run without a mission and that another mission's records are refused (A2). This PR closes it. |
| **SEC-12** | MEDIUM, new | **CLOSED ✅** | `tests/architecture/` is now a CI step — `.github/workflows/ci.yml:137-138`, `pytest tests/ -q -rs`. I ran it on this branch: **`36 passed in 0.54s`**. D-036 and D-037 are enforced again. |
| SEC-03, 04, 05, 06-R, 08, 09, 10, 13, 14 | — | **open, untouched** | Not in this PR's files. Carried forward. |

### 13.3 Dependency audit — **executed**

```
$ pip-audit -r apps/control-api/requirements.txt
No known vulnerabilities found

$ pip-audit -r apps/control-api/requirements-dev.txt
No known vulnerabilities found

$ npm audit
found 0 vulnerabilities

$ npm audit --omit=dev
found 0 vulnerabilities
```

Runtime set is pinned to exact versions (`Django==5.2.17`, `django-ninja==1.6.2`,
`pydantic==2.13.4`, `psycopg[binary]==3.3.4`, `python-dotenv==1.2.2`, `uvicorn[standard]==0.52.1`).
This PR adds no new dependency. The `actions/setup-python` addition in `ci.yml` is pinned to a
commit SHA (`ece7cb06…`), which is the correct form and matches the existing job.

### 13.4 Secrets — **executed**

```
$ grep -n env .gitignore
22:.env
23:.env.*
24:!.env.example

$ git ls-files | grep -i '\.env'
.env.example
apps/control-api/.env.example

$ (secret-shaped literals across every file this PR touches)
apps/control-api/.env.example:40:CONTROL_API_OPERATOR_TOKEN=REPLACE_ME_OPERATOR_TOKEN_MIN_32_CHARS
```

One match, a placeholder in the committed example. No credential in code. The migration contains
no `RunPython`, no `RunSQL` and no data migration. `database_from_url`'s error messages name the
scheme and never the DSN, so the password does not reach a traceback from that path.

### 13.5 What I did **not** review

Listed rather than omitted, per the rule.

1. **Anything concurrent.** Everything above is single-threaded on in-memory SQLite, where
   `SELECT … FOR UPDATE` is a no-op — the same limitation the author declared. **The candidate
   freeze under an interleaved insert, and gap-free `sequence` under two writers, are not
   demonstrated by me and I make no claim about them.** That is the `qa-engineer` seat's run
   against real PostgreSQL and I deliberately did not duplicate it. SEC-15 and SEC-17 are
   single-threaded logic holes and are unaffected by how that run comes out.
2. **The 937-line migration**, beyond confirming it contains no raw SQL, no `RunPython` and no
   data migration. I did not diff it field-by-field against `models.py`; `makemigrations --check`
   is the author's evidence for that and I did not re-run it.
3. **The HTTP layer.** The routers return 501 and were not wired in this PR. No authentication,
   authorization, IDOR, rate-limiting or input-handling review of the mission endpoints was
   possible, because there are no mission endpoints yet. **This is the single largest unreviewed
   surface and it is where SEC-15 becomes Critical.** It needs its own security pass when wired.
4. **The frontend.** `apps/command-center/src/lib/api/schema.d.ts` is generated output; I did not
   review it, and no XSS/CSP/token-storage review was done on the Command Center.
5. **The OpenAPI exporter's reason-phrase pinning (#103).** A correctness and supply-chain-drift
   concern, not a security one; I read the approach and did not test it.
6. **`packages/schemas/openapi.json`** — regenerated output, not read.
7. **`mypy`** — not run by me. **`ruff`** — not run by me; the author's figures are unverified.
8. **Infrastructure.** No container, TLS, header, port or compose review in this round; nothing in
   this PR touches `infrastructure/`. §12's findings stand unchanged.
9. **BUG-012 and BUG-008** — out of scope for #110 by the author's declaration, and I did not
   look at them.

### 13.6 Verdict

**PASS WITH CONDITIONS.**

No Critical finding is open, so I am not exercising the veto. This is good work — the round-1
duck-typing hole is properly closed, `paused_from` genuinely closes both directions, the
second-baseline path is shut at two layers, and there is no route from a confidence value to a
verdict. The author's "NOT RUN / NOT DEMONSTRATED" section is the most honest artifact in this PR
and it is why this review could be adversarial instead of archaeological.

**Conditions on merge — all three are in this PR's own files:**

1. **SEC-15 (HIGH)** — `record_verification` validates that the patch belongs to the mission, with
   the named two-mission test. This is the condition I care about most: it defeats D-046 through
   the sanctioned API, and it is Critical the day a route supplies `patch_id`.
2. **SEC-16 (HIGH)** — one mechanism, model guard or architecture test, making `transitions.transition`
   the only writer of `Mission.state` and the only caller of `assert_transition`. The convention
   holds today; nothing makes it keep holding.
3. **SEC-18 (HIGH)** — `config/env.py` stops silently discarding DSN query parameters. Fail closed
   on an unrecognised one. Until it lands, `.env.example`'s warning stays.

**Follow-ups, not merge blockers** — SEC-17, SEC-20, SEC-21 (Medium) and SEC-22, SEC-23 (Low) get
issues with owners. SEC-19 (Medium) is not #110's to fix but must not outlive #111.

**On the question the CTO put to me directly** — is "the guard is only ever called from a
transaction-scoped path that loaded the records itself" adequate? **No, and SEC-16 is the executed
proof rather than an opinion.** It is a well-chosen convention, defended by two better-than-average
tests, and it is still a convention: I reached terminal `VERIFIED` past a `HUMAN_REVIEW_REQUIRED`
record on disk, through a public function, in four lines, with no test failing. The author was
right that no in-function validation closes BUG-004(c). The answer is not in-function validation —
it is making the sanctioned path the only path, which is a one-file change today and a three-router
change after the HTTP layer lands.

### 13.7 Decision records to fold into `.project/decisions.md`

**DR-SEC-R2-1 · SEC-15 rated HIGH now, Critical on HTTP wiring**

**Decision** — rate the cross-mission verification hole HIGH, make it a merge condition, and
pre-commit to Critical the moment a route passes a caller-supplied `patch_id`.

**Options considered** — (a) Critical now, blocking merge under my veto; (b) HIGH with a merge
condition and a named escalation trigger; (c) HIGH as an ordinary follow-up issue.

**Pros and cons** — (a) matches the impact (the product's central invariant is defeatable) but not
the exploitability: the HTTP layer returns 501, so no external actor can reach it, and a veto on an
unreachable path spends the veto's credibility on a hypothetical. (c) understates it — the next PR
is the routers, and a Medium-priority follow-up will not land before them. (b) is accurate on both
axes and gives the engineering-manager a bright line that does not require re-litigating severity
later.

**Cost implications** — the fix is a query and a comparison inside an existing transaction, plus
one test. Under an hour. Deferring it past the routers costs a security re-review of three
endpoints.

**Security implications** — this is the finding. Unfixed, a mission reaches terminal `VERIFIED` on
a candidate that is not in its own frozen candidate set, which is generate-until-pass.

**Scalability implications** — one indexed primary-key lookup per verification write. None.

**Recommendation** — (b).

**Final approval authority** — cybersecurity (severity is mine).

**DR-SEC-R2-2 · The convention defending BUG-004(c) is judged inadequate, and the required
remedy is a structural test rather than a rewrite**

**Decision** — SEC-16 is a merge condition, satisfiable by *either* a `Mission.save()` guard *or*
an architecture test asserting single-writer. I do not specify which.

**Options considered** — (a) require the `save()` override, matching the append-only idiom already
in `models.py`; (b) require the architecture test; (c) accept the convention plus the existing
signature test as sufficient.

**Pros and cons** — (a) is the strongest mechanism and the most likely to fight the ORM in ways I
cannot foresee (bulk operations, migrations, fixtures) — and choosing it would be me making an
implementation decision that belongs to the software-architect. (b) is 20 lines, uses the technique
already in `test_the_records_are_loaded_by_mission_with_no_filter`, and fails loudly on the exact
refactor the CTO is worried about. (c) is what I tested and defeated.

**Cost implications** — (b) is under an hour. (a) is a half-day with a real regression risk.

**Security implications** — either closes the reachable path. (b) closes it at review time rather
than at runtime, which for an internal-refactor threat actor — a future developer, not an attacker
— is the right layer.

**Scalability implications** — none for (b); (a) adds a check on every `Mission` write.

**Recommendation** — leave the choice to the owning developer and the software-architect; I set the
requirement, not the design. Verify whichever lands.

**Final approval authority** — CTO for the technical approach; cybersecurity for whether the
delivered mechanism satisfies SEC-16.

**DR-SEC-R2-3 · BUG-011 rated HIGH, and the fix is fail-closed rather than best-effort**

**Decision** — SEC-18 is HIGH and the required fix refuses to boot on an unrecognised DSN query
parameter rather than mapping the ones it knows and dropping the rest.

**Options considered** — (a) parse and map the known TLS parameters, ignore the rest — the minimal
fix; (b) parse, map, and raise on anything unrecognised; (c) document it in `.env.example` and set
`sslmode` through a separate environment variable.

**Pros and cons** — (a) fixes today's symptom and preserves the mechanism that caused it: the next
security-relevant parameter is dropped just as silently. (c) is what the author did as a stopgap
and it is a good stopgap, but it leaves two ways to spell the same setting, one of which lies. (b)
costs one `raise` and converts a whole class of silent-misconfiguration bugs into startup failures,
which is what this repository already does for the model-endpoint invariant.

**Cost implications** — an afternoon including the system check and two tests.

**Security implications** — `verify-full` and `disable` are currently indistinguishable to this
code. Any control that silently discards its own configuration is unfalsifiable, and an
unfalsifiable control is the kind people build on.

**Scalability implications** — none.

**Recommendation** — (b), plus the finale system check.

**Final approval authority** — CTO for the parsing approach; cybersecurity for the severity and for
the fail-closed requirement.

---

## 14. Round 3 — 2026-08-08 · PR #111 `feat/model-gateway` · the endpoint policy and replay mode

This is the PR carrying my veto: it is the fix for **#78 / SEC-02**, the ten bypasses I rated in
§2 and re-confirmed open in §12.2. Reviewed at `3cb12a5` in an isolated worktree.

**Verdict: PASS WITH CONDITIONS.** No Critical. Two new findings (SEC-24, SEC-25) are merge
conditions; both are small. **The gateway's egress function is correct and I reproduced that
myself.** SEC-19 is **not** closed here and is re-targeted rather than waived — §14.4.

### 14.1 The bypass table, re-run by me rather than read

I said I do not sign off on someone else's script. I ran it:

```
$ python3 infrastructure/scripts/testing/endpoint-policy-bypass-table.py --quiet

declared MODEL_SERVICE_NAMES: model-host.internal, small-model
60 cases
…
GATEWAY  mismatches: 0 of 60
CONTROL  mismatches: 34 of 60  (gated at exactly 34)
```

**0 of 60 reproduced independently.** Every case I rated in §2 and §12.2 is closed by the gateway
implementation, each refused by a *named rule* rather than by a bare boolean — `denied-network`,
`metadata-name`, `idna-mismatch`, `packed-ipv4`, `userinfo`, `undeclared-private-suffix`,
`undeclared-bare-label`. A URL refused for the wrong reason fails the build. That is a better
artifact than I asked for; the four fixes I specified in §2 are all present and two more besides.

`CONTROL 34 of 60` is the honest state of `contracts/model_policy.py`, printed rather than
asserted, and gated in both directions so it cannot drift silently.

### 14.2 My own cases, which are not in the author's table

Re-running the author's table proves the author's table. These are mine.

Most of what I tried was already closed, and closed structurally rather than by enumeration —
the name path is **allowlist-only** (`localhost`, `host.docker.internal`, or declared), so every
name that is not explicitly permitted falls through to a refusal. That is why the following all
failed to get through even though none of them is in the table:

```
  [ok] want=False got=False public-name       8.8.8.8 as a.b        'http://8.526344/v1'
  [ok] want=False got=False public-name       8.8.8.8 as a.b.c      'http://8.8.2056/v1'
  [ok] want=False got=False public-name       127.0.0.1 as a.b      'http://127.1/v1'
  [ok] want=False got=False public-name       mixed hex dotted      'http://0x8.0x8.0x8.0x8/v1'
  [ok] want=False got=False public-name       loopback octal dotted 'http://0177.0.0.1/v1'
```

`_looks_like_packed_ipv4` only inspects dotless hosts, so `inet_aton`'s partial-dotted forms
(`8.526344` is 8.8.8.8) slip past it — and it does not matter, because the default for a name is
deny. **That is the right shape and it is why this implementation is worth trusting**: the
enumerated bypasses are a defence-in-depth layer over a deny-by-default decision, not the
decision itself.

I also confirmed rule ordering cannot be subverted by the operator's own allowlist — a name
declared in `MODEL_SERVICE_NAMES` is still refused if it is a provider, a metadata name, a packed
address or a denied network, because those checks run *before* the declared-name check:

```
  [ok] want=False got=False hosted-provider   declared 'api.openai.com' then used
  [ok] want=False got=False metadata-name     declared 'metadata.google.internal' then used
  [ok] want=False got=False packed-ipv4       declared '2130706433' then used
  [ok] want=False got=False denied-network    declared '169.254.169.254' then used
```

and that `normalise_service_names` refuses a dangerous declaration at startup rather than
widening the boundary quietly (`api.openai.com`, `metadata.google.internal`, `2130706433`,
`127.0.0.1`, the U+3002 homograph and `evil.example.com` are all refused).

All ten controls that must keep working, do:

```
  [ok] want=True got=True allowed-network  loopback / IPv6 loopback / all three RFC 1918 ranges
  [ok] want=True got=True local-name       localhost
  [ok] want=True got=True declared-service small-model, model-host.internal
  [ok] want=True got=True allowed-network  IPv6 unique-local fd12:3456::1
```

---

### SEC-24 · **MEDIUM** · The IPv6 unwrap is applied to the *allow* path as well as the *deny* path, so a globally routable literal is permitted for what is embedded in it

**Location** — `services/model-gateway/gateway/endpoint_policy.py:515-547` (`_classify_address`),
with `_unwrap` at `:499-512`. `effective = _unwrap(address)` is computed once and then used for
**both** the deny loop at `:521` and the allow loop at `:536`.

**Why unwrapping is right for denying and wrong for allowing.** Unwrapping is what catches
`[::ffff:169.254.169.254]` and `[64:ff9b::808:808]` and `[2002:808:808::1]` — all three are in the
author's table and all three are correctly refused. But `2002::/16` (6to4) and `64:ff9b::/96`
(NAT64) are **globally routable IPv6 prefixes**. A packet addressed to `2002:7f00:1::1` does not
go to 127.0.0.1; it leaves the host toward a 6to4 relay. Judging the *destination* by the address
*embedded* in it is correct when the answer is "deny" and inverted when the answer is "allow".

**Exploit scenario, executed — none of these are in the 60-case table:**

```
  [FAIL] want=False got=True allowed-network  6to4 wrapping 127.0.0.1     'http://[2002:7f00:1::1]/v1'
  [FAIL] want=False got=True allowed-network  6to4 wrapping 10.0.0.1      'http://[2002:a00:1::1]/v1'
  [FAIL] want=False got=True allowed-network  6to4 wrapping 192.168.1.1   'http://[2002:c0a8:101::1]/v1'
  [FAIL] want=False got=True allowed-network  NAT64 wrapping 127.0.0.1    'http://[64:ff9b::7f00:1]/v1'
  [FAIL] want=False got=True allowed-network  NAT64 wrapping 10.0.0.1     'http://[64:ff9b::a00:1]/v1'
  [FAIL] want=False got=True allowed-network  NAT64-local wrapping 192.168.0.1 'http://[64:ff9b:1::c0a8:1]/v1'
```

Each is reported as `allowed-network — loopback or private address (127.0.0.0/8)`. The policy
says loopback; the socket goes to a global IPv6 destination.

**The resolver check inherits the same asymmetry**, so the defence-in-depth layer does not catch
it either:

```
  [ok  ] refused=True  want_refused=True   declared name -> 8.8.8.8
  [ok  ] refused=True  want_refused=True   declared name -> 169.254.169.254
  [ok  ] refused=True  want_refused=True   declared name -> [loopback, 8.8.8.8] (2nd answer poisoned)
  [ok  ] refused=True  want_refused=True   declared name -> 6to4 wrapping 8.8.8.8
  [FAIL] refused=False want_refused=True   declared name -> 6to4 wrapping 127.0.0.1
  [FAIL] refused=False want_refused=True   declared name -> NAT64 wrapping 127.0.0.1
```

A declared name whose resolver answers `2002:7f00:1::1` passes both layers.

**Two of my eight unexpected results are my expectation being wrong, not the code**, and I am
recording that rather than inflating the count: `[::ffff:127.0.0.1]` and `[::ffff:10.0.0.1]` are
IPv4-mapped, and connecting to those genuinely does reach 127.0.0.1 and 10.0.0.1 on a normal dual
stack. Unwrapping those for the allow decision is **correct**. The finding is the six 6to4/NAT64
cases only.

**MEDIUM.** The input is `MODEL_ENDPOINT`, operator configuration — actor A3 from §1, the same
actor as SEC-02 — not attacker-supplied data. SEC-01's topology means the finale has no default
route regardless. It is the same class as the ten cases this PR just closed, in the code written
to close them, and the table to pin it already exists.

**Required fix** — keep `_unwrap` for the deny loop; for the allow loop, permit only when the
address is *itself* in `_ALLOWED_NETWORKS`, with `ipv4_mapped` as the one sanctioned equivalence.
Concretely, in `_classify_address`, refuse any address where `wrapped` is true and the wrapper was
6to4 or NAT64 rather than IPv4-mapped. Add the six rows above to `bypass_table.py`, which makes
them permanent.

---

### SEC-25 · **MEDIUM** · The new runtime pin `idna==3.10` carries CVE-2026-45409, in the exact function that is this PR's security control, and the documented workaround is not implemented

**Location** — `services/model-gateway/requirements.txt` (`idna==3.10`), consumed at
`gateway/endpoint_policy.py:327` (`idna.encode(host, uts46=True)`) and `:231` in
`normalise_service_names`.

**Executed:**

```
$ pip-audit -r services/model-gateway/requirements.txt
Found 2 known vulnerabilities in 1 package
Name Version ID             Fix Versions
---- ------- -------------- ------------
idna 3.10    PYSEC-2026-215 3.15
```

`PYSEC-2026-215` = `CVE-2026-45409` / `GHSA-65pc-fj4g-8rjx`. Quadratic resource consumption in
`idna.encode()` on long inputs — *"the same issue as CVE-2024-3651, however the original
remediation in 2024 was not a complete fix"*. Fixed in 3.15. The advisory names the workaround
explicitly: **enforce the 253-character domain limit before calling `idna.encode()`.**

`classify()` applies no length check before `idna.encode()`. **Executed reachability, through the
public entry point:**

```
CVE-2026-45409 reachability through classify() — no length guard before idna.encode()
RFC 1035 caps a domain at 253 chars; classify() does not enforce that.

  host len   1000  -> idna-invalid   in    0.031s
  host len   5000  -> idna-invalid   in    0.667s
  host len  20000  -> idna-invalid   in   10.303s
  host len  60000  -> idna-invalid   in  100.832s
```

One `classify()` call, 100 seconds. The verdict is still correct — it refuses — it just takes a
minute and a half to say so.

**MEDIUM, not High.** The host comes from `MODEL_ENDPOINT` today, so this is a configuration
foot-gun rather than a remote DoS. Three things stop it staying that way, and they are why this is
a condition rather than a follow-up: `classify()` is documented at `:53-59` as safe to call from a
Django system check, and a 100-second system check is a failed deploy; **D-050 consolidates this
module into `contracts/`**, where the next caller may well hand it a URL from a request body; and
this CVE is a *recurrence* of a 2024 CVE whose first fix was incomplete, which is the strongest
possible argument for not relying on the library alone.

**Required fix** — both halves, because either alone leaves the other gap:

1. `idna>=3.15` in `services/model-gateway/requirements.txt`.
2. A length guard in `classify()` and `normalise_service_names` before `idna.encode()`: refuse a
   host over 253 characters, or any label over 63, as `EndpointDecision(False, "host-too-long", …)`.
   That is the advisory's own workaround, it is two lines, and it holds when this recurs a third
   time.
3. A row in `bypass_table.py` for an over-long host, so the guard is pinned.

This is also a **dependency-policy** point for the CTO: `pip-audit` is not in CI. `apps/control-api`'s
pins are clean today (§13.3), and this one was not, and nothing in the pipeline would have said so.
Adding `pip-audit -r` for every `requirements.txt` as a CI step is the generalisation and I
recommend it.

---

### 14.3 Two claims I verified by injection rather than by reading

**The import-closure walk.** The author reports catching their own check passing by not looking —
a subprocess-based test that **skipped** rather than failed when `import ninja` was injected — and
replacing it with a static walk. I verified the replacement the same way:

```
########## CONTROL: clean tree ##########
8 passed in 0.28s

########## INJECT 'import ninja' into gateway/endpoint_policy.py ##########
71:import ninja  # INJECTED VIOLATION

E   AssertionError: gateway.endpoint_policy failed to import in a bare interpreter, and the
    error names ['django', 'ninja', 'pydantic']. That is not a missing dependency, it is the
    policy having acquired one
2 failed, 6 passed in 0.37s
```

**Two failures, no skips.** The claim holds. The runtime check also correctly distinguishes "this
dependency is missing" from "this module acquired a dependency", which is the distinction that
made the first version useless. Injection reverted; worktree clean.

This is the **fifth** instance of a check passing by not looking, across five seats, and the
**first caught by its own author before review**. That is the standing rule starting to work, and
it is worth saying so in the record.

**"No code in this package opens a socket."** Load-bearing for the security section, so I checked
rather than accepted it:

```
$ grep -rnE "^\s*(import|from) +(httpx|requests|aiohttp|urllib3|openai|anthropic|socket)" \
    --include="*.py" gateway | grep -v "/tests/"
gateway/endpoint_policy.py:65:import socket
$ grep -n "socket\." gateway/endpoint_policy.py
410:    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
```

One `socket` import, used once, for name resolution in the opt-in resolver check. No HTTP client.
The claim is accurate.

**The `SYNTHETIC_FIXTURE` gate.** `transcripts/` contains only `.gitkeep` and `README.md` — no
transcript is committed, as claimed. `CaptureKind.SYNTHETIC_FIXTURE` is refused at load unless
`allow_synthetic` is set (`gateway/transcripts.py:243-245`), with
`test_a_synthetic_fixture_cannot_be_served_as_model_output` naming it. A hand-written diff cannot
be served wearing a model's provenance. Verified by reading; I did not attack the transcript store.

### 14.4 SEC-19 — **not closed by #111.** Re-targeted, not waived

In §13 I wrote that SEC-19 *"must not outlive #111"*. It has, and after reading why, **I am not
blocking on it.**

```
$ git diff origin/main...HEAD --name-only | grep control-api
  NO control-api file touched

$ sed -n '16p' apps/control-api/contracts/checks.py
from contracts.model_policy import assert_local_inference_endpoint

$ manage.py check, on this branch
https://my-llm-proxy.internal/v1     System check identified no issues (0 silenced).
http://169.254.169.254/              System check identified no issues (0 silenced).
https://api.openai.com.evil.test/v1  System check identified no issues (0 silenced).
```

The boot gate still binds to the 34-of-60 implementation and still boots clean on all three.

**Why this is the right call and not a waiver.** The seat's decision record gives two reasons for
not touching `contracts/model_policy.py`: it is another seat's file in a live worktree, and C5
forbids the ASGI process importing `gateway`, so the gateway's implementation is not available to
`checks.py` until D-050 consolidates it into `contracts/`. Both are correct. Demanding the fix
here would be demanding either a hard-rule breach or a premature architectural move, and I do not
get to require that by attaching it to a severity.

**What changes instead.** SEC-19's impact today is materially lower than when I filed it: nothing
in the tree opens a socket to a model, so the boot gate is currently validating a setting that no
code uses to connect. It is a misleading green check, not a live egress path. **It becomes a live
egress path the moment #35/#36 land a real backend.**

**Ruling.** SEC-19 does not block #111. It is re-targeted at **#93 / D-050**, and it **blocks the
first PR that introduces a live model backend** — that is the merge gate it moves to, and I will
enforce it there. It stays MEDIUM and open.

### 14.5 Can #78 close, and what happens to SEC-02

**#78 can close, on the same condition I set in §12.3 and for the same reason.** The component
that will actually open the socket now has a correct egress function — 0 of 60, reproduced by me,
with a named-rule table and a two-column drift guard. SEC-01's topology holds underneath it. #78's
second acceptance box — *"link-local, loopback-to-elsewhere and metadata addresses are explicitly
rejected by the validator"* — is now genuinely ticked **for the gateway**.

**Condition, and it is the same one as last time: SEC-02 and SEC-19 must be filed against #93 with
an owner and a milestone before #78 is closed. Not after.** `contracts/model_policy.py` is at 34
of 60 and is what the ASGI process boots on; closing #78 while that is true, with nothing tracking
it, is exactly how the finding got lost the first time.

**SEC-02 status: still open, still MEDIUM, owner #93.** It is not closed by this PR and this PR
does not claim it is. What changed is that it is now *measured* — 34 of 60, in CI, gated in both
directions — rather than assumed.

### 14.6 D-051, recorded verbatim as the CTO asked

The CTO adopted the gateway seat's sentence, and it **retires my own §5 wording** — the claim that
the private-suffix name check *"proves the hostname is inside the boundary"*. It does not, and
`api.openai.com.evil.test` settles it. The replacement:

> **"not globally routable" and "inside our trust boundary" are different properties, and only
> the second one is the question being asked.**

Nobody owns `.internal`, `.local`, `.svc` or `.test`. Declaration grants trust; a suffix does not.
I endorse both divergences in the gateway's decision record — private suffixes requiring
declaration, and the reserved documentation ranges denied — and I confirmed the three cases they
newly refuse (`small-model.internal`, `model.svc.cluster.local`, `198.51.100.7`) are all refusals
I want. **My §5 wording is superseded; §13's copy of this sentence and this one are the record.**

One inconsistency inside the divergence, recorded as informational rather than a finding:
`_LOCAL_NAMES` at `:141` hardcodes `host.docker.internal` as trusted with no declaration, and it
sits under `.internal` — the namespace the divergence refuses on the grounds that nobody owns it.
Docker owns that specific name by convention, so it is defensible, and `evil.host.docker.internal`
is correctly refused. It is one hardcoded exception to a rule made three lines earlier and the
next reader should know it was deliberate.

### 14.7 Dependency audit and secrets — **executed**

```
$ pip-audit -r services/model-gateway/requirements.txt
Found 2 known vulnerabilities in 1 package
idna 3.10    PYSEC-2026-215   fix: 3.15          <-- SEC-25

$ pip-audit -r services/model-gateway/requirements-dev.txt
  same single finding (dev file includes the runtime file)

$ (secret-shaped literals across every file in the diff)
.env.example:51:POSTGRES_PASSWORD=REPLACE_ME_LOCAL_DEV_PASSWORD
.env.example:68:CONTROL_API_OPERATOR_TOKEN=REPLACE_ME_OPERATOR_TOKEN_MIN_32_CHARS
```

Two matches, both placeholders in the committed example file. No credential in code. Two new
runtime dependencies, both pinned exactly: `pydantic==2.13.4` (matching control-api, deliberately)
and `idna==3.10` (SEC-25).

### 14.8 The suite, run by me — and a stale claim in the PR body

```
$ cd services/model-gateway && pytest -q -rs
274 passed, 1 skipped in 0.39s
SKIPPED [1] gateway/tests/test_contract_alignment.py:172: contracts.ModelProvenance has no
  inference_mode yet — #110 is not merged. The gateway already emits it; this assertion
  activates on merge.
```

The PR body reports **`270 passed`** and states **"No skips."** The branch is at 274 passed and
one skip. The body's evidence block predates the CTO-conditions commit and was not refreshed.

**The skip itself is fine and is the good kind** — it names its reason, it is visible because the
suite runs with `-rs`, and it self-activates when #110 merges. But under the standing rule the
*claim* has to match the run, and "No skips" is now false. **LOW**, no ID: refresh the evidence
block before merge. Flagging it because the whole point of the rule is that stale evidence is how
a green run stops meaning anything, and this PR is otherwise the best-evidenced one I have
reviewed.

Worth recording what that skip means substantively: `test_contract_alignment.py` does **not**
currently validate the replay triple against the real `contracts.ModelProvenance`. That assertion
is dormant until #110 lands. The cross-implementation guarantee is therefore *intended*, not
demonstrated, today.

### 14.9 What I did **not** review

1. **No egress attempt from inside a running container.** Not re-run this session. §12's execution
   stands and is unchanged by this diff. **NOT RUN.**
2. **No live-resolver DNS test.** I exercised `assert_resolves_inside_boundary` with an injected
   resolver only, as the author did. Against a real resolver: **NOT RUN.**
3. **The transcript store's integrity path.** I read the `SYNTHETIC_FIXTURE` gate and the
   self-hashing refusal and did not attack them — no path traversal, symlink, TOCTOU or
   concurrent-write testing on `TranscriptStore`. Unreviewed.
4. **The replay/provenance labelling half of the PR (#82).** I confirmed the chokepoint tests
   exist and are scoped honestly. I did not independently attack the renderers, and the AST
   chokepoint scan's completeness is unverified by me.
5. **`gateway/service.py`, `backends.py`, `schemas.py`, `settings.py`, `tools/transcripts_cli.py`**
   — read for socket use and for the endpoint-policy call sites only, not reviewed line by line.
6. **`mypy` and `ruff`** — not run by me; the author's figures are unverified.
7. **The CI additions** in this PR — not reviewed.

### 14.10 Verdict

**PASS WITH CONDITIONS.**

This is the best security work in the repository. It does the thing I asked for in §12.2 — IDNA
normalisation before deciding, an explicit metadata and link-local deny list rather than
`is_global`, `metadata` refused by name and by leftmost label, and the bare-label pass replaced by
a declared allowlist — and then goes past it with packed-IPv4, userinfo, the IPv6 wrappers and an
opt-in resolver check. The deny-by-default name path is what makes it trustworthy, rather than the
enumeration. It reports its own remaining gap as a number in CI. And its author caught their own
check passing by not looking, which is the first time that has happened here.

**Conditions on merge:**

1. **SEC-24 (MEDIUM)** — the 6to4/NAT64 unwrap must not permit; six rows added to
   `bypass_table.py`.
2. **SEC-25 (MEDIUM)** — `idna>=3.15`, plus the 253-character guard before `idna.encode()`.

**Condition on closing #78** — SEC-02 and SEC-19 filed against #93 / D-050 with an owner and a
milestone **before** #78 closes, not after. Identical to §12.3, for identical reasons.

**Before merge, not a finding** — refresh the PR body's evidence block; "270 passed / No skips" is
now "274 passed, 1 skipped".

**Carried:** SEC-19 re-targeted at #93 and now **blocks the first PR landing a live model backend**
(#35/#36). SEC-02 remains MEDIUM and open, owned by #93, now measured rather than assumed.

I will re-verify SEC-24 and SEC-25 personally, by re-running my own cases, before this merges.

### 14.11 Decision records to fold into `.project/decisions.md`

**DR-SEC-R3-1 · SEC-19 is re-targeted at #93 rather than blocking #111**

**Decision** — SEC-19 does not block #111. It moves to #93 / D-050 and becomes a merge gate on the
first PR introducing a live model backend.

**Options considered** — (a) block #111 until `contracts/checks.py` is rewired; (b) re-target to
#93 with a named future merge gate; (c) close it as fixed because the gateway is 0 of 60.

**Pros and cons** — (a) requires either editing another seat's file in a live worktree (a hard-rule
breach for that seat) or importing `gateway` from the ASGI process, which C5 forbids; I do not get
to require a hard-rule breach by attaching it to a severity. (c) is false — the boot gate demonstrably
still admits `169.254.169.254` and `api.openai.com.evil.test`, and I executed that on this branch.
(b) is accurate: the impact today is a misleading green check rather than an egress path, because
nothing in the tree opens a socket to a model yet, and it names the exact moment that stops being
true.

**Cost implications** — zero now; one import change plus a test when D-050 consolidates.

**Security implications** — a boot gate looser than the runtime control teaches operators that a
green `manage.py check` means something it does not. Tolerable only while no live backend exists.

**Scalability implications** — none.

**Recommendation** — (b), with the gate on #35/#36 written down rather than remembered.

**Final approval authority** — cybersecurity (severity and gate placement are mine).

**DR-SEC-R3-2 · `pip-audit` becomes a CI step for every `requirements.txt`**

**Decision** — recommend `pip-audit -r` in CI for every pinned Python requirements file.

**Options considered** — (a) fix the `idna` pin and move on; (b) add `pip-audit` to CI; (c) add
Dependabot or Renovate.

**Pros and cons** — (a) leaves the next vulnerable pin undetected, and this one was introduced by
the most security-conscious PR in the repository, which is the strongest available evidence that
review does not catch it. (c) is better long-term and is a larger decision about bot noise during a
seven-day build. (b) is one step, fails the build on a known CVE in a pinned dependency, and would
have caught SEC-25 before I did.

**Cost implications** — one CI step, a few seconds. Some risk of a red build from a new advisory on
an unrelated day, which is the intended behaviour.

**Security implications** — closes the gap between "we pin exactly" and "we know what we pinned".
Exact pinning without an audit step is a decision to freeze whatever was vulnerable on the day.

**Scalability implications** — none.

**Recommendation** — (b) now, (c) after the finale.

**Final approval authority** — CTO (technical/CI); cybersecurity sets the dependency policy
requirement.

---

## 15. Round 4 — 2026-08-08 · PR #119 `feat/authorize-snapshot` · the authorization gate and snapshot ingest

Reviewed at `2ae5173` (`origin/feat/authorize-snapshot`), in an isolated `git worktree` off
`origin/main` (`/Users/manu/Documents/GitHub/brahmadatta-ai-pr119`, branch
`review/security-authorize-snapshot`). No code edited, no other role's files changed. Two
other agents were live in `services/model-gateway/`, `adapters/cpp/`, `infrastructure/` during
this review; none of their trees were touched.

**Verdict: PASS WITH CONDITIONS.** No Critical. Seven new findings (SEC-26…SEC-32), one High
(SEC-26) and four Medium. The core claim — every id this gate accepts is checked against the
*locked* mission row, not against what the caller merely asserts — holds everywhere I probed it,
including under real concurrent writers on Postgres. What does not fully hold is two things one
level down from that claim: an archive-safety check that covers path-shaped traversal but not
link-shaped traversal, and a cross-mission uniqueness check that is correct in outcome but not
atomic under real concurrency. Full reasoning in §15.4–§15.6.

### 15.1 Scope and what I ran, for real, this session

```
$ cd apps/control-api && python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
$ DJANGO_SETTINGS_MODULE=config.settings.test .venv/bin/python -m pytest -o addopts=""
======================= 294 passed, 2 warnings in 1.90s ========================

$ source .venv/bin/activate && python manage.py check
System check identified no issues (0 silenced).
$ python manage.py makemigrations --check --dry-run
No changes detected

$ bash infrastructure/scripts/openapi-contract-check.sh
openapi contract: PASS — the committed dump matches the live schema

$ .venv/bin/ruff check apps/control-api/authorization apps/control-api/api/tests/test_authorize_snapshot.py \
    apps/control-api/api/routers/missions.py apps/control-api/config/settings/base.py
All checks passed!

$ .venv/bin/pip-audit -r requirements.txt -r requirements-dev.txt
No known vulnerabilities found
```

Every one of the PR body's claimed results reproduced independently, on a venv I built myself
from the pinned requirements files, not from the author's environment. **294/294, ruff clean,
OpenAPI unchanged, no missing migrations, no vulnerable pin — all confirmed by me, not taken on
report.**

Also run, not claimed by the PR body:

```
$ detect-secrets scan apps/control-api/authorization apps/control-api/api/routers/missions.py \
    apps/control-api/config/settings/base.py apps/control-api/.env.example
# no findings besides the placeholder ARTIFACT_ROOT=/SNAPSHOT_SOURCE_ROOT=/SNAPSHOT_STAGING_ROOT=
# blank defaults in .env.example — not secrets, unset placeholders.
$ git ls-files | grep -i '\.env$'
# (nothing — .env is not tracked; .gitignore:22-23 covers it)
```

### 15.2 The SEC-15-pattern probe, run against every id these two endpoints accept

This is the thing I was asked to go looking for, specifically: `mission_id` vs. `repository_ref`
vs. `archive_ref` vs. cross-mission `Artifact.sha256` reuse, each checked against the *locked*
mission row rather than against what the caller merely claims.

| id | Checked against | Where | Verified how |
|---|---|---|---|
| `mission_id` | `Mission.objects.select_for_update().get(pk=mission_id)` — the lock itself | `service.py:57-64` | Read; the lock is the first statement in both `authorize_mission` and `create_mission_snapshot`. |
| `AuthorizationRequest.repository_ref` | `mission.repository_ref` (the locked row), exact string equality | `service.py:88-94` | **Independently re-verified by injection** — disabled the check, `test_authorization_for_a_different_repository_is_refused` and `test_a_refused_authorize_leaves_no_authorization_row_behind` went red (403→201), restored, green again. §15.3. |
| `SnapshotRequest.archive_sha256` (caller's assertion) | The digest actually computed by re-hashing the bytes the server itself streamed to disk (`store.ingest_from_path`) | `service.py:161-167` | Read + the PR's own `test_a_digest_the_server_cannot_verify_is_refused` / `test_a_swapped_archive_is_refused`, both still green in my run. Not independently re-injected by me — time-boxed to the two checks in §15.3 instead. |
| `Artifact.sha256` (content-addressed) | Every **other** mission's claim on the same digest | `service.py:171-173` | **Independently re-verified by injection** — disabled the check, `test_an_archive_digest_already_claimed_by_another_mission_is_refused` went red (409→201), restored, green again. §15.3. **Also independently re-verified under real concurrent Postgres writers**, where it found a real gap — SEC-27, §15.5. |
| `archive_ref` (staging-root path) | The fixed `SNAPSHOT_STAGING_ROOT` boundary, never against the mission | `service.py:201-215, 261-286` | Read. **Not** checked against the mission at all — this is real, and it is SEC-30, not a false alarm: `archive_ref` is a shared, flat, non-mission-scoped namespace by design. |
| `repository_ref` used to locate bytes | The fixed `SNAPSHOT_SOURCE_ROOT` boundary, by basename only | `service.py:218-258` | Read + symlink-escape and `..`-traversal manual probes, both correctly refused (§15.6 details the one gap that basename-only resolution has, which is not a traversal — it's a collision — SEC-29). |

**Net finding of the probe itself: the pattern SEC-15 named — an id accepted from a request and
never compared to the thing it is supposed to belong to — does not recur here for `mission_id`,
`repository_ref` (the authorization-declaration check), or `archive_sha256`/`Artifact.sha256` in
the single-threaded case.** Two adjacent gaps do exist, and they are not the SEC-15 pattern
exactly — they are a *link-following* variant of the same "check what's named, not what's really
there" family (SEC-26) and a *missing atomicity* variant of the same cross-mission check done
right in principle (SEC-27). Neither is a case of an id simply never being checked.

### 15.3 Independent re-verification by injection, per the standing rule

I did not trust the PR body's own injection table. I re-ran two of the five rows myself, on the
unmodified worktree, saving a `diff`-verified backup before each edit and restoring it after:

**Injection 1 — disable `require_active_authorization` in `create_mission_snapshot`:**

```
--- authorization/service.py
+        # require_active_authorization(mission, MissionStage.INGEST, now)
```
```
$ pytest api/tests/test_authorize_snapshot.py -k "without_an_authorization or expired_authorization or revoked_authorization"
FAILED test_snapshot_without_an_authorization_is_refused
FAILED test_snapshot_with_an_expired_authorization_is_refused
FAILED test_snapshot_with_a_revoked_authorization_is_refused
  assert 409 == 403   # fell through to the digest-mismatch check instead of refusing up front
3 failed, 16 deselected
```
Restored. `diff -q` against the pre-injection file: identical. Full 19-test file green again.

**Injection 2 — disable the cross-mission artifact-claim check in `create_mission_snapshot`:**

```
--- authorization/service.py
+        # if existing_artifact is not None and existing_artifact.mission_id != mission.id:
+        #     raise SnapshotArtifactClaimedError(details={"sha256": result.sha256})
```
```
$ pytest api/tests/test_authorize_snapshot.py -k already_claimed
FAILED test_an_archive_digest_already_claimed_by_another_mission_is_refused
  assert 201 == 409   # a second mission's snapshot silently claimed the first mission's artifact
1 failed, 18 deselected
```
Restored. Full 294-test suite re-run: **294 passed.**

Both of the checks I chose to re-verify are the two most load-bearing ones for the SEC-15 pattern
specifically — the pre-I/O authorization gate, and the cross-mission artifact binding. Both are
genuinely load-bearing, not merely present. I did not re-inject the digest-mismatch or
member-safety checks myself; those are read-verified only (member safety is separately attacked
in §15.6, which found the real gap the injection table did not cover).

### 15.4 The mission-row lock under real concurrency, not SQLite

The PR's own caveat: `SELECT ... FOR UPDATE` is a no-op on SQLite, so "lock the mission row
first, check everything against the locked row" was exercised single-threaded only. I stood up
an isolated `postgres:16-alpine` container (port 15432, unrelated to the other agents'
`brahmadatta-db` container, removed at the end of this session), ran real migrations against it,
and drove two real threads with two real DB connections at three scenarios.

```
=== Scenario A: same mission, two concurrent identical-digest snapshot posts ===
Thread X: ('ok', UUID(...))
Thread Y: ('ok', UUID(...))   <- same UUID as X
Snapshot rows for mission: 1

=== Scenario C: same mission, two concurrent DIFFERENT-digest snapshot posts ===
Thread P (digest1): ('ok', UUID(...), 'e639f1...')
Thread Q (digest2): ('SnapshotAlreadyRecordedError', 'This mission already has a snapshot with a different digest.')
Snapshot rows recorded for the mission: ['e639f1...']
```

**Confirmed under real Postgres: the mission-row lock genuinely serializes.** The loser in
Scenario C did not race, did not see a stale read, and was not able to overwrite the winner's
snapshot — it blocked on the row lock, then read the winner's already-committed row and refused
correctly with the documented `409`. This is exactly the property the PR's docstring claims and
it was previously unverified. **I am closing that half of the caveat: proven, not merely
asserted, on real Postgres, by me, this session.**

### 15.5 SEC-27 — the half of the caveat that did *not* hold

```
=== Scenario B: two DIFFERENT missions, byte-identical content, forced interleave
     via a barrier placed around Artifact.objects.filter(pk=...).first() ===
Thread A (mission_a): ('ok', UUID(...))
Thread B (mission_b): ('error', "IntegrityError: duplicate key value violates unique
    constraint \"artifact_pkey\"\nDETAIL: Key (sha256)=(0ff12f...) already exists.")
Artifact rows for this digest: 1
Snapshot rows: mission_a=1 mission_b=0
```

**The reason this scenario needed a forced interleave and Scenarios A/C did not:** the mission-row
lock only ever protects *one* mission's row. Two different missions' transactions never contend
for the same lock, so `Artifact.objects.filter(pk=result.sha256).first()` (`service.py:171`) and
`Artifact.objects.create(...)` (`service.py:175-180`) are a check-then-act pair with no lock
spanning both operations, for the cross-mission case specifically. A barrier around `.first()`
made the race deterministic instead of relying on thread-scheduling luck; the underlying gap is
real regardless of the barrier — it is a property of the code, not of my harness.

**Outcome quality: correct in the end, wrong in the telling.** The Postgres primary-key
constraint on `Artifact.sha256` is a real backstop — exactly one Artifact row exists, exactly one
mission ends up owning it, no data corruption occurred. But the loser did not get the documented,
tested `SnapshotArtifactClaimedError` → `409 CONFLICT`; it got a raw, unhandled
`django.db.utils.IntegrityError` → the generic `api.errors._unhandled` handler → `500 Internal
Error`, logged as `"unhandled error"` even though this is a fully anticipated, already-named
condition with its own exception class three lines above it. `api/errors.py`'s unhandled-exception
path does not leak internal detail to the client (confirmed by reading it — generic message, trace
id only), so this is not an information-disclosure finding. It is a correctness/robustness finding
that reproduces on demand.

**MEDIUM.** Rated below SEC-26 because (a) no data integrity or authorization property is broken
— the artifact ends up bound to exactly one mission, which is the property the check exists to
guarantee — and (b) the actor is an authenticated operator racing themselves or another operator,
not an external attacker, under the current flat single-`OPERATOR`-role trust model. Rated Medium
rather than Low because it is a demonstrated, reproducible divergence between the tested contract
and the concurrent-runtime behavior, in the exact module whose caveat predicted this class of gap.

**Required fix.** Wrap the `Artifact.objects.create(...)` call in `try`/`except IntegrityError`
and re-raise `SnapshotArtifactClaimedError` on a unique-violation of the primary key — three lines,
same shape as the existing check, and it turns the accidental-500 case into the documented 409
without changing behavior in the non-racing case. Add a regression test using the same
barrier-around-`.filter()` technique in this review (or Django's `TransactionTestCase` with two
real threads against the test Postgres container) so this is pinned rather than re-discovered.

**Location** — `apps/control-api/authorization/service.py:171-180`.

### 15.6 SEC-26 — the zip-slip check covers member *names*, not member *links*

`archive.py`'s docstring makes an explicit promise: `_is_safe_member_name` exists "so a downstream
stage that does extract this archive should never have to make that judgement call again with less
context than this one has." I took that promise as the thing to attack, per the task brief.

**The check.** `_is_safe_member_name(member.name)` is called for every tar and zip member and
correctly refuses `../../etc/passwd`-style and absolute names (`archive.py:33-39`,
`_enumerate_tar:65-69`, `_enumerate_zip:93-97`) — I re-read this and it is genuinely correct for
what it checks. **What it does not check, for a tar member specifically: `member.linkname`, or
`member.type` (`SYMTYPE`/`LNKTYPE`).** A tar symlink or hardlink member can carry an innocuous,
fully-safe `name` while its `linkname` points anywhere on the filesystem the extracting process can
reach. `enumerate_members` never extracts, so it never notices.

**Executed PoC, both halves — first that the "safe" gate accepts the archive, second what an
ordinary extraction of an archive that passed it actually does:**

```
>>> tar = a symlink member name="innocuous_link" -> linkname="../../../../etc",
...       plus a regular member name="innocuous_link/passwd" containing attacker bytes
>>> _is_safe_member_name("innocuous_link")          -> True
>>> _is_safe_member_name("innocuous_link/passwd")   -> True
>>> enumerate_members(tar_path)                     -> ACCEPTED: ArchiveInfo(file_count=1, bytes_total=14)
```

That alone proves the gate misses the class. To show it is not a theoretical miss, I extracted the
*same archive that `enumerate_members` accepted*, the ordinary way, on this project's own target
interpreter:

```
$ python3.12 -c "print(tarfile.TarFile.extraction_filter)"
None
DeprecationWarning: Python 3.14 will, by default, filter extracted tar archives...
```

Python 3.12 — the interpreter this project's own `README.md` tells every developer to build the
venv with — ships the PEP 706 filter machinery but **defaults `extraction_filter` to `None`**,
i.e. **unfiltered**, exactly like every Python version before it. The filter only becomes the
default in 3.14. A plain `tar.extractall(dest)` — the ordinary, unremarkable way the next developer
who writes the BASELINE/ANALYZE extraction stage will call it — gets no protection at all from the
interpreter, only from whatever `archive.py` checked in advance.

```
>>> evil_dir_target = a real directory OUTSIDE the intended extraction root, containing
...                    a pre-existing file HIDDEN_SECRET with known content
>>> tar.extractall(extract_root)   # default filter=None, no filter= kwarg passed
>>> open(victim_file).read()
'ATTACKER CONTROLLED CONTENT\n'
```

**Confirmed: an archive that `enumerate_members` reports as safe, extracted the ordinary way,
overwrites an arbitrary file outside the destination directory.** This is CWE-59 (Link Following),
the symlink variant of the zip-slip family — distinct from, and not covered by, the path-traversal
variant the existing test (`test_a_tar_with_a_path_traversal_member_is_refused`) and the module's
own name-based check actually defend against.

**HIGH, not Critical.** No extraction code path exists anywhere in this PR or the reachable
control-api today — `enumerate_members` only counts, it never writes. Nothing an external attacker
can reach over HTTP is compromised by this today. It is High rather than Critical because of that,
and High rather than Medium because: (a) extraction of exactly these archives is not speculative —
it is the explicit, near-term purpose of the BASELINE stage this same mission pipeline is built
around; (b) the module's docstring makes an affirmative, specific safety promise to that future
developer, and the promise is false; (c) zip-slip-class defects are a named CWE with well-understood
severity once the write path exists, and fixing it now, before any consumer relies on the false
promise, is materially cheaper than fixing it after BASELINE ships and depends on it.

**Required fix**, either is sufficient on its own, both is better:

1. In `_enumerate_tar`, refuse any member where `member.issym() or member.islnk()`
   (`TarInfo.SYMTYPE`/`TarInfo.LNKTYPE`) outright — a repository snapshot has no legitimate reason
   to contain a symlink or hardlink, and `build_tar_from_directory` (the only *writer* this PR
   ships) never produces one, so refusing them costs nothing today.
2. If symlinks must be permitted later, additionally validate `member.linkname` with the same
   `_is_safe_member_name`-style containment check applied to the *resolved* target, not just the
   member's own name.
3. A test that builds the exact PoC archive above and asserts `enumerate_members` raises
   `UnreadableArchiveError` — the zip case should get the analogous check for completeness even
   though Python's stdlib `zipfile.extractall` does not itself create symlinks from Unix mode bits.

**Location** — `apps/control-api/authorization/archive.py:33-39` (`_is_safe_member_name`),
`:59-78` (`_enumerate_tar`, the call site that never inspects `member.linkname`/`member.type`).

### 15.7 SEC-28 — `RepositoryOutOfScopeError`'s error code contradicts the check that just ran

The author's own flagged open question, judged rather than assumed, per the task brief.

**The problem, precisely.** `RepositoryOutOfScopeError` fires inside `_resolve_repository_ref`
(`service.py:218-258`), which is called from `_materialize_source`, which is called from
`create_mission_snapshot` **after** `require_active_authorization` (`service.py:138`) has already
run and already confirmed an active, unrevoked, unexpired authorization covers this stage. By the
time a caller can hit `RepositoryOutOfScopeError`, the system has already proven the authorization
*is* valid. Labeling the resulting refusal `ErrorCode.INVALID_AUTHORIZATION` tells the operator the
opposite of what was just established, for a failure that is actually about something else
entirely: the configured `SNAPSHOT_SOURCE_ROOT` deployment doesn't have this repository checked
out, or the operator supplied a remote URL this endpoint doesn't fetch.

**Why this is a real (if Medium) finding and not a style nit.** `ErrorCode.UNSUPPORTED_REPOSITORY`
already exists in the frozen vocabulary and is used, in this exact file, for exactly this class of
failure — `UnreadableArchiveError` (`errors.py:94-105`, "the archive could not be read as a tar or
zip") is `UNSUPPORTED_REPOSITORY`, not `INVALID_AUTHORIZATION`, for the identical reason: the
authorization is not in question, the *source material* is. Conflating "your authorization is
invalid" with "this deployment cannot read the repository you pointed at" sends an operator toward
the wrong remediation (re-authorizing, which will fail identically every time) instead of the right
one (stage the repository locally, or recognize that remote fetch isn't supported). This is exactly
the kind of mislabeling the standing rule about naming things honestly exists to catch, one level
below "does the check exist" — the check exists and is correct; the *label on its refusal* is not.

**Ruling on the author's open question:** `INVALID_AUTHORIZATION` is the wrong code.
`ErrorCode.UNSUPPORTED_REPOSITORY` is correct, matching the sibling error one function away in the
same file. This also changes the HTTP status from `403` to whatever `UnreadableArchiveError` uses
(`422`) for consistency, or the class can keep `403` with `UNSUPPORTED_REPOSITORY` if 403 is judged
the better status for a scope refusal — the code is the finding, the status is a secondary call for
whoever fixes it.

**Required fix.** `errors.py:107-121`: change `RepositoryOutOfScopeError.code` from
`ErrorCode.INVALID_AUTHORIZATION` to `ErrorCode.UNSUPPORTED_REPOSITORY`. Update
`test_repository_ref_with_an_unsupported_scheme_is_refused` (`api/tests/test_authorize_snapshot.py:471`)
accordingly — it currently pins the wrong code, which is why this shipped.

**Location** — `apps/control-api/authorization/errors.py:107-121`.

### 15.8 SEC-29 — basename-only `repository_ref` resolution collapses distinct paths onto one directory

Judging the author's other flagged decision, per the task brief: basename-only lookup under
`SNAPSHOT_SOURCE_ROOT` versus joining a containment-checked full path versus a registry.

**The traversal question is correctly closed.** I read `_resolve_repository_ref`
(`service.py:218-258`) specifically looking for a string an operator could put in `repository_ref`
that reaches outside `SNAPSHOT_SOURCE_ROOT`, and there isn't one — only `PurePosixPath(...).name`
survives, backslashes are normalized to forward slashes first, and the result is re-checked against
`root.resolve()`'s parents regardless. This is a genuinely stronger construction than "join and
check containment," for the reason the author's decision record gives: there is no path-shaped
input left to get wrong. **I endorse this half of the decision.**

**What the decision record does not weigh: identity, not traversal.** Basename-only resolution
means `file:///org-a/repos/pktcfg`, `file:///org-b/repos/pktcfg`, and bare `pktcfg` are
*indistinguishable* — all three resolve to the identical `SNAPSHOT_SOURCE_ROOT/pktcfg`. Two
missions whose operators each correctly declared a `repository_ref` that matches their own
mission's row (so the SEC-15-pattern check in `authorize_mission` passes for both, honestly) can
still end up snapshotting the exact same on-disk directory if their intended repositories merely
share a final path component — silently substituting the wrong repository's content into one
mission's immutable, authorized evidence record, with no error anywhere in the request path.

**Not reachable today.** `create_mission` is still `NotImplementedYetError` (confirmed by reading
`api/routers/missions.py:74-79`), so `repository_ref` is presently server-side fixture/ORM data, not
attacker- or even operator-reachable through the HTTP surface. This is why it is Medium rather than
High: it is a design gap in code that is real and merged, not a live bypass.

**MEDIUM, and it should be closed before #12 lands `create_mission`,** not after — once mission
creation is a real endpoint, whoever names the second repository with a colliding basename does not
need malicious intent, only bad luck with directory naming (`pktcfg` is exactly the kind of short,
generic name a second target is likely to also use).

**Required fix, either is sufficient:** (a) a uniqueness constraint or startup check enforcing that
every directory directly under `SNAPSHOT_SOURCE_ROOT` has a name used by at most one
`repository_ref` value across all missions — cheap, and keeps the current traversal-proof
resolution; or (b) move to the author's option (c), a registry mapping `repository_ref` to a
specific directory, once #12 exists and there is a natural place to put it. I am not picking
between them — that is an implementation call for the owning developer — but I am requiring that
this decision explicitly re-examine the identity question, not only the traversal question, before
`create_mission` ships.

**Location** — `apps/control-api/authorization/service.py:218-258` (`_resolve_repository_ref`).

### 15.9 SEC-30 — `archive_ref` is a shared namespace with no mission scoping at all

**The gap.** Whenever a caller supplies `archive_ref` (for `source="upload"`, or for
`source="git"` with `archive_ref` also set — both real, tested code paths per the PR body's scope
decision 2), it is resolved under `SNAPSHOT_STAGING_ROOT` and is **never compared to the requesting
mission in any way** (`service.py:261-286` — contrast with `_resolve_repository_ref`, which at
least derives from the mission's own row). `SNAPSHOT_STAGING_ROOT` is one flat directory shared by
every mission.

**Exploit scenario, combined with SEC-27.** Suppose mission A's operator stages a file at
`archive_ref="build.tar"` (a real path once an upload endpoint exists) but has not yet called
`/snapshot`. Any operator — including one working an unrelated mission B — can supply
`archive_ref="build.tar"` on **mission B's** `/snapshot` call. If mission B's request is processed
first, mission B's `Artifact` row claims that digest; when mission A subsequently calls `/snapshot`
with its own correctly-computed digest, it is refused with `SnapshotArtifactClaimedError` — a
mission denied a snapshot of its *own* staged content because a different mission's operator
happened to name the same staged file first.

**Tempered by two things.** First, the current role model (`api/auth.py:83-85`) is a single flat
`OPERATOR` role with no per-mission ACL — every operator can already act on every mission, so this
is not a privilege-boundary crossing between distrusting parties under the system as designed
today. Second, no upload endpoint exists yet to place operator-influenced content at a
`archive_ref`-addressable path — `SNAPSHOT_STAGING_ROOT` is only reachable from fixtures in the
test suite right now.

**MEDIUM.** Real design gap, not a live bypass, in code that is merged and tested. The entire
purpose of the content-addressed `Artifact` index with mission binding (the check SEC-27 is about)
is to make evidence unambiguously belong to the mission that produced it; leaving the *path that
produces the bytes* completely unscoped by mission undermines that purpose even under a flat trust
model, because "which mission's operator gets first claim on a race" is not the same guarantee as
"this snapshot is this mission's own declared content."

**Required fix.** Before an upload endpoint ships: either namespace staged uploads per-mission
(e.g. `SNAPSHOT_STAGING_ROOT/<mission_id>/<archive_ref>`, so one mission's `archive_ref` value
cannot resolve to another mission's staged bytes at all), or require the staging mechanism to record
which mission a staged file was intended for and check it in `_materialize_source`. This does not
need to block #18 in isolation — no upload endpoint exists to exploit it through yet — but it must
be resolved as part of, not after, whichever PR adds one.

**Location** — `apps/control-api/authorization/service.py:261-286` (`_materialize_source`),
`:201-215` (`_resolve_under_root`).

### 15.10 SEC-31 — the module's own docstring cites tests that do not exist

`apps/control-api/authorization/__init__.py:27-33` lists, as the evidence for property 4 ("no
stage runs without an active record"):

```
— ::test_snapshot_without_an_authorization_is_refused,
  ::test_preflight_without_an_authorization_is_refused,
  ::test_start_without_an_authorization_is_refused
```

```
$ grep -rn "test_preflight_without_an_authorization_is_refused\|test_start_without_an_authorization_is_refused" \
    --include="*.py" apps/control-api
(no output)
```

**Neither test exists anywhere in the codebase.** `preflight_mission` and `start_mission`
(`api/routers/missions.py:150-168`) are unconditional `NotImplementedYetError` — they raise before
any authorization check, any orchestrator call, or any business logic runs at all (confirmed by
reading; `require_role` runs, then the router body is exactly one line). The property these two
citations claim to demonstrate is not merely undemonstrated at those two stages — it cannot be,
because nothing reachable at those routes touches the authorization gate yet.

**LOW-MEDIUM.** No security control is weakened by this — it's a documentation-accuracy defect, not
a code defect — but it sits inside the exact module whose stated purpose is to be the trustworthy
record of what this gate enforces, in a codebase whose own standing rule is "a property is described
as enforced only when a named test demonstrates it." A future reviewer or auditor reading this
docstring as the authoritative summary (which its position and tone invite) would reasonably, and
wrongly, conclude `preflight`/`start` already refuse without authorization.

**Required fix.** Either write the two tests against the real `NotImplementedYetError` behavior (a
test that a stub 501s regardless of authorization state is a legitimate, if weak, thing to assert
and name), or remove the two false citations and replace them with an explicit statement of what
§15.11 below states: the property is demonstrated at `INGEST` only, and is not yet reachable at the
other nine stages.

**Location** — `apps/control-api/authorization/__init__.py:27-34`.

### 15.11 SEC-32 · INFO · `Authorization.snapshot_sha256` binding is inert — every authorization is unbound

`contracts/authorization.py:48-53` documents `snapshot_sha256`: "Once set, the authorization covers
this snapshot and no other." `covers_snapshot` (`:87-95`) returns `True` unconditionally whenever
`record.snapshot_sha256 is None`.

```
$ grep -rn "snapshot_sha256" apps/control-api --include="*.py" | grep -v tests
# every hit is a READ (covers_snapshot, load_active_authorization, latest_snapshot_sha256,
# assert_stage_can_run) or a schema field declaration. No call anywhere sets
# Authorization.snapshot_sha256 to anything other than its column default (NULL).
```

`authorize_mission`'s `Authorization.objects.create(...)` (`service.py:97-104`) never passes
`snapshot_sha256`. Every `Authorization` row this PR can produce is therefore permanently unbound,
and `covers_snapshot` returns `True` for it against any snapshot digest, forever.

**Not a live gap today.** The scenario this binding exists to prevent — an authorization granted
for one snapshot being reused to justify work on a *different, later* snapshot of the same mission
— cannot currently occur regardless, because `create_mission_snapshot` is write-once per mission
(`SnapshotAlreadyRecordedError`, independently confirmed serialized under real Postgres in §15.4).
So the two guarantees currently overlap completely: one mission, one snapshot, one (or more renewed)
unbound authorization, and `covers_snapshot` being permanently `True` changes nothing observable.

**INFO, tracked rather than rated as a finding with a required fix**, because there is no code path
today where it matters. Flagging it so nobody reads the schema docstring's "once set" language and
assumes the binding is enforced — it is declared, and it is inert. Whoever implements
re-authorization-after-re-snapshot, or any flow that produces a second snapshot for a mission (a
future scope change), must either set this field or explicitly re-justify why it is still safe to
leave unset.

**Location** — `apps/control-api/authorization/service.py:97-104`; `contracts/authorization.py:48-53,87-95`.

### 15.12 What was reachable, and what plainly was not — the nine-stub caveat

Confirmed by reading `api/routers/missions.py` directly, not inferred from the PR body: **only
`authorize_mission` and `create_snapshot` call into `authorization.service`.**
`create_mission`, `list_missions`, `get_mission`, `preflight_mission`, `start_mission`,
`pause_mission`, `cancel_mission`, `replay_events` and `stream_events` all raise
`NotImplementedYetError` (or its SSE equivalent) unconditionally, **before** any authorization
check, any state-machine call, or any business logic runs.

**"No stage runs without an active authorization record" is demonstrated for exactly one stage:
`INGEST`, via `/snapshot`.** It is not merely "weakly demonstrated" at `BASELINE`/`TRIAGE`/etc — it
is **not exercised at all**, because those routes 501 unconditionally and never reach the
orchestrator or the guard. This matches the PR body's own §"NOT RUN" item 4, and I am independently
confirming it reads correctly, not softening or inflating it: the property this gate exists to
prove holds for the one stage that is wired up, and is simply not yet testable — not "not yet
proven," genuinely not yet testable — for the other nine.

### 15.13 What I did not review

1. **The frontend / OpenAPI-consumer side of any of this.** No `apps/command-center` code exists
   yet to check against the (unchanged) contract.
2. **`mypy`.** Not run — the PR body says the same.
3. **The `.env.example` new keys' effect on the finale/development profile system checks** beyond
   `manage.py check` passing on the test profile. I did not run the finale-profile checks against
   these four new settings specifically.
4. **A live upload endpoint.** Does not exist; SEC-30's exploit path is analyzed against the code as
   written, not executed against a running upload flow.
5. **Concurrent `authorize_mission` calls racing a `create_mission_snapshot` call for the same
   mission** (as opposed to same-endpoint races, which §15.4/§15.5 cover). Not run.
6. **Resource/DoS behavior of `build_tar_from_directory`** against a very large or very deep
   directory tree (as opposed to `ingest_from_path`'s `max_bytes` ceiling, which I did verify —
   §15.1 covers the file-permission and ceiling checks I ran and are not repeated here since they
   held: `0600`/`0700` confirmed on disk, oversized source correctly refused mid-stream with the
   temp file cleaned up, no orphan).
7. **`infrastructure/`, `services/model-gateway/`, `adapters/cpp/`** — out of scope for this PR;
   other agents' live work, untouched.

### 15.14 Verdict

**PASS WITH CONDITIONS.** No Critical finding. The core promise this gate exists to make — every
id is checked against the *locked* mission row, not against what the caller claims — holds
everywhere I probed it, including under real concurrent Postgres writers, which was the specific
thing left unproven going into this review. Two adjacent checks (archive link-safety,
cross-mission-claim atomicity) do not fully hold, and one already-flagged error-code choice is
confirmed wrong. None of the seven findings below allow an unauthorized caller to bypass the
authorization gate, forge a digest, or corrupt another mission's evidentiary record through any
HTTP surface reachable today.

**Conditions on merge:**

1. **SEC-26 (HIGH)** — refuse tar symlink/hardlink members outright in `archive.py`, before any
   extraction-capable stage is built on top of this module. This is the one condition I would treat
   as a hard blocker on the *next* PR that adds archive extraction, even though it does not block
   this one.
2. **SEC-27 (MEDIUM)** — catch the `IntegrityError` on the cross-mission artifact-claim race and
   re-raise `SnapshotArtifactClaimedError`; add a concurrency regression test.
3. **SEC-28 (MEDIUM)** — `RepositoryOutOfScopeError` → `ErrorCode.UNSUPPORTED_REPOSITORY`, and
   update the one test that currently pins the wrong code.
4. **SEC-31 (LOW-MEDIUM)** — remove or make true the two false test citations in
   `authorization/__init__.py`.

**Tracked, not blocking this PR, but blocking the PR that makes them reachable:**

5. **SEC-29 (MEDIUM)** — resolve the basename-collision identity gap before `create_mission` (#12)
   lands and `repository_ref` becomes operator-reachable.
6. **SEC-30 (MEDIUM)** — namespace `archive_ref`/staged uploads per-mission before an upload
   endpoint ships.
7. **SEC-32 (INFO)** — no action required now; re-examine `Authorization.snapshot_sha256` binding
   the moment any flow can produce a second snapshot for one mission.

I will re-verify SEC-26, SEC-27 and SEC-28 personally before the follow-on PRs that depend on this
one merge.

### 15.15 Decision records to fold into `.project/decisions.md`

**DR-SEC-R4-1 · `RepositoryOutOfScopeError` is mislabeled and must move to `UNSUPPORTED_REPOSITORY`**

**Decision** — `RepositoryOutOfScopeError.code` changes from `ErrorCode.INVALID_AUTHORIZATION` to
`ErrorCode.UNSUPPORTED_REPOSITORY`.

**Options considered** — (a) leave it as `INVALID_AUTHORIZATION`, on the grounds that it is "the
closest analog" (the author's own hedge in the PR body); (b) reassign to
`UNSUPPORTED_REPOSITORY`, matching the sibling `UnreadableArchiveError` in the same file; (c) add a
new `ErrorCode` member for this specific case.

**Pros and cons** — (a) is free but actively misleading: the check fires only after
`require_active_authorization` has already proven the authorization valid, so the code contradicts
a fact the system just established, and it sends operators toward the wrong remediation. (c) is a
contract change requiring OpenAPI regeneration and a frontend rebuild, the exact cost DR-BE-1 (#110)
and this PR's own second decision record both already ruled against paying for a distinguishable
`details` payload. (b) is free, reuses an existing code with the correct semantics one function
away in the same file, and requires updating exactly one test that currently pins the wrong value.

**Cost implications** — (b): one line in `errors.py`, one assertion in one existing test.

**Security implications** — (b) improves incident diagnosis and operator remediation for a refusal
on the safety-boundary path ("authorized repositories... only" per `CLAUDE.md`); it does not change
any control's behavior, only its label.

**Scalability implications** — none.

**Recommendation** — (b).

**Final approval authority** — cybersecurity (error-code semantics on a security-relevant refusal
path are mine to call; CTO may arbitrate if this is judged a contract-stability question instead).

**DR-SEC-R4-2 · Basename-only `repository_ref` resolution is accepted for traversal-safety, conditioned on an identity fix before `create_mission` lands**

**Decision** — endorse the author's basename-only resolution under `SNAPSHOT_SOURCE_ROOT` as the
traversal defense (no path-shaped input reaches outside the root); require a uniqueness invariant
or a registry-based resolution before `repository_ref` becomes operator-reachable through
`create_mission` (#12).

**Options considered** — the author's own three, restated in §15.8: (a) basename-only (as built);
(b) full relative path plus containment check; (c) an explicit registry.

**Pros and cons** — (a) is correctly the strongest against traversal, for the reason the author's
decision record gives — no path string is left to get wrong. It is silent on identity: two
different intended repositories sharing a final path component collapse onto one directory, which
is a correctness gap, not a traversal gap, and the author's decision record does not weigh it
because it was framed as a traversal-only question. (b) reopens the traversal risk the author
correctly avoided. (c) resolves both but has no natural home before #12 exists.

**Cost implications** — near-zero now (a directory-naming convention plus a startup check); a
larger, but still small, change if (c) is chosen once #12 lands.

**Security/data-integrity implications** — without a fix, the immutable, authorized snapshot record
— this system's central evidentiary claim — can silently contain the wrong repository's content for
a mission whose own declared `repository_ref` was correctly authorized. That is worse than a refused
request; it is an unnoticed wrong answer.

**Scalability implications** — none at current mission volume; grows with the number of distinct
target repositories sharing directory-naming conventions.

**Recommendation** — ship (a) as built for #18 (traversal safety is real and matters now); require
the identity gap closed as an explicit condition on #12, not deferred indefinitely.

**Final approval authority** — CTO for the resolution mechanism chosen; cybersecurity for whether
the condition on #12 is satisfied before that PR merges.
