# CTO Technical Review — After the Fact

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Document | Retrospective phase 2 technical review (the pass that was skipped) |
| Reviewer | `cto` seat |
| Date | 2026-08-07 |
| Reviewing | D-013, D-014, D-015; the D1–D7 critical path; the #6 contract seam; the two hard invariants |
| Supersedes | Nothing. `.project/decisions.md` is untouched — the orchestrator folds these records in. |

---

## ⚠ Errata — the `D-0xx` numbers in this document are proposals, not canonical

This review **proposed** three new decision records and numbered them D-019, D-020 and D-021.
By the time they were appended to [`.project/decisions.md`](../../.project/decisions.md), the
`ui-ux-designer` seat had already taken D-019 through D-023, so the CTO's records landed further
down. **Following a `D-0xx` reference from this document into the canonical log lands on an
unrelated decision.**

| Proposed here | In the canonical log | Note |
|---|---|---|
| D-019 — queue: no Redis, no Celery | **D-024** — Postgres `SELECT … FOR UPDATE SKIP LOCKED`, no broker | Ratified. |
| D-020 — model gateway replay mode | **no canonical record** | It exists as issue **#82** and inside the batched contract change. This is the gap most likely to bite: `10-fallback-ladder.md` and #82 both lean on it. |
| D-021 — two event channels | **withdrawn** | The CTO withdrew it on the second ruling round in favour of throttling at source. Do not implement it. |
| D-028 (referenced) | **D-028** — no process holding repository content has a route to the internet | Coincidentally correct; the number matches. |

Everything numbered **C1 … C9** in this document is a *condition*, not a decision record, and
those numbers are stable. Two ruling rounds exist and both use `C1 … C9` — the second round is
a review comment on PR #79, not in this file. QA hit this in round 1 and correctly tested the
substance rather than the labels.

Found by the `competition-strategist` seat while writing the fallback ladder. Recorded as an
errata rather than by renumbering, which is the precedent this project has set three times —
prior documents are left intact and corrections are appended.

## Standing and scope

Phase 1 closed **CONDITIONAL GO** and the orchestrator went straight to implementation
without phase 2 (architecture) or phase 4 (engineering-manager breakdown). Four structural
decisions — D-013 through D-016 — were made with no technical review, and two more (D-017,
D-018) are visual and not mine. This document is that review, run after the code started.
That ordering is bad and I am not going to pretend otherwise: the value of a phase-2 gate is
that it is cheap to change your mind before anything is built. Some of what follows is
therefore constrained by what already exists.

Everything below was checked against the repository as of `ad2ef2b`, including work in
flight in the `feat/control-api-scaffold`, `feat/infra-nginx-compose` and `feat/demo-target`
worktrees. Where I state a behaviour I ran it; the output is quoted.

**No code was edited.** Four implementation agents are live.

---

## 0. Summary of verdicts

| Decision | Verdict |
|---|---|
| **D-013** — Astro + Django + nginx | **RATIFIED WITH CONDITIONS** (seven conditions, §1) |
| **D-014** — 14 days / 7-day build | **RATIFIED** as a CEO business call, **with a recorded technical consequence**: the P0 set is *not* deliverable in 7 days at current scope. Six specific reductions in §2 make it deliverable. |
| **D-015** — rented GPU cut | **RATIFIED**, with two conditions (§3) |
| **New — D-019** | Queue: no Redis, no Celery. Single supervised orchestrator process. (§1.8) |
| **New — D-020** | Model gateway gets a replay mode, and the contract carries replay provenance. Lands D2, not D5. (§2.3) |
| **New — D-021** | Two event channels: durable/gap-free, and sampled/non-durable. (§1.4) |

And the answer to the question that actually matters:

> **The two hard invariants are not both structurally enforced today.**
> "No external inference API" is enforced over *configuration* and not over *egress*.
> "No confidence past a verification gate" is enforced over the *verdict record* and
> not over the *mission state*. A mission can reach terminal `VERIFIED` with no
> verification having run. Both gaps are cheap to close and both must close this week.
> Details and the exact repro in §5.

---

## 1. D-013 — Astro + Django + nginx · **RATIFIED WITH CONDITIONS**

### Decision record

**Decision** — Ratify the CEO's stack change with seven binding conditions, each attached to
a specific issue. Do not reverse it.

**Options considered** —
(a) Overturn and revert to the pack's React/Vite + FastAPI.
(b) Ratify unconditionally.
(c) Ratify with conditions on the parts that are genuinely load-bearing.

**Pros and cons** — (a) is defensible on a blank page and indefensible today. The nginx
layer in `feat/infra-nginx-compose` is already correct and is better SSE configuration than
most production systems ship with; the django-ninja contract package in
`apps/control-api/contracts/` is the strongest artifact in the repository. Reversing costs
two of seven build days to re-earn ground already held. (b) is not a review. (c) is the only
honest answer: the risk in this stack is real, is concentrated in exactly one place, and is
addressable for a few hours of work if it is named now rather than discovered on D6.

