# Vision and P0 Cut

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Document | Company-workflow phase 1 deliverable |
| Status | **DRAFT — pending CEO (human) approval at the phase 1 gate** |
| Drafted by | `ceo` agent seat (drafting only; holds no approval authority) |
| Date | 2026-08-06 |
| Supersedes | Nothing. Existing `docs/` pack is left intact and cited. |

## Purpose and standing

The `docs/` pack (79 documents) specifies **what Brahmadatta AI is**. It does not specify
**what gets cut when week 4 slips**. Every in-scope item in
[`docs/01-product/03-mvp-scope-document.md`](../01-product/03-mvp-scope-document.md) carries
equal weight, all five demo scenarios are "required", and
[`docs/08-management/51-project-timeline.md`](../08-management/51-project-timeline.md) allocates
eight workstreams to eight weeks with no buffer. That is a wish list with dates on it.

This document adds the missing layer: a forced ranking, a minimum viable demo, checkable kill
criteria, and the four decisions only the human CEO can make. It **does not restate, replace, or
contradict** the pack — where it disagrees with the pack, it says so openly in §6 and leaves the
pack unedited.

---

## 1. Vision, restated for this competition

Winning AI Kavach does not mean building the best cyber-reasoning system. It means being the
team whose demonstration a judge cannot poke a hole in. The competition material rewards
resource utilization, novelty, and a lightweight solution at shortlisting, and performance,
speed, precision, functionality and scalability at the 36-hour finale
([`docs/10-competition/source-and-feasibility-notes.md`](../10-competition/source-and-feasibility-notes.md)).
Brahmadatta AI wins by doing exactly what
[`docs/01-product/01-project-vision.md`](../01-product/01-project-vision.md) promises and
nothing more: **one complete autonomous loop, proven end to end, on a live authorized target, in
front of the judges — discover a memory-safety defect, minimize it to a deterministic
reproducer, generate a minimal patch with a self-hosted model, and let deterministic tools, not
the model, deliver the verdict — plus the same pipeline visibly *rejecting* a plausible-looking
bad patch.** The rejection is the differentiator. Every competitor will show a patch that
worked; the team that shows its own system refusing a patch that only *looked* like it worked is
the team that has actually built verification rather than a demo. Everything else in the pack —
the three-tier routing, the heavy-model escalation, the Command Center density — exists to make
that loop legible and to earn the resource-utilization and novelty marks. It is subordinate to
the loop, not equal to it.

---

## 2. The P0 cut

Every in-scope item from `03-mvp-scope-document.md`, decomposed into rankable units and forced
into three tiers.

**P0 — the demo dies without it.** If this does not work there is nothing to show.

| # | Item | Source | Why P0 |
|---|---|---|---|
| P0-1 | Authorization gate + immutable repository snapshot | scope §1, `23-security-plan.md` | Hard constraint. Running without it breaches the safety boundary and disqualifies the entry regardless of technical merit. |
| P0-2 | Rootless isolated sandbox with egress denied | scope §1, risk register row 7 | The system runs untrusted target code and a fuzzer. Non-negotiable. |
| P0-3 | Persistent state machine + event stream | scope §3, critical path | The spine. Dashboard, evidence, and every gate read from it. |
| P0-4 | C/C++ adapter: CMake/Make configure + build + CTest invocation | scope §4 | No build, no baseline, no verification, no demo. |
| P0-5 | Baseline build + regression test run, recorded as pass/fail counts | scope §5 | The denominator for "regression preserved". Without it, "Verified" is meaningless. |
| P0-6 | Sanitizer build (ASan + UBSan) | scope §7 | The crash has to be *confirmed*, not merely observed. |
| P0-7 | One fuzzing engine (libFuzzer) reaching the demo defect | scope §7 | Scenario 1. Choice of engine is a CTO call; the *count* is one, not two. |
| P0-8 | Crash capture + minimized input that reproduces deterministically from a clean build | scope §8 | The proof target the entire verdict hangs on. |
| P0-9 | Patch policy: path allowlist, changed-line cap, single-file constraint | scope §12, risk register row 6 | Both a safety control and the mechanism that makes rejection demonstrable. |
| P0-10 | A self-hosted model generating the patch candidate | scope §10 | Without a model this is a fuzzing harness, not a Cyber-Reasoning System. *Serving location is P1; model participation is P0.* |
| P0-11 | Clean-worktree verification: rebuild → reproducer re-run → regression suite → verdict `Verified` / `Rejected` / `Human Review Required` | scope §12 | The product. |
| P0-12 | Evidence database + Markdown/JSON report with an explicit gate matrix | scope §12 | Slide 5's deliverable and the judge's audit trail. |
| P0-13 | Command Center minimum screen set: mission core, stage timeline, findings list, diff view, verdict panel | scope §2 | Five panels, not the full component inventory. |
| P0-14 | Safe teardown of whatever compute was started | scope §12 | Hard constraint and a scored criterion. Applies even with zero rented GPUs. |
| P0-15 | Pre-recorded fallback demonstration | scope §13 | If the live run dies at hour 30, this *is* the demo. Costs one afternoon. Cheapest insurance in the plan. |

