# Condition Register

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Document | Company-workflow phase 5 — the register of every review condition and where it landed |
| Author | `engineering-manager` seat |
| Date | 2026-08-07 (D1) |
| Covers | `05-cto-technical-review.md`, the CTO ruling round on PR #79, `06-architecture-spec.md`, `08-security-review.md`, `09-product-review.md`, `07-task-breakdown-audit.md` §7 |
| Board state read at | 2026-08-07, `origin/main` = `ff0a11e`, 76 issues (70 open) |

---

## 0. Why this exists

Five review gates ran on D1 and produced about a hundred numbered conditions between them.
Some were folded into issues as they were written. Most were not — they lived only in review
documents, and nobody reads a review document while implementing.

A finding that is not an acceptance criterion on an issue somebody owns is a finding that did
not happen. This register is the audit: every condition, its source, the issue that owns it,
and whether it is actually there.

**Status vocabulary, used consistently below:**

| Status | Meaning |
|---|---|
| **Landed (prior)** | Already an acceptance criterion on an issue, or already fixed in code on `main`, before this pass |
| **Landed (this pass)** | Folded into an issue as an acceptance criterion today, by this document's author |
| **Filed (this pass)** | Had no owning issue; one was created today |
| **Superseded** | Overruled by a later decision record. Recorded so nobody implements the withdrawn version |
| **Escalated** | Not the engineering-manager's to decide. Named owner in §10 |
| **Not landed** | Still nowhere. Named in §10 with the reason |

Everything marked *landed* or *filed* in this document was executed with `gh` against
`Mahatav/brahmadatta-ai` on 2026-08-07 and can be checked on the issue. Nothing here describes
an intention.

---

## 1. CTO technical review — `05-cto-technical-review.md`

### 1.1 The eight conditions on D-013

| ID | What it requires | Issue | Status |
|---|---|---|---|
| **C1** | SSE view is `async def` over an async generator; `sync_to_async` per ORM read, never holding an `asgiref` pool thread between reads; hard per-mission concurrent-stream cap rejecting with `429`; server-side close on heartbeat write failure; `X-Accel-Buffering: no` on the response | **#13** | **Landed (this pass)** — 5 criteria |
| **C2** | `CONN_MAX_AGE = 0` in the finale profile | **#9** | **Landed (this pass)**. The CI guard already exists (`tests/architecture/test_ingress_contract.py`) and skips because `apps/control-api/` is not yet on `main` |
| **C3** | Exactly one event writer per mission — the orchestrator; event-emit function private to the orchestrator module | **#12** | **Landed (this pass)** |
| **C4** *(D-021)* | Two event channels: durable/gap-free mission events plus a sampled non-durable telemetry channel | **#13** | **Superseded** by D-027. The CTO withdrew this himself on PR #79: throttle-at-source at ≤1 event/5 s is ~480 rows for a 40-minute campaign and keeps the whole progress history replayable on reconnect, which a non-durable channel would have thrown away. **The replacement is landed on #13 this pass** |
| **C5(a)** | The finale runbook drives `https://…:8443`, not the plaintext listener, so HTTP/2 raises the six-connection cap | — | **Superseded** by #92: the finale runs on plain `http://localhost` to avoid a certificate interstitial in front of a judge. **Consequence, recorded here because nobody has written it down: the browser now negotiates HTTP/1.1 and the six-connections-per-origin cap is back.** C5(b) is no longer an optimisation; it is the only mitigation left |
| **C5(b)** | One plain-TypeScript module owning a single `EventSource`, publishing into a shared store; islands subscribe | **#67**, **#19** | **Landed (prior, weakly)** — both issues already said "one SSE connection shared across islands". **Strengthened this pass** on both, with the #92 consequence stated at the criterion |
| **C6** | Pin Astro `output: 'static'` | **#67** | **Landed (this pass)** |
| **C7** | `USE_X_FORWARDED_HOST = True` in the finale profile with a strict `ALLOWED_HOSTS` | **#9** | **Landed (this pass)**. The security review re-confirmed the owner as #9 in §12.7 |
| **C8** *(D-019)* | No Redis, no Celery, single supervised orchestrator with an in-process work queue | **#9** | **Half superseded** by DR-A / D-024. The Redis/Celery half stands; the in-process-queue half is replaced by a Postgres job table claimed with `SELECT … FOR UPDATE SKIP LOCKED`, because an in-process queue loses a 40-minute fuzz campaign on restart, which defeats the two-timezone protocol. **The surviving half is landed on #9 this pass** as a stack-table reconciliation |

### 1.2 D-015 conditions

