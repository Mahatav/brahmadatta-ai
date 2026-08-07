# QA report — PR #87, `feat/control-api-scaffold`

**Author of this report:** `qa` agent
**Date:** 2026-08-07 (D1)
**Under test:** PR #87 — Django + django-ninja control API and the frozen mission contract
**Tested at:** `origin/feat/control-api-scaffold` (`a853e80`) **merged with** `origin/main`
(`ff0a11e`), merge commit `1eeb176` in a throwaway detached worktree. Nothing was pushed.
**Issues in scope:** #6, #9 (Django half), #77, #78, #80, and the CTO/security conditions
held against this code.

---

## Verdict

# REJECTED

**Two blockers.** Both are CI-red-on-merge, and both are cheap to fix today.

| | |
|---|---|
| **BUG-001** | Merging #87 makes the required CI job `pytest` **fail**. `tests/architecture/test_ingress_contract.py::test_use_x_forwarded_host_is_enabled` passes on `main` only because it skips when `apps/control-api/` is absent. This PR creates that directory and does not set `USE_X_FORWARDED_HOST`. |
| **BUG-002** | The required CI job `openapi dump is current` **fails**, and worse, the gate is non-functional: `tools/export_openapi.py` ignores `argv[1]`, so `infrastructure/scripts/openapi-contract-check.sh` **overwrites the committed dump in the working tree** and then exits 1 with a misleading message. Issue #6's acceptance criterion — "a contract change breaks the frontend build" — is currently false at the CI layer. |

Beyond the blockers, six **major** findings say the same thing in different places: several
invariants this PR describes as *structurally enforced* are in fact **enforced by a
convention the caller has to follow**. That is precisely the failure mode #77 was raised to
eliminate, and it is much cheaper to close on D1 than on D6.

**What is genuinely good, and I want it on the record:** the contract surface is real,
complete and reachable (23 operations, 87 schemas, all 26 event types and all 23 error
codes present in the published dump); the committed dump regenerates **byte-identically**;
`derive_verdict` really does take only a `GateMatrix`; `VerificationRecord` really does
refuse to hold a verdict its gates do not produce; the CTO's exact #77 case really is
refused now; the SSE stream is genuinely streamed under ASGI; and the finale profile really
does force the Django admin off. Those are not narrated — every one is executed below.

---

## 1. Test environment

```
$ .venv/bin/python -V
Python 3.12.13

$ .venv/bin/pip list | grep -iE "^(django|django-ninja|pydantic|uvicorn|psycopg|pytest)"
Django            5.2.17
django-ninja      1.6.2
psycopg           3.3.4
pydantic          2.13.4
pytest            9.1.1
pytest-asyncio    1.4.0
pytest-django     4.13.0
uvicorn           0.52.1

$ git log --oneline -3
1eeb176 Merge remote-tracking branch 'origin/main' into HEAD
ff0a11e docs(product): close phase 1 with the product review and four rulings (#88)
4bbb2df docs: security review gate — one Critical, PR #74 verdict, #78 and isolation rulings (#89)
```

Host: macOS 15.5 (darwin 25.5.0), aarch64. The merge produced exactly one conflict, in
`.project/decisions.md`; it was resolved `-X ours` **in a scratch worktree only** and never
committed to any branch that is pushed. `.project/decisions.md` was not edited.

### On PostgreSQL — the author's stated gap, now closed

The PR says PostgreSQL was unreachable and does not claim otherwise. I closed that gap
rather than inheriting it: Docker was available on this host, so I ran a throwaway
`postgres:16-alpine` on port 55432 and exercised the finale profile against it. Results in
§6. **What that does and does not prove is stated explicitly there** — it is not equivalent
to "PostgreSQL is verified", because this PR contains no models.

---

## 2. Re-running the author's claims

### TC-1 — Full test suite. Claim: "169 tests, run, all passing". **PASS — confirmed.**

```
$ cd apps/control-api && .venv/bin/python -m pytest
........................................................................ [ 42%]
........................................................................ [ 85%]
.........................                                                [100%]
169 passed in 0.99s
```

Collected breakdown, so the number is not just a total:

```
$ .venv/bin/python -m pytest --collect-only | grep -E "^(contracts|api)/" | sed 's/:.*//' | sort | uniq -c
  19 api/tests/test_http_surface.py
   8 api/tests/test_settings_profiles.py
  16 contracts/tests/test_enums.py
   9 contracts/tests/test_envelope.py
  28 contracts/tests/test_model_policy.py
  13 contracts/tests/test_openapi_dump.py
  38 contracts/tests/test_state_machine.py
  38 contracts/tests/test_verdict.py
--- total ---
169 tests collected in 0.12s
```

The count and the result are exactly as reported. No inflation.

### TC-2 — `manage.py check`. **PASS.**

Fails closed with no secret, which is the correct behaviour and worth recording:

```
$ .venv/bin/python manage.py check          # no .env present
config.env.ImproperlyConfigured: Required environment variable DJANGO_SECRET_KEY is unset.
See apps/control-api/.env.example.
exit=1

$ .venv/bin/python manage.py check          # with a locally generated .env
System check identified no issues (0 silenced).
exit=0
```

### TC-3 — Does the committed OpenAPI dump regenerate identically? **PASS.**

```
$ md5 ../../packages/schemas/openapi.json
MD5 (../../packages/schemas/openapi.json) = 8862ca7e4ade67e7365744af71ddbd36
$ .venv/bin/python tools/export_openapi.py
unchanged: .../packages/schemas/openapi.json (172311 bytes)
$ md5 ../../packages/schemas/openapi.json
MD5 (../../packages/schemas/openapi.json) = 8862ca7e4ade67e7365744af71ddbd36
$ git status --short packages/
(no output)
```

And the **served** document is semantically identical to the committed one, which is the
property that actually matters for the freeze:

```
served == committed (semantic): True
paths: 22 schemas: 87
operations: 23
```

Note: the PR says "twenty-two typed endpoints". There are 22 *paths* and **23 operations**
(`/api/v1/missions` carries both `get` and `post`). Documentation nit, no action.

### TC-4 — Is drift actually caught? **PASS (in-suite) / FAIL (CI gate — see BUG-002).**

I injected a real schema change (`ArtifactRef.kind` gained a description) and re-ran:

```
$ .venv/bin/python -m pytest contracts/tests/test_openapi_dump.py::test_committed_dump_is_current
E   AssertionError: packages/schemas/openapi.json is stale. Re-run
    `.venv/bin/python tools/export_openapi.py` and commit the result.
FAILED contracts/tests/test_openapi_dump.py::test_committed_dump_is_current
1 failed in 0.27s
```

The in-suite guard is real. The CI-level guard is not — see BUG-002.

### TC-5 — Contract completeness. **PASS.**

```
envelope module schema classes: 26
NOT reachable in the published dump: none
EventType members in code: 26; in dump: 26; missing: none
payload variants in dump: 15
ErrorCode in code: 23; in dump: 23; missing: none
```

`SANDBOX_UNAVAILABLE`, `JOB_TIMED_OUT` and `VERIFICATION_REQUIRED` are all present. The
claim that every event payload variant is reachable from a route holds.

### TC-6 — "`confidence` appears exactly once". **PASS in substance.**

The string occurs five times in the dump; **exactly one is a field**, and it is
`ModelProvenance.confidence`, marked `DISPLAY ONLY`, optional, and absent from
`required`. The other four are prose in three descriptions and one auto-generated `title`.
The substance of the claim is true.

---

## 3. Invariant 1 — *repository content never reaches a hosted inference API*

I attacked this rather than confirming it. Table-driven, executed against
`contracts.model_policy.is_local_inference_endpoint`:

```
RESULT  ALLOWED  EXPECTED   LABEL                                 URL
--------------------------------------------------------------------------------------------------
[ok]    True     True       loopback (control)                    'http://127.0.0.1:8000/v1'
[ok]    True     True       compose service name (control)        'http://small-model:8000/v1'
[ok]    False    False      OpenAI, plain                         'https://api.openai.com/v1'
[FAIL]  True     False      AWS/Azure/GCP IMDSv1                  'http://169.254.169.254/latest/meta-data/'
[FAIL]  True     False      EC2 IMDS over IPv6 (ULA)              'http://[fd00:ec2::254]/latest/meta-data/'
[FAIL]  True     False      GCP metadata by name                  'http://metadata.google.internal/computeMetadata/v1/'
[FAIL]  True     False      Alibaba metadata (CGNAT)              'http://100.100.100.200/latest/meta-data/'
[FAIL]  True     False      IDNA homograph U+3002                 'http://api。openai。com/v1'
[FAIL]  True     False      IDNA homograph U+FF0E fullwidth       'http://api．openai．com/v1'
[ok]    False    False      punycode label                        'http://xn--api-2h3ea1a.com/v1'
[FAIL]  True     False      bare label 'openai'                   'http://openai/v1'
[ok]    False    False      trailing dot FQDN                     'http://api.openai.com./v1'
[ok]    False    False      uppercase                             'http://API.OPENAI.COM/v1'
[FAIL]  True     False      *.test suffix wraps OpenAI            'http://api.openai.com.evil.test/v1'
[FAIL]  True     False      attacker-controlled .internal         'http://evil.internal/v1'
[FAIL]  True     False      userinfo confusion                    'http://api.openai.com:443@evil.local/v1'
[ok]    False    False      userinfo + real hosted host           'http://user:pass@api.openai.com/v1'
[FAIL]  True     False      decimal-encoded 127.0.0.1             'http://2130706433/v1'
[FAIL]  True     False      hex-encoded loopback                  'http://0x7f000001/v1'
[ok]    False    False      IPv4-mapped IPv6 public addr          'http://[::ffff:104.18.7.1]/v1'
[ok]    False    False      IPv4-mapped IPv6 8.8.8.8              'http://[::ffff:8.8.8.8]/v1'
[FAIL]  True     False      NAT64 well-known prefix -> 8.8.8.8    'http://64:ff9b::808:808/v1'
[ok]    False    False      NAT64 bracketed                       'http://[64:ff9b::808:808]/v1'
[FAIL]  True     False      unspecified 0.0.0.0                   'http://0.0.0.0/v1'
[FAIL]  True     False      unspecified ::                        'http://[::]/v1'
[FAIL]  True     False      ECS task metadata creds endpoint      'http://169.254.170.2/v2/credentials'
[FAIL]  True     False      attacker .svc suffix                  'http://sneaky.svc/v1'
[FAIL]  True     False      mDNS name resolving outward           'http://redirector.local/v1'
[ok]    False    False      fragment ends with .internal          'http://api.openai.com/v1#.internal'
[FAIL]  True     False      TEST-NET-1 documentation range        'http://192.0.2.1/v1'
--------------------------------------------------------------------------------------------------
MISMATCHES: 19 of 30
```

Some of those 19 are arguable by policy (`.internal` / `.test` / `.svc` suffixes are
conventions the pack itself endorses). **These are not arguable**, and each boots the API
clean:

```
$ SMALL_MODEL_BASE_URL=... .venv/bin/python manage.py check

https://api.openai.com/v1                             -> SystemCheckError (brahmadatta.E001)   [correct]
http://169.254.169.254/                               -> System check identified no issues (0 silenced).
http://metadata.google.internal/computeMetadata/v1/   -> System check identified no issues (0 silenced).
http://api。openai。com/v1                            -> System check identified no issues (0 silenced).
http://100.100.100.200/latest/meta-data/              -> System check identified no issues (0 silenced).
http://[fd00:ec2::254]/                               -> System check identified no issues (0 silenced).
http://134744072/v1                                   -> System check identified no issues (0 silenced).
http://openai/v1                                      -> System check identified no issues (0 silenced).
```

