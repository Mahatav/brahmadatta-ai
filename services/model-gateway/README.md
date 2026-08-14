# Model gateway

The component that decides what a model is allowed to see, where it is allowed to be, and
what the system is allowed to say about the answer.

Two things live here, from issues **#82** (recorded-transcript replay) and **#78/#93**
(the endpoint policy, SEC-02).

```
gateway/
  endpoint_policy.py   which hosts a prompt may be sent to        #78 / #93 / SEC-02
  settings.py          configuration, validated at construction
  schemas.py           GenerationRequest / PatchCandidate         one schema, both paths
  provenance.py        where a response came from, in words       the only place wording lives
  context.py           bounded, redacted model context            #35
  transcripts.py       the SHA-256 transcript store               #82
  backends.py          live / replay / operator-supplied sources  the three ladder rungs
  service.py           ModelGateway — one code path
  tools/               operator commands
```

## Running the tests

```
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q -rs
```

`-rs` matters: two modules skip cleanly when `apps/control-api/` or
`docs/09-company/10-fallback-ladder.md` is absent, and a skip that nobody sees is a test
that quietly stopped asserting.

## Replay mode

Live CPU generation is the preferred path. Replay is the fallback for the highest-variance
item in the plan — the D6 gate needs a policy-passing compiling patch in 3 of 10 attempts
from a quantized model on CPU, on day six of seven.

```
MODEL_GATEWAY_MODE=replay
MODEL_TRANSCRIPT_ROOT=services/model-gateway/transcripts
```

`MODEL_GATEWAY_MODE` has **no default**. An unset mode is a startup error, because the
choice between "live" and "replayed" is a claim, and D-049 rules that the system does not
make a provenance claim on the operator's behalf by staying silent.

Replay is never reached by failing. A live timeout, an OOM or an unreachable backend
raises; the transcript store is not consulted. `gateway/tests/test_no_silent_fallback.py`
proves it with a populated store and a spy that fails the test if it is read.

### The honesty constraint

A replayed response is legitimate. Presenting it as inference happening in front of a judge
is not. Three claims, one function:

| Source | Rendered as |
|---|---|
| recorded transcript | `model output recorded 2026-08-06, replayed` |
| operator-supplied diff | `operator-supplied candidate` |
| live inference, fully attested | `model-generated (live inference 2026-08-13)` |
| anything short of the above | `model output, provenance not attested — not presented as live inference` |

The last row is the D-049 Part 1 direction: the fallback branch produces an
**understatement**, so a field somebody forgot to set cannot produce an overclaim.

Two tests carry this rather than a convention:

- `test_provenance_labelling.py` — each renderer, each claim, and the mandated strings.
- `test_provenance_chokepoint.py` — an AST scan asserting that no other module in this
  package puts provenance wording into a runtime string, so a second renderer fails the
  build instead of shipping.

`test_fallback_ladder_wording.py` reads the strings back out of
`docs/09-company/10-fallback-ladder.md`, so editing the document without the code (or the
other way round) fails.

### Operator commands

```
python -m gateway.tools.transcripts_cli list
python -m gateway.tools.transcripts_cli verify                  # pre-flight item 3
python -m gateway.tools.transcripts_cli resolve --prompt-file p.txt --prompt-version v
```

`resolve` exits `0` resolved, `3` transcript absent, `4` present but unusable (digest or
schema mismatch, ambiguity), `5` bad arguments — the fallback ladder's rung-3 trigger as
three distinguishable answers rather than one failure. It prints the exact sentence the run
will display, which is the point of running it at pre-flight rather than at hour 30.

## D5 — Ollama CodeLlama local model prep evidence

`gateway.tools.model_prep` is the local model evidence harness. It does **not** download a
model by default. For D5, the selected operator path is Ollama CodeLlama
(`codellama:7b-instruct`) running on loopback. The operator pulls the model explicitly,
then the tool records the evidence the issue asks for:

- pinned artifact hash, size, model revision and quantization
- proof that the serving endpoint is local-only under the gateway endpoint policy
- cold-start / first-token / throughput evidence in JSON
- hardware snapshot beside the measurement, so numbers are not detached from the machine