| ID | What it requires | Issue | Status |
|---|---|---|---|
| **3.1** | `ResourceUsage.gpu_seconds` renders as "not applicable — no leased GPU (see D-015)", never as `0` | **#43**, **#51** | **Landed (this pass)** on both |
| **3.2** | The model host is a real lease lifecycle — started on entry to `PATCH`, duration recorded, stopped at completion, `TEARDOWN_CONFIRMED` with `released: true` | **#36** | **Landed (this pass)** |

### 1.3 The six scope reductions (§2)

| § | Reduction | Status |
|---|---|---|
| 2.1 | Cut #31, the fuzzing telemetry panel | **Landed (prior)** — #31 is in the `CUT` milestone |
| 2.2 | Merge #20 into #19 | **Half landed.** #20 was moved to `CUT` but its *content* — baseline and repository status — was never added to #19, so it was cut rather than merged. **#19's criterion added this pass**, and #21's dangling dependency on #20 repointed to #19 |
| 2.3 | Split #36; replay mode lands D2 (D-020) | **Landed (prior)** — #82 exists, CEO-approved |
| 2.4 | Split #15 into 15a/15b | **Landed (prior)** — #81 is the D2 subprocess half; #15 is the D4 container half |
| 2.5 | Reduce #43 to a `<pre>` unified diff | **Landed (this pass)** — #43's body still asked for syntax highlighting |
| 2.6 | Reduce #11 to two CI checks | **Landed (prior)** — `.github/workflows/ci.yml` has exactly `pytest` and `openapi-contract`, with the cut documented in the file header |

### 1.4 Critical-path reordering (§4)

| Move | Status |
|---|---|
| #37, #38 → D4 | **Landed (prior)** for the milestone; **the dependency edges were not moved with them.** #37 still depended on #35 (D5) and #38 on #29 (D5) — both fixed this pass, see §8 |
| SSE spike on D1, carved from #13 | **Not landed.** No D1 spike issue exists. See §10 |
| #36 replay half → D2 | **Landed (prior)** — #82 |
| Replay provenance into #6 today | **Landed (this pass)** on #6. It was on #82 as a promise ("going into #6 before the freeze") but not on #6 itself, which is the issue that closes |
| #3 → D1 | **Landed (prior)** — #3 closed on D1 |
| #49 → end of D6 | **Superseded** by D-028, which is better: three dated captures at D5, D6 and D7. **Landed (this pass)** on #49, together with removing its dependency on the D6 gate it insures against |
| #15 → 15a/15b | **Landed (prior)** |
| #31 → CUT, #20 → merged | See §1.3 |

### 1.5 The contract seam (§5)

| § | What it requires | Issue | Status |
|---|---|---|---|
| 5.1 | Test reflecting over every `StrictSchema` subclass, asserting each has a component schema in the committed dump | **#6** | **Landed (this pass)** |
| 5.2 | `GET …/events/replay?since_sequence=N` mandatory, response `Page[MissionEvent]` — the only way the event envelope enters OpenAPI | **#6** | **Landed (this pass)**. The CTO called this "the most important correction to #6" |
| 5.3a | Backend CI regenerates the dump and `git diff --exit-code` | — | **Landed (prior)** — `.github/workflows/ci.yml` job `openapi-contract` |
| 5.3b | Frontend CI `tsc --noEmit` against the generated types | **#6**, **#67** | **Landed (this pass)** on both |

### 1.6 The two hard invariants (§6)

| Item | Issue | Status |
|---|---|---|
| §6.1(1) — remove `is_link_local` from the accepted host set | **#93** | **Filed (this pass)** as SEC-02. #78 carries the criterion but it is **not satisfied**; all ten known bypasses still pass |
| §6.1(2) — one egress function calling `assert_local_inference_endpoint` on every call, plus an AST test asserting the HTTP-client set is exactly `{gateway.client}` | **#35** | **Landed (this pass)** |
| §6.1(3) — control-api on a network with no default route | **#78** | **Landed and verified (prior)**. SEC-01 is closed; verified twice from inside the running container by `cybersecurity` |
| §6.2 — `assert_transition` gains a required `verification` parameter | **#77** | **Landed (prior)** |
| §6.2 — `POSTURE_BY_STATE` must not map `CANCELLED → FAILED` | **#77**, **#19** | **Landed (prior)** on #77; **added to #19 this pass** because it is a rendering rule as much as a mapping |

---

## 2. CTO ruling round on PR #79

Nine further conditions, posted as a comment on the architecture-spec PR. The CTO's own warning
was that if only the `[Δ]` items were folded in, "C1, C2, C4, C5, C7 and C9 are lost, and those
are the ones that make the invariants structural."

