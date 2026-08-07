# Project Folder Structure

```text
brahmadatta-ai/
├── apps/
│   ├── command-center/       # Astro static shell + React client islands
│   ├── control-api/          # FastAPI REST and event streaming
│   └── operator-cli/         # scripted and emergency operations
├── services/
│   ├── orchestrator/         # persistent mission state machine
│   ├── model-gateway/        # context policy and self-hosted model routing
│   ├── evidence-builder/     # Markdown/JSON reports
│   └── telemetry/            # metrics and UI event aggregation
├── workers/
│   ├── baseline/
│   ├── static-analysis/
│   ├── git-analysis/
│   ├── fuzzing/
│   ├── patching/
│   └── verification/
├── adapters/
│   ├── cpp/
│   └── python/               # optional MVP extension
├── packages/
│   ├── schemas/
│   ├── policy/
│   ├── ui-components/
│   └── test-fixtures/
├── infrastructure/
│   ├── compose/
│   ├── gpu/
│   └── scripts/
├── demo/
│   ├── repositories/
│   ├── expected-evidence/
│   └── presentation-mode/
├── docs/
└── tests/
    ├── unit/
    ├── integration/
    ├── e2e/
    ├── security/
    └── performance/
```

## Command Center frontend boundary

`apps/command-center/` builds a static Astro application. Astro owns the page shell,
routing, document metadata, and production bundle; nginx serves the generated `dist/`
directory. React is retained as the client-island framework because the earlier frontend
decision selected React, so Astro does not introduce a second interactive framework.

Only browser-dependent or live elements hydrate. The control API status probe uses
`client:load` because it must prove the browser-to-nginx-to-Django path immediately. Static
identity, explanatory copy, and layout remain Astro HTML. Future below-the-fold panels should
prefer deferred hydration unless their data is needed at first paint.

Mission events have one browser connection owner in
`src/lib/events/connection.ts`. That plain TypeScript module publishes connection state and
events into nanostores in `src/lib/events/store.ts`; islands subscribe to those stores instead
of constructing their own `EventSource`. This protects the localhost/HTTP deployment from one
long-lived HTTP/1.1 connection per panel and gives reconnect/auth policy one implementation
boundary.

## Repository rule

Frontend visual state, backend mission state, model output schemas, and evidence schemas must be versioned independently but tested together through shared contracts.

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