**P1 — the demo is materially weaker without it, but it still runs.**

| # | Item | Source | Effect if missing |
|---|---|---|---|
| P1-1 | Automated `git bisect` + first-bad-commit identification | scope §9 | Loses demo scenario 2 and the "git-aware root-cause localization" novelty claim on slide 4. Not on the pack's own critical path. |
| P1-2 | Semgrep integration + static-delta gate | scope §6 | Verdict falls back to compile + reproducer + regression. Weaker matrix, still deterministic. |
| P1-3 | Renewed-fuzzing gate after patch | scope §12 | Loses the strongest anti-overfit argument. Cheap once P0-7 exists — expected to land. |
| P1-4 | Small model served on a rented GPU, started on escalation and torn down | scope §10, §11 | This is what makes demo scenario 5 real without a heavy model. See D-007. |
| P1-5 | Reproducer → permanent regression test conversion | scope §8 | Pack already hedges with "when practical". |
| P1-6 | Crash deduplication / clustering | scope §8 | One crash is enough for the demo. Matters only if fuzzing produces many. |
| P1-7 | Presentation mode | scope §13 | Polish. Note: cutting it also removes the only place a labelled deterministic mock is permitted. |
| P1-8 | Git history summary panel | scope §9 | Context for the judge; not a gate. |
| P1-9 | Structured JSON logs + trace IDs | `17-technology-stack-document.md` | Primarily a debugging aid for us; invisible to judges. |
| P1-10 | Basic keyboard operability of the Command Center | `30-accessibility-requirements.md` | Single-operator tool; operability yes, full conformance no. |

**P2 — cut first when a week slips.** One line each, as required.