| ID | What it requires | Issue | Status |
|---|---|---|---|
| **C1** | No `PatchCandidate` attached after the first `VerificationRecord` is written — the candidate set is frozen before `VERIFY`. Test `test_cannot_add_candidate_after_verification_starts` | **#12**, **#80** | **Landed (this pass)** on both. This is the hole in fan-out: without it, "add one more candidate and re-verify" is generate-until-pass with no transition-table change for a reviewer to see |
| **C2** | The verdict string carries the candidate denominator: `VERIFIED — 3 of 5 gates ran · 1 of 2 candidates verified`; `EvidenceBundle` records candidate count and verdict distribution | **#42**, **#51**, **#80** | **Landed (this pass)** on all three |
| **C3** | Where two candidates both verify, the bundle names the recommended one | **#51** | **Landed (this pass)** |
| **C4** | nginx is the only container on a routable network | **#11** | **Landed and verified (prior)** — PR #91. `tests/architecture/test_compose_topology.py` is the static guard |
| **C5** | `gateway/` must not be importable from the ASGI process; AST test over `config.urls` and the ninja router | — | **Landed (prior)** — `tests/architecture/test_import_direction.py` exists on `main` and is collected by CI |
| **C6** | `assert_terminal_verdict` takes `Sequence[VerificationRecord]`, not `Sequence[Verdict]` | **#77** | **Landed (this pass)**. A caller passing `[Verdict.VERIFIED]` bypasses the strongest validator in the repository |
| **C7** | `sequence` allocation inside the transaction holding `SELECT … FOR UPDATE` on the mission row | **#12**, **#13** | **Landed (this pass)** on both |
| **C8** | Judge-facing wording is "hash-manifested, tamper-evident against the manifest supplied with the bundle" — never "signed", never "tamper-proof". A hash is not a signature | **#51**, **#53** | **Landed (this pass)** on both |
| **C9** | Import-direction test: `contracts/` imports nothing from `orchestrator/`, `gateway/` or `evidence/`; `gateway/` imports nothing from `orchestrator/` | **#12** | **Partly landed (prior)** — `test_import_direction.py` covers api→gateway. **The remaining two directions added to #12 this pass** |
| **ErrorCode** | `SANDBOX_UNAVAILABLE` and `JOB_TIMED_OUT` into #6 before the freeze — and nothing else | **#6** | **Landed (this pass)** |
| **D-020 contract** | `ModelProvenance` gains `replayed_from_transcript`, `captured_at`, `transcript_sha256` in the same #6 change | **#6** | **Landed (this pass)** |

---

## 3. Architecture spec — the fourteen `[Δ]` items

`06-architecture-spec.md` §9 assigns these to the engineering-manager: *"Fold the `[Δ]` items
into #6, #11, #12, #15, #37, #38, #42, #51 as acceptance criteria. There are fourteen."*

| # | `[Δ]` | What it requires | Issue | Status |
|---|---|---|---|---|
| 1 | `#12` | `paused_from` on the mission row plus `assert_resume`; `PAUSED → X` legal only when `X == paused_from` | **#12** | **Landed (this pass)** |
| 2 | `#12/#38` | R2 — a terminal verdict requires a verification record that produces it | **#77** | **Landed (prior)** |
| 3 | `#15` | R3 — `CANCELLING → CANCELLED` requires a teardown receipt; without one it is `CANCELLING → FAILED` | **#15** | **Landed (this pass)** |
| 4 | `#12` | `derive_mission_outcome(verdicts) -> MissionState` | **#80** | **Landed (prior)** |
| 5 | `#12/#35` | `run_worker` and `run_orchestrator` must not set `requires_system_checks = []` | **#12** | **Landed (this pass)** |
| 6 | `#6` | `MissionPolicy.max_context_bytes`, default 32768 | **#6** | **Landed (this pass)** |
| 7 | `#12` | `assert_terminal_verdict`, called from `assert_transition` | **#77** | **Landed (prior)** |
| 8 | `#38` | The verifier is provenance-blind *by signature* — `run_verification` does not take a `PatchCandidate`. Test `test_verifier_is_provenance_blind` | **#38** | **Landed (this pass)**. #38 said "no code path lets confidence influence it"; the signature constraint is what makes that structural rather than reviewed |
| 9 | `#42` | `tests/security/test_no_score_on_verdict_path.py`, using the `iter_nested_field_names` helper that already ships | **#42** | **Landed (this pass)** |
| 10 | `#37` | Patch policy evaluated from diff text before a candidate is built; a failing candidate never reaches `run_verification` | **#37** | **Landed (prior)** |
| 11 | `#42` | `GateResult` validator: `NOT_RUN` or `ERROR` with an empty `detail` raises | **#42** | **Landed (this pass)** |
| 12 | `#51` | `EvidenceBundle.gates_not_run` derived, not hand-set | **#51** | **Landed (this pass)** |
| 13 | `#6` | `ErrorCode.SANDBOX_UNAVAILABLE` | **#6** | **Landed (this pass)**, together with `JOB_TIMED_OUT` |
| 14 | `#11` | The model host runs with a hard `mem_limit` in compose | **#36** | **Landed (this pass)** — **rehomed**, because #11 is closed. An unbounded model process that OOMs the host takes Postgres with it |