**Cost implications** — none. Every condition below is minutes-to-hours, not days.

**Security implications** — positive on balance. One nginx ingress concentrates TLS, headers
and the admin block; the finale profile forces `django.contrib.admin` out of
`INSTALLED_APPS` rather than defaulting it off, which is the right shape. One new item:
`USE_X_FORWARDED_HOST` (condition C7).

**Scalability implications** — irrelevant at one operator, one mission. The relevant axis is
not scale, it is *the number of concurrently open SSE streams*, which is a different problem
and is condition C1.

**Recommendation** — ratify with C1–C7.

**Final approval authority** — CTO (technical). CEO retains the stack choice itself; I am
not reversing it.

### The honest read on Astro

The recorded concern is right and is also the *least* of the problems. Astro's advantage is
shipping minimal JS for content pages; the Command Center is five interactive panels on a
live feed, so Astro is carrying layout, routing and the build and little else. That is a
**reduced return, not a risk**. Worst case the Command Center is a Vite app inside an Astro
shell, which works fine. I would not spend a day of a seven-day build reversing it.

The risk in this stack is entirely on the Django side, and specifically in holding an
infinite HTTP response open under ASGI. That has not been written down anywhere and it is
the thing most likely to kill a rehearsal.

### C1 — Sync streaming under ASGI will exhaust the thread pool. **Highest-probability live failure.**

Django serves a synchronous view under ASGI by handing it to `asgiref`'s thread pool
(default `min(32, cpu+4)`, overridable by `ASGI_THREADS`). A `StreamingHttpResponse` backed
by a **sync** generator occupies one pool thread for the entire life of the connection — and
an SSE connection never ends. The nginx SSE include sets `proxy_read_timeout 3600s`, which
is correct for the stream and means a dead browser tab can hold a pool thread for an hour.

Three browsers, a couple of reloads each during rehearsal, and the pool is gone. The failure
signature is the nastiest kind: `POST /missions/{id}/authorize` simply hangs, no exception is
raised, nothing appears in any log, and the demo stalls on stage with a healthy-looking
dashboard.

**Condition, as acceptance criteria on #13:**
- The SSE view is `async def` returning a `StreamingHttpResponse` over an **async**
  generator. Every ORM read inside it goes through `sync_to_async` per read and returns the
  thread immediately. It does not hold a thread between reads.
- A hard server-side cap on concurrent streams per mission (reject with `429`), and a
  server-side close when a heartbeat write fails.
- The stream sets `X-Accel-Buffering: no` on the response. `infrastructure/compose/nginx/includes/sse.conf`
  already asks for this in a comment; make it an acceptance criterion, because it is the one
  SSE mitigation that lives on the *control-api owner's* side of a 12.5-hour handoff and can
  therefore be tested by the person who owns the bug.

### C2 — `CONN_MAX_AGE = 60` under ASGI

`config/env.py:database_from_url` sets `CONN_MAX_AGE: 60`. Django's persistent connections
are thread-local. Pool threads serving a long stream keep a Postgres connection checked out
and idle for the stream's life; a stream that lasts an hour holds a connection for an hour.
At this scale it will not exhaust Postgres, but an idle connection held across a migration
will wedge one, and that is a bad thing to discover on D6.

**Condition:** `CONN_MAX_AGE = 0` in the finale profile. One line, on #9.

### C3 — `sequence` is gap-free, which means it is a serialization point

`MissionEvent.sequence` is documented as a *gap-free per-mission ordinal*, and replay
correctness depends on it. Gap-free under concurrent writers requires either
`SELECT max(sequence)+1 ... FOR UPDATE` or a per-mission advisory lock on every insert. With
one writer it is free. #31 (fuzzing telemetry) implies a second writer, and nobody has
written down that there is only one.

**Ruling:** there is exactly **one event writer per mission** — the orchestrator. Workers do
not write events; they report to the orchestrator, which emits. Make that explicit in #12's
description and enforce it structurally by keeping the event-emit function private to the
orchestrator module.

### C4 — High-rate fuzzing telemetry must not go through the durable event log. **(D-021)**

**Decision** — Two event channels, not one.

**Options considered** — (a) one event stream, everything durable and sequenced;
(b) two channels — durable/gap-free for mission events, sampled/non-durable for telemetry;
(c) durable everything but throttle at the UI.

**Pros and cons** — (a) is what the schema currently implies and it does not survive
contact with libFuzzer. A fuzz campaign emits progress continuously; at one row per tick you
get an event table that dwarfs the evidence it is supposed to support, a per-insert lock on
the hot path (C3), and an SSE stream the browser cannot render. (c) fixes the browser and
none of the database. (b) costs one extra event path and fixes all three; the evidence
bundle already carries a terminal `FuzzingReport`, so nothing is lost — the tick history was
never going into the report anyway.

**Cost implications** — hours, and it saves more than it costs on D4.
**Security implications** — none.
**Scalability implications** — this is the only decision in the build with any.

