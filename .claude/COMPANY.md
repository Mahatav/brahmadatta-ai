# The Brahmadatta AI Company

How this repository is staffed. Read this before spawning any agent.

Mahatav is **CEO**. Claude runs the **orchestrator** seat — routing, gating, and hiring —
and does not do a role's work inline. The `ceo` agent drafts; it never approves.

Run the company with `/company`. State persists in `.project/` (`intake.md`, `state.md`,
`decisions.md`) plus this file's roster.

---

## 1. Headcount is dynamic

Roles are **hired when a phase needs them and retired when it doesn't.** A role sitting on
the bench costs nothing; a role kept active "just in case" costs a full agent invocation
every phase and dilutes ownership. Hire late, fire early.

### Hire when

- A phase in the plan lists the role and that phase is now starting.
- A deliverable is blocked on expertise no active role owns.
- An active role's handoff says "this needs X" and X isn't staffed.
- A verdict-holder is required by the gate (`cybersecurity` before merge on
  security-sensitive work; `qa-engineer` before release).

### Fire when

- The role's phase deliverables are done and its gate passed.
- Two active roles have overlapping ownership of the same artifact — retire one and record
  which kept the artifact.
- The role produced no output attributable to it across a full phase.
- The work it was hired for was cut from scope.

Firing means **moving to the bench**, not deleting the definition. Its deliverables stay in
the repo and it can be rehired by name later. Never delete a `.claude/agents/*.md` file to
"fire" someone.

### Rules

- **Log every hire and fire** in §4 below, with the date, the trigger, and the phase. One
  line each. The log is append-only.
- **Cap concurrency at 3 active implementers** *unless the CEO explicitly authorizes more for
  a push.* Raised by explicit CEO instruction on 2026-08-17 for the closeout push to D9 —
  scale to the real remaining work, not to a fixed number. Push WIP branches early and often
  regardless of headcount; a full company pass is many agent calls and has died mid-run on a
  session limit before. Prefer resuming a stopped agent (`SendMessage`) over restarting.
- **Never hire a role to review its own work.** The reviewer is always the seat above.
- **Verify subagent output before acting on it.** Agents read the codebase cold and will
  repeat a stale doc claim as fact. Several of these docs contain estimates presented as
  targets — treat unbenchmarked numbers as unverified.

---

## 2. The review chain

**Nothing merges on the author's own say-so.** Every worker's output is critiqued by the
seat above it before it lands. This is the non-negotiable part of the structure.

```
                        CEO (Mahatav — human)
                                 │
                  ┌──────────────┴──────────────┐
                  │                             │
                 cto                     product-manager
                  │                             │
        software-architect              ui-ux-designer
                  │                             │
          engineering-manager ◄─────────────────┘
                  │
   ┌──────────┬───┴────┬───────────┬──────────────┬───────────────┐
frontend   backend  database   ml-infra   security-research  compiler-
   dev       dev      eng       eng          eng            toolchain eng
   └──────────┴────────┴───────────┴──────────────┴───────────────┘
                                 │
                    qa-engineer  +  cybersecurity   ← both can block
                                 │
                              merge
```

- Specialist output → reviewed by `engineering-manager`
- `engineering-manager` breakdown → reviewed by `software-architect`
- `software-architect` spec → reviewed by `cto`
- UX spec → reviewed by `product-manager`; `ui-ux-designer` reviews the frontend
  implementation against its own spec
- `cybersecurity` BLOCKED or `qa-engineer` REJECTED halts the merge. Fixes route back through
  the `engineering-manager`, then re-review. A critical security finding is waived only by
  written CEO risk acceptance in `decisions.md`.
- Disputes: technical → `cto`; scope/business → `product-manager`, escalating to CEO.

Claude merges PRs once the chain has signed off. That authority is standing — no need to
ask. Claude is the routing layer, not the approver.

---

## 3. Roster

### Active

| Seat | Agent | Owns | Reviewed by |
|---|---|---|---|
| CEO | *Mahatav (human)* | Vision, scope, budget, naming, go/no-go | — |
| Orchestrator | *Claude (this session)* | Routing, gates, hiring, merges | CEO |

Everyone below starts **on the bench.** The orchestrator hires per phase.

### Bench — general roles (defined in `~/.claude/agents/`)