Six of the fourteen were already carried by #77, #80 and #37. Eight were not, and are now.

---

## 4. Architecture spec §8 — the thirteen disagreements

| § | Finding | Issue | Status |
|---|---|---|---|
| 8.1 | The D6 gate is not expressible in the state machine | **#80** | **Landed (prior)** |
| 8.2 | The egress model protects the wrong process | **#78** | **Landed (prior)**, and the topology half is fixed and verified |
| 8.3 | `assert_transition` permits `EXPORTING → VERIFIED` against an empty database | **#77** | **Landed (prior)** |
| 8.4 | `services/` is over-decomposed — DR-C | — | Ratified. The actionable half is PR #79 C9's import test; see §2 |
| 8.5 | The D3 kill criterion names `BASELINE_PASSED`, which is not and should not be a `MissionState` | **#21** | **Landed (this pass)** — the observable is spelled out on the gate issue. Whoever checks the gate on 2026-08-09 would otherwise be hunting for a string that will not be on any screen |
| 8.6 | `gates_not_run` can contradict the matrices beside it | **#51** | **Landed (this pass)** — same as `[Δ #51]` |
| 8.7 | `GateResult.detail` defaults to empty for `NOT_RUN` | **#42** | **Landed (this pass)** — same as `[Δ #42]` |
| 8.8 | P2-12 left open — the queue question | **#9** | **Closed** by DR-A/D-024; the stack-table reconciliation is landed on #9 |
| 8.9 | `TRIAGE`/`ANALYZE` runs and finds nothing, undisclosed | **#51** | **Landed (this pass)** — disclosure belongs in the bundle, not only in a `LOG` line |
| 8.10 | Build the harness-direct path first, invokable with a known crashing input | **#83** | **Landed (prior)**, and its dependency inversion fixed this pass |
| 8.11 | Per-stage caps in `29-performance-requirements.md` will be read as requirements | **#54** | **Landed (this pass)** — all deadlines come from `MissionPolicy`, never from that document |
| 8.12 | `GPU_LIMIT_EXCEEDED` / `gpu_seconds` retained for a client that does not exist | — | Disagreement recorded; **no change requested** by the author and none made |
| 8.13 | The bundle must be exportable from every state, including `FAILED` and `HUMAN_REVIEW` | **#51** | **Landed (this pass)**. The CTO called this "the most valuable paragraph in the document" and said it should be an acceptance criterion, not a paragraph |

---

## 5. Security review — `08-security-review.md`

Three claims in the brief that commissioned this register were wrong, and the corrections
matter, so they are stated first:

- **SEC-R1 was not "checked and did not hold."** It is marked `REQUIRED` and is one of two
  requirements the reviewer says must land. It has since been **satisfied in code** — see below.
- **SEC-02 is not unassigned.** It was assigned to #78; the review's instruction is to *re-file*
  it with its own owner and milestone before #78 closes. No milestone is named in the document.
- **The unassigned set is larger than the six named.** SEC-09, SEC-10, SEC-11, SEC-12, SEC-13,
  SEC-R1, SEC-R2, SEC-R3 and SEC-06-R also had no issue.

