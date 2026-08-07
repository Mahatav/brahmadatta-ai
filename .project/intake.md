# Intake — Brahmadatta AI

Answers derived from the MVP documentation pack in `docs/` (imported 2026-08-06), not from a
fresh interview. The doc pack is the CEO's own prior specification, so it is treated as
authoritative intake. Anything it does not answer is marked **DEFERRED** with the assumption
being worked under.

Source of truth for each answer is cited so a role can go read it rather than trusting this
summary.

---

## Idea

An autonomous, authorized, **defensive** Cyber-Reasoning System for the AI Kavach competition.
Brahmadatta AI investigates a codebase, confirms a vulnerability with deterministic evidence,
proposes a minimal patch, and proves whether the repair holds. The operator drives it through
the Brahmadatta Command Center, a dense mission-control dashboard.

→ `docs/00-overview/00-product-identity.md`, `docs/01-product/01-project-vision.md`

## Target users

A single operator running a competition deployment for a single team — a security engineer
watching an autonomous run and intervening at gates. Not multi-tenant, not self-serve.

→ `docs/01-product/04-target-user-personas.md`, `docs/01-product/03-mvp-scope-document.md`

## Core problem

Vulnerability discovery and repair today either stops at "here's a suspicious line" or
produces patches nobody can prove are correct. Brahmadatta closes the loop with evidence:
reproducer → patch → re-verification, with a hard rule that model confidence never substitutes
for a passing gate.

→ `docs/01-product/05-problem-statement.md`, `docs/01-product/06-jobs-to-be-done.md`

## Required features (P0)

Mission orchestrator with a persistent state machine and event stream. C/C++ adapter for
CMake/Make + CTest. Baseline build and regression testing. Semgrep and compiler static checks.
Sanitizer builds with AFL++/libFuzzer. Crash capture, dedup, minimization, and conversion to a
regression test. Git summary and automated `git bisect`. A small self-hosted code model on one
rented GPU. Bounded heavy-model escalation on a short-lived rented cluster. Patch policy,
clean verification, evidence database, Markdown/JSON report, safe teardown. Presentation mode
and a pre-recorded fallback demo.

Five demo scenarios must all work: memory-safety defect found by fuzzing; git regression found
by bisect; verified repair; **rejected** repair (a crash-only patch that fails a regression
gate); and resource control (GPUs start on escalation, torn down at completion).

→ `docs/01-product/03-mvp-scope-document.md`, `docs/01-product/11-feature-list.md`

## Explicitly out of scope

Public multi-tenant SaaS, billing, legal-policy documents, public-network scanning,
unauthorized targets, automatic merge or production deployment, frontier-model pretraining,
non-C/C++ languages beyond optional Python, binary-only targets, distributed fuzzing, formal
proof, mobile.

→ `docs/01-product/03-mvp-scope-document.md`

## Tech preferences

Fixed, not open: React + TypeScript + Vite command center with the core in SVG; FastAPI +
Pydantic control API; explicit persistent state machine; Redis queue; PostgreSQL (SQLite
allowed only for the earliest single-machine prototype); encrypted S3-compatible artifact
store; rootless Docker/Podman isolation; Semgrep, AFL++, libFuzzer, ASan/UBSan; SSE for live
updates with WebSocket only where bidirectional is genuinely needed; structured JSON logs,
trace IDs, Prometheus metrics.

→ `docs/03-technical/17-technology-stack-document.md`

## Budget

**DEFERRED — the doc pack deliberately excludes financials.** GPU spend is the only real cost
and it is a CEO call.

*Assumption in force:* development runs CPU-first on local hardware at zero marginal cost;
rented GPU time is used only for milestone M5 rehearsals and the finale, on the cheapest
provider that can serve the chosen models. No GPU is left running past the work that justifies
it. Any spend commitment escalates to the CEO before it is incurred.

## Expected user count

One concurrent operator. Concurrency is a non-goal; a single mission runs at a time.

→ `docs/01-product/03-mvp-scope-document.md`

## Launch date

An 8-week build to a code freeze, then a **36-hour finale run**. Week 1 starts 2026-08-06.

| Week | Focus |
|---|---|
| 1 | Freeze scope, brand, architecture, UI system, demo repositories |
| 2 | Mission intake, state machine, event stream, database, sandbox baseline |
| 3 | Static evidence, git analysis, dashboard analysis rail |
| 4 | Sanitizers, fuzzing, minimization, live telemetry |
| 5 | Lightweight model, patch policy, diff view, rejection gates |
| 6 | Heavy rented-GPU integration and teardown |
| 7 | Evidence report, presentation mode, security and performance tests |
| 8 | Rehearsals, five-slide submission, fallback assets, code freeze |

**DEFERRED:** the actual AI Kavach submission deadline and finale date are not recorded
anywhere in the pack. *Assumption in force:* week 1 begins 2026-08-06 and the schedule is
relative to that, i.e. code freeze around 2026-09-30.

→ `docs/08-management/51-project-timeline.md`, `docs/08-management/52-milestone-plan.md`

## Existing code / infrastructure

None. This repository is the greenfield start — documentation and the folder skeleton only, no
implementation. Git history begins 2026-08-06.

## Legal, privacy, and security constraints

Hard constraints, all of them non-negotiable:

- Authorized repositories and isolated environments only. No public-target scanning, no exploit deployment, no automatic production merge.
- Repository content never reaches an external inference API. Self-hosted models exclusively.
- A patch is never accepted on model confidence alone.
- No decorative or fake telemetry in the UI — every displayed number is real or a clearly-labelled deterministic mock in presentation mode.
- Original visual language; no third-party logos, icons, or branded interface assets.
- The Brahmadatta name is used as a technology brand, presented respectfully, never as a deity or religious authority.
- Crash artifacts, corpora, and target source stay out of git.

→ `docs/03-technical/23-security-plan.md`, `docs/03-technical/24-privacy-and-data-handling-plan.md`, `docs/00-overview/00-product-identity.md`

---

## Open items owned by the CEO

Carried from "Open decisions / next review" in the doc pack. These are the only questions the
team cannot answer for itself:

1. **GPU provider and budget ceiling** — needed before week 5 (M5).
2. **Finale date and submission deadline** — the whole schedule hangs off it.
3. **Team composition** — the pack assumes three humans; currently the company is Claude's agent roster plus the CEO.
4. **Demo target repository** — which C/C++ project the finale runs against, and its fallback.

Everything else in the pack is either decided or safely assumable.
