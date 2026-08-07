# CLAUDE.md — Brahmadatta AI

Guidance for Claude Code working in this repository.

## What this is

**Brahmadatta AI** is an autonomous **defensive** Cyber-Reasoning System built as a
competition MVP for AI Kavach. It investigates an *authorized* codebase, confirms a
vulnerability with deterministic evidence, proposes a minimal patch, and proves whether
the repair holds.

Primary interface: the **Brahmadatta Command Center** — a dense, cinematic mission-control
dashboard with a central radial **Brahmadatta Core**.

The full specification lives in [`docs/`](docs/). `docs/README.md` is the index.
**Read the relevant spec before implementing anything.** These documents are the source of
truth; do not invent requirements that contradict them.

## Non-negotiable product rules

Every one of these is repeated across the doc pack. They are not up for reinterpretation:

- **Architecture is three evidence-driven tiers:** fast deterministic triage → destructive
  sandbox testing with lightweight patching → heavy repository-level reasoning only when
  escalation is justified.
- **Mission workflow:** authorize → ingest → baseline → analyze → correlate → stress-test →
  patch → verify → export evidence.
- **A patch is never accepted on model confidence alone.** The original reproducer,
  regression tests, static checks, and renewed fuzzing decide the verdict. Any code path
  that lets confidence substitute for verification is a bug.
- **Repository content is never sent to an external inference API.** CPU-first; self-hosted
  models on rented GPUs. No calls to hosted LLM providers from product code.
- **Safety boundary:** authorized repositories and isolated environments only. No public
  target scanning, no exploit deployment, no automatic production merge.
- **Target language:** C/C++ first. Python support is optional and must not delay C/C++.
- **No decorative fake metrics.** Every counter, chart, and animation in the UI displays real
  telemetry, or a clearly-labelled deterministic mock in presentation mode.

## Stack

| Layer | Choice |
|---|---|
| Command center | React + TypeScript + Vite |
| Visualization | SVG/Canvas for the Core (SVG before WebGL) |
| Live updates | Server-sent events by default; WebSocket only for true bidirectional needs |
| Control API | Python + FastAPI + Pydantic |
| Orchestration | Explicit persistent state machine |
| Queue | Redis (RQ/Celery) or DB-backed |
| Metadata | PostgreSQL (SQLite allowed for the earliest single-machine prototype) |
| Isolation | Rootless Docker/Podman; microVM adapter for higher-risk targets |
| Static analysis | Semgrep, compiler warnings, optional CodeQL/Joern |
| Dynamic analysis | AFL++, libFuzzer, ASan/UBSan |
| Observability | Structured JSON logs, trace IDs, Prometheus metrics |

Folder layout is specified in [`docs/04-development/35-project-folder-structure.md`](docs/04-development/35-project-folder-structure.md)
and already scaffolded. Put code where that document says it goes.

## Working agreements

### Talking to Mahatav

Only stop and ask when you **cannot move forward without a decision only he can make** —
irreversible or outward-facing actions, a genuine fork in the product direction, missing
credentials, or a spec conflict with no defensible default. Everything else: make the call,
state the assumption in your summary, keep going.

When you do need to talk, **run the `adhd` skill first** and bring options with a
recommendation, not an open question. The exception is a pure yes/no approval gate, where
the question is already fully formed.

### Building UI

- **Always invoke the `ui-ux-pro-max` skill before writing UI code.** Every screen,
  component, style pass, and visual fix. Not optional, not "just this small one".
- **If there is no visual reference to work from, ask for inspiration before building.**
  Screenshots, links, product names, a vibe — anything. Do not guess at a look and ship it.
- The design direction already documented in [`docs/02-design/`](docs/02-design/) *is* a
  reference — use it. Ask for inspo when going beyond what those documents cover.
- The visual language must be **original**. Evoke cinematic armored mission-control, never
  copy a third party's logos, icons, wording, or branded interface assets.

Design tokens, in short: near-black/deep-navy ground; cyan, ice-blue, white for information;
green = verified/operational; amber = warning/escalation; red = critical only. Thin luminous
borders, nested glass panels, restrained glow. Circular instrumentation at the center,
rectangular evidence panels around it. Desktop-first at 1440×900+.

### Git

- Branch from `main`; never push to `main` directly.
- Small coherent commits. Conventional-commit style per
  [`docs/04-development/38-commit-message-guide.md`](docs/04-development/38-commit-message-guide.md).
- Branch names follow [`docs/04-development/37-branch-naming-guide.md`](docs/04-development/37-branch-naming-guide.md).
- Every change goes through a PR. **Claude has standing authority to merge PRs** once gates
  pass — no need to ask.
- Security-sensitive changes (isolation, sandboxing, auth, verification gates, secrets) need
  a `cybersecurity` agent review recorded on the PR before merge.

### Definition of done

See [`docs/04-development/40-definition-of-done.md`](docs/04-development/40-definition-of-done.md).
Short version: spec followed, tests written *and run*, gates green, docs updated if behavior
changed. Never report something as working that you have not actually run and observed.

## The agentic company

This project is staffed by agents defined in [`.claude/agents/`](.claude/agents/) and run
through the `company` skill. Headcount is **dynamic** — roles are hired when the work needs
them and retired when it doesn't. The rules, the current roster, and the hire/fire log live
in [`.claude/COMPANY.md`](.claude/COMPANY.md). Read it before spawning agents.
