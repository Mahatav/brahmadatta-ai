# The Seven-Day Plan

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Deadline | **2026-08-20** (14 days from 2026-08-06) |
| CEO target | **2026-08-15** — done, with five days of reserve behind it |
| Build target | **2026-08-13** (D1–D7) |
| Supersedes | `docs/08-management/51-project-timeline.md` (8-week plan) |
| Status | Active |

## What changed

The pack's timeline gave eight workstreams one week each. There are fourteen days, and the
CEO wants the build done in seven. That is not the same plan compressed — it is a different
plan, and pretending otherwise is how teams arrive at day fourteen with nine things half-built.

So: [the P0 cut](01-vision-and-p0-cut.md) stops being a prioritization aid and becomes the
entire scope. Everything ranked P1 or P2 is in the `CUT` milestone on the board. The one thing
being built is the nine-step minimum viable demo from that document's §3.

## The board

[Brahmadatta Delivery](https://github.com/users/Mahatav/projects/3) · milestones are days

| Milestone | Ends | What has to be true at the end of it |
|---|---|---|
| **D1 — Foundations** | Aug 7 | Astro and Django scaffolded and talking through nginx; the demo C target builds and its tests pass; the API contract is frozen; visual references exist |
| **D2 — Spine** | Aug 8 | State machine, Django models, rootless sandbox with egress denied, authorize-and-snapshot gate, P0 screen set specified |
| **D3 — Baseline** ⚑ | Aug 9 | **GATE:** cold start → `BASELINE_PASSED` with real ctest counts, on screen |
| **D4 — Instrumentation** | Aug 10 | ASan/UBSan builds, libFuzzer harness, evidence database, analysis rail |
| **D5 — The finding** ⚑ | Aug 11 | **GATE:** sanitizer-confirmed crash, minimized reproducer replaying 5/5 from clean |
| **D6 — The loop** ⚑ | Aug 12 | **GATE:** one `Verified` and one `Rejected` verdict from a single operator action |
| **D7 — Evidence & freeze** ⚑ | Aug 13 | **GATE:** full nine-step demo runs unattended; report exports; fallback recorded |
| **D8 — Hardening & rehearsal** | Aug 14 | Security checklist, real measurements, timed rehearsals |
| **D9 — Submission & freeze** | Aug 15 | Slides, finale roster, code freeze. **This is the CEO's done date.** |
| **RESERVE** | Aug 16–20 | Nothing scheduled. Slack against the real deadline. |

⚑ = gate. A failed gate triggers a switch to the fallback in
[`10-fallback-ladder.md`](10-fallback-ladder.md) — not an extension, and not an improvised
decision on the day.

**On the reserve.** The CEO confirmed the deadline as 2026-08-20 and set the target at
2026-08-15. Aug 16–20 is reserve and nothing is planned into it. That is what makes the 15th a
real date rather than a wish — a reserve with work in it is not a reserve, and the 15th would
quietly become the 20th.

**On the honest state of D1–D7.** The CTO ruled it undeliverable at 33 issues
([`05-cto-technical-review.md`](05-cto-technical-review.md) §2) and named six reductions, five of
which are applied. The review gates then found seven more P0 items — three of them defects that
would each have failed the demo on the day. So the load went **up**, not down. D1–D7 will very
likely spill; the reserve is where it spills to, and that is the reserve doing its job.

## What got cut, and what that costs

Seventeen issues moved to `CUT`. The ones with real consequences:

| Cut | Consequence |
|---|---|
| Automated `git bisect` and the seeded history | Demo scenario 2 is gone, and with it the git-aware root-cause novelty claim on slide 4 |
| Semgrep and the static-delta gate | The gate matrix shrinks to compile + reproducer-eliminated + regression-preserved. Still deterministic, and the missing gates are disclosed rather than hidden |
| Renewed fuzzing after patch | Loses the strongest anti-overfit argument |
| **Rented GPU entirely** | The small model runs locally on CPU. Demo scenario 5 downgrades to lease control of the local model host. The heavy tier is presented as designed, never as live. This also removes the only real money in the project |
| Presentation mode | No labelled-mock rehearsal mode — rehearsals run against the real pipeline |
| Crash dedup, regression-test conversion, git panel, keyboard operability, structured logs | Polish and hygiene. Each individually survivable |

Nothing here is abandoned. If D7 passes early, items come back from `CUT` in the order above.

## Every risky stage has a fallback

The CEO's instruction on 2026-08-07: build D1–D7 in full, **and** build a fallback behind each
stage that might not work. Not as a contingency to think about later — as issues, now, while
the primary path still looks healthy.

| Stage | Primary | Fallback | Built by |
|---|---|---|---|
| Isolation | Rootless Podman, egress denied | Subprocess jail with a working-directory jail and resource limits | #81 |
| Discovery | libFuzzer campaign reaches the defect | Replay a stored reproducer; the fuzz stage shows as skipped, never as passed | #83 |
| Patch generation | Live CPU inference from the self-hosted model | Replay a recorded transcript; then operator-supplied, labelled | #82 |
| The live run | Unattended end-to-end demo | The rolling recording, re-captured as capability lands | #49 |
| Compute | *(already fallen back)* rented GPU → local CPU | — | D-015 |

The switching rules live in [`10-fallback-ladder.md`](10-fallback-ladder.md) (#84), and they are
written in advance for a reason: at hour 30 of a 36-hour finale, nobody makes a good call about
whether to abandon live fuzzing. Each trigger is observable and time-boxed.

**What every fallback costs is the size of the claim, never the integrity of the gates.** A
replayed model response is not inference happening in the room. A replayed reproducer is not a
fuzzer discovering a bug. The verification gates run identically either way — it is the
provenance that changes, and it must change visibly, in the UI and in the exported report. That
is D-008's rule about operator-supplied patches, generalised: every substituted path has to be
structurally inexpressible as the primary one, enforced by a validator rather than by remembering
to set a flag.

## The honest read on seven days

This is aggressive to the point of being unlikely as specified, and the plan should be run
knowing that rather than discovering it on day five. Two things follow.

**Start from the week-4 fallback, not the ideal.** The P0 cut's contingency for fuzzing was
"if the fuzzer cannot reach the defect, re-harness directly on the vulnerable function." At
seven days that should be the *starting* position. Harness the parser entry point directly,
prove the loop end to end, and only then widen the fuzzer's reach if D5 finishes early. The
demo claim becomes "our harness confirms and minimizes it" rather than "our fuzzer discovered
it" — a smaller claim that is true, versus a larger one that may not land in time.

**D7 is the real deadline, not D14.** Days 8 through 11 are buffer and they will be used. A
plan that needs all fourteen days has no room for the one bad day that always happens.

If the schedule has to give, it gives on the D5/D6 boundary — the loop matters more than the
discovery, because the loop is what nobody else will demonstrate.

## Working it

Two people, twelve and a half hours apart — see [`02-two-person-24h-cycle.md`](02-two-person-24h-cycle.md).
At this compression the handoff discipline stops being nice-to-have: a day lost to "I didn't
know you were blocked" is a seventh of the build.

Long-running jobs go at the end of a shift, every time. Fuzz campaigns, the ten-attempt patch
generation run, full regression sweeps. That is where the second timezone actually pays.