**Recommendation** — adopt (b): durable, gap-free, persisted mission events (state changes,
findings, baselines, patches, verdicts — tens per mission), and a separate **coalesced,
sampled at ≤2 Hz, non-durable** progress channel that is explicitly outside the gap-free
sequence and is never persisted per tick.

**Final approval authority** — CTO (technical). Acceptance criterion on #13, before #31 is
built.

### C5 — The six-connection-per-origin cap

Five islands each doing `new EventSource(...)` is five connections. HTTP/1.1 browsers cap at
six per origin; add the panel's own fetches and the dashboard deadlocks with no error.

The infra agent has already set `http2 on` on both TLS listeners, which raises the cap to
~100 streams and largely defuses this — **but only over the TLS origin.** A demo driven at
the plaintext port gets HTTP/1.1 and the cap comes back.

**Condition:** (a) the finale runbook drives `https://…:8443`, not the plaintext listener;
(b) the SSE client is **one** plain-TypeScript module owning a single `EventSource` and
publishing into a shared store (nanostores is the Astro-idiomatic answer); islands
*subscribe*. Not a per-island `useEffect`. Acceptance criteria on #67 and #19.

### C6 — Pin Astro to `output: 'static'`

Nobody has said this and it gets decided wrong by default the first time someone wants a
runtime environment variable. The Command Center is a static bundle served by nginx with the
API same-origin through the proxy; that is the right configuration and it keeps Node out of
the finale stack entirely. `output: 'server'` adds a Node process, a second thing to
supervise, and a new failure mode, for nothing. **Acceptance criterion on #67.**

### C7 — The ingress contract is half-implemented

`infrastructure/compose/nginx/includes/proxy-headers.conf` documents its half of the seam
and names the two settings Django must set. `config/settings/finale.py` sets
`SECURE_PROXY_SSL_HEADER`; **`USE_X_FORWARDED_HOST` is set nowhere in the repository.**
Without it Django builds `http://` absolute URLs behind the proxy, including the `servers`
block of the generated OpenAPI — which then poisons the frontend client (§4).

This is precisely the class of gap a 12.5-hour handoff produces: one side wrote the contract
down, the other side has not read it yet. **Condition:** set `USE_X_FORWARDED_HOST = True` in
the finale profile alongside a strict `ALLOWED_HOSTS` (which is what makes trusting a
client-supplied host safe). On #9, cross-referenced from #10.

### C8 (D-019) — No Redis, no Celery

The `CLAUDE.md` stack table says "Queue | Redis (RQ/Celery) or DB-backed", and P2-12 of the
P0 cut explicitly flags this as a CTO call that was never made. I am making it.

**Decision** — The orchestrator is a single supervised process with an in-process work queue
and a DB-persisted state machine. No Redis, no Celery, no separate worker deployment.

**Options considered** — (a) Redis + RQ/Celery per the stack table; (b) DB-backed queue with
a polling worker; (c) single in-process orchestrator.

**Pros and cons** — (a) buys durability and parallelism the demo does not want: one mission,
one machine, one operator. It costs a broker to run, a worker to supervise, a second thing
that can be down at the finale, and a whole class of "the task is queued but the worker is
dead" failures that are invisible on a dashboard. (b) is cheaper than (a) and still splits
the process. (c) has one failure mode — the process died — which is visible, and it makes
C3's single-writer rule structural rather than aspirational. The cost is that a crashed
orchestrator loses in-flight work; the state machine is persisted, so a mission resumes from
its last recorded state, which is exactly what a persistent state machine is for.

**Cost implications** — negative (removes a service). **Security implications** — positive
(one fewer network service, no broker credentials). **Scalability implications** — caps us
at one concurrent mission, which is an explicit non-goal of the MVP.

**Recommendation** — (c). Reconcile the stack table in #9.
**Final approval authority** — CTO (technical).

---

## 2. D-014 — the seven-day compression · **RATIFIED, with a recorded consequence**

The schedule is a CEO business decision and I do not overturn it. What I owe instead is a
straight answer to the question asked: *is the surviving P0 set buildable in seven days by
two people plus agents?*

**No. Not as currently scoped.**

