# Mission event fixtures

A committed mission event log, and a command that replays it over the real SSE contract.

**Start here:**

```sh
python3 packages/test-fixtures/sse_replay.py
```

Then point a panel at `http://127.0.0.1:8971/api/v1/missions/b7ad2c10-4f61-4f6d-9d2e-1c7a4b6d0e11/events`.
The paths, the SSE framing, the headers and the JSON are the ones the control API will
serve, so nothing in a panel changes when the orchestrator (#12) lands behind them.

Nothing here needs the control API, a database, a model, or a container. Python 3.12 and
the standard library.

## Why this exists

Mahatav and Raunak are 12.5 hours apart with no overlapping working hours. Every Command
Center panel needs mission events, mission events come from the baseline worker, and the
baseline worker is Raunak's. That dependency costs half a shift on D3, D5 and D7 — a
question asked at the end of one shift is answered at the start of the next.

This breaks it. Panels get built against replayed events today; the day the real worker
lands, they already work.

## What is in the fixture

`missions/mission-pktcfg-001.events.jsonl` — 60 events, one JSON object per line, one
full mission against `demo/repositories/pktcfg`:

| | |
|---|---|
| **Happy path** | authorize → snapshot → preflight → baseline (8/8 green) → analyze → stress test → crash found → minimized reproducer → two patch candidates → one `VERIFIED`, one `REJECTED` → evidence exported → mission `VERIFIED` |
| **A degraded stage** | `ANALYZE` runs with no analyzer configured (Semgrep and warning capture are cut). Completes with 0 findings, `severity: MEDIUM`, and `percent_complete: null` so a panel shows an indeterminate indicator instead of inventing a number |
| **A degraded dependency** | the model host is down, so every candidate carries `replayed_from_transcript`. The degradation is in typed data, not only in a log line |
| **A failed stage** | the first `STRESS_TEST` attempt fails outright — no libFuzzer runtime — and emits `STAGE_COMPLETED` with `status: FAILED`. It then recovers through the recorded-corpus path, reported honestly as `REPLAYED_CORPUS` |
| **A policy rejection** | a third candidate edits `CMakeLists.txt`, is refused by patch policy, and never reaches verification. Exercises `POLICY_VIOLATION` and a patch that carries a verdict-less outcome |
| **A gap** | injected at stream time — see below |

Every payload variant in the envelope union is emitted at least once, so there is no
`switch` branch a panel cannot develop against.

### The numbers are real

The baseline counts, the timings, the resource usage, the sanitizer frames, the crash
digest, and both candidates' gate results all came off real runs of the demo target.
`missions/mission-pktcfg-001.provenance.json` lists every measurement with the command
that produced it, and — just as important — lists what was *constructed* rather than
measured. A value in the fixture that is not traceable to a line in that file should not
be there.

### The gap is in the stream, not in the file

`sequence` is documented as a gap-free per-mission counter, and the stored log respects
that: a gap is something a transport loses, never something a server recorded. Baking one
into the file would teach every panel built against it the wrong invariant.

So the replay withholds sequences 13–15 from the live stream instead. A client sees
`id: 12` then `id: 16`, notices, and recovers the ordinary way:

```
GET /api/v1/missions/{id}/events/replay?since_sequence=12
```

`--drop ''` streams the log intact; `--drop 40-42` moves the window.

## The replay command

```sh
# defaults: loopback, port 8971, 4x speed, sequences 13-15 withheld
python3 packages/test-fixtures/sse_replay.py

# real time, nothing withheld
python3 packages/test-fixtures/sse_replay.py --speed 1 --drop ''

# as fast as the socket takes it — for when a panel just needs terminal state
python3 packages/test-fixtures/sse_replay.py --speed 0

# restart forever, for leaving a panel running
python3 packages/test-fixtures/sse_replay.py --loop

# validate the fixture and exit
python3 packages/test-fixtures/sse_replay.py --check
```

Routes served: `GET /api/v1/missions`, `GET /api/v1/missions/{id}`,
`GET /api/v1/missions/{id}/events` (SSE, honours `Last-Event-ID`), and
`GET /api/v1/missions/{id}/events/replay?since_sequence=N&limit=M`.

### Sort by `sequence`, not by `timestamp`

RFC 3339 drops the fractional part when it is zero, so the stream carries both
`13:00:00Z` and `13:00:00.400000Z`. Lexicographically `.` sorts before `Z`, so a string
sort puts the later event first. `sequence` is a gap-free integer and it is what the SSE
`id:` field carries. There is a test named after this
(`test_timestamps_must_not_be_compared_as_strings`) because it is the kind of thing that
looks fine until an event rail is subtly out of order.

## This is a build tool. It never goes on screen.

`docs/09-company/10-fallback-ladder.md` §2.5 bans this fixture from the finale, and the
reasoning is worth repeating: it is fabricated telemetry that looks exactly like a real
mission, which is what makes it useful in week one and dangerous at hour 30 when the
panels are dead and this is the obvious thing to reach for. There is no labelled-mock
middle ground to hide in — #52 is cut.

Two things enforce that here rather than leaving it to a tired operator:

- the server binds loopback only, and `--allow-remote` is needed to serve it anywhere
  another machine can reach;
- every response carries `X-Brahmadatta-Fixture: replay` and the stream opens with a
  `: FIXTURE REPLAY` comment, so a panel, a proxy log and a screen recording all show
  what it is.

## Checks

```sh
# contract conformance + the mission's own invariants + replay behaviour
pytest packages/test-fixtures/tests -q

# does the stream survive an nginx hop? (needs docker)
./packages/test-fixtures/verify-through-nginx.sh
```

`tests/test_mission_fixture.py` validates every event against
`packages/schemas/openapi.json` — the same frozen dump
`apps/command-center/src/lib/api/schema.d.ts` is generated from. A contract change that
would break the Command Center's TypeScript types breaks this test in the same run.

`verify-through-nginx.sh` is the one that catches the failure nothing else does. nginx
buffers proxied responses by default; a buffered SSE stream arrives as one lump at the
end with no error in any log, and the signature is "works against the app directly, dies
through nginx". Read the header comment in that script before changing anything about the
stream — including the note on what could and could not be reproduced.

## Regenerating

Only when the contract changes or a measurement is re-taken:

```sh
DJANGO_SETTINGS_MODULE=config.settings.test \
DJANGO_SECRET_KEY=fixture-build-not-a-real-secret-0123456789abcdef \
DATABASE_URL=sqlite:///fixture-build.sqlite3 \
python3 packages/test-fixtures/tools/build_mission_fixture.py
```

The generator constructs every event through the real pydantic models, so the cross-field
rules JSON Schema cannot express — verdict derivation agreeing with the gate matrix,
`MODEL_GENERATED` requiring provenance, verdict counts matching their own candidate list
— all run at build time. An invalid fixture cannot be written.
