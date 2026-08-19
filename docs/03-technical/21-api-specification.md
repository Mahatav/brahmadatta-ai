# API Specification

> **Frozen at D1 (2026-08-07) — issues #6 and #9.** The implemented surface is the
> django-ninja schemas in `apps/control-api/contracts/`, published as
> [`packages/schemas/openapi.json`](../../packages/schemas/openapi.json). Where this
> document and that dump disagree, **the dump wins** — it is generated from the code.
> The sections below are the original specification, left intact, with the D1 delta
> recorded in [§ D1 frozen contract](#d1-frozen-contract-2026-08-07) at the end.
> Superseded lines are marked, not deleted.

## Mission API

- `POST /api/v1/missions` — create a mission draft.
- `POST /api/v1/missions/{id}/snapshot` — upload or import an immutable repository snapshot.
- `POST /api/v1/missions/{id}/preflight` — validate authorization, commands, adapter, and limits.
- `POST /api/v1/missions/{id}/start` — start the autonomous workflow.
- `GET /api/v1/missions/{id}` — current state, phase, progress, and summary metrics.
- `GET /api/v1/missions/{id}/events` — ordered event stream through SSE.
- `POST /api/v1/missions/{id}/pause` — pause after the current safe boundary.
- `POST /api/v1/missions/{id}/cancel` — cancel and clean resources.

## Evidence API

- `GET /api/v1/missions/{id}/findings`
- `GET /api/v1/missions/{id}/findings/{finding_id}`
- ~~`GET /api/v1/missions/{id}/git-bisect`~~ — **superseded/cut at D1.** Automated bisect is P1-1, in the `CUT` milestone (D-014).
- `GET /api/v1/missions/{id}/fuzzing`
- `GET /api/v1/missions/{id}/patches`
- `POST /api/v1/missions/{id}/patches` — **added post-D1 (T-3, 2026-08-19, D-008).** Submit an operator-authored unified diff; see § Operator-supplied candidate submission below.
- `GET /api/v1/missions/{id}/patches/{patch_id}/verification`
- `GET /api/v1/missions/{id}/evidence`
- `POST /api/v1/missions/{id}/export`

## Infrastructure API

- `GET /api/v1/system/health`
- `GET /api/v1/system/workers`
- ~~`GET /api/v1/system/gpu-leases`~~ — **superseded at D1.** Rented GPU is cut in full (D-015). Replaced by `GET /api/v1/system/sandboxes`.
- ~~`POST /api/v1/system/gpu-leases/{id}/teardown`~~ — **superseded at D1.** Teardown remains P0-14; replaced by `POST /api/v1/system/sandboxes/{sandbox_id}/teardown`.

## Event schema

```json
{
  "mission_id": "uuid",
  "sequence": 142,
  "timestamp": "ISO-8601",
  "phase": "STRESS_TEST",
  "status": "RUNNING",
  "severity": "INFO",
  "message": "Minimized sanitizer reproducer created",
  "evidence_refs": ["artifact://..."],
  "metrics": {"coverage_percent": 78.6}
}
```

The example above is **superseded at D1** by the `MissionEvent` schema in the OpenAPI
dump: it keeps every field shown here, adds `id`, `type`, `payload` and `trace_id`
(required by issue #6), and replaces free-string `phase`/`status`/`severity` with
enums. See § D1 frozen contract.

## Error codes

`INVALID_AUTHORIZATION`, `UNSUPPORTED_REPOSITORY`, `PREFLIGHT_FAILED`, `BASELINE_BUILD_FAILED`, `BASELINE_FLAKY`, `SANDBOX_POLICY_VIOLATION`, `NO_REPRODUCIBLE_FINDING`, `PATCH_POLICY_REJECTED`, `MODEL_CAPACITY_UNAVAILABLE`, `GPU_LIMIT_EXCEEDED`, `VERIFICATION_FAILED`, `SAFE_CANCELLATION_IN_PROGRESS`.

## API rules

- All mutations are idempotent or carry an idempotency key.
- Every response includes a trace ID.
- Raw secrets and unrestricted source archives are never returned to the browser.
- The UI uses sanitized evidence endpoints and signed short-lived artifact links.

---

## D1 frozen contract (2026-08-07)

Implemented in `apps/control-api/`, published as `packages/schemas/openapi.json`
(22 operations). Everything except `GET /api/v1/system/health` returns
`501 NOT_IMPLEMENTED` with the standard error envelope; the schemas are final.

### Endpoints added to this specification

| Endpoint | Why |
|---|---|
| `POST /api/v1/missions/{id}/authorize` | P0-1. The specification folded authorization into preflight, but the safety boundary needs a durable **record** — `contracts.state_machine` refuses every stage without an active one. Returns `AuthorizationRecord`. |
| `GET /api/v1/missions` | The Command Center needs a mission list; `Page[MissionSummary]`. |
| `GET /api/v1/missions/{id}/events/replay` | Gap recovery. `/events` is the SSE stream; this is the typed JSON replay a reconnecting client uses, since `sequence` is gap-free per mission. |
| `GET /api/v1/missions/{id}/baseline` | P0-5 and the D3 gate are stated in baseline counts; the UI needs them addressable without pulling the whole evidence bundle. |
| `GET /api/v1/system/sandboxes` | Replaces `GET /system/gpu-leases` (D-015). P0-14 teardown still applies to whatever compute a run started. |
| `POST /api/v1/system/sandboxes/{sandbox_id}/teardown` | Replaces the GPU-lease teardown, same reason. |
| `POST /api/v1/missions/{id}/patches` | **Added post-D1 (T-3, 2026-08-19, D-008).** No HTTP-reachable path existed for an operator-supplied candidate (D-084, D-085). See § Operator-supplied candidate submission above. |

### Endpoints cut

`GET /missions/{id}/git-bisect` (P1-1), `GET /system/gpu-leases` and
`POST /system/gpu-leases/{id}/teardown` (D-015). A test asserts these paths are absent
from the OpenAPI document so they cannot reappear without a scope decision.

### Mission states

`CREATED → AUTHORIZED → SNAPSHOTTED → VALIDATING → BASELINE → TRIAGE → STRESS_TEST →
CORRELATE → PATCH → VERIFY → EXPORTING → VERIFIED / REJECTED / HUMAN_REVIEW`, plus
`PAUSED`, `CANCELLING`, `FAILED`, `CANCELLED`.

Three states extend the list in `16-system-architecture-document.md`: `AUTHORIZED`
(the authorization gate needs a state), `EXPORTING` (a mission is not `VERIFIED` until
the evidence bundle that justifies it exists — P0-12), and `PAUSED`/`CANCELLING`
(operator controls this document already specified but that document's state list
omitted). `MissionPosture` is the separate display enum the Core renders — protected,
investigating, vulnerability confirmed, patching, verified, rejected, human review,
failed — derived server-side from the state, never set by the client. It adds a ninth,
`CANCELLED`: folding a deliberate cancellation into `FAILED` would show a red alert
ring on the most visible element in the product for an operator action that worked.

### Event envelope

`MissionEvent`: `id`, `mission_id`, `sequence`, `timestamp`, `type`, `stage`, `state`,
`status`, `severity`, `message`, `payload`, `evidence_refs`, `metrics`, `trace_id`.
`payload` is a union discriminated on `kind` with fourteen variants, so the frontend
gets an exhaustively-checked `switch` and a new variant breaks its build.

SSE framing: `id: <sequence>`, `event: <type>`, `data: <MissionEvent JSON>`. The
endpoint sets `X-Accel-Buffering: no`; nginx also needs `proxy_buffering off`
(issue #10) or the stream arrives in one lump at the end.

### Multiple candidates per mission

A mission carries **N** patch candidates and **N** verification runs, each with its own
gate matrix, verdict and provenance. The demo runs two through the identical pipeline
and shows them side by side — one `Verified`, one `Rejected` — which is the D6 gate and
the competition differentiator.

* `MissionVerdictSummary` carries the mission verdict *and* the per-candidate
  breakdown, and a validator refuses any summary whose counts or mission verdict do not
  follow from its candidates. A rejection cannot be quietly dropped.
* `derive_mission_verdict` states the reduction explicitly: no runs →
  `HUMAN_REVIEW_REQUIRED`; any `HUMAN_REVIEW_REQUIRED` → `HUMAN_REVIEW_REQUIRED`; at
  least one `VERIFIED` → `VERIFIED`; otherwise `REJECTED`. A `VERIFIED` mission never
  means "every candidate passed".
* `EvidenceBundle` carries every candidate and every verification record in full.
* `assert_transition` takes the **set** of verification records and derives the terminal
  state from all of them, not from whichever finished last.

The orchestrator still has to fan out over candidates *inside* the PATCH and VERIFY
stages rather than loop `VERIFY → PATCH` — that half is issues #12 and #80.

### Operator-supplied candidate submission — `POST /api/v1/missions/{id}/patches` (T-3, 2026-08-19)

**Why this exists.** Three live rehearsals of the #50 D7 gate (D-084, D-085) found no
HTTP-reachable path for an operator to supply a patch candidate —
`orchestrator/patch_generate_executor.py` only ever calls the live self-hosted model.
The gate's own acceptance criteria need **both** a `Verified` and a `Rejected` verdict
produced in one run, which a live, non-deterministic model is a poor fit for on a
project whose kill criterion is about reproducibility. D-008 already permits an
operator-supplied candidate, explicitly labelled as such; this endpoint is the first
HTTP surface that reaches it. `demo/repositories/pktcfg/patches/` already ships the
fixture pair this endpoint is exercised against: `candidate-a-correct-bounds-fix.patch`
(→ `Verified`) and `candidate-b-rejected-crash-only-fix.patch` (→ `Rejected`).

**Request** — `OperatorPatchCandidateRequest`: `finding_id` (UUID, must belong to the
mission), `diff` (unified diff, ≤200000 chars), `rationale` (optional, ≤5000 chars).
No `provenance` field: the server always sets `PatchProvenance.OPERATOR_SUPPLIED`, so
an HTTP caller has no vocabulary to claim `MODEL_GENERATED` for a diff it typed itself.

**Response** — `201 PatchCandidate` (the same schema `GET .../patches` already
returns), with `provenance=OPERATOR_SUPPLIED`, `model=null`, and `policy_status` from
the same deterministic `orchestrator.patch_policy.evaluate_patch_policy` gate a
model-generated candidate is evaluated against — never accepted on say-so.

**Auth** — `OPERATOR_ROLES` (operator or administrator), matching every other
mutating mission endpoint. Not reachable by `REVIEWER`.

**Mission state** — the mission must be in `PATCH` (the point `PATCH_GENERATE` would
normally run) or already in `VERIFY` with no verification recorded yet (D-046's
freeze is keyed on `Mission.verification_started_at`, set on the *first*
`VerificationRecord`, not on `Mission.state`, so a second operator-supplied candidate
can still land against a mission this same endpoint already advanced — this is what
lets `candidate-a` and `candidate-b` both go through one mission, one endpoint call
each). Any other state is `409 INVALID_STATE_TRANSITION`.

**What happens on a call**, composed entirely from existing, unmodified functions —
no parallel verification path and no shortcut around any gate:

1. `orchestrator.candidates.record_patch_candidate` — the same D-046 freeze check and
   the same real policy gate a model-generated candidate goes through.
2. If policy-accepted and the mission is still in `PATCH`:
   `orchestrator.transitions.transition(..., MissionState.VERIFY)` — the *only*
   sanctioned writer of `Mission.state` (SEC-16); this module never assigns it
   directly.
3. If policy-accepted: `orchestrator.queue.enqueue_job(..., JobKind.VERIFY,
   payload={"patch_id": ...})` — the same `Job` table `run_worker`'s claim loop and
   `run_orchestrator`'s `dispatch_terminal_jobs` already drive for every other kind.
   The job is executed by the real, unmodified `orchestrator/verify_dispatch.py`
   executor (real `git apply`/`cmake`/`ctest` inside a `packages.sandbox.Jail`,
   SEC-47) and routed onward by its real, unmodified transition policy.
4. A policy-*rejected* candidate is recorded in full (visible on `GET .../patches`,
   with its own `PATCH_POLICY_EVALUATED` event) but the mission is left exactly where
   it was, and nothing is enqueued — a mission with nothing accepted never advances
   into a `VERIFY` stage with no job that could ever move it onward.

Implemented in `apps/control-api/orchestrator/operator_candidates.py` and
`apps/control-api/api/routers/evidence.py::submit_patch`. Real-toolchain proof of
both verdicts in one run, through this endpoint: `apps/control-api/orchestrator/
tests/test_operator_candidate_submission.py`.

### The D3 gate signal

The D3 kill criterion is written as the literal string `BASELINE_PASSED`. It is an
**outcome, not a mission state**: the mission is in `BASELINE` while the stage runs.
The observable signal is `EventType.BASELINE_PASSED` / `BASELINE_FAILED` on the event
stream, plus the derived boolean `BaselineReport.passed` (configure and build succeeded,
at least one test ran, none failed). Whoever checks the gate on 2026-08-09 should look
for the event type, not for a state.

### Fallback provenance — a substituted path is inexpressible as the primary one

The CEO approved fallbacks for D1–D7 (issues #81 subprocess jail, #82 model replay,
#83 reproducer replay). Using one is legitimate. Presenting one as the primary path is
not, and the schemas make that impossible rather than relying on a flag someone
remembers to set:

| Fallback | How the contract prevents the inflated claim |
|---|---|
| Model replay (#82) | `ModelProvenance.inference_mode` is **required with no default** — `LIVE_INFERENCE` or `REPLAYED_TRANSCRIPT` — and `REPLAYED_TRANSCRIPT` must carry `replayed_from_transcript` / `captured_at` / `transcript_sha256`, all three or none. Silence is a validation error, not a claim of live inference (D-049). |
| Reproducer replay (#83) | `FindingSummary.discovery_method` is **required with no default** — `FUZZING_CAMPAIGN`, `DIRECT_HARNESS` or `REPLAYED_REPRODUCER` — and a replayed finding must name its `replay_source` while a live one may not carry one. `FuzzingReport.mode` is required, and `NOT_RUN` cannot report executions or crashes |
| Gate evidence | `GateResult.evidence_source` is **required with no default** (D-049). A gate may only `PASS` on `TOOL_EXECUTION` with a named tool; a `NOT_RUN` gate may not claim `TOOL_EXECUTION` at all. A replayed artifact is recordable and displayable and **cannot pass a gate** — so a run whose fuzzer never executed cannot claim the renewed-fuzz gate |
| Subprocess jail (#81) | `IsolationMode` is **required with no default** on both `SandboxStatus` and `EvidenceBundle` (D-049 — the bundle previously defaulted to the stronger claim); `SUBPROCESS_JAIL` cannot be reported as `ROOTLESS_CONTAINER` |
| Operator-supplied patch (D-008) | `PatchCandidate` validator: `MODEL_GENERATED` requires `ModelProvenance`, `OPERATOR_SUPPLIED` forbids it. `POST /missions/{id}/patches` (T-3, § above) never accepts a `provenance` field from the caller at all — the server sets `OPERATOR_SUPPLIED` unconditionally, so an HTTP submission has no vocabulary to claim it came from the model. |

`EvidenceBundle.substitutions` lists every fallback used, with a mandatory non-empty
reason. An empty list is the claim that the primary path ran throughout — a claim the
pipeline has to earn, not one a reader has to infer from a missing section.

`EvidenceBundle.recommended_patch_id` names the one diff we stand behind (D-048). It is
derived and validated, not free-form: when set it must name a patch in `patches` whose
verification verdict is `VERIFIED`, and when exactly one candidate verified it must be
set to that one. A bundle showing two verified patches without naming one invites a
judge to pick the wrong one and ask why we shipped it.

### Properties the schemas enforce structurally

* **No verdict from confidence.** `derive_verdict(gates: GateMatrix) -> Verdict` has
  no parameter a confidence value could occupy; `GateResult`/`GateMatrix` forbid extra
  fields; `VerificationRecord` re-derives the verdict and refuses to serialize when the
  stored verdict does not follow from the gates. `confidence` exists exactly once in
  the whole document, on `ModelProvenance`, marked display-only.
* **No stage without authorization.** Every stage but `AUTHORIZE` requires an active,
  unrevoked, unexpired record bound to the snapshot being worked on. Cancellation and
  failure are deliberately exempt — losing authority is a reason to stop, not a reason
  to be unable to.
* **No sandbox egress.** `SandboxPolicy.network` is the literal `"deny"`; the API has
  no vocabulary for anything else.
* **No hosted inference endpoint.** Validated at startup by a Django system check; a
  hosted provider URL fails `manage.py check` and therefore fails boot.
* **No verdict state without verification.** `VERIFIED`, `REJECTED` and `HUMAN_REVIEW`
  reached from `EXPORTING` require the mission's verification records, and the target
  state must equal `derive_mission_verdict` over them. `HUMAN_REVIEW` reached earlier —
  a policy pause before anything ran — is deliberately not gated.

### Error envelope

Every non-2xx response:

```json
{
  "error": {"code": "INVALID_AUTHORIZATION", "message": "...", "details": {}},
  "trace_id": "..."
}
```

`code` is from the frozen vocabulary above, extended with `VERIFICATION_REQUIRED` (a
verdict state was requested with nothing to justify it — distinct from
`VERIFICATION_FAILED`, where the gates ran and said no), `SANDBOX_UNAVAILABLE` and
`JOB_TIMED_OUT` (architecture spec §6.1, §6.3), and the transport-level codes the API
cannot avoid emitting: `UNAUTHENTICATED`, `FORBIDDEN`, `NOT_FOUND`,
`VALIDATION_ERROR`, `INVALID_STATE_TRANSITION`, `CONFLICT`, `NOT_IMPLEMENTED`,
`INTERNAL_ERROR`. The trace id is also returned as the `X-Trace-Id` header on every
response, including successes.

### Authentication

`Authorization: Bearer <token>`, one token per role (operator, reviewer,
administrator), supplied by the environment. No configured token means no principal can
authenticate — the API fails closed. `GET /api/v1/system/health` is the only
unauthenticated operation, and a test asserts it is the only one.

---

## Fixed MVP competition decisions

- **Product name:** Brahmadatta AI.
- **Product type:** an authorized, defensive Cyber-Reasoning System for the AI Kavach competition MVP.
- **Architecture:** three evidence-driven tiers: fast deterministic triage, destructive sandbox testing with lightweight patching, and heavy repository-level reasoning only when escalation is justified.
- **Interface:** a dense futuristic armor-command-center dashboard with a central mission core, live telemetry, drill-down panels, and operator controls. The visual language is original and does not copy third-party logos or branded interface assets.
- **Primary workflow:** authorize → ingest → baseline → analyze → correlate → stress-test → patch → verify → export evidence.
- **Compute:** CPU-first processing with self-hosted models on rented GPU infrastructure. Repository content is not sent to an external inference API.
- **MVP target:** C/C++ repositories first; Python support is optional.
- **Verification rule:** a patch is never accepted on model confidence alone. The original reproducer, regression tests, static checks, and renewed fuzzing determine the verdict.
- **Safety boundary:** authorized repositories and isolated environments only; no public-target scanning, no exploit deployment, and no automatic production merge.

## Open decisions / next review

- Assign the final three-person team roles.
- Lock the rented GPU provider and tested model-serving recipe.
- Replace estimated performance targets with benchmark results.
- Confirm the final competition demo repository and fallback recording.
