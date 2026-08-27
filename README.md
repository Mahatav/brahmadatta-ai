# Brahmadatta AI

Autonomous armor for software — an authorized, defensive Cyber-Reasoning System built as the
competition MVP for AI Kavach.

Brahmadatta investigates a codebase you own, confirms a vulnerability with deterministic
evidence, proposes a minimal patch, and then proves whether the repair actually holds. The
operator watches all of it through the **Brahmadatta Command Center**, a mission-control
dashboard built around a central radial core.

**Status:** documentation complete, implementation not started. The repository currently
contains the full specification and the folder skeleton it describes.

## How it works

The mission runs one path: **authorize → ingest → baseline → analyze → correlate →
stress-test → patch → verify → export evidence.**

Behind that sit three tiers, and work only moves up a tier when the evidence justifies the
cost:

1. **Deterministic triage** — build the target, run its tests, run Semgrep and the compiler's own warnings, read the git history. Cheap, fast, no model involved.
2. **Destructive sandbox testing** — fuzz it with AFL++ and libFuzzer under ASan/UBSan, triage the crashes, produce a reproducer anything else can replay. A lightweight self-hosted model drafts a patch.
3. **Heavy repository reasoning** — a short-lived rented multi-GPU cluster, spun up only when a mission has earned the escalation and torn down after.

Two rules constrain the whole design. A patch is never accepted on model confidence — the
original reproducer, the regression tests, the static checks and renewed fuzzing decide, and
confidence is only ever displayed next to its source. And repository content never leaves for
an external inference API; everything runs on self-hosted models on infrastructure this
project controls.

## Safety boundary

Authorized repositories only. No public-target scanning, no exploit deployment, no automatic
production merge.

Fuzzing and static analysis run inside a `--network none`, non-root, `--cap-drop ALL`
container (a standard container runtime, not rootless Podman — D-024 accepted that
substitution explicitly, with eight binding conditions, after Podman was not available on
the build host; see `packages/sandbox/container.py`). BASELINE (a target's own build/test
suite) and VERIFY's compile/reproducer-replay/regression gates run the same way when
`SANDBOX_BUILD_IMAGE` is configured (#181/SEC-57) — that is a real, deliberate opt-in still
being rolled out to every deployment, not the default everywhere yet: unset, both stages
fall back to a subprocess-only jail with resource ceilings but no network/filesystem
isolation from the host, and every mission's evidence records honestly which one actually
ran a given stage. See `.project/decisions.md`'s SEC-57 entry for the current rollout state
and the known gap in wiring container isolation into the containerized worker deployment.

## Stack

React + TypeScript + Vite for the command center, with the core drawn in SVG. FastAPI and
Pydantic for the control API, an explicit persistent state machine for orchestration, Redis
for the queue, PostgreSQL for metadata, encrypted object storage for artifacts. Analysis
leans on Semgrep, AFL++, libFuzzer, the sanitizers, and `git bisect run`. C and C++ targets
first; Python is an optional extension.

## Layout

```
apps/            command-center (UI), control-api, operator-cli
services/        orchestrator, model-gateway, evidence-builder, telemetry
workers/         baseline, static-analysis, git-analysis, fuzzing, patching, verification
adapters/        cpp, python
packages/        schemas, policy, ui-components, test-fixtures
infrastructure/  compose, gpu, scripts
demo/            repositories, expected-evidence, presentation-mode
docs/            the full specification — start at docs/README.md
tests/           unit, integration, e2e, security, performance
```

## Documentation

[`docs/README.md`](docs/README.md) indexes all 79 documents. If you're new, read them in this
order: product identity, project vision, PRD, MVP scope, UI design direction, dashboard
screen specification, system architecture, technology stack, testing strategy, then the
five-slide submission outline and the 36-hour finale runbook.

## Contributing

Branch from `main` — direct pushes are not allowed. Small commits, a PR for every change, and
the review chain in [`.claude/COMPANY.md`](.claude/COMPANY.md) applies: nothing merges on the
author's own say-so. Security-sensitive changes need security sign-off recorded on the PR.
Details in [`docs/04-development/`](docs/04-development/).

## The name

Brahmadatta refers to a divine armor associated with Brahma in Hindu epic tradition, chosen
because the system's purpose is to surround software in layered, evidence-driven protection.
It is used here as a technology brand — not as a deity, a religious authority, or a claim of
literal invincibility.