The safe CI path uses a deterministic fake backend and loads no model:

```
python -m gateway.tools.model_prep measure --backend fake \
  --endpoint http://127.0.0.1:8080/v1 \
  --output evidence/model-prep/fake-measurement.json
```

The real Ollama operator run shape is printed by:

```
python -m gateway.tools.model_prep plan --evidence-dir evidence/model-prep
```

That plan expands to this sequence:

```
# Fetch explicitly. This is the multi-GB step; the harness never starts it on its own.
ollama pull codellama:7b-instruct

# Serve on loopback only, then prove the boundary before measuring. Ollama's default
# local API base is http://127.0.0.1:11434/api.
ollama serve

python -m gateway.tools.model_prep doctor \
  --endpoint http://127.0.0.1:11434/api \
  --output evidence/model-prep/model-doctor.json

python -m gateway.tools.model_prep check-serving \
  --endpoint http://127.0.0.1:11434/api \
  --output evidence/model-prep/model-serving.json

# Measure through the same local-only endpoint shape the gateway permits.
python -m gateway.tools.model_prep measure \
  --backend ollama \
  --endpoint http://127.0.0.1:11434/api \
  --model codellama:7b-instruct \
  --revision ollama-library/codellama \
  --prompt-file prompts/patch-generation.txt \
  --prompt-version patch-prompt/3 \
  --output evidence/model-prep/model-measurement.json
```

If the final command cannot produce `first_token_ms` and a non-empty output stream from the
actual machine on D5, record that immediately. That is the point of the issue: a slow or
unavailable local CPU model is a D5 fact, not a D6 surprise.

`doctor` writes an evidence record in both directions. A ready record means the local
Ollama API is reachable and `codellama:7b-instruct` is present. A blocked record says the
deterministic tier is active and why; it does not pretend CodeLlama ran.

Compose also has an opt-in `model-host` profile in both dev and finale stacks. It runs the
pinned Ollama image on the internal `backend` network with `mem_limit` set, and no external
route. Use it when the model store has already been prepared; the app-facing loopback path
above remains the quickest local developer check.

## Context boundary

`gateway.context.build_context(finding, policy)` is the only producer of
`ContextPackage`, and `request_patch(context, policy, gateway)` is the only consumer. The
gateway does not accept a repository root, directory handle, file object, or caller-written
prompt for patch generation. It receives a bounded finding package and policy, redacts
absolute paths plus `KEY|TOKEN|SECRET|PASSWORD`-shaped lines, records `prompt_sha256` and
`context_bytes`, and only then calls the local gateway.

## The endpoint policy

`endpoint_policy.classify()` is the gateway's egress function: the last thing between a
prompt built from repository source and a TCP connection.

**It is defence in depth, and the network is the real control.** SEC-01 closed the exploit
path by topology — the process holding repository snapshots has no default route, verified
from inside the running container by
`infrastructure/scripts/finale-egress-evidence.sh`. This module does not repeat that claim.

It matters anyway because `docs/04-development/31-development-setup-guide.md` documents a
bare `uvicorn` on a laptop with a full default route, where the validator is the only
control — and because a control that returns the wrong answer is worse than no control.

Configuration:

```
MODEL_ENDPOINT=http://small-model:8080/v1
MODEL_SERVICE_NAMES=small-model          # empty by default; nothing extra is trusted
```

Permitted without any declaration: loopback, RFC 1918, IPv6 unique-local, `localhost`,
`host.docker.internal`. Everything else is an explicit operator declaration.

### Two deliberate divergences from `contracts/model_policy.py`

Both tighten, and both are called out because they would fail existing control-API tests if
the two implementations were ever merged.

- **Private DNS suffixes (`.internal`, `.local`, `.svc`, `.test`) no longer pass on the
  suffix alone.** Nobody owns those namespaces. Issue #78 names
  `https://my-llm-proxy.internal/v1` as part of the finding, and QA found `evil.internal`,
  `sneaky.svc`, `redirector.local` and `api.openai.com.evil.test` passing.
