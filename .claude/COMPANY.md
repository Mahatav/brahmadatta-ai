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
- **Cap concurrency at 3 active implementers.** A full company pass is many agent calls and
  has died mid-implementation on a session limit before. Push WIP branches so nothing is
  stranded. Prefer resuming a stopped agent (`SendMessage`) over restarting its work.
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

- 2026-08-06 · FOUNDED · company chartered from the MVP documentation pack; full roster on the bench

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
- **Never report a test, build, or scan as run** unless the executing agent's handoff shows
  real command output. "Should pass" is reported as "not verified".
- **Security work comes first** when it competes with a feature for the same slot.
- Findings go in the issue or the PR, where the team reads them — not into the CEO's inbox.
