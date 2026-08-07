# packages/schemas

`openapi.json` is the frozen control-API contract, generated from the django-ninja
schemas in `apps/control-api/contracts/`. It is **generated, never hand-edited**.

## Regenerating it

```bash
cd apps/control-api
.venv/bin/python tools/export_openapi.py
```

Deterministic output — sorted keys, two-space indent — so a contract change reads as
a diff rather than a reshuffle. `apps/control-api/contracts/tests/test_openapi_dump.py`
fails when the committed file is stale, so the freeze is enforced by CI rather than by
memory.

## Generating TypeScript types for the Astro client

The Command Center consumes this document; it does not describe the API in its own
types. Add to `apps/command-center/package.json`:

```jsonc
{
  "scripts": {
    "types:api": "openapi-typescript ../../packages/schemas/openapi.json -o src/lib/api/schema.d.ts",
    "prebuild": "npm run types:api && git diff --exit-code src/lib/api/schema.d.ts"
  },
  "devDependencies": {
    "openapi-typescript": "^7"
  }
}
```

Then use the generated document type:

```ts
import type { components, paths } from "./schema";

export type MissionEvent   = components["schemas"]["MissionEvent"];
export type MissionDetail  = components["schemas"]["MissionDetail"];
export type ErrorEnvelope  = components["schemas"]["ErrorEnvelope"];
export type MissionState   = components["schemas"]["MissionState"];
```

**Why `prebuild` re-generates and then diffs.** If the backend changes a schema and the
committed types are stale, the build fails on the diff instead of the demo failing on
a missing field. That is the whole point of freezing the contract — see issue #6,
"so a contract change breaks the frontend build rather than the demo".

## What breaks a frontend build on purpose

* Every schema forbids unknown properties, so `openapi-typescript` emits closed object
  types and an added field is visible in the diff.
* `MissionEvent.payload` is a **discriminated union on `kind`**. A `switch` over it
  with `never`-exhaustive default stops compiling the moment a payload variant is
  added:

  ```ts
  function render(payload: MissionEvent["payload"]) {
    switch (payload.kind) {
      case "state_changed": return renderState(payload);
      case "baseline":      return renderBaseline(payload);
      // ...
      default: {
        const unreachable: never = payload; // fails to compile on a new variant
        return unreachable;
      }
    }
  }
  ```
* `MissionState`, `MissionPosture`, `EventType`, `Verdict`, `GateStatus` and
  `ErrorCode` are string enums in the document, so a removed or renamed member is a
  type error at every use site.
* Sandbox network policy is the literal `"deny"`. The UI cannot offer another option
  without the type failing.

## Ownership

The contract is owned jointly and changed through a PR that touches
`apps/control-api/contracts/`, this file's `openapi.json`, and
`docs/03-technical/21-api-specification.md` together. Frozen at D1 by issues #6 and #9.