Nine of these ten cases are already documented by `cybersecurity` as **SEC-02** (issue #78,
downgraded HIGH → MEDIUM after SEC-01's network fix landed on #91). `contracts/model_policy.py`
is untouched by this PR, so SEC-02 is neither fixed nor regressed here. I am **not** rating
its severity — that is `cybersecurity`'s call and they have already made it.

### One bypass that is not in the security review, and it is worse than the homograph

```
$ python -c "import socket; print(socket.getaddrinfo('134744072', 80, socket.AF_INET)[0][4])"
('8.8.8.8', 80)
```

`http://134744072/v1` reaches `model_policy.py:99` — *"A bare label with no dots is a
container/compose service name"* — and is **allowed**, because `"." not in host`. But
`inet_aton` accepts a bare 32-bit decimal, so the OS resolver turns it into a fully public
address. Every dotless integer is a public IPv4 in disguise. The existing SEC-02 fix
proposal (IDNA normalisation + explicit metadata denies + an allowlist of service names)
closes this too **only if** the bare-label branch is replaced with a real allowlist read
from settings, rather than patched case by case. That is the version to implement.

And, confirming the reviewer's homograph finding independently:

```
homograph raw host repr: 'api。openai。com'
idna.encode(uts46=True): b'api.openai.com'
```

### What I did **not** run

- **No egress attempt from inside a running container.** `cybersecurity` executed that on
  #91 and closed SEC-01 with `Network is unreachable` from the kernel. I did not re-run it;
  the finale compose stack was not brought up in this session. **NOT RUN.**
- **No proxy-environment-variable test.** There is no HTTP client to any model endpoint in
  this diff at all, so there is nothing for `HTTPS_PROXY` to affect yet. The test belongs
  with the model gateway (#35). **NOT RUN — not yet applicable.**
- **No DNS-resolving-outward test against a live resolver**, beyond the decimal-encoding
  case above, which is the same class and needed no network. **NOT RUN.**

### Sandbox egress vocabulary — **PASS**

```
$ curl -X POST -H "Authorization: Bearer <operator>" -d '{... "policy":{"sandbox":{"network":"allow"}}}' .../api/v1/missions
422
{"error":{"code":"VALIDATION_ERROR", ..., "loc":["body","payload","policy","sandbox","network"],
 "msg":"Input should be 'deny'", "ctx":{"expected":"'deny'"}} ...}
```

`SandboxPolicy.network: Literal["deny"]` holds. The API has no vocabulary for egress.

---

## 4. Invariant 2 — *confidence never gates a verdict*

### 4a. #77's exact case — **FIXED. Confirmed by execution.**

```
[refused] A1  EXPORTING -> VERIFIED, verifications=() (default):
              VerificationRequiredError: Cannot enter VERIFIED: no verification records.
              A verdict state must be justified by at least one gate matrix.
[refused] A2  EXPORTING -> REJECTED, verifications=():
              VerificationRequiredError: Cannot enter REJECTED: no verification records. ...
[refused] A3  EXPORTING -> VERIFIED, one record over a FAILED regression gate:
              VerificationRequiredError: Cannot enter VERIFIED: the mission's 1 verification
              run(s) derive REJECTED, which does not justify that state.
[refused] A4  VerificationRecord(verdict=VERIFIED) over a FAILED regression gate:
              ValidationError: 1 validation error for VerificationRecord
[ALLOWED] A5  EXPORTING -> VERIFIED with one genuine passing record  (expected: allowed)
```

The CTO's Critical is closed on its own terms. #77 acceptance criteria 1–5 are met, and
criterion 6 is met too:

```
POSTURE_BY_STATE[CANCELLED]  = CANCELLED     <- no longer FAILED. Correct.
POSTURE_BY_STATE[CANCELLING] = CANCELLED
POSTURE_BY_STATE[PAUSED]     = HUMAN_REVIEW  <- observation, see §8
```

### 4b. C6 — the guard takes *anything with a `.verdict` attribute*. **BUG-003, major.**

`assert_verdict_is_evidenced` is annotated `Sequence[VerificationRecord]` but it is a plain
function, so the annotation is not checked at runtime. Line 225 does `record.verdict`, and
that is the whole contract:

```
[BYPASS] B1  verifications=[SimpleNamespace(verdict=Verdict.VERIFIED)]        ALLOWED
[BYPASS] B2  verifications=[CandidateVerdict(verdict=VERIFIED)]               ALLOWED
[refused] B3 verifications=[Verdict.VERIFIED]  (bare enum)
             AttributeError: 'Verdict' object has no attribute 'verdict'
```

**B2 is the one that matters.** `CandidateVerdict` is not a hostile stub — it is a schema
in this very contract package, it is what `MissionVerdictSummary` is built from, and it
carries **no gate matrix at all**. A caller holding a `MissionVerdictSummary` (the natural
thing to have at `EXPORTING` time) and passing `summary.candidates` gets `VERIFIED` with
zero gates consulted. The PR's own table says the fix works because "`assert_transition`
takes the mission's verification records". It takes whatever the caller hands it.

B3 shows the bare-enum form raises — but with an `AttributeError`, not a
`VerificationRequiredError`. A guard that fails on the wrong exception type is a guard that
somebody's `except VerificationRequiredError` will eventually swallow into a 500.

### 4c. The candidate set is not bound to the mission. **BUG-004, major.**

The derivation rule (D-025) is written down and correct in isolation:

```
derive_mission_verdict([VERIFIED, REJECTED])              = VERIFIED
derive_mission_verdict([VERIFIED, HUMAN_REVIEW_REQUIRED]) = HUMAN_REVIEW_REQUIRED
```

But nothing checks that the list is the mission's actual, complete candidate set:

```
[BYPASS] C1  mission ran 2 candidates; caller passes ONLY the passing one -> VERIFIED
[BYPASS] C2  mission ran [VERIFIED, HUMAN_REVIEW]; caller drops the HR record -> VERIFIED
[BYPASS] C3  records from a DIFFERENT mission_id justify this mission's VERIFIED
[BYPASS] C4  the SAME record supplied twice counts as two candidates
```

C3 is the sharpest: `VerificationRecord` carries `mission_id`, and `assert_transition` is
given `current`/`target` but never a mission identity, so it cannot and does not check that
the records belong to the mission being transitioned. C2 is the product risk: the
`HUMAN_REVIEW_REQUIRED`-outranks-everything rule — the honest one, the one that stops us
claiming a verdict when a gate errored — is exactly the rule a dropped record defeats.

I searched the contract for any freeze concept:

```
schema names containing candidate-set / frozen / manifest / freeze:  NONE
MissionDetail has a candidate list field?  NO — only verdict_summary
```

The CTO's condition that the candidate set be frozen before `VERIFY` begins is **not met**.
`MissionCounts.patch_candidates` is a display counter, not a binding.

### 4d. A mission can reach VERIFIED without ever entering PATCH or VERIFY. **BUG-005, major.**

`_RESUMABLE` includes `EXPORTING`, so `PAUSED → EXPORTING` is legal from any pause point.
Full walk, every step executed:

```
   CREATED      -> AUTHORIZED    ALLOWED
   AUTHORIZED   -> SNAPSHOTTED   ALLOWED
   SNAPSHOTTED  -> VALIDATING    ALLOWED
   VALIDATING   -> BASELINE      ALLOWED
   BASELINE     -> PAUSED        ALLOWED
   PAUSED       -> EXPORTING     ALLOWED
   EXPORTING    -> VERIFIED      ALLOWED
   VERDICT: mission reached VERIFIED without ever entering PATCH or VERIFY: True
```

Combined with BUG-004 (records need not belong to this mission), the "no verdict state
without verification" invariant reduces to *the caller must supply a plausible-looking
list*. Fix: resume must return to the state the mission paused from, or `_RESUMABLE` must
drop `EXPORTING`; and `EXPORTING` should only be reachable from `VERIFY`.

### 4e. Authorization edges — **PASS.**

```
[refused] E1  EXPORTING -> VERIFIED with an EXPIRED authorization: AuthorizationRequiredError
[refused] E2  EXPORTING -> VERIFIED with authorization=None:       AuthorizationRequiredError
[refused] E3  CREATED -> VERIFIED directly:  InvalidStateTransitionError: not a legal transition
[ALLOWED] E4  VERIFY -> HUMAN_REVIEW with no records  (documented as legitimate — correct)
```

---

## 5. #80 — the multi-candidate question, verified independently

The author says the schemas are already shaped for N candidates and need no rework. **That
is substantially true, and I verified it rather than taking it.** Two candidates driven
through one mission, end to end:

```
   PATCH -> VERIFY: ALLOWED
   VERIFY -> EXPORTING: ALLOWED
   EXPORTING -> VERIFIED with [VERIFIED, REJECTED]: ALLOWED
   MissionVerdictSummary constructed: mission=VERIFIED candidates=2 v=1 r=1
   EvidenceBundle carries 2 verification records and both verdicts: ['VERIFIED', 'REJECTED']
   [refused] a summary claiming verified_count=1 with only a REJECTED candidate: ValidationError
```

And the read surface supports it — these are real, per-candidate routes in the frozen dump:

```
GET  /api/v1/missions/{mission_id}/patches                              listPatchCandidates
GET  /api/v1/missions/{mission_id}/patches/{patch_id}/verification      getPatchVerification
GET  /api/v1/missions/{mission_id}/evidence                             getEvidenceBundle
```

**So: yes.** A mission can carry two candidates, two verification runs, two gate matrices
and two verdicts; the D6 side-by-side `Verified`/`Rejected` pair is the default shape of
the data; and `MissionVerdictSummary` refuses to misreport its own counts. The claim in the
PR body stands. #80's schema-shaped acceptance criteria are met by this package.

**But the CTO's freeze condition is not met** (BUG-004 above), and that is the half of #80
that the schemas alone cannot answer. Without a frozen candidate set, "both verdicts reach
the evidence bundle" is a property of a well-behaved orchestrator, not of the contract. The
D6 differentiator survives an honest pipeline and does not survive a buggy one. Fixing this
in `contracts/` on D1 costs maybe twenty lines; retrofitting it under #12 on D6 does not.

Also missing: there is no `GET /missions/{id}/verifications` collection route. Every
verification is reachable only through a known `patch_id`. A client that wants "all
verification runs for this mission" must list patches and fan out. Minor, but it is the
exact shape the Command Center's side-by-side panel wants. **BUG-017, minor.**

---

## 6. PostgreSQL — the gap the author left open, now measured

The author was right not to guess credentials. I ran a disposable container instead
(removed at the end of the session).

```
$ docker run -d --name brahmadatta-qa-pg -e POSTGRES_PASSWORD=... -p 55432:5432 postgres:16-alpine
$ docker exec brahmadatta-qa-pg pg_isready -U qauser -d brahmadatta_qa
/var/run/postgresql:5432 - accepting connections
PostgreSQL 16.13 on aarch64-unknown-linux-musl

$ DJANGO_SETTINGS_MODULE=config.settings.finale APP_ENV=finale \
  DATABASE_URL=postgresql://qauser:...@127.0.0.1:55432/brahmadatta_qa \
  .venv/bin/python manage.py check
System check identified no issues (0 silenced).

$ ... manage.py migrate
Operations to perform:
  Apply all migrations: auth, contenttypes, sessions
Running migrations:
  Applying contenttypes.0001_initial... OK
  ... (15 migrations) ...
  Applying sessions.0001_initial... OK
```

Serving under uvicorn against real PostgreSQL, finale profile, with
`CONTROL_API_ADMIN_ENABLED=true` deliberately set:

```
$ curl .../api/v1/system/health
{"status": "ok", "service": "brahmadatta-control-api", "version": "0.1.0",
 "app_env": "finale", "dependencies": [{"name": "database", "reachable": true, "detail": ""}], ...}

GET /django-admin/        -> 404      <- forced off; the env var cannot re-enable it
GET /api/v1/openapi.json  -> 200
GET /api/v1/docs          -> 200
GET /api/v1/missions      -> 401      (no token)
```

Runtime settings under the finale profile, read from `django.conf.settings`:

```
CONN_MAX_AGE = 0                     <- CTO C2 satisfied, verified at runtime not by reading
ENGINE       = django.db.backends.postgresql
OPTIONS      = {'connect_timeout': 5}
DEBUG        = False
ADMIN_ENABLED= False
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST    = False      <- BUG-001
SECURE_HSTS_SECONDS     = 0
SECURE_SSL_REDIRECT     = False
```

```
$ .venv/bin/python manage.py check --deploy
WARNINGS:
?: (security.W004) You have not set a value for the SECURE_HSTS_SECONDS setting. ...
?: (security.W008) Your SECURE_SSL_REDIRECT setting is not set to True. ...
System check identified 2 issues (0 silenced).
```

Both warnings are mitigated at nginx (TLS terminates there and nginx redirects), so I am
recording them as informational rather than as bugs. `check --deploy` had not been run
before; it should be part of the finale checklist.

### What PostgreSQL verification does **not** cover — stated plainly

**This PR contains no models.** So what I proved is: the DSN parser builds a working
PostgreSQL config, `psycopg` connects, Django's own migrations apply, and the health probe
reports `reachable: true`. What remains **unverified against PostgreSQL**:

- every application table, index, constraint and migration (they do not exist — D2, #7)
- the gap-free `sequence` writer (CTO C3) — nothing writes events yet
- transaction and isolation behaviour under concurrent stage writes
- JSON field behaviour for `MissionEvent.payload` (SQLite and PostgreSQL differ materially)
- connection-pool behaviour under held SSE streams with a real database in the loop
- anything the 169-test suite covers, since `config.settings.test` pins in-memory SQLite
  and cannot be pointed at PostgreSQL without editing it

Treating "the suite passes on SQLite" as "the suite passes" would be wrong. It passes on
SQLite, against code that touches no database.

---

## 7. HTTP surface, auth, and the streaming path

Executed against uvicorn on the development profile. Every line below is a real response
code from a real request.

```
GET  /api/v1/system/health (no auth)               -> 200
GET  /api/v1/openapi.json                          -> 200 (100301 bytes, compact)
GET  /api/v1/docs                                  -> 200
GET  /api/v1/missions (no token)                   -> 401
GET  /api/v1/missions (bad token)                  -> 401
GET  /api/v1/missions (operator)                   -> 501
GET  /api/v1/missions (reviewer)                   -> 501
POST /api/v1/missions/{id}/start (reviewer)        -> 403
POST /api/v1/missions/{id}/start (operator)        -> 501
POST /api/v1/missions  network="allow"             -> 422
POST /api/v1/missions  extra field "confidence"    -> 422   (extra="forbid" holds over HTTP)
GET  /api/v1/missions/notauuid                     -> 422
GET  /django-admin/ (development profile)          -> 302
```

Error envelopes are consistent and carry a trace id in body and header:

```json
{"error":{"code":"UNAUTHENTICATED","message":"A valid operator bearer token is required.",
 "details":{}},"trace_id":"15970c41c51340f9bb1bc7f68f0a481e"}

{"error":{"code":"FORBIDDEN","message":"Role reviewer may not perform that action.",
 "details":{"required_roles":["administrator","operator"]}},"trace_id":"a3a4c73a40ba..."}

{"error":{"code":"NOT_IMPLEMENTED","message":"Not implemented yet; tracked by #12 (orchestrator state machine).",
 "details":{"tracked_by":"#12 (orchestrator state machine)"}},"trace_id":"82465ad26f22..."}
```

### SSE is genuinely streamed — **PASS**, timestamped per line by the client

```
09:44:11.859  : brahmadatta stream open
09:44:12.110  : heartbeat
09:44:12.360  : heartbeat
09:44:12.367  event: contract.not_implemented
09:44:12.371  data: {"error":{"code":"NOT_IMPLEMENTED", ... "trace_id":"1f63141979de..."}}

content-type: text/event-stream
cache-control: no-cache, no-transform
x-accel-buffering: no
transfer-encoding: chunked
```

250 ms gaps observed by the client — the stream is not assembled and flushed at the end.

### Trace-ID header validation — **PASS**

```
X-Trace-Id: abcd1234abcd1234        -> echoed:  abcd1234abcd1234
X-Trace-Id: short                   -> replaced: 7af79b9e0e23427eb8cc357d6ff22201
X-Trace-Id: AAAA...(200 chars)      -> replaced
X-Trace-Id: evil id with spaces     -> replaced
X-Trace-Id: ../../etc/passwd        -> replaced
X-Trace-Id: a%0d%0aSet-Cookie:x=1   -> replaced;  set-cookie count in response: 0
```

### Concurrency under SSE load — **PARTIAL**, and I want the caveat on the record

CTO condition C1 is "sync streaming under ASGI will exhaust the thread pool — highest-
probability live failure". The view is `async def` with an async generator, which is the
right shape. My probe:

```
=== 16 simultaneous SSE streams while health is polled ===
  health probe 1: http=200 time=0.012846s
  health probe 2: http=200 time=0.014303s
  health probe 3: http=200 time=0.015535s
  health probe 4: http=200 time=0.011828s
  health probe 5: http=200 time=0.010442s
  health probe 6: http=200 time=0.021135s
  all 16 SSE streams completed
```

**This is a weak test and I am not presenting it as C1 cleared.** The SSE stub closes after
~0.5 s, so no connection is held long enough to pin anything. C1's real failure mode is a
long-lived stream holding a pool thread for minutes. **That cannot be tested against this
stub at all** and must be re-tested the moment #12 emits real events over a held connection,
with the CTO's own scenario: six browser tabs open plus a seventh issuing ordinary requests.
**Recorded as NOT RUN, not as passed.**

---

## 8. Provenance rules — "structurally impossible" is overstated

The question asked was whether a replayed model response can be recorded as live inference,
and whether an operator-supplied patch can be recorded as model-generated. Both must be
structurally impossible. Executed:

```
[BYPASS] D1  a replayed response recorded with NO replay fields -> reads as LIVE inference
[BYPASS] D2  operator-written diff recorded as MODEL_GENERATED with a fabricated provenance
[BYPASS] D3  a REPLAYED gate result that omits evidence_source -> defaults to TOOL_EXECUTION and PASSes
[refused] D4 GateResult PASS explicitly marked REPLAYED_ARTIFACT: ValidationError   [correct]
```

The validators that exist are good and they work (D4, and the all-or-nothing replay triple
is genuinely enforced). The problem is **which way the defaults point**. This PR gets it
exactly right in two places and exactly wrong in two others:

| Field | Default | Effect of a caller who says nothing |
|---|---|---|
| `FindingSummary.discovery_method` | **required, no default** | caller must state the claim — correct |
| `FuzzingReport.mode` | **required, no default** | caller must state the claim — correct |
| `ModelProvenance.replayed_from_transcript` | `None` | silently claims **live inference** |
| `GateResult.evidence_source` | `TOOL_EXECUTION` | silently claims **a tool ran** |

A replay-mode gateway (the D5 fallback this design exists for) that forgets to set three
fields produces a record indistinguishable from a live generation. A gate populated from a
stored artifact by code that forgets one field **passes the gate**. The mitigation pattern
is already in this file twice; it just is not applied here. **BUG-007, major.**

D2: `PatchCandidate` requires `MODEL_GENERATED` to carry a `ModelProvenance`, but
`ModelProvenance` requires only `model_name` and `served_from`, both free strings, and
`prompt_sha256` is optional. So attaching two invented strings to a hand-written diff
presents it as model output. Making `prompt_sha256` required for `MODEL_GENERATED` would
mean the claim has to be backed by a digest of a prompt that was actually assembled.
**BUG-008, major** — for a competition submission, "the model wrote this" is the single
claim a judge is most entitled to test.

### Display coupling is documented but not enforced — BUG-009, minor

```
[BYPASS] MissionDetail(verdict=VERIFIED, verdict_summary=None): ALLOWED
         — the field docstring says "Never displayed without verdict_summary beside it"
[BYPASS] MissionDetail(state=VERIFIED, posture=FAILED): ALLOWED
         — posture is not derived by the schema, despite the enum docstring saying it is
```

Both are one `model_validator` each. The second matters more than it looks: `posture` is
what the Brahmadatta Core renders, and the enum's own docstring says it is "derived from
`MissionState`, never set directly". Nothing enforces that, so a serialization bug shows a
judge a red alert ring on a verified mission.

### Observation, not a bug: `HUMAN_REVIEW` is a one-way door

```
allowed_transitions(HUMAN_REVIEW) = []
allowed_transitions(PAUSED)       = ['BASELINE','CANCELLING','CORRELATE','EXPORTING','FAILED','PATCH','STRESS_TEST','TRIAGE','VERIFY']
allowed_transitions(CANCELLING)   = ['CANCELLED','FAILED']
```

A mission sent to `HUMAN_REVIEW` from `CORRELATE`, `PATCH` or `VERIFY` — the documented
"a person should look before we claim anything" path — can never be resumed, resolved or
even cancelled. The human reviews it and then has nowhere to put the answer. Also
`POSTURE_BY_STATE[PAUSED] = HUMAN_REVIEW`, so an operator pause and a genuine escalation
render identically on the Core. **BUG-014, minor** — but it is a **product** question, and
the answer belongs to `product-manager`, not to me.

---

## 9. CI — the two blockers, with output

### BUG-001 — required job `pytest` goes red on merge

On clean `origin/main`, the check skips:

```
$ .rootvenv/bin/python -m pytest tests/architecture/test_ingress_contract.py -q -rs
sss                                                                      [100%]
SKIPPED [1] tests/architecture/test_ingress_contract.py:54: apps/control-api/config/settings does not exist yet
SKIPPED [1] tests/architecture/test_ingress_contract.py:66: apps/control-api/config/settings does not exist yet
SKIPPED [1] tests/architecture/test_ingress_contract.py:88: apps/control-api/config/settings does not exist yet
3 skipped in 0.01s
```

With #87 merged, it runs — and fails:

```
$ .rootvenv/bin/python -m pytest tests/ -q
................................sF..                                     [100%]
_____________________ test_use_x_forwarded_host_is_enabled _____________________
E       AssertionError: USE_X_FORWARDED_HOST is not set anywhere in config/settings/.
        Django will build absolute URLs from its own Host header rather than the
        browser's, so every redirect behind nginx points at the wrong host and port.
E
E         Add to apps/control-api/config/settings/base.py:
E             USE_X_FORWARDED_HOST = True
E             SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
tests/architecture/test_ingress_contract.py:56: AssertionError
FAILED tests/architecture/test_ingress_contract.py::test_use_x_forwarded_host_is_enabled
1 failed, 34 passed, 1 skipped in 0.32s
```

The PR body flags this as item 3 under "known gaps" and declines to fix it because
`infrastructure/` is not the author's to touch. **The fix is not in `infrastructure/` — it
is one line in `config/settings/base.py`, and the failing test says so verbatim.** The other
half of the pair, `SECURE_PROXY_SSL_HEADER`, is already set in `finale.py`. This is a
two-line change that turns a red required check green.

### BUG-002 — required job `openapi dump is current` cannot pass, and mutates the artifact it polices

```
$ infrastructure/scripts/openapi-contract-check.sh
  exporter: apps/control-api/tools/export_openapi.py
  dump:     packages/schemas/openapi.json
unchanged: /Users/.../packages/schemas/openapi.json (172311 bytes)
openapi contract: FAILED — the exporter produced nothing.
REAL EXIT=1
```

The script documents its contract at the top of the file: *"an exporter that writes the dump
to stdout or to a path given as argv[1]"*. `tools/export_openapi.py::main()` takes no
arguments and always writes to the hard-coded `packages/schemas/openapi.json`, printing a
status line to stdout. So the script's first branch "succeeds" (exit 0) while writing
nowhere near `$REGENERATED`, the temp file stays empty, and the check dies on `[ ! -s ]`.

It never compares anything. And with a real drift present it is actively harmful:

```
# after injecting a schema change and NOT regenerating the dump:
$ infrastructure/scripts/openapi-contract-check.sh
updated: /Users/.../packages/schemas/openapi.json (172356 bytes)
openapi contract: FAILED — the exporter produced nothing.
EXIT=1
$ git status --short packages/schemas/openapi.json
 M packages/schemas/openapi.json
```

**The gate silently rewrote the committed dump** — the exact drift it exists to prevent —
and then failed for the wrong reason. If anyone ever makes this job green by "fixing" the
empty-file check without fixing the exporter, the dump self-heals in CI forever and #6's
acceptance criterion is permanently, invisibly false.

Fix (backend developer, `apps/control-api/tools/export_openapi.py`): honour `sys.argv[1]`
as the output path when given. Four lines. The script's dual-shape support then works as
designed.

### BUG-016 — C5's import-direction check silently skips in CI. **minor.**

```
SKIPPED [1] tests/architecture/test_import_direction.py:125:
  could not import config.asgi in this environment (dependencies missing?)
```

`ci.yml` runs `pytest tests/ -q` **before** installing `apps/control-api/requirements.txt`,
so this architecture invariant — the ASGI process must not import the gateway — will skip on
every run rather than fail. Reorder the steps. Owner: `devops` (ci.yml came from #91, not
this PR), but the skip only became reachable because this PR added `config/asgi.py`.

### BUG-015 — "ruff / mypy … both were green at D1" is not accurate. **trivial.**

```
$ ruff check apps/control-api --output-format=concise
... 29 findings ...
apps/control-api/contracts/verdict.py:26:1: UP035 Import from `collections.abc` instead
apps/control-api/contracts/state_machine.py:16:1: I001 Import block is un-sorted
apps/control-api/tools/export_openapi.py:66:5: T201 `print` found
apps/control-api/contracts/schemas/evidence.py:140:58: UP037 Remove quotes from type annotation  (x8)
Found 29 errors.  [*] 23 fixable with the `--fix` option

$ mypy --config-file mypy.ini api config contracts
contracts/tests/test_verdict.py:91: error: Unused "type: ignore" comment  [unused-ignore]
contracts/tests/test_verdict.py:101: error: Unused "type: ignore" comment  [unused-ignore]
Found 2 errors in 1 file (checked 44 source files)

$ mypy --config-file mypy.ini .          # including tools/
tools/export_openapi.py: error: Source file found twice under different module names
Found 1 error in 1 file (errors prevented further checking)
```

Every finding is cosmetic and 23 are auto-fixable. The bug is not the lint debt, it is that
`ci.yml`'s comment asserts a state that does not hold — and since lint is *not* in CI, that
comment is the only record anyone will check.

---

## 10. Database configuration

### BUG-010 — `sqlite:///name.db` resolves to an absolute path at `/`. **major.**

```
$ python -c "from config.env import database_from_url as f; ..."
sqlite:///qa.sqlite3        -> {'ENGINE': '...sqlite3', 'NAME': '/qa.sqlite3'}
sqlite:///ci.sqlite3        -> {'ENGINE': '...sqlite3', 'NAME': '/ci.sqlite3'}
sqlite:///:memory:          -> {'ENGINE': '...sqlite3', 'NAME': '/:memory:'}
sqlite:////tmp/abs.sqlite3  -> {'ENGINE': '...sqlite3', 'NAME': '//tmp/abs.sqlite3'}
sqlite://                   -> {'ENGINE': '...sqlite3', 'NAME': ':memory:'}
```

Consequence, observed:

```
$ DATABASE_URL=sqlite:///qa.sqlite3 .venv/bin/python manage.py migrate
django.db.utils.OperationalError: unable to open database file

$ curl .../api/v1/system/health
{"status":"degraded", ..., "dependencies":[{"name":"database","reachable":false,"detail":"OperationalError"}]}
```

`sqlite:///relative.db` is the standard SQLAlchemy / `dj-database-url` spelling for a
**relative** path, and it is the exact form the repository's own `ci.yml` uses
(`DATABASE_URL: "sqlite:///ci.sqlite3"`) — twice. It is harmless today only because nothing
in the suite touches the database. The day D2's models land, CI breaks with a message that
points at SQLite rather than at the DSN parser. Only `sqlite://` (no path, in-memory) and
`sqlite:////absolute` currently work. `README.md` and `.env.example` both advertise
`sqlite://` as supported without saying which spelling.

### BUG-011 — PostgreSQL DSN query parameters are silently dropped

```
postgresql://u:p@db:5432/brahmadatta?sslmode=require
  -> {'ENGINE':'...postgresql','NAME':'brahmadatta','USER':'u','PASSWORD':'p',
      'HOST':'db','PORT':'5432','CONN_MAX_AGE':60,'OPTIONS':{'connect_timeout':5}}
```

`sslmode=require` is discarded without a warning: the operator writes a DSN that asks for
TLS and gets a plaintext connection. **I am not assigning a severity — this is
`cybersecurity`'s to rate.** Today the database is on an `internal: true` compose network,
which is why I am reporting rather than escalating. Either honour the query string or
refuse a DSN carrying one.

### BUG-012 — health returns HTTP 200 while degraded. **minor.**

```
$ curl -o /dev/null -w "%{http_code}" .../api/v1/system/health    # database unreachable
200
{"status":"degraded", ..., "reachable": false, ...}
```

A container healthcheck or load balancer reads the status code, not the body. A control API
that cannot reach its database reports itself healthy to every automated consumer. Return
503 when `status != "ok"`, or document that this endpoint is for humans only and add a
separate readiness probe. Owner: backend developer, with `devops` on the compose healthcheck.

---

## 11. Bug register

Severity: **blocker** = cannot merge; **major** = must fix before the D6 demo depends on it;
**minor** = fix when convenient; **trivial** = cosmetic.

| ID | Sev | Summary | Owner |
|---|---|---|---|
| **BUG-001** | **blocker** | `USE_X_FORWARDED_HOST` unset → required CI job `pytest` fails on merge (§9) | backend-developer |
| **BUG-002** | **blocker** | Exporter ignores `argv[1]` → CI job `openapi dump is current` cannot pass and rewrites the dump it polices (§9) | backend-developer |
| BUG-003 | major | `assert_verdict_is_evidenced` duck-types on `.verdict`; an in-contract `CandidateVerdict` with no gate matrix satisfies the #77 guard (§4b) | backend-developer |
| BUG-004 | major | The verification-record set is not bound to the mission: cross-mission records accepted, duplicates counted twice, dropping a `REJECTED`/`HUMAN_REVIEW` record reaches `VERIFIED`. Candidate set is not frozen (CTO C1, #80) (§4c) | backend-developer |
| BUG-005 | major | `PAUSED → EXPORTING` lets a mission reach `VERIFIED` having never entered `PATCH` or `VERIFY` (§4d) | backend-developer |
| BUG-006 | *deferred to `cybersecurity`* | `model_policy` accepts metadata endpoints, IDNA homographs, and **a decimal-encoded public IPv4** (`http://134744072/` → 8.8.8.8) — the last is new beyond SEC-02 (§3) | cybersecurity → backend-developer |
| BUG-007 | major | Provenance defaults point at the strong claim: `ModelProvenance` replay fields default to "live", `GateResult.evidence_source` defaults to `TOOL_EXECUTION` (§8) | backend-developer |
| BUG-008 | major | An operator-supplied patch is recordable as `MODEL_GENERATED` with two invented strings; `prompt_sha256` is optional (§8) | backend-developer |
| BUG-009 | minor | `MissionDetail(verdict=…, verdict_summary=None)` and `(state=VERIFIED, posture=FAILED)` both constructible, contradicting their own docstrings (§8) | backend-developer |
| BUG-010 | major | `sqlite:///name.db` → `/name.db`; `migrate` fails; the repo's own `ci.yml` uses this form twice (§10) | backend-developer |
| BUG-011 | *deferred to `cybersecurity`* | PostgreSQL DSN query params silently dropped — `?sslmode=require` ignored (§10) | cybersecurity → backend-developer |
| BUG-012 | minor | `/api/v1/system/health` returns 200 while `degraded` (§10) | backend-developer + devops |
| BUG-013 | *deferred to `cybersecurity`* | `/api/v1/docs` and `/api/v1/openapi.json` are unauthenticated in the **finale** profile (§6) | cybersecurity |
| BUG-014 | minor | `HUMAN_REVIEW` is terminal with no outgoing transitions — a reviewed mission cannot be resumed, resolved or cancelled. `PAUSED` also displays as `HUMAN_REVIEW` (§8) | product-manager (decision), then backend-developer |
| BUG-015 | trivial | `ci.yml` asserts ruff and mypy "were green at D1"; ruff reports 29, mypy 2 (§9) | backend-developer |
| BUG-016 | minor | `ci.yml` runs `pytest tests/` before installing control-api deps, so C5's import-direction check skips silently on every run (§9) | devops |
| BUG-017 | minor | No `GET /missions/{id}/verifications` collection route; the D6 side-by-side panel must fan out over patches (§5) | backend-developer + product-manager |

### Reproduction

Every result above came from three scripts executed in this session. They are throwaway QA
harnesses, not committed to the repository:

- model-policy attack table — 30 hostile URLs (§3)
- state-machine / verdict attack suite — cases A1–A5, B1–B3, C1–C4, D1–D4, E1–E5 (§4, §8)
- sequencing and multi-candidate walk — cases F, G, H, I, J (§4d, §5, §8)

The exact case list is reproduced inline in each section, and each case is a handful of
lines against `contracts.*` with no I/O. `engineering-manager`: the right home for these is
`apps/control-api/contracts/tests/` as regression tests, owned by whoever fixes BUG-003
through BUG-008 — a bypass that is not in the suite is a bypass that comes back.

---

## 12. Explicitly NOT RUN

Listed because omitting them would be the dishonest part.

| Area | Status | Why |
|---|---|---|
| SSE through nginx (`proxy_buffering off`) | **NOT RUN** | The finale compose stack was not brought up. `infrastructure/scripts/smoke-sse.sh` exists on `main` and is the right tool. This is the failure that is invisible until the demo — it must run before D6. |
| Egress attempt from inside the control-api container | **NOT RUN** | `cybersecurity` executed and signed this off on #91. I did not re-run it. |
| CTO C1 — thread-pool exhaustion under long-lived SSE | **NOT RUN** (16-stream probe is a weak proxy only, §7) | The SSE stub closes after ~0.5 s; the failure mode needs held connections. Re-test when #12 emits real events. |
| CTO C3 — gap-free `sequence` under concurrent writers | **NOT RUN** | Nothing writes events yet. |
| Any PostgreSQL-specific behaviour beyond connect + `migrate` | **NOT RUN** | No models exist. §6 lists what this leaves open. |
| The 169-test suite against PostgreSQL | **NOT RUN** | `config.settings.test` pins in-memory SQLite. No test touches the database, so this is currently a no-op — it stops being one on D2. |
| `openapi-typescript` generation into the Command Center | **NOT RUN** | `apps/command-center/` does not exist yet (#9's Astro half). |
| Semgrep / bandit beyond ruff's `S` rules | **NOT RUN** | `cybersecurity`'s scope. |
| Accessibility and UI testing | **N/A** | No UI in this PR. |
| Load, soak, or resource-ceiling testing | **NOT RUN** | Every endpoint but health is a 501. |
| Unhandled-500 envelope and traceback leakage with `DEBUG=False` | **NOT RUN** | I could not trigger an unhandled exception; every path I reached raised a typed `ContractError`. Worth a deliberate fault-injection test later. |

---

## 13. Decision record — recommending rejection on D1

**Decision.** Reject PR #87 rather than merge with the two CI blockers filed as follow-ups.

**Options considered.**
(a) **REJECTED** — send it back for BUG-001 and BUG-002 plus a ruling on BUG-003/004/005.
(b) **APPROVED WITH KNOWN ISSUES** — merge now, file everything, fix in flight.
(c) **APPROVED** — not defensible; two required CI jobs fail on merge.

**Pros and cons.**
(a) costs a few hours on the day of the compressed build with the most slack. Both blockers
are small and precisely located: two lines in `base.py`, four in `export_openapi.py`. The
real value is that BUG-003/004/005 get decided while `contracts/` is still the only consumer
of the state machine. Con: it delays the Command Center's start against the frozen types —
though the dump is already correct and committed, so a frontend developer can begin against
it today regardless of merge state.
(b) unblocks everything immediately, but merges a red `main`. On a 14-day build a red `main`
is not a nuisance, it is the loss of the only automated signal anyone has; and the second
blocker specifically disables the drift gate that #6 exists to provide, so the freeze becomes
honour-based on the day it is declared frozen. Con is decisive.
(c) invalid on its face.

**Cost implications.** Rejection costs roughly half a day of one developer. Option (b) costs
whatever a silently-drifting OpenAPI dump costs when discovered — historically, at
integration, which here is D4–D6.

**Security implications.** Neutral to positive. BUG-006 and BUG-011 are `cybersecurity`'s to
rate and neither is regressed by this PR. BUG-013 (unauthenticated `/docs` in the finale
profile) is new information for them.

**Scalability implications.** None from this decision. BUG-005 and BUG-004 are correctness,
not scale. C1's thread-pool question remains genuinely open and untested (§12).

**Recommendation.** (a) REJECTED. Fix BUG-001 and BUG-002; get a CTO ruling on BUG-003,
BUG-004 and BUG-005 before #12 starts, because #12 is the code that will encode whichever
answer is given.

**Final approval authority.** CTO for the technical rejection; CEO + `product-manager`
jointly if they choose to ship over it, in writing, in `.project/decisions.md`. My rejection
is not a veto on the schedule — it is a statement of what was executed and what it showed.

---

## 14. Exit criteria for re-review

I will re-run everything in §2, §3, §4 and §9 on the updated branch. To flip to APPROVED:

1. `pytest tests/ -q` green on the merge result (BUG-001).
2. `infrastructure/scripts/openapi-contract-check.sh` exits 0, **and** leaves
   `git status --porcelain packages/schemas/openapi.json` empty (BUG-002). I will verify by
   injecting drift and confirming it fails for the right reason.
3. A ruling — fix or explicit written deferral with an owner and a date — on BUG-003,
   BUG-004 and BUG-005. A deferral is acceptable; silence is not.
4. BUG-007 and BUG-008 fixed, or the PR body's "structurally impossible" wording corrected
   to "validated where declared". Either is fine. Both claims cannot stand as written.
5. 169+ tests still green, with new regression tests covering whichever of B2, C1–C4 and F
   get fixed.