| # | Item | Source | Why it is first to go |
|---|---|---|---|
| P2-1 | Heavy-model (Kimi K3-class) Tier 3 escalation as a **live** finale dependency | scope §11, M5 | Highest cost, highest schedule risk, depends on an external provider and an unverified model; P1-4 already earns the resource-control scenario. |
| P2-2 | AFL++ as a second fuzzing engine alongside libFuzzer | scope §7 | Two engines is two harness formats and two triage paths for one crash we only need to find once. |
| P2-3 | Python adapter | `11-feature-list.md` P1 | Pack already says it must not delay C/C++; a competition judged on C/C++ memory safety gains nothing from it. |
| P2-4 | microVM isolation adapter | `17-technology-stack-document.md` | Rootless containers satisfy the safety boundary for a controlled authorized target; microVM is hardening we will not be scored on. |
| P2-5 | Prometheus metrics + observability panels | `17-technology-stack-document.md` | Real telemetry is required in the UI, but it can come from the event stream; a metrics backend is infrastructure the demo never displays. |
| P2-6 | Coverage visualization | `11-feature-list.md` P1 | Beautiful, expensive, and irrelevant to whether the patch verdict is sound. |
| P2-7 | Patch ranking / multiple competing candidates | `11-feature-list.md` P1 | We need one accepted and one rejected patch, not a ranked set. |
| P2-8 | Signed evidence bundles | `11-feature-list.md` P1 | Integrity theatre for a demo where we hand the judge the artifacts directly. |
| P2-9 | Offline deployment bundle | `11-feature-list.md` P1 | The finale runs on our machine; portability is a post-competition concern. |
| P2-10 | Multi-finding correlation across static + dynamic evidence | `16-system-architecture-document.md` | One correlated finding is the demo; a correlation engine is a product. |
| P2-11 | Full WCAG conformance pass | `30-accessibility-requirements.md` | Single named operator, desktop-only, no external users — the cost/benefit does not survive a schedule slip. |
| P2-12 | Redis-backed distributed queue | `17-technology-stack-document.md` | One mission at a time, one machine; an in-process or DB-backed queue is functionally identical here. **CTO owns this call** — flagged as business-cheap, not decided. |

**A note on what this ranking is for.** P2 is not "won't build". It is the pre-agreed cut list,
so that when week 5 slips nobody spends a day arguing about it. If everything lands, everything
ships.

---

## 3. The minimum viable demo

Of the five required scenarios, the single sequence that, alone, is still a credible competition
entry is **scenarios 1 + 3 + 4 run back to back on one target** — discovery, verified repair, and
rejected repair. Scenario 2 (bisect) and scenario 5 (resource control) are additive, not
load-bearing.

Concretely, the run is:

1. **Target.** The primary controlled C target (see §5.4) — a small CMake + CTest C library with
   one seeded heap-buffer-overflow in its input parser and a green baseline test suite.
2. **Authorize and snapshot.** Operator authorizes the repository in the Command Center. Snapshot
   hash recorded. Sandbox provisioned, egress denied.
3. **Baseline.** Configure, build, `ctest` → all tests pass, counts recorded in the evidence DB
   and shown in the UI.
4. **Finding.** ASan + UBSan build; libFuzzer harness on the parser entry point with a seeded
   corpus. Run produces a **sanitizer-confirmed heap-buffer-overflow** with a stack trace naming
   the vulnerable function. Input minimized; minimized input replays the crash 5/5 times from a
   clean build.
5. **Patch.** The self-hosted small model receives the crash report plus the localized source
   context and returns a candidate. Patch policy accepts it: one file, within the allowlist,
   under the changed-line cap — a bounds check before the read.
6. **Verdict A — Verified.** Fresh worktree, rebuild, run the minimized reproducer → no crash.
   Run the full regression suite → all pass. Verdict `Verified`, with the gate matrix
   enumerated: compile ✓, reproducer eliminated ✓, regression preserved ✓, plus whichever of
   static-delta and renewed-fuzz actually ran.
7. **Verdict B — Rejected.** A second candidate — the tempting crash-only fix that clamps the
   parse length to zero — goes through the *identical* pipeline. Reproducer: eliminated ✓.
   Regression suite: **fails**. Verdict `Rejected`, shown beside verdict A.
8. **Evidence.** Markdown + JSON bundle exported containing snapshot hash, crash report,
   minimized input, both diffs, both gate matrices, both verdicts, and resource usage.
9. **Teardown.** All sandboxes and any leased compute confirmed released in the UI.

That sequence is defensible on its own in front of a judge: a real defect found by our own
fuzzing, a real patch from a self-hosted model, and a real rejection produced by tools rather
than by a confidence score. If nothing else in the eight weeks works, this is the entry.

**Honesty constraint on step 7.** If the model does not spontaneously produce a bad candidate,
the rejected patch may be operator-supplied — but the UI, the report, and the narration must
label it **"operator-supplied candidate"**, never "model-generated". The *gates* are real either
way; the provenance claim must not be inflated. See D-008.

