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
- **Repository content is never sent to an external inference API.** CPU-first, self-hosted
  models. No calls to hosted LLM providers from product code. **Rented GPU was cut entirely**
  (D-015, 2026-08-06, cost/schedule-risk/external-dependency reasons) — CPU-only inference
  (codellama:7b-instruct via a local Ollama container, D-121) is the real, committed path,
  not a placeholder. `docs/03-technical/17-technology-stack-document.md` and
  `26-infrastructure-and-hosting-plan.md` still describe the pre-D-015 rented-GPU plan in
  places; this line wins.
- **Safety boundary:** authorized repositories and isolated environments only. No public
  target scanning, no exploit deployment, no automatic production merge.
- **Target language:** C/C++ first. Python support is optional and must not delay C/C++.
- **No decorative fake metrics.** Every counter, chart, and animation in the UI displays real
  telemetry, or a clearly-labelled deterministic mock in presentation mode.

## Stack

**The stack was changed by CEO decision on 2026-08-06, after the doc pack was written.**
`docs/03-technical/17-technology-stack-document.md` still shows React/Vite and FastAPI in
places — this table wins, and that document gets reconciled in issue #9.

| Layer | Choice |
|---|---|
| Command center | **Astro**, with the live panels as client islands |
| Visualization | SVG for the Core (SVG before WebGL) |
| Ingress | **nginx** — serves the Astro build, proxies the API, terminates TLS |
| Control API | **Django** + django-ninja (Pydantic schemas, generated OpenAPI) |
| Live updates | Server-sent events over ASGI; WebSocket only for true bidirectional needs |
| Persistence | Django ORM + migrations against PostgreSQL |
| Orchestration | Explicit persistent state machine |
| Queue | Postgres-backed, no broker — one `Job` table, `SELECT ... FOR UPDATE SKIP LOCKED` (Redis runs in the compose stack but is currently unused by the orchestrator) |
| Isolation | Rootless Docker/Podman |
| Static analysis | Semgrep, compiler warnings |
| Dynamic analysis | libFuzzer, ASan/UBSan |
| Observability | Structured JSON logs, trace IDs |

Two things to know about this combination:

- **Astro is carrying layout, routing, build and the static shell.** The Command Center is an
  almost entirely interactive real-time dashboard, so most of it lives in client islands.
  Share one SSE connection across islands rather than opening one per panel.
- **nginx buffers proxied responses by default, which silently breaks SSE.** The stream will
  work against Django directly and die behind the proxy. `proxy_buffering off` on the SSE
  location, and always test through nginx.

Folder layout is specified in [`docs/04-development/35-project-folder-structure.md`](docs/04-development/35-project-folder-structure.md).
Put code where that document says it goes — the directories are created as code lands, not
kept as empty placeholders.

## Schedule

**14 days total. Deadline 2026-08-20. Build target 2026-08-13 (7 days).** The doc pack's
8-week plan is superseded; see [`docs/09-company/03-seven-day-plan.md`](docs/09-company/03-seven-day-plan.md).

At this compression the [P0 cut](docs/09-company/01-vision-and-p0-cut.md) is not a
prioritization aid, it *is* the plan. Everything ranked P1 or P2 is in the `CUT` milestone.
Do not build anything from `CUT` without an explicit decision, however small it looks.

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
