# The Fallback Ladder

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Document | What we switch to, when we switch, and what we may claim once we have |
| Author | `competition-strategist` seat |
| Date | 2026-08-07 (D2) |
| Issue | [#84](https://github.com/Mahatav/brahmadatta-ai/issues/84) |
| Status | Active for the triggers. Presentation wording in §6 is flagged for the CEO and not decided here |
| Reads with | [`03-seven-day-plan.md`](03-seven-day-plan.md) · [`01-vision-and-p0-cut.md`](01-vision-and-p0-cut.md) §3, §4 · [`../10-competition/36-hour-finale-runbook.md`](../10-competition/36-hour-finale-runbook.md) |

## Why this exists

The CEO's instruction on 2026-08-07 was to build D1–D7 in full **and** build a fallback behind
every stage that might not work. Those fallbacks are now issues — #81, #82, #83, #49. What was
missing is the thing that makes them usable: a decision, taken in daylight, about when to reach
for one.

At hour 30 of a 36-hour finale, on no sleep, nobody makes a good call about whether to abandon
live fuzzing. So the call is made here, and every trigger below is a fact somebody exhausted can
check in ten seconds and get the same answer from that anyone else would.

The second half of this page matters at least as much. **Every rung down this ladder shrinks a
claim.** The gates stay real in every mode — what changes is provenance. A replayed model
response is not inference happening in the room. A replayed reproducer is not a fuzzer
discovering a bug. The sentence that goes with each mode is written down so that nobody has to
invent one on stage.

## 0. How to use this on the day

- **Triggers are facts, not judgements.** Read the trigger column. If it fired, switch.
- **The operator on shift switches.** No consultation, no waiting twelve hours for the other
  timezone. Log the switch and the time on the mission log.
- **Rungs do not go back up inside a run.** If discovery fell back at minute 20, the fuzzer does
  not get restarted at minute 50 because it started behaving. One mission, one provenance.
- **Every switch changes a sentence.** The sentence is in the table. Say that one.

---

## 1. The ladder

| Stage | Primary | Fallback (built by) | Trigger — observable and time-boxed | Claim in primary mode | Claim in fallback mode |
|---|---|---|---|---|---|
| **Authorize and ingest** | Operator authorizes in the Command Center; mission reaches `INGESTED`; snapshot SHA-256 recorded and matching the frozen release manifest | **None, deliberately** (§2.1) | Not `INGESTED` within **5 min** of the Authorize action, or snapshot hash ≠ manifest → one restart, capped at 5 more min | "The operator authorized this repository. This is its snapshot hash." | — second failure is a stop condition (§3) |
| **Baseline** | Cold start → `BASELINE_PASSED` with real `ctest` counts from the run | **None, deliberately** (§2.1) — one restart is a retry, not a fallback | `BASELINE_PASSED` not reached within **15 min** of mission start, or any `ctest` failure on unmodified source → one restart, same 15-min box | "N passed, 0 failed, from this run, recorded in the evidence bundle." *(N is read off the run; if it was not recorded we do not say it — D-010)* | Identical. A restart changes nothing about what ran |
| **Isolation** | **#15** — container with `--network none`, fixed non-root uid, `--cap-drop ALL`, `no-new-privileges`, `--read-only`, runtime memory/CPU/pids limits, teardown receipt | **#81** — subprocess jail: working-directory jail, CPU/memory/wall-clock limits, process-group kill, cleanup on every exit path | At **pre-flight**, the egress smoke check (start container on the frozen image → DNS + TCP attempt from inside → expect refusal → teardown → `docker ps -a` empty) fails **twice inside 10 min**. **Decided in hours 0–3; no switch after hour 3** (§2.2) | Name the runtime that actually ran, and show the egress test output. Never "rootless" unless Podman rootless is what ran (#15 condition 8) | "Build and tests ran in a working-directory jail with CPU, memory and wall-clock limits, killed as a process group on timeout. That is process-level containment, not a container — and we did not run the fuzzer under it." |
| **Discovery** | libFuzzer campaign on `pktcfg_fuzz_one_input` from `corpus/`, producing a sanitizer-confirmed heap-buffer-overflow with a stack trace | **#83** — mission starts from the stored reproducer `crash/crash-literal-tab.bin`; the fuzz stage renders **skipped**, never passed | Any one of: (a) the `-DPKTCFG_FUZZ=ON` build produces no `pktcfg_fuzz` binary → switch immediately, no waiting; (b) **20 minutes of accumulated fuzz time** with no sanitizer-confirmed crash — read the campaign's own elapsed counter, not the wall clock; (c) isolation is in #81 mode → switch before starting (rule **C1**) | "Our fuzzing campaign reached this defect in N minutes from a seeded corpus. Here is the ASan report." | "This mission started from a stored reproducer. Our harness confirms it and reproduces it 5 out of 5 from a clean build. The fuzzing stage did not run here — the timeline shows it skipped." Never "our fuzzer found it" |
| **Patch generation — rung 2** | Live CPU inference from the self-hosted small model | **#82** — recorded-transcript replay, same code path and schema | **3 generation attempts or 10 minutes wall-clock, whichever comes first**, with no candidate that passes patch policy and compiles. The trigger does **not** switch the system — it tells the operator to choose, and the operator sets replay mode by hand (§2.3) | "This patch was generated here, now, by our self-hosted model on this machine's CPU. No repository content left the machine." | **"Model output recorded &lt;date&gt;, replayed"** — the mandated string, in the UI and the exported report. Spoken: "a recorded response from the same model and the same prompt, captured on &lt;date&gt;. Replayed, not generated now. The gates you are about to watch ran live against it." |
| **Patch generation — rung 3** | **#82** replay | **Operator-supplied candidate** under D-008, from `demo/repositories/pktcfg/patches/` (shipped in #74) | Replay does not resolve a policy-passing candidate: transcript absent, `transcript_sha256` mismatch, or schema-version mismatch. One command, one answer — no time box needed | *(as rung 2)* | **"Operator-supplied candidate"** — never "model-generated", in the UI, the report and the narration. Spoken: "we wrote this one, not the model. What matters here is what the system does with it: the identical policy and verification pipeline." |
| **Verification** | Fresh worktree → rebuild → minimized reproducer → full regression suite → gate matrix → both verdicts | **None, by design** (§2.4) | Both verdicts not produced within **20 min** of the first candidate being applied → one retry from a clean worktree → still nothing is a stop condition (§3) | Enumerate the gates that ran **and name the ones that did not** (D-009). Static delta and renewed fuzzing are in `CUT` (#22, #40), so the matrix is compile / reproducer-eliminated / regression-preserved, and we say the other two did not run | — |
| **Observability (the Core and the timeline)** | Live SSE through nginx into the Command Center | **None that may be shown** (§2.5) | `infrastructure/scripts/smoke-sse.sh` does not stream through the finale stack at pre-flight; **or** the timeline stops advancing for **90 s** while the mission log continues (D-022: a stale stream freezes the display, it does not invent progress) | "The panels are following the run." | Narrate from the exported bundle and the terminal, or present #49 — **CEO call, §6** |
| **Teardown** | Teardown receipt in the UI at mission end; no containers left (#15, #72, Arch §2.2 R3) | Operator runs the documented teardown command and shows the empty container list in the terminal | Receipt not shown within **60 s** of the mission reaching a terminal state, or any container from the run still listed | "The system tore this down itself and recorded a receipt." | "Teardown was run from the command line and confirmed here. The UI receipt did not render." GPU lease reads **"not applicable — no leased GPU"**, never `0` (D-015) |
| **The live run** | The nine steps of the minimum viable demo, unattended (#50) | **#49** — the rolling recording. The D6 capture is the fallback of record; the D7 capture supersedes it only if complete | Any stop condition in §3; **or** the run has not reached step 6 — the first verdict — by **hour 31**, which is the runbook's evidence-and-polish boundary | "You are watching this happen now." | "A recording of a complete run from &lt;date&gt;. Nothing in it is staged or re-shot; where a stage failed we re-ran it. Here is that run's evidence bundle, and here is the repository." Opening framing **flagged, §6** |

---

## 2. The rows that need more than a cell

### 2.1 Ingest and baseline have no fallback, and that is the decision

There is no issue behind these two rows because none is proposed. A second baseline failure
inside fifteen minutes does not mean the baseline needs a gentler path — it means the
environment is wrong, and no fallback repairs a wrong environment on the day. The honest
response is the recording.

The P0 cut's week-2 contingency (shrink the target to one `.c` file, hardcode the build recipe)
is a *build-phase* cut, taken days earlier when there is still time to change the target. It is
not available at hour 3 of the finale. Anyone reaching for it on the day is starting a new
project.

### 2.2 Isolation is decided before the clock, and it decides discovery

This is the one rung that must be settled at pre-flight rather than when it bites, because it
constrains what the rest of the run is allowed to do. #81 says so in its own acceptance
criteria: a working-directory jail is **not** sufficient to run untrusted fuzzing, and #15 is
required before #28 runs. So a finale in #81 mode is a finale with no live fuzz campaign in it.

Two wording traps live here, and both have already been walked into once in this project:

- If Docker was substituted for rootless Podman, the result is **never** described as
  "rootless". That is condition 8 on #15, and `cybersecurity` accepted the substitution on
  exactly that basis.
- We do not say the system "cannot reach the internet". We say egress is denied by network
  topology on the sandbox, and we show the DNS-plus-TCP test output. The stronger sentence was
  corrected once already; it does not come back.

### 2.3 The model rung fires a decision, not a switch

#82 is explicit that replay mode is an operator choice and never a silent fallback on timeout.
That is deliberate and it is worth understanding rather than working around. A system that
quietly degrades to replay under load is a system that can present a recorded response as live
inference without anybody choosing to — which is the exact failure this whole page is written to
prevent.

So the trigger's output is a prompt to a human: three attempts or ten minutes, then decide. The
operator flips replay mode by hand and the provenance fields follow from that action.

**Candidate B is operator-supplied by default.** The rejected-patch case has been an
operator-supplied fixture since D-008, and the fixture is checked in at
`patches/candidate-b-rejected-crash-only-fix.patch`. That is the plan, not a fallback, and it
carries the "operator-supplied candidate" label in every mode including full-live.

### 2.4 Verification has no fallback because verification is the claim

Every other rung on this ladder trades provenance for reliability. Verification is not
provenance. It is the thing being claimed — that a patch is accepted by tools rather than by a
confidence score. A demo that shows a verdict the gates did not produce is the single failure
this project cannot survive, and there is no version of it that is worth the twenty minutes it
would save.

If the gates cannot run twice in a row, we show the recording of a run where they did.

### 2.5 The event fixture is a build tool and never goes on screen

**#71's committed SSE fixture must not be streamed in front of a judge.** It is realistic
fabricated events, built so that the frontend could be developed against something before the
worker existed. It exists precisely because it looks like a real mission, which is what makes it
dangerous at hour 30, when the panels are dead and it is the obvious thing to reach for.

Showing it would be decorative fake telemetry presented as a run — forbidden by the product
rules, and worse than showing nothing. There is also no presentation mode to hide behind: #52 is
in `CUT`, so there is no labelled-mock middle ground between live and the recording.

---

## 3. Which combinations are allowed

### Coupling rules

- **C1 — #81 isolation forces #83 discovery.** We do not run a fuzzer under a working-directory
  jail. This is the only rung that drags another one down with it.
- **C2 — Replayed discovery does not shrink any later claim.** The reproducer is a real crash,
  minimized, reproducing 5/5 from a clean build. The model still receives a real crash report.
  Only the discovery sentence changes.
- **C3 — Replayed generation does not touch the gates.** They run live against the replayed
  diff, and that is worth saying out loud, because it is the part a judge should care about.
- **C4 — Verification and observability have no fallbacks.** Lose either and the live run is
  over.
- **C5 — No rung goes back up inside a run.**

### The modes

| Mode | Isolation | Discovery | Patch | Allowed? | Opening posture |
|---|---|---|---|---|---|
| **A — full live** | #15 | fuzz campaign | live inference | Yes | "Everything you are about to see is running now." |
| **B — replayed discovery** | #15 | #83 | live inference | **Yes — and this is the expected mode** | Say up front that the fuzz stage is skipped and why. The seven-day plan already treats the harness-confirms claim as the starting position, not the consolation prize |
| **C — replayed generation** | #15 | fuzz or #83 | #82 | Yes | Disclose the replay at the patch step, unprompted, before anyone asks |
| **D — reduced isolation** | #81 | #83 *(forced by C1)* | live or #82 | Yes, with the isolation sentence stated accurately and unprompted | Recommended: disclose in the opening rather than under question — **CEO call, §6** |
| **E — three rungs down** | #81 | #83 | operator-supplied | **No. Present #49 instead** | The only thing still live would be build and test. The recording shows more of the real system than the live run would, and it is no less honest |

### Stop conditions — present #49 rather than run live

Any one of these, no debate:

1. Verification does not produce both verdicts after one retry.
2. Baseline fails twice inside its 15-minute box.
3. The Command Center is not streaming and cannot be made to stream at pre-flight.
4. All three patch rungs fail policy.
5. Three or more rungs are down at once (Mode E).
6. Step 6 — the first verdict — has not been reached by hour 31.

---

## 4. Sentences we do not say

Four times in two days, across four different seats, this project described a property as
enforced when it was not. A judge who catches one overstatement has grounds to doubt every other
claim in the run, and our entire pitch is that we do not overstate what the tools proved. The
standing rule from D-049: **a property is described as enforced only when a named test
demonstrates it.**

| Never | Instead | Why |
|---|---|---|
| "air-gapped" | "egress is denied on the sandbox — here is the test output" | Rented and shared infrastructure. Already a hard rule in the finale runbook |
| "rootless", when Docker was substituted | name the runtime that ran, and list the flags | #15 condition 8 |
| "the system cannot reach the internet" | "no process holding repository content has a route out, enforced by network topology; here is the test" | Corrected once already |
| "structurally impossible", "guaranteed", "proven" | name the test in the same sentence, or say "intended" / "validated at startup" / "by convention" | D-049 |
| "signed by hash" | "hash-manifested" — a hash is not a signature | D-025 |
| "model-generated", for a replayed or operator-supplied candidate | "model output recorded &lt;date&gt;, replayed" / "operator-supplied candidate" | D-008, #82 |
| "our fuzzer found it", in replay mode | "our harness confirms and minimizes a stored reproducer" | #83 |
| a `0` for GPU spend or lease time | "not applicable — no leased GPU" | D-015 |
| "verified", with no gate list | enumerate what ran and name what did not | D-009 |

---

## 5. Where this ladder is not built yet

Read on 2026-08-07, close of D1. Every rung below is an open issue, which is the point: an
unbuilt fallback should show up on the board, not as a reassuring sentence in a document.

| Rung | Issue | Milestone | State today |
|---|---|---|---|
| Container isolation | #15 | D4 | Open |
| Subprocess jail | #81 | D2 | Open |
| Transcript replay | #82 | D2 | Open. Transcripts must be **captured on D5/D6 from real runs** — a transcript nobody recorded is not a fallback |
| Reproducer replay | #83 | D4 | Open. The stored reproducer and `pktcfg_replay` already exist from #74, so the path is buildable now |
| The recording | #49 | D5 | Open. Three dated captures: D5 partial, D6 the fallback of record, D7 superseding only if complete |

### The gap that worries me most

**BUG-007 and BUG-008 are open.** `ModelProvenance`'s replay fields default to "live" and
`GateResult.evidence_source` defaults to `TOOL_EXECUTION`, and an operator-supplied patch is
recordable as `MODEL_GENERATED` with two invented strings. Until those close — D-049 Part 1,
batched into #6 under D-048 — the exported evidence bundle will quietly make the *stronger*
claim whenever nobody sets a field.

Which means that today, this ladder is enforced by a tired person remembering to set a flag.
That is exactly the arrangement it was written to replace, and closing those two bugs is worth
more to the honesty of the finale than anything else on this page.

Once they close, the mode does not need recording anywhere separately: it is the conjunction of
`FindingSummary.discovery_method`, `FuzzingReport.mode`, `ModelProvenance.replayed_from_transcript`
and `GateResult.evidence_source`, all of which the contract already carries. The bundle then
cannot disagree with the narration.

---

## 6. Flagged for the CEO — presentation calls, not made here

1. **The opening sentence for the recorded-demo path (#49).** How we introduce a recording
   without either apologising for it or blurring what it is.
2. **Whether Mode D is disclosed in the opening or only when asked.** Recommendation: the
   opening. A reduced-isolation claim volunteered reads as rigour; the same claim extracted by a
   question reads as something we hoped nobody would check.
3. **Whether anything runs live alongside the recording in Mode E.**
4. **Slide wording versus finale mode.** The five slides freeze at D9 (#58, #60); the mode is not
   known until pre-flight at the finale. Either the deck is written to survive every allowed mode
   in §3, or it has to be edited after freeze. Recommendation: mode-neutral wording on slide 4,
   with the stronger discovery claim made verbally only if Mode A actually runs.

---

## 7. Pre-flight — decide everything that can be decided before hour 0

The runbook's pre-flight block already verifies the frozen release, images, tool cache, model
artifacts, demo repositories and the fallback recording. Add these five, and record each answer
on the mission log:

1. Run the isolation egress smoke check twice. **This sets the isolation mode for the whole
   finale**, and with it whether discovery can be live at all.
2. Confirm the `-DPKTCFG_FUZZ=ON` build produces a `pktcfg_fuzz` binary on the finale machine.
   The toolchain either ships libFuzzer or it does not, and Apple clang does not.
3. Resolve one #82 transcript by hash and confirm the schema version matches.
4. Run `smoke-sse.sh` through the finale stack, not against Django directly.
5. Play the #49 capture of record from the local file, with the network off.

Four of the ten triggers in §1 can be answered here rather than under the clock. Every one moved
forward is a decision hour 30 does not have to make.