---

## 4. Kill criteria

Weeks are relative to the assumed start of 2026-08-06 (see §5.2 — this anchor is itself an open
decision). Each condition is observable at the stated week's end. Failing it triggers the stated
cut, not an extension.

### Week 2 (ends 2026-08-19) — spine and baseline

**Condition:** from a cold start with an empty database, a mission submitted on the primary
target reaches state `BASELINE_PASSED` in the Command Center, showing a real `ctest` summary of
N passed / 0 failed, inside 15 minutes — reproduced **twice consecutively**.

**If not met:** cut, do not push. Replace the primary target with the smallest possible fixture
(one `.c` file, one CTest case), hardcode the build recipe, and drop adapter generality from
scope entirely. The C/C++ adapter becomes "runs our target", not "runs CMake projects".

### Week 4 (ends 2026-09-02) — the finding

**Condition:** at least one **sanitizer-confirmed** crash on the demo target, produced by our own
fuzzing run within 30 minutes of fuzz time, with an ASan report containing a stack trace, and a
minimized input that reproduces 5/5 times from a clean build.

**If not met:** cut in two steps. (a) Stop investing in fuzzer reach; re-harness directly on the
vulnerable function and re-scope scenario 1 from "fuzzing discovers the defect" to "the fuzz
harness confirms and minimizes it". (b) If still not met by 2026-09-05, the live fuzzing step
moves to the recorded fallback and the live demo reduces to reproducer → patch → verify. Do not
carry fuzzing debt into week 5.

### Week 5 (ends 2026-09-09) — the loop

**Condition:** a single operator action produces both verdicts — one model-generated patch
reaching `Verified` and one candidate reaching `Rejected` on a regression failure — with the
gate matrix present in the exported report, reproduced **twice consecutively**. Supporting
threshold: the small model produced a policy-passing, compiling patch on the demo defect in **at
least 3 of 10 attempts**.

**If not met:** cut Tier 3 entirely and **do not start week 6**. Reallocate week 6 to making the
Tier 2 loop reliable. Demo scenario 5 downgrades to lease control of the small-model host.

### Week 6 (ends 2026-09-16) — compute control and freeze

**Condition (a):** a rented GPU is provisioned on escalation, serves the model for a real patch
request, and is confirmed torn down — provider console shows the lease terminated, the UI shows
teardown, and the lease duration is recorded — achieved within **3 attempts**, with **zero**
leases left running unattended and cumulative spend at or under the approved ceiling.
**Condition (b):** the release candidate runs the §3 minimum viable demo end to end, unattended,
start to finish.
**Condition (c):** the pre-recorded fallback demonstration **exists**, in full, as a playable
file.

**If (a) not met, or if spend passes 50% of the ceiling without one successful full cycle:** cut
rented-GPU escalation from the live demo. Keep the measured spike as evidence and present the
tier as designed-and-measured, not live. Never present it as live if it is not.
**If (b) not met:** declare feature freeze at end of week 6 — a full week earlier than the plan —
and spend week 7 exclusively on reliability.
**If (c) not met:** week 7 opens with recording the fallback, before anything else. This is
deliberately pulled forward from week 8 (see D-011).

---

## 5. The four open CEO decisions

These are the items the team cannot answer for itself, carried from the end of
[`.project/intake.md`](../../.project/intake.md). **Last responsible moment (LRM)** is the date
after which the absence of an answer starts destroying work.

### 5.1 GPU provider and budget ceiling

| Option | Cost (order of magnitude — **unvalidated, CTO/ml-infra to confirm**) | Risk |
|---|---|---|
| **A.** No rented GPU. Quantized small code model served on local CPU. | $0 | Weakest on "resource utilization" novelty. Demo scenario 5 becomes process-level lease control only. Zero external dependency, zero failure mode. |
| **B.** One on-demand mid-size GPU for small-model serving and escalation, used across build, rehearsal and finale. | Low tens to low hundreds of dollars over ~40–80 hours | Provider availability at finale time; forgotten lease. Both mitigable with hard caps. |
| **C.** B, plus a short-lived multi-GPU node for one heavy-model spike and one finale escalation. | Several hundred dollars on top, concentrated in ~10–20 hours | Capacity may be unavailable; the model may not fit; risk register already rates this High/High. Highest cost and highest chance of buying nothing usable. |

