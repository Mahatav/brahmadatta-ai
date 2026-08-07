# Technology Stack Document

| Layer | Competition MVP choice |
|---|---|
| Command-center frontend | React, TypeScript, Vite, CSS variables/Tailwind-style utilities |
| Visualization | SVG/Canvas for the Brahmadatta Core; chart library for telemetry; syntax-highlighted diff viewer |
| Live updates | Server-sent events by default; WebSocket only where bidirectional streaming is necessary |
| Control API | Python, FastAPI, Pydantic schemas |
| Orchestration | Explicit persistent state machine |
| Queue | Redis with RQ/Celery or a DB-backed queue |
| Metadata | PostgreSQL; SQLite permitted for the earliest single-machine prototype |
| Artifacts | Encrypted S3-compatible storage or encrypted volume |
| Isolation | Rootless Docker/Podman; microVM/VM adapter for higher-risk targets |
| Static analysis | Semgrep, compiler warnings, optional CodeQL/Joern adapter |
| Dynamic analysis | AFL++, libFuzzer, Address/UndefinedBehavior sanitizers; optional Atheris |
| Tests | CTest/PyTest and configured command adapter |
| Git | Native Git CLI and `git bisect run` wrapper |
| Small-model serving | Self-hosted inference engine on one rented GPU |
| Heavy-model serving | Validated self-hosted engine on a short-lived rented multi-GPU cluster |
| Observability | Structured JSON logs, trace IDs, Prometheus-compatible metrics |
| Packaging | Docker Compose for development; scripted competition deployment |

## Frontend implementation notes

- Build the central Brahmadatta Core in SVG before considering WebGL.
- Use design tokens for color, glow, spacing, typography, and motion.
- Virtualize long event, finding, and log lists.
- Separate mission state from visual animation state.
- Provide deterministic mock telemetry for rehearsals and screenshots.

## Reproducibility requirements

Pin container images, tool versions, model artifacts, prompts, JSON schemas, and dependency lockfiles. Record all identifiers in the evidence report.

---

## Fixed MVP competition decisions

- **Product name:** Brahmadatta AI.
- **Product type:** an authorized, defensive Cyber-Reasoning System for the AI Kavach competition MVP.
- **Architecture:** three evidence-driven tiers: fast deterministic triage, destructive sandbox testing with lightweight patching, and heavy repository-level reasoning only when escalation is justified.
- **Interface:** a dense futuristic armor-command-center dashboard with a central mission core, live telemetry, drill-down panels, and operator controls. The visual language is original and does not copy third-party logos or branded interface assets.
- **Primary workflow:** authorize → ingest → baseline → analyze → correlate → stress-test → patch → verify → export evidence.
- **Compute:** CPU-first processing with self-hosted models on rented GPU infrastructure. Repository content is not sent to an external inference API.
- **MVP target:** C/C++ repositories first; Python support is optional.
- **Verification rule:** a patch is never accepted on model confidence alone. The original reproducer, regression tests, static checks, and renewed fuzzing determine the verdict.
- **Safety boundary:** authorized repositories and isolated environments only; no public-target scanning, no exploit deployment, and no automatic production merge.

## Open decisions / next review

- Assign the final three-person team roles.
- Lock the rented GPU provider and tested model-serving recipe.
- Replace estimated performance targets with benchmark results.
- Confirm the final competition demo repository and fallback recording.
