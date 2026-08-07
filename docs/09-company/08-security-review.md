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
| **Overall security posture of the reviewed surface** | **BLOCKED — one Critical open (SEC-01).** |

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