- **Reserved documentation ranges (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`) are
  denied.** The old module permitted them for not being globally routable. They also cannot
  serve a model, and "not globally routable" is a different property from "inside our trust
  boundary".

### SEC-24 and SEC-25 — round-3 security review findings, both fixed

**SEC-24 — a 6to4/NAT64 literal was judged by its embedded address.** `2002:0a00:0001::`
(6to4) and `64:ff9b::a00:1` (NAT64) both carry 10.0.0.1, and the old code unwrapped either
one and judged the result exactly like any other address — so a private or loopback
embedded address was permitted. Wrong: reaching either literal means a translation relay
outside this policy's visibility rewrites the packet to the embedded destination, so "the
embedded address is private" was never the same claim as "this destination is inside the
boundary". Neither mechanism is meant to carry a non-global address in the first place (RFC
3056 §2, RFC 6052 §3.1). Fixed: a 6to4/NAT64-unwrapped address is refused outright,
regardless of what it carries. `ipv4_mapped` (`::ffff:x.y.z.w`) is unaffected — that is a
notation, not a translation path, and stays judged by the address it carries.

**SEC-25 — a single unbroken label of certain Unicode scripts is quadratic in `idna`.**
`idna`'s ContextO check (needed for same-script constraints, e.g. Arabic-Indic digits) is
called once per codepoint in a label and scans the label each time — O(N²) per label —
*before* `idna`'s own length check runs. The advisory's payload, a ~60,000-character label
of U+0660 repeated, measured 99.8s-122.5s through this exact call site on the previously
pinned `idna==3.10` (CVE-2026-45409). Two independent fixes, both required: `idna>=3.15`
(now pinned to 3.18), and an RFC 1035 length guard (253 chars total, 63 per label) applied
to the raw string before `idna.encode()` is called anywhere in this module — so the guard
holds even against a future regression in the library.

### Re-running the bypass table

```
python3 infrastructure/scripts/testing/endpoint-policy-bypass-table.py
```

68 cases, every one written down by a reviewer — the security review's SEC-02 proof blocks,
its §12.2 re-run inside the built finale image, the QA report's 30-row attack table, issue
#78's own examples, and the round-3 review's SEC-24 and SEC-25 regression cases. Each row
carries its source. The same table is the pytest parametrisation in
`gateway/tests/test_endpoint_policy.py`, so the script and the suite cannot disagree about
what "correct" means.

The script gates **both** columns (CTO condition 2 on #111): the gateway column at zero, and
the control-API column at exactly `CONTROL_BASELINE` — a recorded number, not zero, because
`contracts/model_policy.py` is not modified on this branch (tracked on #93) and a hard zero
would make every unrelated PR unmergeable for a defect none of them introduced. It fails in
*both* directions: a regression breaks the build, and an unrecorded improvement does too,
until `CONTROL_BASELINE` is lowered in the same commit. See "What this does not do".

## What this does **not** do

Listed because a component that quietly does not do something is worse than one that says
so.

- **No local CodeLlama runtime is implied by the code.** The Ollama backend exists, and
  `doctor` records whether `codellama:7b-instruct` is actually reachable on the machine.
  A failed doctor record means the deterministic tier is active; no latency, throughput
  or patch-quality number may be reported as measured against CodeLlama until `doctor`
  and `measure --backend ollama` pass on that host.
- **`contracts/model_policy.py` is unchanged.** The ASGI process must not import `gateway`
  (C5, `tests/architecture/test_import_direction.py`), and that file belongs to the
  control-API seat. The bypass-table script measures it; issue #93 fixes it.
- **No raw repository loading.** `context.py` redacts and packages a bounded finding, but
  the model gateway never receives a repository root and never walks source trees.
- **No escalation, no GPU lifecycle, no context policy.** D-015 cut the rented GPU;
  tier-escalation mechanics are not in this build.
- **The UI and the evidence builder are not covered by the chokepoint test.** It is a claim
  about `services/model-gateway/`, not about the product. The gateway hands out
  `render_for_ui()['label']` as a finished string for those consumers to print verbatim;
  whether they print it is theirs to test.
