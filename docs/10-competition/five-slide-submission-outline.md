# Five-Slide Submission Outline

| Field | Value |
|---|---|
| Status | Full draft against the P0 cut (issue #33) |
| Drafted by | `competition-strategist` seat, 2026-08-16 |
| Prior claim audit | `.project/evidence/d9-submission-claim-audit-2026-08-15.json` — passed for the outline as it stood before #154 was found. Superseded by this draft; a fresh audit is owed before submission (see "Before this goes out," below). |
| Scope rule | Every claim below traces to a file, a test, or a recorded evidence run in this repository. Where it doesn't, it's marked as a target, a design intent, or a cut. |
| Contingent on #154 | Slide 5 in particular. Flagged inline wherever it applies — search this file for "#154" before submitting. |

This is a real draft, not a placeholder. It is built against what's true in the repository
today (2026-08-16): D5 and D6 are done and evidenced, the D7 unattended gate (#50) has not
run live, and the reason is a specific, named piece of unfinished wiring (#154), not a vague
"not yet." If #154 lands before this is finalized, slide 5 gets stronger and the notes below
say exactly how. If it doesn't, every sentence here is still defensible as written.

---

## Slide 1 — Introduction, ideation, and brief description

**Title:** Brahmadatta AI — Autonomous Armor for Software

- Vulnerability scanners are common. What's rare is a tool that finishes the job: reproduces
  the bug deterministically, writes a patch, and then checks its own patch instead of asking
  a human to. Most of what's marketed as "AI security" stops at the report.
- Brahmadatta AI is an autonomous, defensive Cyber-Reasoning System built for AI Kavach. Given
  an authorized C/C++ repository, it finds a real memory-safety defect through its own fuzzing,
  generates a candidate patch with a self-hosted model, and hands the verdict to deterministic
  tools — compiler, reproducer, regression suite — rather than to the model's own confidence.
- Three tiers, evidence gated: fast deterministic triage first, sandboxed destructive testing
  and lightweight patching second, heavier reasoning only when the first two tiers justify the
  cost. Nothing escalates on a guess.
- The one thing that actually distinguishes this entry: the pipeline can produce a patch that
  eliminates the crash and still get rejected, because eliminating the crash isn't the bar —
  preserving the program's behavior is. That rejection is demonstrated, not asserted. Slide 4
  has the specifics.
- Brahmadatta AI is a technology brand. The name is drawn from Hindu epic tradition (a warrior
  armor associated with Brahma) as a metaphor for layered, evidence-based protection — it is
  presented that way and only that way, never as a claim of invincibility or a religious one.

---

## Slide 2 — Detailed methodology

**The pipeline, as built:**

`Authorize → Snapshot → Baseline → Fuzz & Reproduce → Patch (self-hosted model) → Verify → Evidence → Teardown`

This is the nine-step minimum viable demo from the P0 cut
(`docs/09-company/01-vision-and-p0-cut.md` §3), run against `pktcfg`, a small CMake/CTest C
library purpose-built for this competition with one seeded heap-buffer-overflow and an
otherwise-green test suite.

**The step that matters most: the pipeline runs twice on the same finding and disagrees with
itself on purpose.**

1. **Authorize + snapshot.** The operator authorizes the target repository; a snapshot hash is
   recorded before anything touches it.
2. **Baseline.** Configure, build, run the existing CTest suite. Recorded pass/fail counts —
   this is the denominator everything downstream is checked against.
3. **Fuzz and reproduce.** A libFuzzer harness against the parser entry point finds the seeded
   defect through the system's own fuzzing, confirmed by AddressSanitizer with a stack trace,
   and minimizes it to a reproducer that replays deterministically from a clean build.
4. **Patch.** A self-hosted CodeLlama model, given the crash report and the localized source,
   proposes a candidate. The patch policy — single file, within an allowlist, under a
   changed-line cap — has to pass before the candidate is even compiled.
5. **Verify, twice, on two different candidates.** The correct patch (fixes the two-pass
   sizing/writing mismatch that caused the overflow) and a tempting-looking wrong one (patches
   the write site instead of the size calculation, which kills the crash by deleting the
   feature that was overflowing) go through the identical gate sequence: compile, replay the
   reproducer, run the full regression suite. The correct patch passes all three and is marked
   `Verified`. The wrong one passes compile and eliminates the crash, then fails six of the
   fourteen assertions in the regression suite and is marked `Rejected` — beside the accepted
   one, in the same run, from the same gate matrix.
6. **Evidence.** Markdown and JSON export: snapshot hash, crash report, minimized input, both
   diffs, both gate matrices, both verdicts.
7. **Teardown.** Sandbox and model-host release confirmed in the record.

**What's in this build's verification matrix, and what isn't.** Compile, reproducer
elimination, and regression preservation are real gates that ran and decided both verdicts
above. Static-delta analysis (Semgrep) and a renewed-fuzzing pass after patching are designed
but cut from this build (`docs/09-company/01-vision-and-p0-cut.md` P1-2, P1-3; tracked as
open issues #22/#23 and #40) — every recorded verdict discloses them as `NOT_RUN` rather than
omitting the row. `git bisect` root-cause localization is cut entirely, not merely deferred
(issues #5, #24, #26; #63 is the open decision on whether it ever comes back) and is not
presented as part of this methodology. Nothing above is inferred — see
`.project/evidence/d6-verdict-loop-report.md` for the exact gate matrix from a real run,
reproduced twice consecutively.

---

## Slide 3 — Technology stack and architecture

- **Brahmadatta Command Center.** Astro, with the live panels built as client islands sharing
  one SSE connection. SVG for the central Brahmadatta Core visualization. This replaces the
  React/Vite stack in the original doc pack — the stack changed by CEO decision after the pack
  was written; Astro is what's actually in the repository.
- **Control plane.** Django + django-ninja, with a generated OpenAPI contract checked into CI
  so a schema change breaks the build before it breaks a demo. Persistent mission state machine
  backed by PostgreSQL. Server-sent events over ASGI for live updates, `proxy_buffering off` on
  the SSE route because nginx buffers by default and silently kills streaming otherwise.
- **Isolation.** `packages/sandbox/` provides two isolation primitives behind one interface: a
  subprocess jail for build/test commands (CPU, memory, wall-clock and process-count limits) and
  a container-based jail for the fuzzer, which is what the D5 finding above actually ran inside
  — `--network none`, non-root, every capability dropped, read-only root filesystem, egress
  failure proven by a real DNS-and-TCP test against a running container, not asserted
  (`packages/sandbox/tests/test_container_jail.py`, 28 tests, real Docker daemon). The subprocess
  jail was independently security reviewed before merge and cleared with no Critical finding, on
  the condition that two Medium findings — both specific to adversarial, rapidly-repeating
  process behavior rather than the ordinary build path — get closed before it's trusted against
  fuzzer-derived input (`docs/09-company/08-security-review.md` §17; D-056). This submission
  doesn't assert those two are re-verified closed, only that they're found, tracked, and don't
  describe the path the fuzzer actually uses.
- **Tier 1 — deterministic triage.** CMake/Make build, CTest, compiler warnings
  (`-Wall -Wextra -Wshadow -Wconversion`, clean by default). Static analysis (Semgrep) is
  designed and scoped but not built in this cut.
- **Tier 2 — destructive testing and lightweight patching.** libFuzzer plus ASan/UBSan for
  finding and confirming defects; a self-hosted CodeLlama 7B-instruct model, served locally
  through Ollama on a loopback-only endpoint, for generating patch candidates once deterministic
  evidence exists. Repository content never leaves that endpoint — the model-serving policy is
  enforced as an allow-listed private-network rule, not a comment.
- **Tier 3 — heavy escalation.** Designed as an architectural path, not built or claimed live in
  this MVP. No specific heavy model is named anywhere in this submission — naming one before a
  feasibility spike confirms it fits an obtainable, rentable topology is a commitment this team
  isn't making on a slide.
- **Compute posture.** CPU-first. Rented-GPU escalation is fully cut from this build (issues
  #44, #46, #47, #48 — real money, explicitly not opted into) in favor of process-level lease
  and teardown control of the local model host, which is what's actually demonstrated.

---

## Slide 4 — Salient features and novelty

**Leading with the one no competitor can also claim: this system rejects its own patch when
the patch is wrong, and the rejection is a real, checked-in test failure, not a scripted
demo beat.**

- `pktcfg`'s regression suite includes `test_tab_expansion`, a CTest case labelled `asymmetry`
  that asserts a literal tab byte decodes to exactly four spaces. The crash-only fix trips six
  of its fourteen assertions — the sanitizer points a patcher at the write site, but the actual
  defect is in the size calculation one function away. A system (or a person) that patches where
  the crash trace points, without checking behavior against the pre-patch baseline, ships a
  patch that "works" and is wrong. Brahmadatta AI's gate catches that, in the same run that
  accepts the correct fix, and shows both verdicts side by side.
- **Evidence-first compute routing.** Nothing escalates to the model until deterministic tiers
  have produced a confirmed, minimized finding to hand it.
- **Deterministic verification, not confidence.** A patch's verdict comes from compile status,
  reproducer replay, and regression results — never from the model's own assessment of its
  patch. Recorded, twice, consecutively: `.project/evidence/d6-verdict-loop-gate.json`.
- **Local model only.** Every generation request in this build went to a loopback endpoint.
  Repository source never reaches an external inference API — this is a policy the serving
  layer enforces, not a claim about intent.
- **A live Command Center**, not a status page. The central AI core, the mission's live
  automation progress, and a side-by-side verdict-comparison panel all read off the real
  server-sent event stream from the control API (`apps/command-center/src/lib/events/`), so
  what a judge watches is the same run producing the evidence bundle, not a recording styled to
  look live.
- **Bounded compute even without rented hardware.** The local model host has a real lease
  lifecycle — start-on-escalation, hard memory limit, confirmed teardown on mission end —
  visible in the evidence record whether or not the GPU tier is ever turned on.
- **What's honestly not novel yet.** Root-cause localization via `git bisect` and a
  renewed-fuzzing pass after patching are both cut from this build (see slide 2). They would
  add to the novelty story; claiming them now would not survive a judge reading the code.

---

## Slide 5 — Final deliverables and proof of concept

**What's true today, stated plainly rather than rounded up:**

- **A real, working pipeline through patch and verify**, demonstrated twice consecutively at
  the orchestrator level: one sanitizer-confirmed crash, found by the system's own fuzzing
  (1,878 executions, under half a second, per `.project/evidence/d5-live-fuzzing.json`); one
  minimized reproducer, replayed 5 out of 5 times from a clean build
  (`.project/evidence/d5-reproducer-gate.json`); one model-generated patch reaching `Verified`;
  one candidate patch reaching `Rejected` on a real regression failure — both from the same
  gate matrix, in the same run, twice (`.project/evidence/d6-verdict-loop-gate.json`).
- **The local model actually works under load.** 10 of 10 live generation attempts against the
  self-hosted CodeLlama endpoint returned schema- and policy-valid patch candidates
  (`.project/evidence/d6-model-generation-attempts.json`). That measures generation reliability,
  not the full bar — the P0 kill criterion (3 of 10 attempts producing a policy-passing,
  *compiling* patch) is answered separately by the verdict-loop runs below: both candidates in
  both runs compiled cleanly and went all the way through the gate matrix, one to `Verified`
  and one to `Rejected`.
- **An exported evidence bundle** — snapshot hash, crash report, minimized input, both diffs,
  both gate matrices, both verdicts — readable by someone who didn't build the system.
- **A fallback recording exists and is hash-verified** (`fallback-demo-d6.html`, manifest at
  `.project/evidence/fallback-demo-d6-manifest.json`). If the live run has any trouble on the
  day, there is something real to fall back to — not a promise to record one later.

**What's not true yet, and won't be claimed as true until it is:**

- **The full nine-step run has not been demonstrated live, unattended, through the actual
  mission API, start to finish.** That's gate #50, and it is open. Everything above was run
  at the orchestrator/service level — real code, real gates, real evidence — but not yet
  driven end-to-end through `POST /api/v1/missions`, because that endpoint and six others
  next to it are still stubbed. **This is entirely contingent on #154**, which is the specific,
  scoped fix (wire the seven remaining mission-lifecycle HTTP routers to the orchestrator that
  already exists and already works underneath them). If #154 lands and #50 passes before this
  submission is finalized, this bullet becomes a genuine "runs unattended, start to finish,"
  with a timed run attached. Until then, the honest sentence is the one above.
- **Timed rehearsals (#57)** haven't happened — they're gated on #50 passing once first. A
  rehearsal of a gate that hasn't itself passed proves nothing, so none is claimed.
- **Rented-GPU escalation** is not part of this submission, live or otherwise. It's cut, on
  purpose, and stays cut unless a separately-approved spend decision reverses that.

---

## Claim audit for submission

| Claim family | Submission wording | Evidence status |
|---|---|---|
| Product identity | Authorized defensive Cyber-Reasoning System for AI Kavach | Repository scope, `docs/00-overview/00-product-identity.md`, authorization-first mission flow |
| The rejection scenario | One correct patch verified, one plausible wrong patch rejected on regression, same run, same gate matrix | `.project/evidence/d6-verdict-loop-gate.json`, `demo/repositories/pktcfg/tests/test_tab_expansion.c`, two consecutive runs |
| Deterministic verification | Compile, reproducer replay, and regression decide the verdict — not model confidence | D6 verdict loop evidence; static-delta and renewed-fuzz gates explicitly logged `NOT_RUN`, not omitted |
| Local AI only | Repository content is not sent to an external inference API | `.project/evidence/d5-model-serving.json` — loopback-only, policy-enforced |
| Model hit rate | 10 of 10 live generation attempts schema/policy-valid | `.project/evidence/d6-model-generation-attempts.json` |
| Metrics | No unmeasured number presented as measured; unbenchmarked rows stay unpublished | D-010; `.project/evidence/d8-benchmark-case-set.md` |
| Rented GPU | Not claimed as live; explicitly cut, not opted into | Issues #44/#46/#47/#48; P0 cut §2 |
| Heavy model (Tier 3) | Not named; presented as designed escalation path only | CEO doc §6.4; no model name appears anywhere in this draft |
| Full unattended run (D7) | **Not** claimed complete | Gate #50, open; blocked on #154, open |
| Timed rehearsals (D8) | Not claimed complete | Gate #57, blocked on #50 |
| Fallback recording | Exists, hash-verified | `.project/evidence/fallback-demo-d6-manifest.json` |

---

## Before this goes out

- **Re-run the claim audit against this draft specifically.** The prior audit
  (`d9-submission-claim-audit-2026-08-15`) passed an earlier version of this outline, written
  before #154 was found. This draft's slide 5 is new; it should get its own audit pass, not
  inherit the old one's clearance.
- **Check #154 and #50 immediately before finalizing.** If #154 has merged and #50 has a
  recorded PASS, slide 5's first "what's not true yet" bullet needs to move up into "what's
  true today," with the actual timed-run numbers substituted in. If #50 still hasn't run live,
  ship this draft as written — it's honest either way, which is the property that matters more
  than which way the die landed.

---

## Fixed MVP competition decisions

- **Product name:** Brahmadatta AI.
- **Product type:** an authorized, defensive Cyber-Reasoning System for the AI Kavach competition MVP.
- **Architecture:** three evidence-driven tiers: fast deterministic triage, destructive sandbox testing with lightweight patching, and heavy repository-level reasoning only when escalation is justified.
- **Interface:** a dense futuristic armor-command-center dashboard with a central mission core, live telemetry, drill-down panels, and operator controls. The visual language is original and does not copy third-party logos or branded interface assets.
- **Primary workflow:** authorize → ingest → baseline → analyze → correlate → stress-test → patch → verify → export evidence.
- **Compute:** CPU-first, with a self-hosted local model in this MVP cut. Repository content is not sent to an external inference API. Rented-GPU escalation is designed but cut, not live.
- **MVP target:** C/C++ repositories first; Python support is optional.
- **Verification rule:** a patch is never accepted on model confidence alone. The original reproducer, regression tests, and (where built) static checks and renewed fuzzing determine the verdict.
- **Safety boundary:** authorized repositories and isolated environments only; no public-target scanning, no exploit deployment, and no automatic production merge.

## Open decisions / next review

- #154 — wire the seven remaining mission-lifecycle HTTP routers. The one thing actually
  gating #50, and by extension every downstream D9 item.
- #50 — run and record the D7 unattended gate live, once #154 lands.
- #57 — run and record three timed rehearsals, once #50 passes.
- #59 — finale roster (who is physically present), a CEO decision, unrelated to #154 and
  answerable in parallel.
- #60 — code freeze, gated on #57.