**Recommendation:** approve **B now with a hard ceiling**, and hold **C as a separate,
separately-approved one-off spike budget** released only if the week-5 kill criterion passes.
Never leave a lease uncapped. A dollar ceiling with an automatic stop is worth more than a
provider choice.

**LRM:** **2026-09-02 (end of week 4)** for option B — week 5 begins model work and the provider
must be live before it starts. **2026-09-09 (end of week 5)** for the C top-up.

### 5.2 Finale date and submission deadline

| Option | Cost / risk |
|---|---|
| **A.** Keep the relative assumption (week 1 = 2026-08-06, freeze ≈ 2026-09-30). | Free, and possibly wrong by weeks. If the real submission deadline is earlier, everything after week 5 is fiction and we miss the entry entirely. |
| **B.** Human confirms the actual AI Kavach submission deadline and finale dates from the competition material this week and the schedule is re-anchored. | Costs an hour. Removes the single largest unquantified risk in the project. |

**Recommendation: B, and treat it as the highest-severity open item in the project.** An 8-week
plan anchored to nothing is not a plan. Additionally, adopt a defensive hedge regardless: **draft
the five-slide submission against the P0 cut by end of week 4**, so that a deadline discovered to
be earlier than assumed does not catch us with no submission. Slides are cheap; missing a
deadline is total.

**LRM:** **2026-08-12 (end of week 1).** Every week without an anchor converts directly into
scope that must be cut later at worse prices.

### 5.3 Team composition

| Option | Cost / risk |
|---|---|
| **A.** The pack's assumed three humans (`54-team-roles-and-responsibilities.md`). | Matches the docs. Does not match reality; no such team exists. |
| **B.** CEO + the agent roster (current reality). | Zero marginal cost. **The 36-hour finale runbook assigns three concurrent human roles** — incident lead, demo operator, evidence lead. One human cannot cover 36 in-person hours. This is a real, dated failure mode, not a staffing preference. |
| **C.** B for the build, plus 1–2 recruited humans for the in-person finale only. | Recruitment effort and possible registration/travel constraints. Removes the solo-operator failure mode. |

**Recommendation:** **B for the build, C for the finale** — recruit at least one co-presenter who
can operate the demo while the other handles incidents. Separately and urgently: confirm whether
the competition rules require named human team members, and whether agent-authored code is
permitted or must be disclosed. That is a rules question, not a preference, and a wrong
assumption there is disqualifying.

**LRM:** **2026-08-19 (end of week 2)** for build staffing, because phase 4 task breakdown
allocates against it. **2026-09-02 (end of week 4)** for the finale roster, because of
registration and travel lead time.

### 5.4 Demo target repository

| Option | Cost / risk |
|---|---|
| **A.** Purpose-built controlled C target in our own repository, with a seeded memory-safety defect and a git history where the defect is introduced at a known commit. | Cheap, fully controllable, guarantees the fuzzer reaches the defect and the bisect has a right answer. Risk: a judge dismisses it as a toy. |
| **B.** A real small open-source C library pinned to a commit with a known historical CVE. | Far more credible. Hits two High/High risk-register rows at once: "target does not build" and "fuzzer cannot reach defect". |
| **C.** Both — A as the guaranteed path, B attempted only after the week-4 kill criterion passes. | Costs the setup of A plus opportunistic work on B. Credibility upside with a guaranteed floor. |

**Recommendation: C.** Build A in week 1 and treat it as the demo of record. Attempt B only from
week 5 onward, and only if A is already green. Any B candidate must be genuinely authorized for
this use — the authorization basis gets written down before a single build runs.