| ID | Severity | Issue | Status |
|---|---|---|---|
| **SEC-01** | Critical | #78 | **Closed and verified.** No default route in the container's routing table; `Network is unreachable` from the kernel, confirmed twice from inside the running container |
| **SEC-02** | Medium *(downgraded from High)* | **#93** | **Filed (this pass)** — D4, `raunak · india`. All ten known bypasses still pass. #78's second acceptance box is **not** ticked and must not be, and a comment saying so is on #78 |
| **SEC-03** | High | **#94** | **Filed (this pass)** — D3, `mahatav · kelowna`. The highest-severity open finding, and it had no owner |
| **SEC-04** | Medium | **#95** | **Filed (this pass)** — D3. Confirmed still open on `main`: `nginx.conf:65` is `client_max_body_size 0`, and every `tmpfs: - /tmp` is unsized |
| **SEC-05** | Medium | **#96** | **Filed (this pass)** — D3 |
| **SEC-06** | Medium | — | **Fixed on `main`.** D-037's `.gitignore` rewrite landed |
| **SEC-06-R** | Low | — | **Fixed on `main`.** The residual is closed: `.gitignore` now re-includes the authored fixtures by **exact path**, never by wildcard, and the file carries the reasoning. Verified in the working tree |
| **SEC-07** | Medium | **#77** | **Landed (this pass)** — `mission_id` as a required positional, and `assert_verdict_is_evidenced` refusing a foreign record rather than filtering it. #77 existed but carried no criterion for this |
| **SEC-08** | Low | **#97** | **Filed (this pass)** — D3 |
| **SEC-09** | Low | — | **Fixed on `main`.** The `DELIBERATELY VULNERABLE` banner is in `demo/repositories/pktcfg/include/pktcfg/pktcfg.h`. Verified |
| **SEC-10** | Low *(blocks publication)* | **#99** | **Filed (this pass)** — D9, `needs:ceo`. Confirmed absent from `main`: no root `SECURITY.md`, no `LICENSE`, no `demo/repositories/README.md` |
| **SEC-11** | Info | — | Not a defect. No action |
| **SEC-12** | Medium | — | **Fixed on `main`.** `tests/architecture/` is now collected — `.github/workflows/ci.yml` has an explicit `Architecture tests` step running `pytest tests/ -q` |
| **SEC-13** | Medium | — | **Fixed on `main`.** `tests/architecture/test_compose_topology.py` exists and asserts the members of every non-`internal` network against a declared allowlist |
| **SEC-14** | Low | **#98** | **Filed (this pass)** — D3. Confirmed still open: `control-api.Dockerfile:64` is `--forwarded-allow-ips "*"` in the `dev` target, eight lines above the correct pattern |
| **SEC-R1** | Required | — | **Satisfied on `main`** by the `Architecture tests` CI step |
| **SEC-R2** | Required | — | **Satisfied on `main`** by `test_compose_topology.py` |
| **SEC-R3** | Recommended | **#53**, **#57** | **Landed (this pass)** on both — run `finale-egress-evidence.sh` at each rehearsal and once before submission, recorded in the runbook |
| **SEC-P3** | Requirement | **#53** | **Landed (this pass)** — CI has a secrets guard and no dependency audit job, so the checklist item cannot be ticked from a manual run |

### The eight isolation conditions

`cybersecurity` accepted the substitution of `--network none` plus a non-root user for rootless
Podman, did **not** exercise its veto, and bound the acceptance to eight conditions. All eight
are now acceptance criteria on **#15**, added this pass. Condition 4 (Docker socket never
bind-mounted, asserted by a test) is already satisfied in code and is now also collected by CI,
which is what the reviewer said condition 4 required.

---

## 6. Product review — `09-product-review.md`

The eight conditions on PR #70 name **no GitHub issue at all** — they attach to the PR. They
have been folded in by surface.

| ID | Condition | Issue | Status |
|---|---|---|---|
| **C1** | Step 9 has no surface on the successful path. Persistent bottom-strip resource chip, `[ — RELEASE PENDING ]` until every `TEARDOWN_CONFIRMED` has `released = true`. Never an absence | **#19** | **Landed (this pass)**. The bundle half is on #51; the mechanism is #72 |
| **C2** | Step 4's two evidence values have no home. Finding row gains `minimized 22 B · replay 5/5 from clean`; em dash before minimization, never `0/0` | **#19** | **Landed (this pass)** |
| **C3** | The two-candidate compare renders at overlay width, two 652 px columns, not in the 608 px centre panel | **#43** | **Landed (this pass)** — D-024 |
| **C4** | Compare columns carry the provenance chip; `[ × PROVENANCE MISSING ]` and a suppressed body if absent | **#43** | **Landed (this pass)** |
| **C5** | The Core's spoke order contradicts the state machine | — | **Escalated.** CTO arbitrates, per architecture §2.6, then CEO if `CLAUDE.md` needs amending. Not folded anywhere on purpose — it is not the engineering-manager's to rule on, and it must be settled before the Core is built because spoke order is baked into SVG geometry with fixed 60° arcs |
| **C6** | `NOT_RUN` renders neutral with its reason inline, not amber. The design system wins over architecture §5.4 | **#42** | **Landed (this pass)**, with the contradiction stated at the criterion so nobody implements the spec version |
| **C7** | Four specified items are not P0 — move to `CUT` and record in §11's table | — | **Not landed.** It is an edit to `04-design-system.md` §11, not to an issue, and that file belongs to the `ui-ux-designer` seat and is unmerged on PR #70. Named in §10 |
| **C8** | ANALYZE row reads `no static analyzers in this build`, not `semgrep — not run` | **#51** | **Landed (this pass)** |

### Rulings D-024 … D-030

All seven exist in the product review. Where each one has an issue consequence:

| ID | Consequence | Issue | Status |
|---|---|---|---|
| D-024 | Two-candidate compare is guaranteed and renders on the overlay | #43 | **Landed (this pass)** |
| D-025 | Em dash extends to `report.md`; `report.json` uses `null` plus `*_reason`, never a glyph; a third state, *not applicable* | #51, #42 | **Landed (this pass)** |
| D-026 | Two budget profiles, 28:00 unattended and 20:00 narrated; >25% overrun is a gate failure | #64, #50 | **Landed (prior)** — #64's body is the full definition |
| D-027 *(PM)* | Eight-case benchmark set on `pktcfg`; every metric row relabelled "target — not measured" | #61 | **Landed (prior)** — #61's body is the full definition |
| D-028 | #49 becomes three dated captures, D5/D6/D7, with the D6 capture the fallback of record | #49 | **Landed (this pass)** |
| D-029 | The minimized reproducer is emitted at export into `artifacts/regression/`, never added to the target's committed CTest suite | #41 | **Landed (prior)** — #41 is the standing prohibition, in `CUT` |
| D-030 | P1-1 (`git bisect`) stays in `CUT`; the seeded git history is authored on D1 regardless | #63, #5 | **Escalated** — CEO arbitrates on #63 |

**Numbering collision, unresolved and not mine.** `.project/decisions.md` already carries
D-019…D-023 from the `ui-ux-designer` seat. The CTO review's §8 proposes a *different*
D-019…D-022, and the product review's records start at D-024. The orchestrator owns the log and
owns that call. This register cites decision records by the number the source document used,
which is the only thing it can honestly do until the collision is resolved.

---

## 7. Task-breakdown audit §7 — the unapplied worklist

The audit was written by this seat in a session with no shell. §7 was "complete, unapplied".
Executed now, item by item, with the validity check the audit itself demanded.

