# Product Review — PR #70, the four inherited questions, and two EM findings

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Document | Company-workflow phase 1 close-out — the PM seat that was skipped |
| Author | `product-manager` seat |
| Date | 2026-08-07 |
| Reviews | PR #70 (design system), issues #61 #62 #63 #64, `07-task-breakdown-audit.md` §1.2(b) and P1-5 |
| Supersedes | Nothing. The `docs/` pack and every phase deliverable are left unedited. |

## Standing

Phase 1 closed CONDITIONAL GO with this seat skipped, and the four questions the `ceo` seat
left at the end of its handoff went onto the board as #61–#64 instead of being answered. The
CTO names #64 as the reason the D7 gate (#50) has no definition of done. This document
answers all four, gives PR #70 a product verdict, and rules on the two engineering-manager
findings that are mine.

Everything here was checked against: `01-vision-and-p0-cut.md`, `03-seven-day-plan.md`,
`04-design-system.md` and `tokens.css` (PR #70), `05-cto-technical-review.md`,
`06-architecture-spec.md`, `07-task-breakdown-audit.md`, `13-success-metrics.md`,
`15-risk-register.md`, `.project/decisions.md` D-006…D-023, and the `pktcfg` target from
PR #74.

**This document does not edit `.project/decisions.md`.** Seven decision records are written
out in §6 for the orchestrator to fold in. It also does not edit `15-risk-register.md` or
`13-success-metrics.md`, following the precedent every other seat set: the pack records what
Brahmadatta AI is meant to be, and the correction is recorded here.

---

## 1. PR #70 — the design system

### Verdict: APPROVE WITH CONDITIONS

The design is better than the documents it was drawn against. It is internally consistent,
it makes D-008, D-009 and the no-fake-telemetry rule *visible and checkable in review* rather
than leaving them as prose, and the component reduction from 32 to 22 is correctly argued. I
am not asking for anything to be redrawn.

Eight conditions follow. Two of them (C1, C4) are defects against uncuttable P0 items, which
is why this is not a clean approve. None of them requires new visual work.

### 1.1 Walking the nine steps

§4.1's journey table has nine rows, but they are not the P0 cut's nine steps — the designer
renumbered around what the operator touches. Mapped properly against
[§3 of the P0 cut](01-vision-and-p0-cut.md#3-the-minimum-viable-demo):

| P0 step | Surface in the design | Verdict |
|---|---|---|
| 1 Target | Top strip `[ REPO … ]` chip | Covered |
| 2 Authorize + snapshot + sandbox | §4.1 row 2 dialog naming repo, hash, egress policy; bottom strip `[ SESSION SECURE ] [ EGRESS DENIED ] [ SANDBOX 1 ]` | Covered |
| 3 Baseline | §6.2 stage row carrying real `ctest` counts; §4.1 row 4 | Covered |
| 4 Finding | §6.3 finding row, `[ ● CONFIRMED ]` | **Gap — C2** |
| 5 Patch | §6.4 header: provenance, policy, files/lines/allowlist | Covered, and well |
| 6 Verdict A | §6.5 verdict panel with the mandatory five-row matrix | Covered |
| 7 Verdict B | §6.5 two-candidate compare | **Gap — C3, C4** |
| 8 Evidence | §4.1 row 9 export chip with paths | Covered (see 1.4) |
| 9 Teardown | §4.2 only, on the emergency path | **Gap — C1** |

Six of nine are covered cleanly. The three gaps are below.

### C1 — Step 9 has no surface on the successful path. Blocking.

`[ + ALL SANDBOXES RELEASED ]` is specified in §4.2, the *operator intervenes* journey,
reachable only after `[ EMERGENCY TEARDOWN ]`. §4.1's primary journey ends at export. So a
mission that runs the nine steps correctly and terminates cleanly has no teardown surface at
all.

P0-14 is one of five items the engineering-manager audit lists as structurally uncuttable,
it is step 9 of the demo, and it is a scored competition criterion. The EM audit already
flagged that teardown "has no home" in the milestone table (§1.2(a)); this is the same gap
showing up in the UI.

Two further things the current chip cannot say. The CTO's condition 3.2 requires the local
model host to be a real lease — started on entry to `PATCH`, duration recorded, stopped at
completion, emitting `TEARDOWN_CONFIRMED` with `resource_kind: model-host`. And architecture
§6.7 requires the claim to follow the receipt, never the intention. So:

**Required.** Add a terminal row to §4.1 and a persistent bottom-strip chip:

```
[ + ALL RESOURCES RELEASED · 1 SANDBOX · 1 MODEL HOST ]
```

rendered only once a `TEARDOWN_CONFIRMED` event with `released = true` exists for every
resource the mission started. Before that it reads `[ — RELEASE PENDING ]`, per D-023. Never
an absence, because an absence is indistinguishable from "we did not check".

### C2 — Step 4's two load-bearing evidence values have no home. Blocking.

Step 4's pass condition is a sanitizer-confirmed crash "with a stack trace naming the
vulnerable function", plus a minimized input that "replays the crash 5/5 times from a clean
build". Neither appears anywhere in the design.

§6.3's finding row carries category, location, tool and a confirmed chip. §6.4's diff overlay
carries the candidate, not the finding. §11 cut the Finding Detail screen with the reasoning
that finding detail collapses "into the finding row plus the diff overlay" — but the stack
trace and the replay record went into neither. The `[ + REPRODUCER ELIMINATED ]` gate chip is
about the *post-patch* re-run; it is not the pre-patch 5/5 confirmation.

This matters more than it looks. "Sanitizer-confirmed" and "5/5 from a clean build" are the
two claims that separate this from a crash someone saw once. A judge who asks "how do you
know it reproduces?" should be able to be shown the answer, not told it.

**Required.** The finding row gains a second sub-line, and selecting the row expands the top
three ASan frames in place:

```
[ FINDING 01 ]  HEAP-BUFFER-OVERFLOW               [ ● CONFIRMED ]
                decode.c:31 emit_tab · write 3 @ +0 · ASan
                minimized 22 B · replay 5/5 from clean
```

`replay 5/5` renders from `Reproducer.replay_successes / replay_attempts`, which architecture
§5.1 already persists and already sets from `successes == attempts` rather than guessing.
Before minimization completes it is an em dash, not `0/0`.

### C3 — The compare lives in a panel the overlay covers, at a size nobody has measured.

This is the competition differentiator and it currently has an internal contradiction and an
unbudgeted layout.

**The contradiction.** §4.1 row 8 gives the entry point as `[ OPEN DIFF ]` with two candidates
present, and the response as "verdict panel splits into two 292px columns". §6.4 confirms
"the demo's side-by-side comparison happens in the verdict panel (§6.5), not here". But the
diff overlay is 1328 × 684 inset inside the page frame, and the verdict panel sits in the
centre column *underneath* it. Opening the diff hides the panel that is doing the comparing.

**The arithmetic.** §3 budgets the verdict panel at 608 × 124. In the split state each column
is 292px and must hold a `display-lg` verdict word plus a complete five-row gate matrix.
"Verified" is eight characters at 72px in a high-contrast serif — that is within a few pixels
of 292 on the actual metrics, so the single most important word in the product is one glyph
of overflow away from clipping. And five gate chips, one of which is
`[ + REGRESSION PRESERVED · 8/8 ]`, will not stack inside 124px of height. §3's own region
budget leaves 36px of slack, which does not close it.

§6 invites exactly this: "If a state, label or value is missing below, that is a defect in
this document — raise it rather than guessing."

**Required.** The two-candidate compare renders **at overlay width**, not in the 608 centre
column: the same 1328 × 684 surface, two 652px columns, one candidate each, with its diff
above and its verdict and full gate matrix below. §6.5 already contemplates the verdict panel
living in the overlay ("336 wide in the overlay's right column"), so this is a re-anchoring
rather than a new component. The centre-column verdict panel keeps its single-candidate
rendering for the live run.

This also fixes the entry point: `[ OPEN DIFF ]` with two candidates present opens the compare
directly, which is what §4.1 row 8 already describes the operator doing.

### C4 — The compare columns drop provenance. Blocking, integrity control.

§6.5's compare uses `[ CANDIDATE 01 ]` and `[ CANDIDATE 02 ]` as column headers. §6.4 makes
`[ PROVENANCE · … ]` "mandatory and adjacent to the candidate ID" in the diff header, with no
default and no third value, and suppresses the diff body entirely if it is missing. The
compare drops it.

That is the one frame a judge photographs. Under D-008 the rejected candidate may legitimately
be operator-supplied, and under the CTO's D-020 a model response may legitimately be a replayed
transcript — both are honest, and both are only honest if the label travels with the claim.
An unlabelled side-by-side is the exact failure D-008 exists to prevent, on the exact surface
where it costs most.

**Required.** Each compare column header carries the provenance chip directly beneath the
candidate ID, on the same terms as §6.4: exactly `MODEL-GENERATED` or `OPERATOR-SUPPLIED`, no
default, and `[ × PROVENANCE MISSING ]` in critical with the column body suppressed if absent.
Where D-020 applies, the chip reads `[ PROVENANCE · MODEL-GENERATED · REPLAYED <date> ]`.

### C5 — The Core's spoke order contradicts the state machine. Escalated to the CTO.

§7.1 fixes six phases clockwise from 12 o'clock:

`INGEST → ANALYZE → CORRELATE → STRESS TEST → REMEDIATE → VERIFY`

The architecture spec's transition table (§2.2) runs `BASELINE → TRIAGE → STRESS_TEST →
CORRELATE → PATCH → VERIFY`. STRESS_TEST executes **before** CORRELATE, so the wheel would
fill out of order: the CORRELATE arc completes after the STRESS TEST arc that sits
clockwise-after it. §3's wireframe timeline has the same inversion, listing `[ 05 ] CORRELATE`
above `[ 06 ] STRESS TEST` in a panel that is chronological by construction.

The designer is not at fault. `CLAUDE.md` lists the workflow as
"authorize → ingest → baseline → analyze → **correlate → stress-test** → patch → verify" and
calls it non-negotiable; the design follows it. The architecture spec inverts the last two,
and on the merits it has to: CORRELATE's job is to "bind the confirmed crash to a source
location", and a confirmed crash only exists after STRESS_TEST.

I am not resolving a conflict between a non-negotiable product rule and a draft architecture
spec. **CTO arbitrates**, per architecture §2.6 ("adding, removing or renaming a
`MissionState` … those are CTO calls"). Whichever order wins, §7.1's spoke order and §3's
timeline indices follow it, and it must be settled before the Core is built — the spoke order
is baked into an SVG geometry with fixed 60° arcs.

### C6 — `NOT_RUN` renders amber in the architecture spec and neutral in the design.

Architecture §5.4 specifies `NOT_RUN` in amber with its reason inline. The design system §2.6
and §5 specify the em dash in `--bd-text-secondary`, **never a state colour**, and amber is
`--bd-state-warning`.

Both cannot ship. This is the mechanism D-009 depends on, so it needs settling rather than
discovering.

**Ruling: the design system wins, in both surfaces.** A gate that was cut from the build by
decision is not a warning; it is a disclosed absence. Rendering it amber also collapses it
into `ERROR`, which architecture §5.4 renders amber too — and those are genuinely different
things ("we chose not to build this" versus "this broke"). Neutral secondary text with the
reason inline discloses just as loudly and keeps amber meaning what it means everywhere else.
This is a PM call under D-009 and D-023, and `cybersecurity` retains its veto on the
disclosure mechanism.

### C7 — Four things specified that are not P0.

Each is small on its own; together they are most of a shift on the two days the EM audit
already names as at-risk.

| Item | Where | Why it is not P0 |
|---|---|---|
| Diff truncation state, `[ ! TRUNCATED · 2000 OF 4118 LINES ]` + `[ DOWNLOAD FULL PATCH ]` | §6.4 | Unreachable by construction. P0-9 caps a candidate at one file and 25 changed lines, and architecture §4.2(9) evaluates policy from the diff text *before* verification, so a policy-failing diff never reaches a rendered gate matrix. Building a state for a 4118-line diff also implies a download endpoint that does not exist. |
| Unconfirmed-finding state and `[ FINDINGS · 1 · +2 UNCONFIRMED ]` header arithmetic | §6.3 | P0-8 requires a sanitizer-confirmed crash. Nothing in the seven-day pipeline produces an "observed but unconfirmed" finding — the harness runs under ASan. Crash dedup and clustering are P1-6. |
| Timeline virtualization above 200 rows with `[ … 148 EARLIER EVENTS ]` | §6.2 | The CTO's D-021 moved per-tick fuzz telemetry off the durable event stream entirely and §2.1 cut #31, so the row count this defends against no longer arrives. Real virtualization is a day. |
| `aria-live="polite"` regions and `role="alert"` | §9 | P1-10 (keyboard operability) and P2-11 (WCAG) are both in `CUT`. Contrast, visible focus, semantic elements and colour-never-alone genuinely are free and stay in P0 — the designer is right about those. A polite live region on a 200-row autoscrolling timeline is a real bug surface with no user in the loop: one named operator, desktop, in person. |

**Required.** Move all four to `CUT`, recorded in §11's table so the reasoning survives. Keep
the empty, loading, degraded, failed and render-error states — those are cheap and they are
what stop a blank panel from reading as "no findings".

### C8 — One copy string overstates.

§3's wireframe renders the ANALYZE stage sub-line as `semgrep — not run`. Semgrep is not cut
from *this run*, it is not built at all (#22, `CUT`). Naming it implies a configured tool that
declined to produce a finding, which is a slightly better story than the true one.

Architecture §2.5 already mandates the honest string for the `LOG` event: *"No static
analyzers configured in this build"*. **Required:** the stage row uses the same claim —
`no static analyzers in this build` — matching the document's own copy rule 2, "never claim
more than the tools proved".

### 1.2 The designer's question 5, answered

> *Is a second patch candidate guaranteed to exist at demo time, or is the two-column verdict
> compare conditional?*

**Guaranteed. Build it as the default rendering, not a conditional branch.**

PR #74 commits both candidates as static files:

```
demo/repositories/pktcfg/patches/candidate-a-correct-bounds-fix.patch
demo/repositories/pktcfg/patches/candidate-b-rejected-crash-only-fix.patch
```

Three things make the guarantee hold rather than merely being likely:

1. **Both candidates are files, not model output.** If the model produces nothing, both still
   exist. D-008 already authorizes injecting them as `OPERATOR_SUPPLIED` with mandatory
   labelling.
2. **Candidate B passes policy.** It is one hunk in one file, well inside the 25-line cap, so
   it reaches verification and produces a real `VerificationRecord` and a real gate matrix. A
   candidate that failed policy would produce no matrix to compare against.
3. **Architecture §2.3 already fans out.** The `PATCH` stage produces a *set* of
   `PatchCandidate` rows and `VERIFY` produces one record per policy-passing candidate. The
   two-candidate case is the schema's normal shape, not a special case.

The condition attached: the orchestrator must enqueue candidate B into the candidate set **on
the standard run**, not behind a second operator action. The D6 kill criterion is "a single
operator action produces both verdicts", and the CTO's §4.1 reordering puts #37/#38 on D4
specifically so both files are proven end to end before the model arrives.

Retain the single-column rendering as the **degraded** state, not the default: if only one
candidate exists the panel stays single-column with no empty second column, exactly as §4.1
row 8 already says. It should never be reached in the demo of record, and if it is, that is
information.

### 1.3 D-023's extension to the evidence report — accepted, with the mechanism corrected

> *Recommendation — as implemented, and extended to the exported evidence report so the UI and
> the artifact tell the same story. That extension is the PM's and the backend's to accept.*

**Accepted for `report.md` and every judge-facing surface. Rejected for `report.json`. And the
rule needs a third value it does not currently have.**

The principle is right and it is the same family as D-009 and D-010: if the screen says `—`
and the artifact says `0`, a judge comparing the screenshot to the bundle sees two different
stories, and the weaker one wins. Architecture §5.4 already mandates that all five gate rows
render in `report.md` with their reasons inline, so the report already has the convention —
this makes the glyph match.

Two corrections.

**`report.json` takes `null`, never an em dash.** The bundle is a serialized `EvidenceBundle`
against a frozen pydantic schema with `extra="forbid"` and typed fields. `"—"` where an
`int | None` lives is a type violation that makes the bundle unparseable as data and breaks
round-tripping. The JSON representation of not-measured is `null` plus a sibling `*_reason`
string; the renderer turns that pair into `—` and its reason for `report.md`. Same truth, two
correct encodings.

**There are three states, not two.** The design has "not measured" (`—`) and "measured zero"
(`0`). The build has a third: **not applicable**. `ResourceUsage.gpu_seconds` is the case —
under D-015 there is no GPU, so the value is neither unmeasured nor a measured zero, and the
CTO's condition 3.1 already says it must not render as `0`. Rendering it `—` would tell a
judge we failed to measure our own GPU usage, which is a worse claim than the truth.

**Required:** one new glyph token and one new bracket form.

| State | UI | `report.md` | `report.json` |
|---|---|---|---|
| Not measured / not run | `[ — STATIC DELTA · NOT RUN ]` | `NOT RUN   cut from the seven-day build (P1-2)` | `null` + `reason` |
| Measured zero | `[ FINDINGS · 0 ]` | `0` | `0` |
| Not applicable | `[ n/a GPU SECONDS · NO GPU LEASED ]` | `not applicable (no GPU was leased for this run)` | `null` + `reason: "no GPU leased (D-015)"` |

Adding the glyph is a token change under §2.1's own discipline, recorded as D-025.

### 1.4 Two smaller notes, not conditions

- §4.1 row 9's export chip reads `[ + EXPORTED · report.md · report.json ]`. Architecture §5.3
  writes a directory and a `.tar.gz` containing five files plus `artifacts/`. Naming two
  understates what the judge is handed. Prefer the bundle path: `[ + EXPORTED · <path> ]`.
- The wireframes use `libparse@a4f1c9` and `ctest 42/42`. The target of record is `pktcfg` with
  **8** CTest cases, so the real baseline is `8/8` and candidate B's rejection is `7/8` with
  `test_tab_expansion` named. Illustrative numbers in a wireframe are fine; they should not
  survive into the built components or into #64's acceptance criteria.

---

## 2. #64 — acceptance criteria for the minimum viable demo

The full issue body is written out separately and is the artifact. Summarised here.

Each of the nine steps gets an observable pass condition, what is on screen at that moment, a
time budget, and a defined overrun behaviour. Two budget profiles, differing in exactly one
policy value:

| Profile | Total | Purpose | `fuzz_seconds` |
|---|---:|---|---:|
| Unattended | **28:00** | The D7 gate (#50). Runs start to finish with no operator. | 600 |
| Narrated | **20:00** | The finale run, with the operator talking over it. | 240 |

A run that completes but exceeds its profile by more than 25% is a **gate failure**, not a
pass with a note. A demo that overruns its slot is a demo that does not finish on stage.

Three properties hold across every step, and they are what make these criteria testable rather
than aspirational:

1. **Every overrun has a defined outcome that is not "try again".** `deadline_at` is mandatory
   at enqueue (architecture §3.3), and `TIMED_OUT` is a result rather than a failure (§6.3).
2. **Verification is never retried.** `max_attempts = 1` on `VERIFY`. Retrying a verification
   is how a flaky pass becomes a verdict.
3. **Every claim follows a receipt.** Teardown is reported from `TEARDOWN_CONFIRMED`,
   reproducibility from `successes == attempts`, and the terminal mission state from a
   persisted `VerificationRecord` once the CTO's §6.2 fix lands.

**One input I do not have.** The finale slot length is unknown. The narrated profile assumes
at least 20 minutes of demonstration time. If the real slot is shorter, the fuzz step is the
only knob, and below roughly 12 minutes the discovery step has to move to the recorded
fallback and the live run starts from the committed reproducer. That is a claim change, so it
is the CEO's and the competition-strategist's, not mine. Raised in §7.

---

## 3. #61 — the benchmark case set

`13-success-metrics.md` asserts ≥80% confirmed-finding precision, ≥50% verified patch rate,
≤30 min to first confirmed finding and ≤30% Tier 3 escalation, with no case list and no
denominator anywhere in the pack. The CEO seat's §6.1 called this out; D-010 already rules
that unmeasured targets are not published.

Defining the set is the part that was missing. The full definition is in the #61 issue body;
the shape is:

**Eight cases across three groups, on one target.**

| Group | Count | What it is the denominator for |
|---|---:|---|
| Defect | 1 | Finding precision, time-to-finding |
| Candidate | 4 + 10 model attempts | Verified-patch rate, policy enforcement, the D6 supporting threshold |
| Control | 3 | Precision's false-positive opportunity — without negatives, precision is not a number |

The control group is the part the pack never had and the reason its precision figure is not
falsifiable. A precision metric measured only on cases where a defect exists has no way to be
wrong. BD-002 is a clean tree where the correct answer is "no finding", and it is free: it is
the same target with candidate A applied.

**The ruling that follows, and it will be unpopular.** At N=1 defect, **no percentage in
`13-success-metrics.md` is publishable**. Per D-010 every row becomes "target — not measured".
A precision figure over a denominator of two is not a benchmark, and a judge who asks
"measured on what?" gets an answer that is worse than not having quoted it.

What we can defend, and should say instead:

> On our controlled target, the pipeline found the seeded heap-buffer-overflow, verified the
> correct patch, and rejected the crash-only patch, reproducibly across N consecutive runs.

That is a claim with a denominator we actually have, and it is the claim the demo makes
anyway. Every case carries a required artifact so QA can check it rather than take it on
trust.

If the D8–11 buffer survives, §5.4 option B (a real open-source C library pinned to a
CVE commit) adds BD-005 and moves the precision denominator to three. Worth attempting;
not worth promising.

---

## 4. #62 — risk register owners and triggers

`15-risk-register.md` states its purpose as tracking risks "with owners and mitigations" and
has neither an owner column nor a threshold at which any mitigation fires. Eleven rows, all
unowned.

The full table is in the #62 issue body. Four things about its shape.

**Every trigger is a command, a query, or a grep.** "Watch for X" is not a trigger. Row 5
(patch overfits reproducer) fires when `ctest -L asymmetry` *passes* with candidate B applied,
because that means somebody weakened the test pktcfg's README explicitly warns against
weakening. Row 9 fires when a terminal mission has no `TEARDOWN_CONFIRMED` with
`released = true`. Row 10 fires on a grep for "air-gapped" across judge-facing artifacts.

**Rows a day gate already covers cross-reference it rather than duplicating.** Rows 3 and 4
point at the D3 (#21) and D5 (#48) gates and at the kill criteria in §4 of the P0 cut. A risk
row that restates a gate in weaker language is how two sources of truth start.

**Two rows are retired rather than owned.** Row 1 (Kimi K3 capacity) and row 2 (adapter
tuning) were made moot by D-015 and P2-1. Row 1 does not disappear entirely — it converts into
a *claim* risk with a grep trigger, because the model name must not reach judge-facing
material before the spike has run (P0 cut §6.4). Row 2 is genuinely gone; recording it as
retired is more honest than assigning an owner to watch nothing.

**Three rows are added.** The register predates the seven-day build and is missing its top
three risks, all named in the CTO's §7: the CPU-served model failing the 3-of-10 threshold,
SSE wedging the API under ASGI, and a mission reaching terminal `VERIFIED` with no
verification record. Added and marked as PM-added, with owners and triggers on the same terms.

Owners are Raunak for anything inside the pipeline, the sandbox or the target, and Mahatav for
anything in the API, the UI, the evidence bundle or the judge-facing claim. That split follows
the EM audit's §2.2 ownership and the shift direction, so no trigger fires on the wrong side of
a 12.5-hour handoff.

---

## 5. #63 — does `git bisect` stay cut?

**Recommendation: yes, it stays cut for the seven-day build — and the seeded git history gets
authored on D1 anyway.** CEO arbitrates.

The reasoning, since a shrug was explicitly not acceptable.

**What losing it costs.** Demo scenario 2, and the git-aware root-cause localization claim on
slide 4. It also leaves the `ANALYZE` phase of the Core doing nothing: architecture §2.5 is
blunt that `TRIAGE` "runs and finds nothing, by construction" once Semgrep (#22), compiler
diagnostics (#23), bisect (#24) and git history (#26) are all cut. One of six spokes on the
most visible element of the product lights up having performed no work. That is a real cost
and it is larger than the P1 ranking implies.

**What reinstating it costs, and here is the part nobody has priced.** The target as shipped
in PR #74 documents no seeded history and ships no history-seeding tooling — the defect is
described as living in `src/decode.c:75-77`, with no commit named, and the README's layout
listing has no such script. **So bisect currently has no right answer to find.** Reinstating
it is not one job, it is two:

| Half | Cost | Reversible? |
|---|---|---|
| Seed a plausible history in `pktcfg` where the sizing-pass omission is introduced at a known commit, with enough surrounding commits that a bisect is non-trivial | ~1 hour of Raunak's D1 target work | **No.** It changes the commit graph, and therefore the snapshot hash. |
| Build the runner: `git bisect run` driving the committed reproducer against each build | ~half a day, on D5–D6 | Yes |

The runner is cheap *given* a working reproducer and a working build adapter, both P0, both
landing D3/D5. But it lands on Raunak, on the two days he is already the bottleneck on both
gates, behind the reproducer that D5 exists to produce. That is the wrong place to put an
optional day.

**The asymmetry is the whole recommendation.** The irreversible half is an hour and the
expensive half is deferrable. If the history is seeded on D1, reinstating bisect during the
D8–11 buffer is a runner and a report line. If it is not, reinstating it during the buffer
means rewriting the target's commit graph — which invalidates the snapshot hash in every
recording and every evidence bundle produced up to that point, on the days reserved for
reliability. That is the change that eats a buffer day, and it is avoidable for an hour now.

So: keep the capability cut, take the cheap irreversible half now, and pre-position bisect as
**first item back from `CUT`** if D7 passes — ahead of Semgrep and renewed fuzzing, because it
is the only one of the three that buys a novelty claim rather than a stronger gate.

**One input I do not own, and it could flip this.** The shortlisting criteria reward novelty,
and shortlisting may happen before the finale. If slide 4's git-aware claim is load-bearing
for getting shortlisted at all, the calculus changes — a P1 item that gates entry is not a P1
item. That is a competition-strategy judgement resting on #2 and #3, both still open with the
CEO. Named in §7.

**If the CEO reinstates it**, the honest scope is: history seeded on D1, runner on D6 end of
shift as an overnight job (it is wall-clock-bound and fits the L-series pattern), no new UI
panel — a stage-timeline row and the first-bad-commit string in the export. `GitBisectTimeline`
and the commit timeline stay cut; they were correctly cut on their own merits.

---

## 6. The two engineering-manager findings

### 6.1 Fallback recording, D7 → rolling from D5 (#49) — CONFIRMED, with the shape sharpened

The EM audit's §1.2(b) is correct and the reasoning is D-011's own: the insurance policy must
not sit in the slot most likely to be compressed. The seven-day plan then put #49 on D7,
*behind the gate it insures against*, which is precisely what D-011 was written to prevent.
The CTO reached the same conclusion independently in §4.3 and landed on "end of D6".

They are both right about different things, and the disagreement is worth resolving rather
than averaging. A capture taken at D5 is not yet insurance — the fallback has to show a
verdict, and no verdict exists before D6. So:

| Capture | Contains | Standing |
|---|---|---|
| End of D5 | Steps 1–4: authorize, baseline, sanitizer-confirmed finding, 5/5 replay | A playable file exists. **Not yet the fallback.** |
| End of D6 | Steps 1–7, including both verdicts side by side | **The fallback of record.** If D7 fails, this is the entry. |
| End of D7 | All nine steps including export and teardown | Supersedes D6's capture **only if complete.** A partial D7 re-record never replaces a complete D6 one. |

That gives #49 three dated acceptance criteria and a named artifact at each, rather than
"rolling". The EM's sequencing is confirmed; the CTO's "the one that counts is D6" is folded
in as the standing column.

**Scope impact: none.** This is a sequencing call inside an already-approved P0 item (P0-15),
so it does not need CEO sign-off on budget or date. It does change one thing: D5 stops being
Mahatav's idle day, which the EM audit §2.4 already identified as 14% of the schedule going
to waste.

D-011 requires `cybersecurity` to review the recording before it leaves the machine. Three
captures do not need three reviews. **Rule: review the one that ships**, and only that one.

### 6.2 Reproducer → permanent regression test (P1-5) — stays a fixture, with the shape specified

P1-5 hedges with "when practical". PR #74 makes it look practical: `tools/pktcfg_replay.c` is
already a deterministic reproducer runner taking a file and a repeat count, so a committed
CTest case is one line of CMake:

```cmake
add_test(NAME test_repro_literal_tab
         COMMAND pktcfg_replay ${CMAKE_SOURCE_DIR}/crash/crash-literal-tab.bin 5)
```

**Do not add that line.** It would kill the demo at step 3.

At baseline, pktcfg has the defect. A committed reproducer test fails at baseline. Architecture
§6.2 is non-negotiable that any `ctest` failure on the pristine tree is `BASELINE_FLAKY` →
mission `FAILED`, "because without a green baseline, 'regression preserved' has no denominator
and every downstream verdict is meaningless". So the test can only exist *after* a patch lands,
and the baseline is measured *before*. A static fixture in the target cannot be both.

That is what the "when practical" hedge was concealing, and it is the reason to rule rather
than leave it to whoever gets there first at 03:00.

**Ruling.** The reproducer stays a fixture in the target, exactly as PR #74 ships it. The
regression-test conversion becomes an **export-time artifact**, not a committed one: when a
candidate reaches `VERIFIED`, the export step emits the reproducer as a ready-to-apply CTest
case into `artifacts/regression/` — the minimized input plus a one-hunk patch adding the
`add_test` line. The report claims exactly what QA can check with two `ctest` runs:

> The minimized reproducer is emitted as a regression test. It fails against the pre-patch
> tree and passes against the verified tree.

**It stays P1, not promoted.** The evidence for that claim already exists without the artifact:
the verifier re-runs the reproducer as the `REPRODUCER_ELIMINATED` gate, so the pre-patch
failure and post-patch pass are already in the gate matrix. The emitted file is packaging, and
packaging does not go on the critical path of a seven-day build. Specifying the shape now
means that if the buffer survives it is a two-hour job rather than a design conversation.

**And a standing prohibition, because this one is a trap someone will walk into:** the
reproducer is never added to `pktcfg`'s committed CTest suite. A reviewer rejecting that
change does not need to argue the point.

---

## 7. Decision records

For the orchestrator to fold into `.project/decisions.md`. This document does not edit that
file — four agents are live.

**A numbering collision to resolve first.** `.project/decisions.md` already contains
D-019…D-023 from the `ui-ux-designer` seat. The CTO review's §8 proposes a different
D-019…D-022. Both cannot be right. Mine start at D-024, the next free number in the committed
log; the CTO's four need renumbering when they land. The orchestrator owns the log and owns
that call.

### D-024 · The two-candidate verdict compare is guaranteed, and renders at overlay width

**Decision** — A second patch candidate is guaranteed at demo time, so the side-by-side
Verified/Rejected compare is the default rendering rather than a conditional branch. It renders
on the 1328px overlay surface in two 652px columns, not in the 608px centre column. Each column
carries its candidate's provenance chip and its complete five-row gate matrix.

**Options considered** — (a) keep it conditional as `04-design-system.md` §6.5 specifies;
(b) guarantee it and keep the 292px split in the centre column; (c) guarantee it and move the
compare to the overlay.

**Pros and cons** — (a) leaves the competition differentiator dependent on a branch nobody has
proven, and PR #74 has already removed the uncertainty by committing both candidates as files.
(b) takes the guarantee but keeps an unbudgeted layout: "Verified" at 72px in a
high-contrast serif is within a few pixels of 292px, and five gate chips do not stack in the
124px the region budget allows. It also leaves the contradiction that `[ OPEN DIFF ]` opens an
overlay covering the panel meant to be comparing. (c) resolves all three for one re-anchoring
of a component §6.5 already specifies at overlay width.

**Cost implications** — none. The compare component was going to be built either way; this
changes where it mounts.

**Security implications** — none directly. It carries an integrity control: the provenance chip
per column is mandatory under D-008, and this is the frame most likely to be photographed.

**Scalability implications** — the fan-out in architecture §2.3 already produces N candidates
and N verification records. Beyond two, the compare paginates rather than subdividing.

**Recommendation** — (c), with the single-column rendering retained as the degraded state that
should never be reached in the demo of record.

**Final approval authority** — PM for the scope call (it widens a user-facing surface within
P0-13); CTO if the frontend disputes buildability.

### D-025 · The not-measured rule extends to `report.md`, not to `report.json`, and gains a third value

**Decision** — D-023's em dash extends to `report.md` and every judge-facing surface.
`report.json` encodes not-measured as `null` plus a sibling reason string, never a glyph. A
third state, **not applicable**, is added for structurally-absent measurements such as
`ResourceUsage.gpu_seconds` under D-015.

**Options considered** — (a) reject the extension and let the report keep its own convention;
(b) accept it uniformly across both report formats; (c) accept for the human-readable artifact,
encode correctly in the machine-readable one, and add the missing third value.

**Pros and cons** — (a) leaves the screen saying `—` and the bundle saying `0` for the same
fact, and a judge comparing the two believes the weaker one. (b) puts `"—"` where the frozen
`EvidenceBundle` schema declares `int | None`, which breaks round-tripping and makes the bundle
unparseable as data — the exact artifact whose parseability is its value. (c) keeps one truth
in two correct encodings, and closes a gap neither D-023 nor the CTO's condition 3.1 covers on
its own: rendering `gpu_seconds` as `—` claims we failed to measure it, when the truth is there
was nothing to measure.

**Cost implications** — one glyph token, one bracket form, and a `*_reason` field alongside
each nullable measurement. Hours.

**Security implications** — an integrity control of the same family as D-008, D-009, D-010 and
D-023. A panel or a report line rendering an unproduced value as `0` is a finding for the
`cybersecurity` seat when it reviews judge-facing output.

**Scalability implications** — none.

**Recommendation** — (c). Also settles the live contradiction between architecture §5.4
(`NOT_RUN` in amber) and design system §2.6 (`NOT_RUN` never in a state colour) in favour of
the design system, in both surfaces: a gate cut by decision is a disclosed absence, not a
warning, and amber already means `ERROR`.

**Final approval authority** — CEO for the product rule, consistent with D-010 and D-023;
`cybersecurity` retains its veto on the disclosure mechanism under D-009.

### D-026 · The nine-step demo has two time-budget profiles, and an overrun is a gate failure

**Decision** — The minimum viable demo carries per-step budgets summing to 28:00 unattended
(the D7 gate, #50) and 20:00 narrated, differing only in `MissionPolicy.fuzz_seconds`
(600 / 240). A run that completes but exceeds its profile by more than 25% fails the gate.

**Options considered** — (a) no budget, which is the status quo and the reason #50 has no pass
condition; (b) one budget; (c) two profiles with a single knob between them.

**Pros and cons** — (a) leaves the D7 gate undefined, which the CTO named as blocking.
(b) forces one number to serve an unattended overnight run and a narrated stage run, which have
genuinely different constraints. (c) keeps one set of criteria and one variable, so the two
runs cannot drift apart, and `fuzz_seconds` is already a `MissionPolicy` field feeding the
mandatory `deadline_at`.

**Cost implications** — none. Both numbers are policy values.

**Security implications** — none. Note that these are budgets, not measurements: under D-010
neither figure appears in judge-facing material as a performance claim.

**Scalability implications** — none.

**Recommendation** — (c). The finale slot length is an unresolved input; below roughly 12
minutes the discovery step moves to the recorded fallback, which is a claim change and the
CEO's.

**Final approval authority** — PM for the criteria; CEO for any claim change arising from the
slot length.

### D-027 · The benchmark case set is one defect, four candidates and three controls, and no percentage is published

**Decision** — The benchmark set is eight named cases on `pktcfg`, plus a ten-attempt model
run. Every metric row in `13-success-metrics.md` is relabelled "target — not measured" under
D-010; no percentage is quoted in judge-facing material at this denominator.

**Options considered** — (a) leave the metrics as they are; (b) define a set large enough to
support the stated percentages; (c) define the smallest honest set and publish the reproducible
claim instead of a percentage.

**Pros and cons** — (a) is what the pack does and it is unfalsifiable, which the CEO seat
already called out and `source-and-feasibility-notes.md` already demanded be fixed. (b) needs
five to ten real defects with harnesses; that is weeks, and it is the eight-week plan the
seven-day plan replaced. (c) gives every metric a real denominator, adds the control group the
pack never had — without negative cases, precision has no opportunity to be wrong — and
replaces four unquotable percentages with one reproducible claim.

**Cost implications** — low. BD-002 is the same target with candidate A applied; BD-003 and
BD-004 are two hand-authored patches of a few lines each.

**Security implications** — none directly; it is the same publication discipline as D-010.

**Scalability implications** — the set is designed to grow. Adding option B from §5.4 moves the
precision denominator from two to three without changing any harness.

**Recommendation** — (c).

**Final approval authority** — PM for the case set; CEO for the publication rule, under D-010.

### D-028 · Fallback capture rolls from D5, and the fallback of record is the D6 capture

**Decision** — #49 becomes three dated captures: D5 (steps 1–4, a playable file exists), D6
(steps 1–7 including both verdicts — **the fallback of record**), D7 (all nine steps,
superseding D6 only if complete). `cybersecurity` reviews only the capture that ships.

**Options considered** — (a) D7 as the seven-day plan has it; (b) end of D6, per CTO §4.3;
(c) rolling from D5, per EM §1.2(b); (d) rolling from D5 with the D6 capture named as the one
that counts.

**Pros and cons** — (a) puts the insurance behind the gate it insures against, which is exactly
what D-011 exists to prevent and which survived only because nobody re-read D-011 when the
schedule was rebuilt. (b) is correct about which capture is insurance and leaves D5 idle, which
the EM audit costs at 14% of the build. (c) fixes the idle day but calls a verdict-less capture
a fallback, which it is not. (d) takes both: the D5 capture is real work with a real artifact,
and the D6 capture is the one that would actually be submitted.

**Cost implications** — roughly half a day, spread across three days instead of concentrated on
the most compressed one. Net neutral to positive, since it fills an idle shift.

**Security implications** — the recording must contain no credentials, no provider console
detail and no target source beyond what the bundle already exposes. One review, on the capture
that ships.

**Scalability implications** — none.

**Recommendation** — (d). This confirms the engineering-manager's scope call and folds in the
CTO's correction.

**Final approval authority** — PM (sequencing inside an approved P0 item; no budget or date
change, so no CEO sign-off required).

### D-029 · The reproducer is emitted as a regression test at export, never committed to the target

**Decision** — P1-5 stays P1. The minimized reproducer remains a fixture in `pktcfg`. On a
`VERIFIED` verdict the export step emits it as a ready-to-apply CTest case into
`artifacts/regression/`. It is never added to the target's committed CTest suite.

**Options considered** — (a) commit it as a permanent CTest case in the target, which PR #74
makes a one-line change; (b) leave it a fixture and drop the P1-5 claim; (c) fixture in the
target, emitted artifact at export.

**Pros and cons** — (a) **breaks the demo at step 3.** The defect is present at baseline, so a
committed reproducer test fails at baseline, and architecture §6.2 makes any baseline `ctest`
failure terminal — deliberately, because a red baseline leaves "regression preserved" with no
denominator. The one-line change is a demo-killer wearing the costume of good hygiene. (b) is
safe and gives up a genuinely strong artifact. (c) gets the artifact without touching the
baseline, and produces a claim QA verifies with two `ctest` runs.

**Cost implications** — a template and one file write, in the export step. Stays P1, so it is
buffer work, not critical path.

**Security implications** — none. The emitted patch and input are already in the bundle.

**Scalability implications** — none. It generalizes to any target with a reproducer runner.

**Recommendation** — (c), plus a standing prohibition on (a) that a reviewer can enforce
without argument.

**Final approval authority** — PM (priority call inside an existing P1 item).

### D-030 · `git bisect` stays cut; the seeded history is authored on D1 regardless

**Decision** — Recommend that P1-1 stays in `CUT` for the seven-day build, that the seeded git
history in `pktcfg` is authored on D1 anyway, and that bisect is first back from `CUT` if D7
passes. **CEO arbitrates.**

**Options considered** — (a) reinstate bisect now; (b) keep it cut entirely and do nothing;
(c) keep the capability cut, take the irreversible cheap half now.

**Pros and cons** — (a) costs roughly a day and a half and lands on Raunak across D5–D6, the
two days he is already the bottleneck on both gates, behind the reproducer D5 exists to
produce. (b) is the status quo and quietly forecloses the option: the target as shipped in
PR #74 documents no seeded history, so after D1 adding one rewrites the commit graph and
invalidates the snapshot hash in every recording and bundle produced to that point — a
buffer-day change made during the days reserved for reliability. (c) separates an hour of
irreversible work from a day of deferrable work and keeps the option open at almost no cost.

**Cost implications** — about one hour on D1. Reinstatement during the buffer then costs half a
day rather than a day and a half.

**Security implications** — none.

**Scalability implications** — none.

**Recommendation** — (c). One input could flip it: if the git-aware novelty claim on slide 4 is
load-bearing for *shortlisting* rather than for the finale, a P1 item that gates entry is not a
P1 item. That rests on #2 and #3, both open with the CEO.

**Final approval authority** — **CEO**, per issue #63 and `.project/state.md`.

---

## 8. What I am escalating

| Item | Why it is not mine | Owner |
|---|---|---|
| C5 — the Core's spoke order contradicts the state machine, and `CLAUDE.md`'s non-negotiable workflow contradicts architecture §2.2 | A `MissionState` ordering change is a CTO call under architecture §2.6; `CLAUDE.md`'s workflow is a stated non-negotiable I do not override | **CTO**, then CEO if `CLAUDE.md` needs amending |
| #63 — whether bisect returns | Named as a CEO decision in `.project/state.md`; recommendation given in §5 | **CEO** |
| The finale slot length, and whether the narrated profile fits it | A competition input, and below ~12 minutes it becomes a claim change | **CEO** / competition-strategist |
| Whether slide 4's git-aware novelty claim is load-bearing for shortlisting | Competition strategy, resting on #2 and #3 | **CEO** / competition-strategist |
| The presentation claim for a replayed model response (CTO D-020) | Already escalated by the CTO; I concur, and #64 step 5 assumes it is resolved in favour of explicit labelling | **CEO** |
| D-019…D-023 numbering collision between the designer's records and the CTO's proposed ones | The orchestrator owns `.project/decisions.md` | orchestrator |
| Whether the reduced gate matrix is acceptable for the finale | D-009 rules on disclosure; the mechanism veto is not mine | **cybersecurity** |

---

## 9. What I did not do

- **No GitHub issue, PR or review comment was posted from this seat, and no commit was made.**
  This session had file read/write only: no `gh`, no `git`, no shell. The issue bodies, the
  PR #70 review comment and the branch/commit/PR steps are prepared as files for a re-run with
  shell access. Same constraint the engineering-manager seat hit and recorded in `07`'s §0.
- No code was run, no test was executed, and nothing in this document claims otherwise. Every
  behaviour asserted about `pktcfg` is read from its committed source, its README, and its two
  committed patch files.
- `.project/decisions.md`, `15-risk-register.md`, `13-success-metrics.md`, the `docs/` pack and
  every other seat's deliverable are unedited.