**LRM:** **2026-08-12 (end of week 1)** for the primary target A — week 2's baseline and week 4's
fuzzing both build directly against it, and picking it late invalidates both. **2026-09-02 (end
of week 4)** for whether B is attempted at all.

---

## 6. What I would challenge in the pack

Read critically, and stated plainly.

**6.1 The success metrics are invented numbers wearing the costume of targets.**
[`13-success-metrics.md`](../01-product/13-success-metrics.md) asserts ≥80% confirmed-finding
precision, ≥50% verified patch rate, ≤30 minutes to first confirmed finding, ≤30% Tier 3
escalation. There is no benchmark set, no case list, and no denominator anywhere in the pack.
As written these are unfalsifiable, and quoting any of them in a five-slide submission is a claim
we cannot defend if a judge asks "measured on what?". Either define the case set explicitly
(N controlled defects, named, with the harnesses) or relabel every row **"target — not measured"**
and publish only what is actually measured by week 7. The pack's own
[`source-and-feasibility-notes.md`](../10-competition/source-and-feasibility-notes.md) already
demands exactly this. It never happened.

**6.2 The "Open decisions / next review" block is copy-pasted verbatim at the bottom of every
document.** It appears identically on all 79 files. That is why four genuinely open, genuinely
blocking items have sat unresolved and invisible — repeating a question 79 times is
indistinguishable from answering it zero times. There is no single place in the pack where the
live state of an open question is tracked. That is the specific gap this document and
`.project/decisions.md` exist to close.

**6.3 The per-stage performance table is fabricated precision.**
[`29-performance-requirements.md`](../03-technical/29-performance-requirements.md) gives fuzzing a
20-minute target and a 45-minute hard cap, and bisect 10/25. Time-to-crash is not a schedulable
quantity — it is a property of the target, the harness and the seed corpus. On a seeded defect it
may be seconds; on anything real, 20 minutes is a coin flip. Publishing a cap makes an
unmeasured guess look like a benchmark. The row "Kimi K3 candidate — 10m / 20m" is worse: it
budgets latency for a model on a topology nobody has ever run.

**6.4 M5 names a specific heavy model, and should not.**
[`52-milestone-plan.md`](../08-management/52-milestone-plan.md) defines M5 as "self-hosted Kimi K3
request is bounded, audited, and torn down". Naming a specific frontier-scale model in a
milestone commits us to a dependency whose weight availability, licence, memory footprint, and
rentable topology are all unverified — and the pack's own risk register rates "cannot fit
available rented cluster" as **High likelihood / High impact**, the worst row in the table. I
cannot verify from inside this repository that a model by that name exists in an obtainable form
at all, and neither, as far as the pack shows, has anyone else. **It must not appear in any
external material, slide, or report until the ml-infra engineer has confirmed it and run the
spike.** M5 should be capability-shaped: "one bounded, audited, torn-down escalation to a larger
self-hosted model, model TBD post-spike."

**6.5 The timeline has no anchor and no slack.** Eight distinct workstreams, one week each, zero
buffer, and week 8 simultaneously carries full rehearsals, the five-slide submission, fallback
asset production, and code freeze. Any single week slipping cascades into the freeze. And the
whole thing floats — the actual deadline is unknown (§5.2). Week 1's own deliverable is "freeze
scope", which means the plan's first act is to do what this document is doing, which is fine,
but nothing after it has been costed against real capacity.

**6.6 Treating all five demo scenarios as equally mandatory hides the real conflict.** Scenario 5
(resource control) is the only one that costs money, the only one that depends on an external
provider, and simultaneously the one the shortlisting criteria most reward. The pack never
resolves that tension. §2 and D-007 resolve it: escalate-and-teardown demonstrated with the
*small* model is P1 and cheap; the heavy model is P2.