`ceo` (drafting only) · `cto` · `product-manager` · `software-architect` ·
`engineering-manager` · `ui-ux-designer` · `frontend-developer` · `backend-developer` ·
`database-engineer` · `ai-ml-engineer` · `devops-engineer` · `cybersecurity` ·
`qa-engineer` · `technical-writer` · `customer-analytics`

### Bench — Brahmadatta specialists (defined in `.claude/agents/`)

| Agent | Hire when |
|---|---|
| `security-research-engineer` | Building the fuzzing, crash-triage, or reproducer workers |
| `compiler-toolchain-engineer` | Building baseline/build, sanitizer, ctest, or `git bisect` workers for C/C++ targets |
| `ml-infra-engineer` | Building the model gateway, self-hosted serving, or rented-GPU infrastructure |
| `competition-strategist` | Submission materials, judging-rubric alignment, or finale rehearsal |

---

## 4. Hire / fire log

Append-only. Format: `YYYY-MM-DD · HIRED|FIRED · agent · phase · trigger`

- 2026-08-17 · SCALE-UP · CEO authorized concurrency above 3 for the closeout push to D9.
  Real remaining scope: #154 (wire 7 of 11 mission routers — the one true P0 blocker),
  #50/#57/#60 downstream of it, #33 independent, plus selective un-cut of `CUT` items
  (analysis rail, keyboard nav, presentation mode) if #154 lands with room to spare.
  #44/#46/#47/#48 (rented GPU) stay untouched — real money, `needs:ceo`, not opted into.
