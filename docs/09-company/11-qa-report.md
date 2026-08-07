# QA report — PR #87, `feat/control-api-scaffold`

**Author of this report:** `qa` agent
**Date:** 2026-08-07 (D1)
**Under test:** PR #87 — Django + django-ninja control API and the frozen mission contract
**Round 1 tested at:** `origin/feat/control-api-scaffold` (`a853e80`) merged with `origin/main`
(`ff0a11e`), merge commit `1eeb176`.
**Round 2 (re-review) tested at:** `origin/feat/control-api-scaffold` (`743ffa9`), already
containing `origin/main` (`81e7657`) — no merge needed.
Both in throwaway detached worktrees. Nothing was pushed to either branch.
**Issues in scope:** #6, #9 (Django half), #77, #78, #80, #103, and the CTO's nine conditions
C1–C9 (review comment on **#79** — see §0).

---

## 0. Round 2 — re-review after the mechanical fixes

Round 1 rejected this PR on two blockers. Both are fixed, plus BUG-016. I re-ran §2, §3, §4
and §9 against `743ffa9`. **Everything below in this section is executed output from the
re-run, not a report of what I was told.**

| Bug | Round 1 | Round 2 | Evidence |
|---|---|---|---|
| **BUG-001** `USE_X_FORWARDED_HOST` | **blocker** — CI job `pytest` red | **CLOSED** | §9.1 |
| **BUG-002** exporter ignores `argv[1]` | **blocker** — drift gate dead | **CLOSED** | §9.2 |
| **BUG-016** C5 check skipping in CI | minor | **CLOSED** | §9.1 |
| BUG-003 – BUG-005, BUG-007 – BUG-010, BUG-012, BUG-014, BUG-017 | open | **still open, re-verified byte for byte** | §3, §4 |
| BUG-006, BUG-011, BUG-013 | `cybersecurity`'s to rate | unchanged | §3, §10 |

**The verdict moves from REJECTED to APPROVED WITH KNOWN ISSUES.** The revised verdict, and
what it is conditional on, is in §0.4.

### 0.1 Correction to my Round 1 assumption about C1–C9

I recorded in Round 1 that I could not find a nine-condition set and had tested the
*substance* of the two conditions described to me rather than their labels. That assumption
is now resolved: **the nine conditions are a CTO review comment on PR #79**, not the merged
`05-cto-technical-review.md` I read (which carries C1–C8 of an earlier, different ruling).
Retrieved and read in this session. My substance-first approach was correct, and the mapping is:

- **BUG-004 is the CTO's C1** — *"no `PatchCandidate` may be attached to a mission after the
  first `VerificationRecord` for that mission is written. Enforce it where the transition
  guard lives, not by convention. Test: `test_cannot_add_candidate_after_verification_starts`."*
  That test does not exist and the rule is not enforced. **C1 unmet.**
- **BUG-003 is the CTO's C6** — *"Take `Sequence[VerificationRecord]` and read `record.verdict`
  … Passing raw enum values snaps [the chain] at the one link that matters."* The signature
  says `Sequence[VerificationRecord]`; Python does not check it, and §4b shows an in-contract
  `CandidateVerdict` satisfying the guard. **C6 met in letter, not in substance.**
- One deviation from C6 worth naming, and it is in the *safe* direction: C6 says *"Keep
  empty-list → `HUMAN_REVIEW`"*. The implementation raises `VerificationRequiredError`
  instead (§4a, case A1). Refusing is stricter than degrading. Recorded, not filed.
- **C2** (*mission verdict carries its candidate denominator*) is **met at contract level** —
  `MissionVerdictSummary` carries `candidates` plus `verified_count` / `rejected_count` /
  `human_review_count`, which is everything the "1 of 2 candidates verified" string needs.
  Rendering is #42/#51, not this PR.
- **C3** (*where two candidates both verify, the bundle must name the recommended one*) is
  **unmet** and is a **new finding this round** — see BUG-018, §0.3.
- **C5** (*`gateway/` not importable from the ASGI process*) now genuinely asserts, having
  silently skipped before (§9.1).

### 0.2 I verified the fixer's own account of their rejected first attempt

The orchestrator reported that their first BUG-016 fix also set `DJANGO_SETTINGS_MODULE` on
the root architecture step, which broke the step outright, and that they caught it by
replaying the CI job rather than reading the YAML. I reproduced that failure mode rather than
take it on trust:

```
$ DJANGO_SETTINGS_MODULE=config.settings.test pytest tests/ -q -rs
  File ".../pytest_django/plugin.py", line 193, in _handle_import_error
    raise ImportError(msg) from None
ImportError: No module named 'config'

pytest-django could not find a Django project (no manage.py file could be found). You must
explicitly add your Django project to the Python path to have it picked up.
```

Dies before a single test runs. The shipped fix — install first, no env block — is correct.
The self-report is accurate.

### 0.3 New this round — BUG-018, CTO C3 unmet. **minor.**

Now that I have the real condition text, one is not satisfied by the contract:

```
EvidenceBundle fields: ['mission_id','generated_at','snapshot_sha256','authorization_statement',
 'baseline','findings','reproducers','fuzzing','patches','verifications','verdict_summary',
 'resource_usage','gates_not_run','substitutions','isolation_mode','tool_versions']
any recommended / primary / chosen field: NONE
```

C3: *"where two candidates both verify, the bundle must name the recommended one. Minor.
`EvidenceBundle.verifications` is a list and nothing says which diff we are claiming. One
field."* Still one field. Cheap now, and it is the field a judge asks about the moment two
candidates both pass.

### 0.4 Revised verdict

# APPROVED WITH KNOWN ISSUES

The two blockers are closed and I verified each by executing the failing case, not by reading
the diff. What remains are **contract-shape questions with a live CTO ruling behind them** —
C1 and C6 are the CTO's own open conditions, and the orchestrator deliberately did not patch
them, which is the right call. A QA gate is not the place to decide a contract shape over the
CTO's head.

**This approval is conditional on all four of these, and I will re-check each:**

1. **C1 (BUG-004) and C6 (BUG-003) are ruled on by the CTO before #12 merges** — not before
   #12 *starts*, before it *merges*, since #12 is the code that encodes the answer. Fix or a
   written deferral with an owner and a date; silence is not a ruling.
2. **BUG-005 (`PAUSED → EXPORTING` reaches `VERIFIED` skipping `PATCH` and `VERIFY`) is fixed
   or ruled on in the same pass.** It is the same class as C1 and arrived from a different
   direction.
3. **BUG-007 and BUG-008 are fixed, or the PR body's "structurally impossible" wording is
   corrected** to "validated where declared". Either is acceptable. Both claims cannot stand
   as written, because that wording is the kind that reaches a slide.
4. **#103 is fixed before any second Python version touches this repository** (§0.5).

**What "approved with known issues" does not mean.** It does not mean the eight open findings
are acceptable at D6. It means they are not merge-blockers for a D1 scaffold whose HTTP
surface is 22 of 23 endpoints returning 501, and that holding the branch hostage while the CTO
rules would cost more than merging it does. Every one of them is in §11 with a severity and an
owner.

### 0.5 #103 — confirmed, and it is the right call to file it

```
Python 3.12.13    422 -> 'Unprocessable Entity'
Python 3.13.12    422 -> 'Unprocessable Content'

$ grep -o "Unprocessable [A-Za-z]*" packages/schemas/openapi.json | sort | uniq -c
  23 Unprocessable Entity
```

Twenty-three occurrences, inherited from `http.HTTPStatus`. The suite on 3.13, with
`pytest-asyncio` present:

```
$ .venv313/bin/python -m pytest --tb=no
1 failed, 168 passed in 0.97s
FAILED contracts/tests/test_openapi_dump.py::test_committed_dump_is_current
E  - ocessable Content"
E  + ocessable Entity"
```

Exactly one failure and exactly the predicted cause. The orchestrator's framing is right and
worth repeating: **the interpreter version is an undeclared input to a supposedly
deterministic exporter**, and a drift detector that fires on non-drift is one people learn to
mute. The fix belongs in the exporter (normalise the reason phrase) rather than in a pin,
because a pin only holds until someone runs it locally on a newer Python — which is precisely
how this was found.

---

## Verdict — Round 1 (superseded by §0.4)

# REJECTED

**Two blockers.** Both are CI-red-on-merge, and both are cheap to fix today.
**Both were fixed in `1db13a2` / `743ffa9` and re-verified closed in §0 and §9.**

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

**Round 2, `743ffa9`, fresh venv, Python 3.12.13 — still 169, still all passing:**

```
$ .venv/bin/python -m pytest
........................................................................ [ 42%]
........................................................................ [ 85%]
.........................                                                [100%]
169 passed in 1.23s
```

On **Python 3.13.12**, which CI does not use: `1 failed, 168 passed`, the single failure being
`test_committed_dump_is_current` on the HTTP-422 reason phrase. That is issue **#103** and it
is environmental, not a defect in this PR — full evidence in §0.5.

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

**Round 2, `743ffa9`.** The exporter now takes an optional output path, so I re-checked that
the *no-argument* default still writes where it always did and still produces the same bytes:

```
$ md5 ../../packages/schemas/openapi.json
MD5 (...) = 8862ca7e4ade67e7365744af71ddbd36
$ .venv/bin/python tools/export_openapi.py
unchanged: .../packages/schemas/openapi.json (172311 bytes)
$ md5 ../../packages/schemas/openapi.json
MD5 (...) = 8862ca7e4ade67e7365744af71ddbd36
$ git status --porcelain packages/
(empty)
```

Identical digest to Round 1. The `argv[1]` change did not alter the default output.

### TC-4 — Is drift actually caught? **Round 1: PASS in-suite / FAIL at the CI gate. Round 2: PASS at both.**

I injected a real schema change (`ArtifactRef.kind` gained a description) and re-ran:

```
$ .venv/bin/python -m pytest contracts/tests/test_openapi_dump.py::test_committed_dump_is_current
E   AssertionError: packages/schemas/openapi.json is stale. Re-run
    `.venv/bin/python tools/export_openapi.py` and commit the result.
FAILED contracts/tests/test_openapi_dump.py::test_committed_dump_is_current
1 failed in 0.27s
```

The in-suite guard was always real. The CI-level guard was not, in Round 1 — see BUG-002 and
its Round-2 resolution in §9.2, where I re-injected the same drift and confirmed the gate now
fails for the *right* reason and leaves the committed dump untouched.

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

### Round 2 re-run of this entire section — **unchanged, byte for byte**

`contracts/model_policy.py` was not touched by the fix commit, and I re-ran the table rather
than infer that from the diff:

```
$ .venv/bin/python attack_model_policy.py        # against 743ffa9
MISMATCHES: 19 of 30

$ SMALL_MODEL_BASE_URL=... .venv/bin/python manage.py check
https://api.openai.com/v1                  -> SystemCheckError (brahmadatta.E001)   [correct]
http://169.254.169.254/                    -> System check identified no issues (0 silenced).
http://api。openai。com/v1                 -> System check identified no issues (0 silenced).
http://134744072/v1                        -> System check identified no issues (0 silenced).
```

Nothing regressed and nothing improved. SEC-02 and the new decimal-encoding case both stand.

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

### 4f. Round 2 re-run of §4a–§4e — **every case reproduces identically**

The fix commit touched `config/settings/base.py` and `tools/export_openapi.py` only. I still
re-executed the full attack suite against `743ffa9` rather than reason from the diff, because
"nothing in `contracts/` changed" is a claim and re-running is a measurement:

```
A1 refused · A2 refused · A3 refused · A4 refused · A5 allowed (expected)
B1 BYPASS  · B2 BYPASS  · B3 AttributeError
C1 BYPASS  · C2 BYPASS  · C3 BYPASS  · C4 BYPASS
D1 BYPASS  · D2 BYPASS  · D3 BYPASS  · D4 refused (expected)
E1 refused · E2 refused · E3 refused · E4 allowed · E5 allowed

F   mission reached VERIFIED without ever entering PATCH or VERIFY: True
G   allowed_transitions(HUMAN_REVIEW) = []
H   POSTURE_BY_STATE[CANCELLED] = CANCELLED   ·   PAUSED = HUMAN_REVIEW
I   two candidates -> two records -> [VERIFIED, REJECTED] in one EvidenceBundle: works
J   schema names containing candidate-set / frozen / manifest / freeze: NONE
```

Identical to Round 1 in every case. **#77 stays fixed; C1 and C6 stay open.** The orchestrator
stated they deliberately did not patch BUG-003/004/005 pending a CTO ruling, and that is what
the code shows.

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

> **Round 2 status: all three CI findings in this section are CLOSED.** §9.1 and §9.2 below
> carry the Round-1 evidence first, then the Round-2 re-verification. I closed each by
> executing the case that failed, not by reading the fix.

### 9.1 — BUG-001 and BUG-016, CLOSED. Round-2 evidence first.

I replayed CI job 1 in the exact step order `ci.yml` now specifies:

```
--- step: Install test tooling (root requirements-dev.txt)
--- step: Install control API dependencies          <- NEW, and it is the whole fix
--- step: Architecture tests:  pytest tests/ -q -rs
....................................                                     [100%]
36 passed in 0.67s
```

**36 passed, zero skipped.** Round 1 was `1 failed, 34 passed, 1 skipped`. Both the failure
and the skip are gone, and the skip's disappearance is the more valuable half — a check that
skips is a check that reports green while asserting nothing.

The two specific checks that were broken, named individually so this is not a count:

```
tests/architecture/test_ingress_contract.py::test_use_x_forwarded_host_is_enabled          PASSED
tests/architecture/test_ingress_contract.py::test_finale_closes_database_connections...    PASSED
tests/architecture/test_ingress_contract.py::test_secure_proxy_ssl_header_is_set           PASSED
tests/architecture/test_import_direction.py::test_asgi_packages_do_not_import_the_gateway  PASSED
tests/architecture/test_import_direction.py::test_importing_the_asgi_app_does_not_load...  PASSED
5 passed in 0.17s
```

`test_import_direction` is the CTO's **C5**. It was skipping silently in Round 1; it now
asserts.

The setting landed in `base.py`, not `finale.py`, so **both profiles carry it** — I checked
both rather than trusting the file location:

```
development  USE_X_FORWARDED_HOST=True  SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https')
finale       USE_X_FORWARDED_HOST=True  SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https')
```

That is better than what I asked for. My Round-1 recommendation said "one line in `base.py`";
putting `SECURE_PROXY_SSL_HEADER` there too means the development profile, which runs behind
the same nginx, stops having the same defect.

**Regression check — did the ingress fix break the running surface?** Smoke-tested under
uvicorn after the change:

```
GET  /api/v1/system/health          -> 200
GET  /api/v1/missions (no token)    -> 401
GET  /api/v1/missions (operator)    -> 501
GET  /api/v1/openapi.json           -> 200
POST /api/v1/missions network=allow -> 422
health via forwarded headers        -> 200
SSE:  10:06:38.707 : brahmadatta stream open
      10:06:38.952 : heartbeat
      10:06:39.205 : heartbeat
      10:06:39.212 event: contract.not_implemented
```

Nothing regressed; SSE still genuinely streams at 250 ms intervals.

**One operational note, verified and deliberately *not* filed as a bug.** With
`USE_X_FORWARDED_HOST = True`, an `X-Forwarded-Host` outside `ALLOWED_HOSTS` now yields
`400 Bad Request`. That is correct Django behaviour and it is the point of the setting. I
checked whether the infrastructure already accounts for it, and it does — nginx forwards
`$http_host` as both `Host` and `X-Forwarded-Host`
(`infrastructure/compose/nginx/includes/proxy-headers.conf:25,29`), and the finale compose
already hard-fails without the hostname:

```
docker-compose.finale.yml:109  DJANGO_ALLOWED_HOSTS: ${DJANGO_ALLOWED_HOSTS:?set to the finale hostname}
```

So the coupling exists, it predates this change, and infra handled it. Recording it because
whoever runs the finale needs to know a wrong `DJANGO_ALLOWED_HOSTS` is now a 400 on every
request rather than a subtly wrong redirect.

### BUG-001 — Round-1 evidence: required job `pytest` goes red on merge

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

### 9.2 — BUG-002, CLOSED. Round-2 evidence.

The fix landed as recommended. Clean run, exit 0, and the committed dump untouched:

```
$ infrastructure/scripts/openapi-contract-check.sh
  exporter: apps/control-api/tools/export_openapi.py
  dump:     packages/schemas/openapi.json
updated: /private/var/folders/.../tmp.SmHiu7Hocu/openapi.json (172311 bytes)
openapi contract: PASS — the committed dump matches the live schema
REAL EXIT=0

$ git status --porcelain packages/schemas/openapi.json
(empty)
```

Note the path in `updated:` — it is now the script's scratch directory, not the repository.

**A gate that passes proves nothing; a gate that fails correctly is the whole product.** So I
re-injected the same drift as TC-4 (`ArtifactRef.kind` gains a description, dump not
regenerated) and ran it again:

```
REAL EXIT=1
updated: /private/var/folders/.../tmp.HpXzfXgcLU/openapi.json (172358 bytes)
--- /dev/fd/63
+++ /dev/fd/62
@@ -49,6 +49,7 @@
         "properties": {
           "kind": {
+            "description": "QA DRIFT PROBE 2",
             "maxLength": 64,

openapi contract: FAILED — the committed dump is stale.

The API schema changed and packages/schemas/openapi.json was not regenerated. Anything
generated from that file — the frontend client above all — is now describing an API that
does not exist.

Fix:
  python3 apps/control-api/tools/export_openapi.py packages/schemas/openapi.json
  git add packages/schemas/openapi.json

$ git status --porcelain packages/schemas/openapi.json
(empty)          <- the gate did NOT self-heal the dump this time
```

Three properties, each of which had to hold and each of which I checked separately:

1. it **fails** on real drift (exit 1, not the Round-1 exit-1-for-the-wrong-reason);
2. it fails with a **readable unified diff naming the exact field**, which is what makes the
   message actionable rather than a wall;
3. it leaves the committed dump **unmodified**, which is the property whose absence made the
   Round-1 gate worse than no gate.

The in-suite `test_committed_dump_is_current` also still fails on the same drift, so the
freeze now has two independent guards rather than one guard and one decoy. Issue #6's
acceptance criterion is true for the first time.

### BUG-016 — CLOSED. Round-1 evidence: C5's import-direction check silently skips in CI. **minor.**

```
SKIPPED [1] tests/architecture/test_import_direction.py:125:
  could not import config.asgi in this environment (dependencies missing?)
```

`ci.yml` ran `pytest tests/ -q` **before** installing `apps/control-api/requirements.txt`,
so this architecture invariant — the ASGI process must not import the gateway — skipped on
every run rather than failing. Owner: `devops` (ci.yml came from #91, not this PR), but the
skip only became reachable because this PR added `config/asgi.py`.

**Round 2: closed** — a dedicated install step now precedes the architecture step, and
`-rs` was added so any future skip prints its reason in the CI log instead of passing as a
dot. Evidence in §9.1: 36 passed, zero skipped, `test_import_direction` named and passing.

The first attempt at this fix also set `DJANGO_SETTINGS_MODULE` on that step, which broke it
outright. The fixer caught it themselves and reported it; I reproduced it rather than take
the account on trust (§0.2). Worth recording because it is a good failure: the bug was found
by *replaying the CI job* instead of reasoning about the YAML, which is the same reason this
QA phase caught BUG-002 at all.

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
**Status** is as of Round 2 (`743ffa9`). Every "CLOSED" was verified by executing the case
that previously failed — none was closed by reading a diff.

| ID | Sev | Status | Summary | Owner |
|---|---|---|---|---|
| **BUG-001** | **blocker** | **CLOSED** §9.1 | `USE_X_FORWARDED_HOST` unset → required CI job `pytest` fails on merge. Now in `base.py`, so both profiles carry it; 36 passed, 0 skipped | backend-developer |
| **BUG-002** | **blocker** | **CLOSED** §9.2 | Exporter ignored `argv[1]` → the drift gate rewrote the dump it polices and could never fail. Now exits 0 clean, exits 1 with a field-level diff on real drift, and leaves the dump untouched | backend-developer |
| BUG-016 | minor | **CLOSED** §9.1 | `ci.yml` ran `pytest tests/` before installing control-api deps, so C5's import-direction check skipped silently every run | devops |
| BUG-003 | major | **open** — CTO **C6** | `assert_verdict_is_evidenced` duck-types on `.verdict`; an in-contract `CandidateVerdict` with no gate matrix satisfies the #77 guard (§4b) | **CTO ruling**, then backend-developer |
| BUG-004 | major | **open** — CTO **C1** | The verification-record set is not bound to the mission: cross-mission records accepted, duplicates counted twice, dropping a `REJECTED`/`HUMAN_REVIEW` record reaches `VERIFIED`. Candidate set is not frozen; `test_cannot_add_candidate_after_verification_starts` does not exist (§4c) | **CTO ruling**, then backend-developer |
| BUG-005 | major | **open** | `PAUSED → EXPORTING` lets a mission reach `VERIFIED` having never entered `PATCH` or `VERIFY` (§4d) | **CTO ruling**, then backend-developer |
| BUG-006 | *deferred to `cybersecurity`* | open | `model_policy` accepts metadata endpoints, IDNA homographs, and **a decimal-encoded public IPv4** (`http://134744072/` → 8.8.8.8) — the last is new beyond SEC-02 (§3) | cybersecurity → backend-developer |
| BUG-007 | major | **open** | Provenance defaults point at the strong claim: `ModelProvenance` replay fields default to "live", `GateResult.evidence_source` defaults to `TOOL_EXECUTION` (§8) | backend-developer |
| BUG-008 | major | **open** | An operator-supplied patch is recordable as `MODEL_GENERATED` with two invented strings; `prompt_sha256` is optional (§8) | backend-developer |
| BUG-009 | minor | **open** | `MissionDetail(verdict=…, verdict_summary=None)` and `(state=VERIFIED, posture=FAILED)` both constructible, contradicting their own docstrings (§8) | backend-developer |
| BUG-010 | major | **open** | `sqlite:///name.db` → `/name.db`; `migrate` fails; the repo's own `ci.yml` uses this form twice (§10) | backend-developer |
| BUG-011 | *deferred to `cybersecurity`* | open | PostgreSQL DSN query params silently dropped — `?sslmode=require` ignored (§10) | cybersecurity → backend-developer |
| BUG-012 | minor | **open** | `/api/v1/system/health` returns 200 while `degraded` (§10) | backend-developer + devops |
| BUG-013 | *deferred to `cybersecurity`* | open | `/api/v1/docs` and `/api/v1/openapi.json` are unauthenticated in the **finale** profile (§6) | cybersecurity |
| BUG-014 | minor | **open** | `HUMAN_REVIEW` is terminal with no outgoing transitions — a reviewed mission cannot be resumed, resolved or cancelled. `PAUSED` also displays as `HUMAN_REVIEW` (§8) | product-manager (decision), then backend-developer |
| BUG-015 | trivial | **open** | `ci.yml` asserts ruff and mypy "were green at D1"; ruff reports 29, mypy 2. Re-checked on `743ffa9`: the two changed files carry one finding, `export_openapi.py:71 T201 print found` (pre-existing pattern, and the script is meant to talk to the operator) | backend-developer |
| BUG-017 | minor | **open** | No `GET /missions/{id}/verifications` collection route; the D6 side-by-side panel must fan out over patches (§5) | backend-developer + product-manager |
| **BUG-018** | minor | **open** — CTO **C3**, new in Round 2 | `EvidenceBundle` has no `recommended_patch_id`. Where two candidates both verify, nothing says which diff we are claiming. One field (§0.3) | backend-developer |

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
| **Round 2 only:** PostgreSQL re-verification (§6) | **NOT RE-RUN** | Round 1's PostgreSQL run stands. The fix commit touched `base.py` (two settings) and `export_openapi.py` only, and `env.database_from_url` is unchanged — but I am recording this as *not re-run* rather than implying it was. |
| **Round 2 only:** §7 HTTP surface in full | **PARTIAL** | Re-smoked after the ingress change (health, 401, 501, 422, openapi, forwarded headers, SSE — all in §9.1). The full role/envelope matrix and the trace-ID table were **not** re-executed; Round 1's results stand for those. |

---

## 13. Decision records

### DR-QA-2 (Round 2) — approving with known issues once the blockers closed

**Decision.** Move the verdict from REJECTED to **APPROVED WITH KNOWN ISSUES**, conditional
on the four items in §0.4.

**Options considered.**
(a) **APPROVED WITH KNOWN ISSUES** — the two blockers are executed-verified closed; the eight
open findings are documented with owners, and the two sharpest are the CTO's own open
conditions.
(b) **Hold REJECTED until C1 and C6 are ruled on.** Nothing merges until the contract shape
is settled.
(c) **APPROVED, clean.** Not defensible — eight findings remain, three of them touching the
product's central claim.

**Pros and cons.**
(a) unblocks the Command Center against a frozen, drift-guarded contract on D1, and both CI
jobs are now green with the drift gate proven to fail correctly on injected drift. Con: eight
findings ride into `main`, and "known issues" is a phrase that decays into "issues" if nobody
re-checks. Mitigated by §0.4's four named conditions and §14's re-check list.
(b) is the purist call and I considered it seriously, because BUG-004 is the CTO's C1 and C1
is the one that makes D6 structurally reachable. I rejected it for a reason of authority, not
convenience: **C1 and C6 are the CTO's conditions, and QA blocking a merge to force a CTO
ruling inverts who decides what.** My job is to make the cost of not ruling visible, which
§0.4 and §14 do. It is also empirically weak — the branch sitting unmerged does not make the
ruling arrive faster, and it stops a frontend developer starting against a contract that is
now demonstrably frozen.
(c) invalid; §11 lists eighteen findings, eight still open.

**Cost implications.** Approving now costs the re-check in §14 — about an hour of mine when
#12 lands. Holding would cost every role downstream of the frozen contract a day, to force a
decision I do not own.

**Security implications.** Unchanged from Round 1. BUG-006, BUG-011 and BUG-013 are
`cybersecurity`'s to rate; none is regressed by this PR and one (the decimal-encoded public
IPv4) is new information for them. The ingress fix is a net security improvement: the
development profile stops having the same forwarded-header defect the finale profile had
fixed.

**Scalability implications.** None from this decision. CTO C1's thread-pool question (§7)
remains genuinely untested and is called out as NOT RUN, not as passed.

**Recommendation.** (a), with §0.4's four conditions binding and re-checked by me.

**Final approval authority.** CTO for BUG-003/004/005 (they are C6, C1 and a sibling of C1);
`product-manager` for BUG-014 and BUG-017; `cybersecurity` for BUG-006/011/013. My verdict
covers the release gate only — it is a statement of what was executed and what it showed.

---

### DR-QA-1 (Round 1, superseded by DR-QA-2) — recommending rejection on D1

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

## 14. Exit criteria

### Round 1's exit criteria, and how each was met

| # | Criterion | Result |
|---|---|---|
| 1 | `pytest tests/ -q` green on the merge result (BUG-001) | **MET** — `36 passed`, and the 1 skip is gone too |
| 2 | `openapi-contract-check.sh` exits 0 **and** leaves the dump unmodified; verified by injecting drift and confirming it fails for the right reason (BUG-002) | **MET** — all three properties checked separately, §9.2 |
| 3 | A ruling on BUG-003, BUG-004, BUG-005 | **NOT MET — carried forward.** Correctly so: these are CTO C6, C1 and a sibling of C1. The fixer declined to patch them pending a ruling, which is the right call |
| 4 | BUG-007 and BUG-008 fixed, or the "structurally impossible" wording corrected | **NOT MET — carried forward** |
| 5 | 169+ tests green, with regression tests for whichever bypasses got fixed | **PARTIAL** — 169 green; no bypasses were fixed, so no new regression tests were due |

Two of five met, and they are the two that were blocking. Three carry forward into §0.4.

### What I re-check next, and when

**Trigger: before #12 merges** — because #12 is the code that encodes whatever answer the CTO
gives on C1 and C6.

1. **BUG-003 / C6** — re-run attack case B2 (`CandidateVerdict` satisfying the guard). Expect
   a refusal, not an `AttributeError`.
2. **BUG-004 / C1** — re-run cases C1–C4, and check for the existence of
   `test_cannot_add_candidate_after_verification_starts` by name, since the CTO specified it
   by name.
3. **BUG-005** — re-run the seven-step `PAUSED → EXPORTING → VERIFIED` walk (case F).
4. **BUG-007 / BUG-008** — re-run cases D1, D2, D3. If the wording is corrected instead of the
   code, I check the wording in the PR body, `00-product-identity.md` and any slide copy, and
   the finding closes as documentation rather than as code.
5. **#103** — re-run the suite on **both** 3.12 and 3.13 and require the same result from each.
   A version-independent exporter is the fix; a pin is not.
6. **BUG-010** — re-run the DSN table the moment D2's models land, since that is when it stops
   being dormant.
7. **BUG-018 / C3** — check `EvidenceBundle` for a recommended-candidate field.

**Trigger: before D6** — the items in §12 that cannot be tested against a 501 surface:
SSE through nginx (`smoke-sse.sh`), CTO C1's thread-pool behaviour under genuinely held
streams, C3's gap-free `sequence` under two writers, and the full suite against PostgreSQL
once there is a schema to exercise.

### Standing note on this report

Round 1 and Round 2 are both preserved above rather than overwritten. A QA report that
silently rewrites its own history to match the current state is worth as much as a drift
detector that regenerates the file it is checking — which is, as it happens, exactly the bug
this phase found.