**6.7 The Command Center as specified is a multi-week frontend project competing with the
pipeline.** [`docs/02-design/`](../02-design/) specifies a dense mission-control UI with a full
component inventory, motion spec, and state spec, budgeted as slices of weeks 2–7 alongside all
the backend work. The Command Center is the differentiator on the slide; the pipeline is the
differentiator in the finale. When they collide, **the pipeline wins** — which is why the P0
screen set is five panels, not the inventory.

**6.8 The risk register has no owners and no triggers**, despite stating its own purpose as
tracking risks "with owners and mitigations" — there is no owner column and no threshold at
which any mitigation fires. The kill criteria in §4 are the fix for the schedule-facing subset;
the rest needs an owner assigned per row, which is the PM's to do.

---

## 7. Runway re-scope, 2026-08-19 — reopening part of the P1 cut

**Status: DECIDED, CEO, `.project/decisions.md` D-086. This section is the current,
authoritative scope statement for the remaining build. Where it conflicts with §2's P1/P2
tables above or with `docs/09-company/03-seven-day-plan.md`, this section wins — those are
left unedited as the historical record of the original 3-day-compression call, not
corrected in place.**

The user told the orchestrating session directly, 2026-08-19, that the real runway is
~10 days from that date (deadline ≈2026-08-29), not the 2026-08-20 date the seven-day plan
and `CLAUDE.md` were compressed against — roughly 7x the runway D-014's emergency
compression assumed. At the same time, the backend/orchestration engine reached genuine
feature-completeness for the D7 happy path (all seven mission-stage executors merged and
reviewed, `#168` closed) modulo one open bug (`#207`, routed to CTO/backend-developer, not
a CEO call), while the Command Center frontend has had zero attention this session and is
unverified against the now-complete API. Full reasoning for everything below is in D-086.

**This does not reopen the whole `CUT` milestone.** Two already-committed priorities outrank
every CUT item: (1) `#207` fixed and a real live E2E rehearsal reached; (2) a real phase-5
verification pass on the Command Center's five P0 panels (P0-13, above) against the complete
API — not new scope, work this session skipped entirely. **No CUT-reopen work below is
staffed until both of those, plus `#50` passing live once, are real.**

**Reopened from `CUT`, into `D8 — Hardening & rehearsal (extended)`, staffed only after the
gate above:**

| Item | Was | Now | Why |
|---|---|---|---|
| `#25` — Analysis rail (findings by severity, dependency/compiler health) | CUT | **D8** | Cheapest reopen — spec and shared component (`NotRunCoverageRow`) already exist (`D-057`). Reinforces the product's actual differentiator: disclosing what was *not* checked, not hiding it. |
| `#56` — Keyboard operability | CUT | **D8** | Cheap by design (`D-059`: tab-order only, no palette, no new key layer). Reduces real operational risk for the solo operator during the scored run. |
| `#52` — Presentation mode | CUT (P1-7) | **D8, rehearsal-only** | Re-scoped as rehearsal-enablement, not demo scope — architecturally excluded from the finale build (`D-058`). Lets the demo operator rehearse narration while backend stabilization continues; `#50` has failed three live attempts in a row, so this has real near-term value. `cybersecurity` to confirm the build-time exclusion is tested, per `D-058`'s own recommendation. |
| `#40` — Renewed-fuzzing gate after patch | CUT (P1-3) | **D8, contingent on CTO** | The strongest anti-overfit argument in the product's own story; expected to be cheap "once P0-7 exists" — it now does (`T2`/`FUZZ`, `#188`). Reopened contingent on CTO confirming it's genuinely cheap now and doesn't threaten the `#50`/`#57` critical path. |
| `#31` — Fuzzing telemetry panel | CUT | **D8, contingent on PM scoping** | Visually reinforces "our own fuzzing found it," but cost is unclear pending whether the FUZZ executor already emits progress events on the existing SSE stream. PM scopes a cheap (reuse-only) version before any engineering time is committed; if it needs new backend instrumentation, it waits. |

**Left in `CUT`, explicitly re-evaluated and declined, not merely un-reopened:**