| Item | What it asked for | Result |
|---|---|---|
| **A** | Reconcile issue numbers against the board | **Done.** All 76 issues read at `ff0a11e` — 70 open, 41 of them inside D1–D7. Everything below keys off that dump |
| **B** | Close #8 as answered by D-017/D-018 | **Already done.** #8 is closed. No action |
| **C1** | File: sandbox teardown and orphan reaper | **Already exists** as #72 — moved D2 → D4 this pass, because it depended on #15 at D4 and was therefore unstartable on the day it was scheduled |
| **C2** | File: teardown confirmed in the UI and in the evidence bundle | **Deliberately not filed as a new issue.** The same requirement is PM-C1, and it now sits as acceptance criteria on **#19** (the chip) and **#51** (the bundle record), with **#72** owning the mechanism. A third issue over the same three surfaces would be a duplicate, and duplicates cost more than gaps here |
| **C3** | File: crash-only bad-patch fixture | **Already shipped.** #74 committed both `candidate-a-correct-bounds-fix.patch` and `candidate-b-rejected-crash-only-fix.patch`. This is why #37 and #38 are buildable on D4 |
| **C4** | File: recorded SSE event fixture and replay command — *"file this one first"* | **Already exists** as #71 |
| **C5** | File: rolling fallback capture rig | **Superseded** by D-028, which is a better version of the same idea; landed on **#49** this pass |
| **C6** | File: model artifact fetch and CPU warm-up (L1) | **Already exists** as #73 — its dependency inversion on #35 fixed this pass |
| **D** | Move: exporter D7 → D5; fallback rolling from D5; bad-patch fixture D6 → D1 | **Done.** #51 moved D7 → D5 with the reasoning on the issue. Fallback handled by D-028 on #49. Fixture shipped in #74 |
| **E** | Split the five oversized items into sixteen issues | **Deliberately not done.** Three of the five are already split (#15→#81, #36→#82, D7→#50/#51/#49) and the D3 integration is split across #16/#17/#21. Creating eleven more issues on D1 of a seven-day build adds board churn, not throughput — the constraint is shift capacity, not task granularity. Recorded as a judgement call, not an oversight |
| **F** | Verify `parallel-safe` against §3's collision table | **Done.** One violation found and fixed: **#14** (Django models and migrations, D2) carried `parallel-safe` while touching `**/migrations/` — the audit's own worst collision surface — concurrently with #12, #77 and #80. Label removed, reasoning on the issue. #55 is the only remaining `parallel-safe` issue in the seven-day plan and it does not collide |
| **G** | Verify dependencies: no cycle, no edge from an earlier milestone to a later one | **Done. No cycles. Ten inversions found and all ten fixed** — see §8 |
| **H** | Label the long-running six and add the three body lines | **Partly done.** L1 = #73 (exists, D4). L2 = #28 — `handoff:to-raunak` added this pass with the three lines specified in a comment. L5 = #50. L6 is inside #15. **L3 — the ten-attempt patch-generation run — has no issue of its own** and is the D6 supporting threshold; named in §10 |

---

## 8. Dependency inversions found and repaired

Ten issues depended on work scheduled *after* them. Five of the ten exist because the CTO's
§4.1 reordering was applied to milestones and never to the `Depends on` blocks — the dates
moved and the edges did not, which is exactly the failure mode a dependency graph exists to
catch.

| Issue | Was | Now | Why |
|---|---|---|---|
| **#16** (D3) | → #15 (D4) | → **#81** | The D3 gate was behind a D4 issue. #81 is the split the CTO made for this reason |
| **#21** (D3 gate) | → #20 (CUT) | → **#19** | #20 is cut; its content merges into #19 per CTO §2.2 |
| **#32** (D4) | → #29 (D5) | → **#71** | Evidence models are shaped by the contract, not by a crash. Build them against the event fixture |
| **#37** (D4) | → #35 (D5) | *(removed)* | CTO §4.1: patch policy is pure tooling over diff text, provable today against the two committed patch files |
| **#38** (D4) | → #29 (D5) | *(removed)* | Same ruling. #74 ships the reproducer and both candidates as committed files |
| **#49** (D5) | → #45 (D6 gate) | *(removed)* | The insurance policy sat behind the gate it insures against — precisely what D-011 was written to prevent |
| **#67** (D1) | → #7 (D2) | *(removed)* | A D1 deliverable blocked on a D2 one. Tokens are already on `main`; #7 also moved to D1 |
| **#72** (D2→D4) | → #15 (D4) | → #15, **+#81** | You cannot verify container teardown before the code that starts containers exists |
| **#73** (D4) | → #35 (D5) | *(removed)* | The whole point is that the download happens on D4, before anything depends on it |
| **#83** (D4) | → #29 (D5) | *(removed)* | Contradicted the issue's own goal of being independent of fuzzing |

Every one of these has the reasoning appended to the issue body, not just applied silently.

---

## 9. Parallelism, re-run

Both people must have unblocked work every day. The board as of this morning did not deliver
that, and it failed differently from how the D1 audit predicted.

**Before (open issues per lane per milestone):**

| | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 |
|---|---|---|---|---|---|---|---|---|---|
| Raunak | 1 | **9** | 3 | **7** | 3 | 1 | **0** | 2 | 0 |
| Mahatav | 2 | 3 | **1** | 2 | **1** | 2 | 1 | 2 | 3 |

**After the resequencing in this pass:**

| | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 |
|---|---|---|---|---|---|---|---|---|---|
| Raunak | 1 | **8** | 4 | **8** | 3 | 1 | 1 | 1 | 0 |
| Mahatav | 3 | 2 | 6 | 2 | 2 | 2 | 0 | 2 | 4 |

### Days at risk, and what was done

**D3 — was Mahatav idle. Fixed.** The audit predicted this and its fix (#71's event fixture)
exists but is one of eight items in Raunak's D2. Rather than rely on it, D3 is now loaded with
four small, collision-free security fixes for Mahatav — #94, #95, #96, #97, #98 — that touch
nginx configuration and settings files, none of which Raunak is on for D3's toolchain work. If
#71 lands, Mahatav also builds #19 against it. If #71 slips, he still has a full shift.

**D5 — was Mahatav nearly idle. Fixed.** #51 moved D7 → D5, which the D1 audit asked for and
which was never applied. Mahatav now has #49 (the D5 capture under D-028) and #51.

**D7 — Raunak had literally nothing. Fixed, partly.** #55 (structured JSON logs and trace IDs)
moved D8 → D7. An unattended run that fails without a trace ID is a night lost to guessing, so
this is gate-path work rather than filler. D7 is a gate day; #50 is assigned to both people and
running it is the work.

**D2 — Raunak is over capacity and no resequencing fixes it.** Eight open issues, of which
#12, #77 and #80 are three views of one file (`contracts/state_machine.py`) and should be worked
as one branch. Every one of the eight is D2-or-earlier by dependency, so nothing can be pushed
right without breaking something downstream. **The lever here is scope, and scope is the PM's
and the CTO's, not mine.** Two things that follow:

- **If only one of Raunak's eight D2 items lands, it must be #71.** Mahatav's D3, D5 and D6 all
  build against it. Its own body says it goes at the front of D2; that instruction needs to
  survive a bad night.
- **#82 (replay-mode gateway) is the item I would move to D3 if asked**, and I have not, because
  the CTO scheduled it on D2 and the CEO approved the claim. Raising it rather than deciding it.

**D4 — Raunak is over capacity for the same reason.** Eight items, though #73 is a background
download and #93 is a small validator fix. #27 was moved D4 → D3 to pair with #16 and #17 on the
same CMake surface; that move is reversible if the D3 gate looks tight on the morning.

**D9 — Raunak has nothing, by design.** Submission material is Mahatav's by ownership split and
#60 (code freeze) is pool-assigned to both. Not a defect.

---

## 10. What I could not resolve, and whose it is

| Item | Why it is not mine | Owner |
|---|---|---|
| **PM-C5** — the Core's spoke order contradicts the state machine, and `CLAUDE.md`'s workflow contradicts architecture §2.2 | An architecture arbitration. It must be settled before the Core is built: spoke order is baked into SVG geometry with fixed 60° arcs | **CTO**, then CEO if `CLAUDE.md` needs amending |
| **PM-C7** — four non-P0 items to move into `04-design-system.md` §11's cut table | It is an edit to another seat's document, on an unmerged PR. Never silently rewrite another role's work | **ui-ux-designer**, on PR #70 |
| **CTO §4.2** — the D1 SSE spike, carved from #13 | Nowhere to put it: D1 ends today and the spike's value is that it happens before #13 is built. Filing a D1 issue on the evening of D1 is theatre. The C1 criteria are on #13, so the knowledge is not lost — the *early warning* is | **CTO / control-api**, to decide whether to run it on D2 morning or accept the risk |
| **L3** — the ten-attempt patch-generation run, the D6 supporting threshold | It has no issue anywhere. It is a long-running overnight job the audit named and nobody filed. I did not file it because it is unclear whether it belongs to #35, #36 or #39, and that is a decomposition call inside another seat's specification | **CTO / ai-ml-engineer** |
| **D-019…D-023 numbering collision** | Three seats numbered decision records independently. The orchestrator owns `.project/decisions.md` and owns the renumbering | **orchestrator** |
| **D2 scope for Raunak** | Eight items in one shift, all dependency-bound to D2. Rebalancing means cutting, and cutting is not the engineering-manager's | **PM / CTO** |
| **#82 on D2 vs D3** | CTO scheduled it, CEO approved the claim. Flagged, not moved | **CTO** |
| **Closing #78** | SEC-02 is now re-filed as #93, which was `cybersecurity`'s stated condition. The close itself is theirs, and the second acceptance box must not be ticked | **cybersecurity** |
| **#73's handoff direction** | Labelled `handoff:to-mahatav` while the audit's L1 argued for `handoff:to-raunak`. Both are defensible; the important half (D4, measured latency) is in the body. Left alone rather than churned | **Raunak**, at the D4 handoff |
| **The E-item split** — sixteen issues from five oversized ones | Deliberately not done; reasoning in §7 | Revisit only if a milestone slips for a reason granularity would have caught |

---

## 11. Summary of issue edits performed

Executed against `Mahatav/brahmadatta-ai` on 2026-08-07. All of these are facts, verifiable on
the issues.

**Acceptance criteria folded in — 76 criteria across 20 issues:**

| Issue | Criteria added |
|---|---:|
| #6 contract freeze | 6 |
| #9 Django scaffold | 3 |
| #12 mission state machine | 6 |
| #13 SSE endpoint | 5 |
| #15 rootless sandbox | 9 |
| #19 Command Center shell | 5 |
| #21 D3 gate | 1 |
| #35 model gateway | 5 |
| #36 model serving | 2 |
| #38 clean-worktree verification | 2 |
| #42 gate matrix | 4 |
| #43 diff view and verdict panel | 4 |
| #49 fallback recording | 2 |
| #51 evidence export | 9 |
| #53 security checklist | 4 |
| #54 measured performance numbers | 1 |
| #57 timed rehearsals | 1 |
| #67 Astro scaffold | 3 |
| #77 verification gate | 2 |
| #80 two-candidate fan-out | 2 |

**Issues created — 7**, all labelled by lane, assigned, milestoned, and added to project 3:

| Issue | Finding | Milestone | Lane |
|---|---|---|---|
| #93 | SEC-02 — model-endpoint allowlist bypasses | D4 | `raunak · india` |
| #94 | SEC-03 — finale system checks never run | D3 | `mahatav · kelowna` |
| #95 | SEC-04 — unbounded ingress body and unsized tmpfs | D3 | `mahatav · kelowna` |
| #96 | SEC-05 — OpenAPI dump and docs unauthenticated | D3 | `mahatav · kelowna` |
| #97 | SEC-08 — dev admin guard on the wrong path | D3 | `mahatav · kelowna` |
| #98 | SEC-14 — dev image trusts forwarded headers from anywhere | D3 | `mahatav · kelowna` |
| #99 | SEC-10 — `SECURITY.md`, fixture scoping, `LICENSE` before publication | D9 | `mahatav · kelowna`, `needs:ceo` |

**Dependency edges repaired — 10 issues:** #16, #21, #32, #37, #38, #49, #67, #72, #73, #83.
Each carries a `## Sequencing correction` section stating what changed and why.

**Milestones changed — 5:** #51 D7→D5, #55 D8→D7, #72 D2→D4, #7 D2→D1, #27 D4→D3. Each has an
explanatory comment on the issue.

**Labels changed — 2:** `parallel-safe` removed from #14 (migrations collision); `handoff:to-raunak`
added to #28 (L2, the overnight fuzz campaign).

**Comments posted — 8:** the five milestone moves, the two label changes, and the SEC-02 re-file
notice on #78.

**Not touched, deliberately:** `.project/decisions.md`, any code, any other seat's document, and
`04-design-system.md`. Four agents were live while this ran.