- 2026-08-06 · FOUNDED · company chartered from the MVP documentation pack; full roster on the bench
- 2026-08-06 · HIRED · `ceo` · phase 1 · discovery needed a forced P0 ranking the pack does not contain
- 2026-08-06 · FIRED · `ceo` · phase 1 · delivered `01-vision-and-p0-cut.md` and D-006…D-012; gate passed
- 2026-08-06 · SKIPPED · `product-manager` · phase 1 · its four open questions went onto the board as #61–#64 instead; the 7-day budget could not absorb a full PM pass
- 2026-08-07 · HIRED · `backend-developer` · D1 · Django scaffold (#9) and the frozen contract (#6)
- 2026-08-07 · HIRED · `devops-engineer` · D1 · nginx (#10), compose and CI (#11)
- 2026-08-07 · HIRED · `general-purpose` as `compiler-toolchain-engineer` · D1 · demo C target (#4). **The project-local seats in `.claude/agents/` are not registered as agent types in this session** — the registry loads from the session's working directory, which is the parent folder. Workaround: spawn `general-purpose` and have it read the role file as its first instruction. Same for `security-research-engineer`, `ml-infra-engineer`, `competition-strategist`.
- 2026-08-07 · HIRED · `ui-ux-designer` · D1/D2 · P0 screen set and tokens (#7), unblocked once the CEO supplied visual references
- 2026-08-17 · HIRED · `devops-engineer` · closeout · reviewing PR #155, standing merge-readiness duty across the fleet for this push
- 2026-08-17 · HIRED · `cto` · closeout · design brief for #154 before backend starts, to pre-empt an SEC-15-shaped bug in the new HTTP surface
- 2026-08-17 · HIRED · `competition-strategist` · closeout · #33, five-slide draft, independent of #154
- 2026-08-17 · HIRED · `ui-ux-designer` · closeout · spec for pulling back #25/#52/#56 from CUT, independent of #154
- 2026-08-17 · HIRED · `general-purpose` as `competition-strategist` (2nd instance) · closeout · reconcile PR #157's slide redraft with the pre-existing honesty-tripwire test (`tests/test_submission_and_finale_closure.py`); wording-only fix, pushed as `3cff324`
- 2026-08-17 · HIRED · `backend-developer` (Engineer A) · #154 · wired `create_mission`/`list_missions`/`get_mission`, PR #160
- 2026-08-17 · HIRED · `engineering-manager` · #154 · review PR #160. **First attempt failed**: built-in `engineering-manager` has no `Bash`/`gh` tool — correctly refused to fabricate a verdict. Retried as `general-purpose` reading `~/.claude/agents/engineering-manager.md`. Same limitation likely applies to `product-manager`, `ui-ux-designer`, `ceo` — check the registry's Tools column before assuming shell access. Retry: APPROVE.
- 2026-08-17 · HIRED · `cybersecurity` · #154 · review PR #160's idempotency-key write surface. Verdict: CLEARED.
- 2026-08-17 · MERGED · PR #160 (`create_mission`/`list_missions`/`get_mission`, 3 of 7 stubs) · #154 · both reviews signed off, CI green
- 2026-08-17 · HIRED · `backend-developer` (Engineer B) · #154 · wired `preflight`/`start`/`pause`/`cancel`, fixed the `transitions.py` DoesNotExist bug, PR #161 rebased on #160
- 2026-08-17 · HIRED · `engineering-manager` (as `general-purpose`) · #154 · review PR #161. Verdict: APPROVE.
- 2026-08-17 · HIRED · `cybersecurity` · #154 · review PR #161's row-lock concurrency. Verdict: CLEARED.
- 2026-08-17 · HIRED · `qa-engineer` · #154 · verify PR #161's concurrency tests. Verdict: PASS — deliberately weakened the lock, confirmed the test catches it (5/5 failures), restored, confirmed green.
- 2026-08-17 · HIRED · `general-purpose` as `security-research-engineer` (2nd instance) · #159 · fixed SEC-38 (freeze-before-kill) and SEC-35 (FSIZE fallback) in `packages/sandbox/jail.py`, PR #162
- 2026-08-17 · HIRED · `cybersecurity` · #159 · binding D-056 independent re-attack of PR #162. Verdict: CLEARED — SEC-38 re-attacked with a harder adversarial variant (60x clean, ~220k process creations); SEC-35 re-attacked with a non-Python SIGXFSZ-ignoring target. Found and filed 3 new non-blocking residuals (#163/#164/#165).
- 2026-08-17 · MERGED · PR #162 (SEC-38/SEC-35 sandbox jail fixes) · #159 CLOSED
- 2026-08-17 · MERGED · PR #161 (`preflight`/`start`/`pause`/`cancel`, rebased onto #160 post-squash) · #154 CLOSED · all 7 of 7 mission-lifecycle routers now wired; #50 unblocked
- 2026-08-17 · MERGED · PR #157 (five-slide submission draft) · #33 · CI green after the wording-precision fix
- 2026-08-17 · HIRED · `devops-engineer` · #50 · first live attempt at the D7 unattended gate run since #154 closed — fresh env, no-cache rebuild, real nine-step mission through the HTTP API. Verdict: FAIL — new, deeper gap found (#168): nothing advances a mission past `VALIDATING`. Two small infra bugs fixed on the spot (demo/repositories mount, ARTIFACT_ROOT perms), PR #167.
- 2026-08-17 · FILED · #168 · P0 · mission-stage driver gap, the actual remaining blocker on #50
- 2026-08-17 · HIRED · `cto` · #168 · design brief (D-061) — found this is finishing #12, not new design: architecture spec + migrated `Job` model already exist with zero callers
- 2026-08-17 · HIRED · `engineering-manager` (as `general-purpose`) · #168 · staffing plan (D-062) — MVP scope call (T4-lite), honest 3-day deadline-risk flag, T0 slip = critical failure mode
- 2026-08-17 · HIRED · `engineering-manager` (as `general-purpose`) · #167 · review the D-032 fix (demo/repositories bind mount → build-time COPY, after CI caught the original mount violating a real architecture invariant no reviewer had caught). Verdict: APPROVE.
- 2026-08-17 · MERGED · PR #167 (finale snapshot ingestion fix + #50 FAIL evidence) · #50
- 2026-08-17 · MERGED · PR #169 (D-061/D-062 decision records)
- 2026-08-17 · HIRED · `backend-developer` · #168 T0 · orchestrator tick loop — the highest-risk item, isolated worktree `driver-t0`
- 2026-08-17 · HIRED · `backend-developer` · #168 T0b · snapshot-extraction utility, isolated worktree `driver-t0b`. Delivered PR #170 — round-trip + malicious-archive tests, 30/30 passing.
- 2026-08-17 · HIRED · `cybersecurity` · #168 T0b · adversarial re-attack of PR #170's tar/zip extraction safety (path traversal, symlinks, setuid smuggling)
- 2026-08-17 · HIRED · `engineering-manager` (as `general-purpose`) · #168 T0b · review PR #170 against D-062's scope. Verdict: APPROVE, conditional on rebase.
- 2026-08-17 · HIRED · `cybersecurity` (final confirmation) · #168 T0b · re-attack the decompression-bomb fix (commit 73d8471) specifically. Verdict: CLEARED — reproduced the original bomb refused, the cross-member cumulative case, and independently verified the author's stdlib-internals claim by forging lying archive headers.
- 2026-08-17 · MERGED · PR #170 (T0b snapshot extraction, incl. decompression-bomb fix) · #168
- 2026-08-17 · HIRED · `engineering-manager` · #168 T0 · review PR #171 (highest-stakes review of the day). Verdict: APPROVE — independently reproduced 455/455 passing on real Postgres, confirmed the `_HeartbeatThread` bug fix, confirmed exactly 3 `transitions.transition()` call sites.
- 2026-08-17 · HIRED · `cybersecurity` · #168 T0 · adversarial concurrency attack on the SKIP LOCKED claim mechanism — 50 threads, 6 real separate processes, split-brain lease fencing, all held. Verdict: CLEARED, with SEC-42 (HIGH, duplicate Job rows under two racing orchestrator processes — precondition doesn't exist yet) and SEC-43 (MEDIUM, no singleton guard) filed as #176/#177.
- 2026-08-17 · MERGED · PR #171 (T0 orchestrator tick loop) · **#168's actual fix** — VALIDATING → BASELINE now genuinely drives
- 2026-08-17 · HIRED · `engineering-manager` + `cybersecurity` (parallel) · #168 T1/T5/T7 · review the three executor PRs (#174/#175/#173) after rebase onto the merged T0/T0b. T5 (VERIFY) specifically flagged for an unsandboxed model-generated-patch-execution risk (D-067) — cybersecurity given explicit authority to make the ship/block call, not just flag it.
- 2026-08-17 · MISTAKE + CORRECTION · PR #173 (T7) merged on CI+cybersecurity alone, before engineering-manager's review landed — its CHANGES REQUESTED arrived seconds later, finding the TEARDOWN policy correct but unreachable (`CANCELLING` excluded from job-backed dispatch). Fixed forward, not reverted: PR #179. **Lesson applied for the rest of the session: always wait for BOTH engineering-manager and cybersecurity before merging.**
- 2026-08-17 · CLEARED · T5 cybersecurity BLOCKED (SEC-44 CRITICAL: verification subprocess inherited full worker env incl. `DATABASE_URL`; SEC-45 HIGH: leak channel in `GateResult.detail`; SEC-47 HIGH: no sandbox isolation, cheap fix identified). Routed back, fixed (env allowlist, redacted detail, real `packages.sandbox.Jail` wrap), independently re-verified with real POCs (fake secret never reached a subprocess; runaway process killed by jail wall-clock). Verdict: CLEARED.
- 2026-08-17 · CHANGES REQUESTED · a second, narrower engineering-manager pass on T5's Jail-rewrite (learned from the PR #173 mistake) found a real regression invisible on macOS: sanitizer builds need far more `RLIMIT_AS` than the Jail's 2GB default, so on real Linux every VERIFY would silently come back REJECTED regardless of patch correctness. Reproduced empirically in Ubuntu Docker. Routed back for a fix sizing `memory_bytes` off the existing `MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS` constant.
- 2026-08-17 · MERGED · PR #170, #171, #174, #173, #179 (T0b, T0, T1, T7, T7-fast-follow) — all of #168's foundational + 2 of 5 executor stages now on `main`.
- 2026-08-17 · FOUND + FIXED (urgent) · T1's merge silently broke every `control-api`/`worker` container boot (`ModuleNotFoundError: No module named 'workers'` — Docker build context never included `workers/`/`packages/`/`adapters/`, invisible to CI since it never builds images). Found by the T5 engineer mid-merge. Fixed via the same `additional_contexts` pattern PR #167 established, PR #183, both reviews cleared fast given severity, merged.
- 2026-08-17 · HIRED · `backend-developer` × 3 (parallel, isolated worktrees) · #168 T2 (FUZZ/MINIMIZE), T3 (CORRELATE), T6 (EXPORT — D-061's own "hard dependency, not optional" stage) — started in parallel with T5's fix rather than waiting, given the 2026-08-20 deadline.
- 2026-08-17 · BLOCKED (external) · GitHub Actions CI down repo-wide — "recent account payments have failed or spending limit needs to be increased." Not fixable by the team; escalated to CEO. Merges paused; review work (local verification, no CI needed) continued in parallel so everything is ready the moment CI returns.
- 2026-08-17 · CLOSED · T5 sanitizer-memory fix (commit 67f4407) independently re-verified on real Linux by a fresh engineering-manager pass — genuinely closes the finding. T5 now has full sign-off from both seats, blocked only on CI.
- 2026-08-17 · MERGED · PR #186 (T3 CORRELATE), incl. a same-day SEC-44 fix (malformed `crashes_found` now degrades gracefully instead of raising) — 4th independent "SEC-44" collision this session, tracked separately.
- 2026-08-17 · DELIVERED · PR #187 (T6 EXPORT — D-061's hard dependency) and PR #188 (T2 FUZZ/MINIMIZE, draft) — both under review.
- 2026-08-17 · FOUND (via T2's review) + FILED + STAFFED · #189 P0 · no pinned fuzzing-toolchain Docker image exists anywhere — even with #168 fully closed, a live #50 run would die one stage further than before, at FUZZ instead of VALIDATING. Same shape of discovery as #168 itself. Staffed immediately rather than deferred, since CI being down left no merge-blocked capacity idle anyway.

**NOTE (2026-08-17): this log has been clobbered by concurrent agent writes twice this session** (agents with `Write`/`Edit` access reading a stale copy of this file at spawn time, then overwriting the whole file on their own save). Restored both times from the orchestrator's own record. If a hire-log entry you expect to see is missing, it may be a third occurrence — check recent PR/issue history on GitHub as the source of truth, not just this file.

**Humans on the repo:** Mahatav (CEO, Kelowna) and Raunak (`raunaksachinkhanna`, India) — both
push access. Agent work goes through the same PR and review chain as theirs.

---

## 5. Standing orders

- **Escalate only CEO calls.** Money, user-facing naming, scope traded against the
  competition deadline, deleting a capability, anything legal, anything needing his
  credentials, anything that spends real money. Batch them into one list, each with options
  and a recommendation. Everything else, the team decides.
- **When escalating, run the `adhd` skill first** — bring branches, not an open question.
  Skip it for a formed yes/no approval gate.
- **UI work always goes through `ui-ux-pro-max`,** and asks the CEO for visual inspiration
  when the design docs don't already cover the surface being built.
- **A property is described as enforced only when a named test demonstrates it.** Not "structurally
  impossible", not "cannot", not "denied" — unless you can point at the test. This is a standing
  rule because it has already gone wrong four times, across four different seats, in a single day:
  "the system cannot reach the internet" (D-028), "signed-by-hash" when a hash is not a signature
  (D-025), a `[ SESSION SECURE ]` chip over plain HTTP (D-039), and "structurally impossible"
  provenance that QA violated on its first attempt (D-049). Four is a habit, not a coincidence.
  It is also the single most dangerous habit available to a team whose entire pitch is that it
  does not overstate what the tools proved. Until the test exists, describe what is *intended*.
- **Defaults point at the humbler claim.** A field that defaults to "live inference" or
  "tool execution" produces an overclaim by omission the first time someone forgets to set it.
  Make the weaker claim the one you get for free.
- **Never report a test, build, or scan as run** unless the executing agent's handoff shows
  real command output. "Should pass" is reported as "not verified".
- **Security work comes first** when it competes with a feature for the same slot.
- Findings go in the issue or the PR, where the team reads them — not into the CEO's inbox.
- 2026-08-17 · HIRED · `devops-engineer` · closeout · reviewing PR #155, standing merge-readiness duty across the fleet for this push
- 2026-08-17 · HIRED · `cto` · closeout · design brief for #154 before backend starts, to pre-empt an SEC-15-shaped bug in the new HTTP surface
- 2026-08-17 · HIRED · `competition-strategist` · closeout · #33, five-slide draft, independent of #154
- 2026-08-17 · HIRED · `ui-ux-designer` · closeout · spec for pulling back #25/#52/#56 from CUT, independent of #154