| Item | Was | Reasoning |
|---|---|---|
| `#26` — Git history summary + bisect timeline panel | CUT (P1-1/P1-8) | There is already a standing, closed decision on this — `#63`, "bisect stays cut." More runway does not by itself overturn a decision already deliberately made once, and reopening it needs real new backend capability (automated `git bisect` + a seeded history with a known-bad commit), a materially bigger lift than any item reopened above, for a demo scenario this document's own §3 already ranked additive, not load-bearing. PM/CTO may bring a case to reopen `#63` itself if circumstances genuinely warrant it — not done unilaterally here. |
| `#44`/`#46`/`#47`/`#48` — GPU escalation set | CUT (P2-1 family) | `D-015`'s reasoning (cost, external-provider dependency, schedule risk, "the only real money in the project") is not a function of calendar days. Attempting a never-yet-tested rented-GPU escalation for the first time in the same window as an already-fragile live-E2E gate (`#50` has failed three live attempts) is a *worse* risk now than on the original calm schedule. Stays cut. |
| `#5`, `#22`, `#23`, `#24`, `#30`, `#62` | CUT | Not ruled on — no descriptions were available to this decision. Default: stay cut. Delegated to product-manager/engineering-manager to triage against the priority order below and bring back anything clearly cheap and clearly load-bearing for items 1–3, not decoration. |

**Priority order for the remaining runway** (see D-086 for full reasoning; this is what
PM/EM build a task breakdown from): fix `#207` and run a real phase-5 Command Center
verification pass **concurrently**; get `#50` to pass live once; run the three `#57`
rehearsals; only then staff the reopened CUT items in order `#25` → `#56` → `#52` → `#40`
(CTO-gated) → `#31` (PM-scoped); confirm or re-record the fallback demo against the
now-complete pipeline; hold a real reserve before `#60` code freeze ahead of the actual
~2026-08-29 deadline. Separately: the 16 non-blocking findings filed during this session's
review rounds (`#176`, `#177`, `#180`, `#184`, and others in the `#163`–`#207` range) are
real correctness/hygiene gaps, not scope, and engineering-manager should triage that
backlog as part of "hardening" for anything that poses genuine risk to a live rehearsal or
the finale — this is already the priority this section sets, not a separate ask.

**Day-numbering.** D7/D8/D9 are not renumbered — they remain the correct conceptual labels
(D7 = evidence/freeze gate, D8 = hardening & rehearsal, D9 = submission & freeze). What's
stale is the calendar mapping in `03-seven-day-plan.md` (Aug 6–20); engineering-manager
should re-anchor D7/D8/D9 to real dates inside the ~10-day window from 2026-08-19 and hold
a genuine reserve before ~2026-08-29 — not a repeat of the original plan's reserve, which
sat inside a deadline that turned out to be wrong anyway.

**§5.3 (finale roster / `#59`) reaffirmed, not re-opened.** Option C stands: agent roster
for the build, 1–2 recruited humans for the in-person finale only, covering the
incident-lead/demo-operator/evidence-lead split. What's still missing — actual human names,
availability, registration and travel logistics — is not derivable from this repository and
needs the user directly. 10 days instead of 3 makes this more achievable, not less urgent to
start now.

---

## Constraints reaffirmed

Nothing in this document relaxes any of these. Every tier, cut, and kill criterion above is
subordinate to them:

- Defensive posture, authorized targets and isolated environments only. No public scanning, no
  exploit deployment, no automatic production merge.
- Repository content never reaches an external inference API. Self-hosted models exclusively.
- A patch is never accepted on model confidence alone.
- No fake or decorative telemetry in the UI; mocks only in presentation mode and clearly labelled.
- Brahmadatta is a technology brand, presented respectfully, never as a deity or religious claim.

---

*Decision records for the non-trivial calls in this document: D-006 … D-012 and D-086 in
[`.project/decisions.md`](../../.project/decisions.md).*