Roughly 33 open issues sit in D1–D7 for two humans — about 2.4 issues per person per day —
and several of them are multi-day items in their own right (#15 rootless sandbox, #35 model
gateway, #36 model serving, #38 clean-worktree verification). The plan document's own line
that this is "aggressive to the point of being unlikely as specified" is correct and was
then not acted on: nothing was removed as a result of writing it.

It becomes buildable with the six reductions below. These are technical scope calls within
an already-approved cut, so they are mine to make; anything that changes what the *product
claims* is flagged for the CEO.

### 2.1 Cut #31 — fuzzing telemetry panel → `CUT`

The most expensive UI item remaining, the direct cause of the event-rate problem in C4, and
not required by any gate. A static `FuzzingReport` panel rendered once on stage completion
delivers the same thing to a judge — executions, runtime, crashes, corpus size — at a tenth
of the cost and with no live-feed failure mode. **CTO call.**

### 2.2 Merge #20 into #19

#20 (baseline and repository status in the analysis rail) is a second UI surface landing on
D3, which is gate day. Two panels on gate day is one too many. The baseline counts belong in
the D3 screen set; the "analysis rail" as a distinct surface is P1 dressing. **CTO call.**

### 2.3 Split #36, and land a replay mode on D2 — **the single most important change in this review (D-020)**

**Decision** — The model gateway gains a recorded-transcript replay mode, landing D2. Live
CPU generation remains the preferred path. The contract carries replay provenance, and that
contract change lands in #6 **today**, before the freeze.

**Options considered** —
(a) Status quo: live CPU-served small model on D5, no fallback.
(b) Gateway with replay mode on D2; live generation attempted D5; whichever is available at
    the finale runs, honestly labelled.
(c) Drop model participation to operator-supplied patches only.

**Pros and cons** — (a) is the current plan and it is the highest-variance item left. D-015
removed the GPU, so this is a quantized small code model on CPU, and the D5 kill criterion
demands *a policy-passing, compiling patch in at least 3 of 10 attempts*. That is not a safe
bet with no prompt-engineering budget, and it sits on day five of seven with the entire D6
loop gate behind it. There is **no written fallback for "the model cannot produce a
compiling patch"** — the P0 cut wrote a fallback for fuzzing and never wrote one for this.
(c) throws away P0-10 and with it the claim to be a Cyber-Reasoning System rather than a
fuzzing harness; rejected. (b) costs a fixture format and a code path, buys a deterministic
finale, and is the *exact same reasoning that produced D-008* for the rejected-patch case —
applied to the model itself, which is the larger risk. The cost is a slightly smaller claim.

**Cost implications** — a few hours on D2, against the possibility of losing D6 and D7.
**Security implications** — positive: a replayed transcript makes no network call at all.
**Scalability implications** — none.

**Honesty constraint, non-negotiable.** A replayed response is not model inference happening
in front of the judge, and must never be presented as if it were. `PatchProvenance` currently
has two values; the contract needs a third state, and the cleanest shape is to keep
`provenance = MODEL_GENERATED` and add to `ModelProvenance`:

- `replayed_from_transcript: bool`
- `captured_at: datetime | None`
- `transcript_sha256: str | None`

with a validator requiring `captured_at` and `transcript_sha256` whenever
`replayed_from_transcript` is true, and the UI and the evidence report both rendering
**"model output recorded <date>, replayed"**. Same discipline as D-008, same reason.

**This has to go into #6 before the contract is frozen.** Adding it after the freeze means
changing the seam mid-build across a twelve-hour timezone gap, which is the one thing #6
exists to prevent. It is a schema addition of three optional fields and it costs minutes
today.

**Final approval authority** — CTO for the technical shape; **CEO for the presentation
claim**, since it changes what we tell a judge. Escalated in §7.

### 2.4 Split #15 — do not let the sandbox block the first gate

#15 (rootless sandbox, egress denied, teardown) is a day's work on D2, and the D3 gate
(#21: cold start → `BASELINE_PASSED` with real ctest counts) is *behind* it. But the baseline
does not need container isolation to be correct — it needs a build and a test run. The
sandbox is a hard requirement by the time untrusted fuzzing starts, which is D4.

**Split:** #15a — subprocess isolation with a working directory jail and resource limits,
sufficient for D3. #15b — rootless Podman with `--network=none` and confirmed teardown,
required before #28 runs on D4. The `SANDBOX_POLICY` block in `settings/base.py` already has
the right shape for both. **CTO call.**

### 2.5 Reduce #43 to a `<pre>` diff

A real diff viewer is a day. The judge needs to read six lines of C with `+`/`-` colouring.
Monospace block, unified diff, two colours. If D8–11 buffer survives, upgrade it. **CTO call.**

### 2.6 Reduce #11 to two CI checks

On D1, CI earns its keep with exactly two jobs: `pytest`, and "the committed OpenAPI dump is
current" (§4.3). Lint, type-check matrices and coverage gates are cost with no gate behind
them this week. **CTO call.**

### 2.7 What I am *not* cutting, and why

- **#49 fallback recording** — stays P0, and moves earlier (§3.3).
- **#53 security checklist / #57 rehearsals** — these are the D8–11 buffer's actual purpose.
- **#64 acceptance criteria for the MVD** — it is the definition of done for #50, the D7
  gate. Without it, #50 has no pass condition and the D7 gate is a vibe. It must land on D1.
  This is the PM deliverable that never happened; the CEO seat should absorb it.

### Recorded consequence of D-014

With 2.1–2.6 taken and the reordering in §3, the P0 set is buildable, tightly. Without them,
my estimate is that D6 slips into the D8–11 buffer, the buffer is consumed by reliability
work, the unattended D7 run (#50) never happens, and **the pre-recorded fallback (#49)
becomes the actual submission.** That is survivable — it is why D-011 exists — but it should
be a chosen outcome, not a discovered one on day twelve.

---

## 3. D-015 — rented GPU cut · **RATIFIED**

This was my own seat's call under the CEO's schedule decision and it is correct: it removes
the only external dependency, the only spend, and the worst row in the risk register. It is
the cheapest risk reduction available and I would make it again. Two conditions.

### 3.1 `gpu_seconds: 0.0` must not render as a zero

`ResourceUsage.gpu_seconds` defaults to `0.0` and stays in the schema for bundle stability —
correct. But a literal `0` in a resource panel sitting next to a resource-control claim reads
to a judge as a broken counter, and it brushes the no-decorative-telemetry rule from the
other direction: a measurement that was never taken is being displayed as a measured zero.

**Condition:** the UI and the Markdown report render this field as
**"not applicable — no leased GPU (see D-015)"**, never as `0`. Acceptance criterion on #43
and #51.

### 3.2 The local model host must actually be leased and torn down

D-015 says demo scenario 5 "downgrades to lease control of the local model host". If #36
just starts a server at boot and leaves it running, scenario 5 is not downgraded, it is
**gone**, and the P0-14 teardown item has nothing to demonstrate.

**Condition:** #36 exposes the model host as a real lifecycle — started on entry to `PATCH`,
lease duration recorded, stopped at mission completion, emitting `TEARDOWN_CONFIRMED` with
`released: true`. The `TeardownPayload` schema already has `resource_kind` documented as
`sandbox | model-host`, so the contract is ready; the behaviour is not specified anywhere.

---

## 4. The critical path

The pack's stated path is **state machine → controlled reproducer → patch policy → clean
verification → live dashboard → full rehearsal.** The board's day milestones implement it as
D2 spine → D3 baseline → D4 instrumentation → D5 finding → D6 loop → D7 evidence.

The ordering is broadly right and wrong in four specific places.

### 4.1 Move #37 and #38 from D6 to D4. **The highest-value reordering on the board.**

Patch policy (#37) and clean-worktree verification (#38) are *the product*. They are also
completely independent of the model and of fuzzing: rebuild in a fresh worktree, re-run a
reproducer, run the regression suite, derive a verdict from the gate matrix. That is pure
tooling over a diff.

And the inputs already exist. The demo-target agent has committed **both patch candidates as
static files**:

```
demo/repositories/pktcfg/patches/candidate-a-correct-bounds-fix.patch
demo/repositories/pktcfg/patches/candidate-b-rejected-crash-only-fix.patch
```

So #37 and #38 can be built and proven end to end on D4 against those two files, with zero
dependency on #28, #29, #34, #35 or #36. Doing that converts D6 from *"build the loop and
hope the model cooperates"* into *"put the model in front of a loop that already produces
both verdicts."*

It also means that **if D5 fails outright, D6 still passes** with operator-supplied
candidates — which D-008 already permits and already requires us to label honestly. That is
four days of schedule risk removed for zero extra work; it is purely a sequencing choice.

**Affected issues:** #37, #38 → D4. #45 (the D6 gate) then becomes "swap in the model",
not "build everything".

### 4.2 Spike SSE on D1, do not build it on D3

#13 sits on D3 behind #6, #12 and #10. Everything visual depends on it and it carries every
unknown in §1 (C1–C4). Discovering the ASGI thread-pool behaviour on D6 is fatal;
discovering it on D1 costs an hour.

The spike is nearly free — the infra agent has already written
`infrastructure/scripts/testing/sse-stub.py` and `sse-client.py`. Carve a D1 task from #13:
a throwaway ASGI endpoint emitting a counter, driven **through nginx**, with five browser
tabs open and a sixth issuing ordinary API requests. If request six blocks, C1 is real and
we have six days to fix it instead of one.

### 4.3 Move #49 (record the fallback) to the end of D6

D-011 established the principle in plain terms — the insurance policy must not sit in the
week most likely to be compressed — and the seven-day plan then put #49 on **D7, behind the
gate it insures against**. That is precisely the failure D-011 was written to prevent, and it
survived because nobody re-read D-011 when the schedule was rebuilt.

Record whatever works at the end of D6. Re-record on D7 if D7 passes. **Affected issue:** #49.

### 4.4 Move #3 out of D12–14

#3 (competition rules on team composition and agent-authored code) is scheduled in the
submission milestone. If the answer is "agent-authored code must be disclosed" that is a
paperwork problem; if it is "not permitted", the entire seven-day plan is void and we find
out on day twelve. It is a *build* input, not a *submission* input. **Move to D1.** CEO owns
the answer.

Same argument, weaker, for #2 (the deadline): it is already on D1 and it is still open. Every
milestone in the plan is anchored to an unverified date.

### 4.5 The reordering, in one table

| Issue | From | To | Why |
|---|---|---|---|
| #37, #38 | D6 | **D4** | Independent of the model; both patch files already exist; de-risks the D6 gate by four days |
| SSE spike (carve from #13) | D3 | **D1** | Highest unknown in the stack; the stub script already exists |
| #36 (replay half, D-020) | D5 | **D2** | The only fallback for a model that will not produce a compiling patch |
| Contract change for replay provenance | — | **today, into #6** | Must land before the freeze, not after |
| #3 | D12–14 | **D1** | A wrong answer voids the plan; it is a build input |
| #49 | D7 | **end of D6** | D-011's own reasoning, reapplied |
| #15 → #15a/#15b | D2 | D2 / **D4** | The sandbox must not block the D3 gate |
| #31 | D4 | **`CUT`** | §2.1 |
| #20 | D3 | merged into #19 | §2.2 |

---

## 5. The contract seam (#6)

**Is django-ninja schemas + a committed OpenAPI dump the right seam? Yes.**

**Does it currently make a contract change break the frontend build rather than the demo?
No — and it will not, unless three specific things are added to #6's acceptance criteria.**

The schema work itself is genuinely good. `StrictSchema` with `extra="forbid"` on every
contract type is the right call and for the right reason: drift surfaces as a 422 or a
validation error rather than a silently-ignored key. The discriminated union on
`payload.kind` is exactly what makes a frontend `switch` exhaustively checked. Whoever wrote
`contracts/` understood the assignment.

### 5.1 A schema not referenced by a route does not appear in the dump

django-ninja generates `components.schemas` from the operations registered on the `NinjaAPI`
instance. It does not walk your package. `contracts/` today has **no routes at all** — there
is no `api/` app and no `config/urls.py`. Confirmed by running the checks:

```
$ DJANGO_SECRET_KEY=x DATABASE_URL=sqlite:///tmp/x.db .venv/bin/python manage.py check
...
ModuleNotFoundError: No module named 'config.urls'
```

So as of right now the dump would be empty, and once routes exist, any schema not reachable
from a response type (`EvidenceBundle`, `FindingDetail`, most payload variants) will be
missing from it with no error anywhere.

**Add to #6:** a test that reflects over every `StrictSchema` subclass in `contracts.schemas`
and `contracts.verdict` and asserts each has a component schema in the committed
`openapi.json`. An unreferenced schema becomes a test failure instead of a silent hole.

### 5.2 The event envelope — the widest part of the contract — is invisible to OpenAPI

OpenAPI can say a response is `text/event-stream`. It cannot describe the schema of the
frames inside it. So `MissionEvent` and all fourteen payload variants — the part of the
contract the entire dashboard renders, and the part most likely to drift — **will not be
typed by the generated client** unless they are deliberately forced into the schema graph.

The fix is already half-designed: `contracts/schemas/envelope.py` documents
`GET /api/v1/missions/{id}/events/replay?since_sequence=N`. Make that endpoint **mandatory**
in #6 with a response type of `Page[MissionEvent]`. That pulls the envelope and every payload
variant into `components.schemas`, and `openapi-typescript` renders the union as a
discriminated TS union.

Without it the seam is typed everywhere except the one place the two humans actually meet.
This is the most important correction to #6.

*(Aside: `nginx conf.d.finale/brahmadatta.conf` scopes SSE with
`location ~ ^/api/v1/missions/[^/]+/events/?$`, which correctly does **not** match
`/events/replay` — replay is a finite response and gets ordinary buffered proxying. That is
right, and it should stay right when the replay endpoint lands.)*

### 5.3 A committed dump only breaks the build if CI diffs it

Committing `openapi.json` by hand means the backend can change a schema, forget to
regenerate, and the frontend builds happily against stale types. The break then lands in the
demo, which is the exact outcome #6 exists to prevent.

**Add to #6, both halves:**
- Backend CI: regenerate the dump and `git diff --exit-code packages/schemas/openapi.json`.
- Frontend CI: `tsc --noEmit` against the generated types, as part of the Astro build.

With both, a schema change that is not regenerated fails backend CI, and one that is
regenerated but not consumed fails frontend CI. **These two lines are what make the answer to
the original question "yes".** They are the entire mechanism; the rest is packaging.

### 5.4 Two smaller notes

- `contracts` is a Django app, not a standalone Python package: importing `contracts.verdict`
  requires `django.setup()`, because `ninja.Schema` reads Django settings at import time
  (verified — it raises `ImproperlyConfigured` otherwise). That is fine, because the frontend
  consumes the JSON, not the Python. **Do not spend a day making it standalone.**
- C7 bites here: without `USE_X_FORWARDED_HOST`, the `servers` block in the generated OpenAPI
  will carry the wrong scheme and port behind the proxy.

---

## 6. The two hard invariants — structural, or merely intended?

### 6.1 "Repository content never reaches an external inference API"

**Partially structural. Enforced over configuration, not over egress.**

What genuinely *is* structural, and is better than the doc pack specified:
`contracts/model_policy.py` is **allowlist-shaped** — an endpoint is permitted only if its
host is demonstrably local or private, and the denylist of known providers only sharpens the
error message rather than being what makes a host illegal. `contracts/checks.py` raises a
Django `Error` (not a `Warning`), which stops `manage.py check`, `runserver` and ASGI
startup. A hosted-provider URL in `MODEL_ENDPOINTS` cannot boot the API. That is real
enforcement and it deserves credit.

What it does not do. I ran the policy against a set of hosts:

```
False  https://api.openai.com/v1
True   http://127.0.0.1:8080/v1
True   http://small-model:8080
True   https://my-llm-proxy.internal/v1
True   http://169.254.169.254/
False  https://gateway.ai.cloudflare.com/v1
False  http://localhost.evil.com/v1
```

Three problems, in order of severity:

1. **It constrains settings, not egress.** Any code that builds a URL literal, reads an env
   var not listed in `MODEL_ENDPOINTS`, respects `HTTPS_PROXY`, or is handed a URL at runtime
   is entirely outside this control. The actual call site — the model gateway, #35 — does not
   exist yet, and nothing forces it to route through `assert_local_inference_endpoint` when
   it does.
2. **"Local endpoint" is not "local inference."** `https://my-llm-proxy.internal/v1` passes.
   A relay, a LiteLLM instance pointed at a hosted provider, an Ollama with a remote backend,
   or a corporate egress proxy all satisfy the policy and still ship the repository to a
   third party. The check proves the *hostname* is inside the boundary. It proves nothing
   about where the weights are.
3. **`169.254.169.254` passes**, because `_host_is_private_ip` accepts `is_link_local`. On any
   rented VM that is the cloud metadata service — a credential-exfiltration target sitting
   inside the model-endpoint allowlist. Cheap and unambiguous fix.

Also worth stating plainly: `SANDBOX_POLICY["network"] = "deny"` protects the sandbox running
untrusted target code. **The control-api process — the one that holds the snapshot, builds
the prompt, and makes the call — has no network restriction at all.** The invariant is
guarded on the wrong process.

**To make it structural, three cheap things:**

1. Remove `is_link_local` from the accepted set in `_host_is_private_ip`. (#35)
2. The model gateway has **exactly one** egress function, which calls
   `assert_local_inference_endpoint` on **every call**, not only at startup. Add a test that
   scans the codebase for `httpx.` / `requests.` / `urllib.request` outside that module and
   fails on a hit. That is what turns "one audited egress path" from a claim into a check. (#35)
3. Put the control-api container on a compose network with **no default route**, with
   explicit access to postgres and the model host only. Then the invariant is enforced by the
   kernel rather than by string matching, and the claim becomes unconditional. (#11 / #10;
   roughly half an hour of compose config.)

**Until (3) ships, the honest wording for the evidence bundle and the slides is:**
*"enforced by startup validation and a single audited egress path"* — **not** *"the system
cannot reach the internet."* Do not make the stronger claim to a judge before the network is
actually closed.

### 6.2 "No code path lets model confidence advance a mission past a verification gate"

**Structural for the verdict. Conventional for the mission. That gap is real and it matters.**

The verdict half is done properly, and I want to be clear that it is the best security
engineering in the repository. `derive_verdict(gates: GateMatrix) -> Verdict` accepts exactly
one argument and there is no parameter a confidence value could be passed as. `GateStatus` is
a four-valued enum with no numeric field, so there is nothing for a threshold to compare
against. `extra="forbid"` blocks smuggling a field through `**payload`.
`VerificationRecord`'s validator re-derives the verdict from the gates and refuses to
construct a record that disagrees. Verified:

```
confidence-like fields reachable from GateMatrix: NONE
regression FAIL -> REJECTED
```

**The gap: the state machine and the verdict derivation never meet.**
`assert_transition(current, target, authorization, now, snapshot_sha256)` takes no
`VerificationRecord` and no `GateMatrix`. So:

```
EXPORTING -> VERIFIED with NO verification record and NO gate matrix: ALLOWED
```

A mission can reach terminal `MissionState.VERIFIED` — the state that drives
`MissionPosture.VERIFIED`, which is what the Brahmadatta Core displays and what a judge reads
off the screen — with no verification having occurred at all. The gate matrix constrains the
*record*; nothing constrains the *mission*. Today the two are held together by the
orchestrator (#12) doing the right thing, which is exactly the "by convention" the invariant
is supposed to rule out. And #12 has not been written yet, so there is still time.

The same applies, at lower stakes, to `VERIFY → EXPORTING`: nothing requires that a
verification actually ran before the evidence bundle is written.

**The fix, which must land with #12 and not after:** `assert_transition` gains a required
`verification: VerificationRecord | None` parameter. Entering `VERIFIED`, `REJECTED` or
`HUMAN_REVIEW` requires a record whose `verdict` maps to the target state and whose
`mission_id` matches. Required positional, no default — the identical discipline that
`authorization` already has, in the same file, written by the same author three functions
earlier. The docstring there says it well: *"the parameter is required and `None` is a
refusal, not a skip."* Apply that sentence to verification and the invariant is structural on
both axes.

**One smaller thing, and it is on stage.** `POSTURE_BY_STATE` maps `CANCELLED →
MissionPosture.FAILED`. A mission the operator deliberately cancelled will display as
`FAILED` on the Core during a live demo. Cancellation is not failure, and showing one as the
other is a small piece of untrue telemetry in the most visible element of the product. Add a
`CANCELLED` posture. (#7 / #19.)

---

## 7. Ranked: what breaks first

| # | What breaks | Why | Mitigation | Owner |
|---|---|---|---|---|
| 1 | **The D6 loop gate (#45)** — the CPU-served model cannot produce a policy-passing, compiling patch in 3 of 10 attempts | D-015 removed the GPU; the P0 cut wrote a fallback for fuzzing and never wrote one for the model; it sits on day 5 of 7 with two gates behind it | D-020: replay-mode gateway on **D2**; replay provenance into #6 **today**; #37/#38 moved to D4 so the loop is proven before the model arrives | CTO / control-api |
| 2 | **SSE wedges the API under ASGI** — thread-pool exhaustion, no error in any log | Sync streaming holds a pool thread for the connection's life; `proxy_read_timeout 3600s` makes a dead tab expensive | C1–C2: async generator view, `sync_to_async` per read, concurrent-stream cap, `CONN_MAX_AGE=0`, **D1 spike** using the existing `sse-stub.py` | control-api + infra |
| 3 | **The D3 baseline gate (#21) slips** — #12, #14 and #15 all land on D2 | The rootless sandbox is a day's work and the first gate is behind it, though the baseline does not need containers | §2.4: split #15 into 15a (subprocess jail, D2) and 15b (rootless + `--network=none`, D4) | eng / infra |
| 4 | **The contract drifts and the two humans meet on D4 with mismatched types** | The dump is committed by hand; nothing regenerates or diffs it; the event envelope is not in OpenAPI at all | §5.1–5.3: schema-coverage test, mandatory `/events/replay` returning `Page[MissionEvent]`, CI `git diff --exit-code` + `tsc --noEmit` | both, on #6 |
| 5 | **The event log and the browser drown in fuzzing telemetry** | #31 emits per-tick events into a gap-free, serialized, durable log | §2.1 cut #31; D-021 two-channel design as an acceptance criterion on #13 **before** #31 would have been built | CTO / control-api |
| 6 | **A mission displays `VERIFIED` without verification**, or repository content leaves via an unaudited path | §6.1 and §6.2 — both invariants are one gap short of structural | §6.1 (1)(2)(3) on #35/#11; §6.2 required `verification` parameter, landing **with #12** | cybersecurity review on the PR |
| 7 | **#2 or #3 turn out to be wrong** — wrong deadline, or agent-authored code disallowed | Every milestone is anchored to an unverified date; #3 is scheduled in the submission milestone, twelve days after it can still change anything | No technical mitigation exists. Move #3 to D1. Both answered by the CEO **today** | **CEO** |
| 8 | **The D7 unattended run (#50) never happens** and the buffer is eaten by reliability work | 33 issues, two people, no slack | §2.1–2.6; and #49 recorded at the **end of D6** so there is always something to show | eng |

---

## 8. Decision records to fold into `.project/decisions.md`

The orchestrator should append these; I have not edited the log, because four agents are
live and would collide.

- **D-019** — Queue: single supervised orchestrator process, no Redis, no Celery. §1 C8.
  *Authority: CTO (technical). Closes P2-12, which the P0 cut left explicitly open for me.*
- **D-020** — Model gateway replay mode, landing D2; `ModelProvenance` gains
  `replayed_from_transcript` / `captured_at` / `transcript_sha256`; a replayed response is
  labelled as replayed everywhere it appears. §2.3.
  *Authority: CTO for the technical shape; **CEO for the presentation claim.***
- **D-021** — Two event channels: durable/gap-free mission events, and sampled/non-durable
  telemetry outside the sequence. §1 C4.
  *Authority: CTO (technical).*
- **D-022** — Ratification record for D-013 (with conditions C1–C8), D-014 (with the recorded
  consequence in §2), D-015 (with conditions 3.1–3.2). This document.
  *Authority: CTO (technical), except the D-014 schedule itself, which remains the CEO's.*

---

## 9. What I am escalating, not deciding

| Item | Why it is not mine | Owner |
|---|---|---|
| The seven-day build target itself | Business/scope decision. I have recorded the technical consequence in §2 rather than overturning it. | CEO |
| #2 — the actual AI Kavach deadline | Still open on D1. Everything is anchored to it. | CEO |
| #3 — rules on agent-authored code | A wrong assumption is disqualifying; it belongs on D1, not D12. | CEO |
| The presentation claim for a replayed model response (D-020) | Changes what we tell a judge. The technical shape is mine; the claim is not. | CEO |
| #64 — acceptance criteria for the minimum viable demo | It is the pass condition for the D7 gate (#50) and the PM seat never ran. | CEO / PM |
| Whether the reduced gate matrix is acceptable for the finale | D-009 already rules on disclosure; the `cybersecurity` seat holds the veto on the mechanism. | cybersecurity |

---

*This review does not edit `.project/decisions.md`, does not modify any other role's files,
and does not touch code. Every behaviour asserted in §5 and §6 was executed against the
working tree at `ad2ef2b` and the output is quoted verbatim.*
