# Cut Pullback Design Spec — Analysis Rail, Presentation Mode, Keyboard Operability

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Document | Design addendum — closeout pullback, `CUT` milestone issues #25, #52, #56 |
| Status | **Draft, pending `product-manager` review** (user-facing scope) and `cybersecurity` review (§3, presentation-mode gating; §4, destructive-control confirm pattern) |
| Drafted by | `ui-ux-designer` seat |
| Date | 2026-08-16 |
| Extends | [`04-design-system.md`](04-design-system.md) rev 2 — does not replace it. Every token, rule and state word below is drawn from `packages/ui-components/tokens.css`; no new primitive colour is introduced. |
| Governs | `apps/command-center/src/components/MissionCommandCenter.tsx` (Analysis Rail extension), a new presentation-mode surface, and the keyboard/focus contract for the whole app |
| Reads with | `.project/decisions.md` D-009, D-023, D-049; `docs/09-company/03-seven-day-plan.md`; `docs/09-company/10-fallback-ladder.md` §2.5, §4 |

---

## 0. What this document is answering, and a disclosure about how it was built

`.project/state.md` and `.claude/COMPANY.md` were read in full before drafting. Issues **#25**,
**#52** and **#56** were named as the source of acceptance criteria, to be read in full with
`gh issue view`. **This session had no shell/`gh` tool available** — only file read/write/search
tools — so the live issue bodies could not be fetched. Per the standing rule this project holds
everyone to (D-049: a property is described as enforced only when a named test/source
demonstrates it), that gap is disclosed here rather than silently worked around.

What this spec is grounded in instead, all read in full:

- `docs/09-company/04-design-system.md` rev 2 (tokens, panel specs, D-009/D-023 as built into the
  UI, §11's record of what P1-7/P1-10/`StaticFindingsPanel` were when cut)
- `docs/09-company/01-vision-and-p0-cut.md` §2 (P1-7 presentation mode, P1-10 keyboard
  operability, and the cut `StaticFindingsPanel`/Semgrep line)
- `docs/09-company/03-seven-day-plan.md` (the CUT table's one-line consequence for each of the
  three items)
- `docs/09-company/10-fallback-ladder.md` §2.5 and §4 (the existing, load-bearing doctrine on
  mock data and disclosure — presentation mode has to fit inside this, not around it)
- `packages/test-fixtures/README.md` and `mission-pktcfg-001.events.jsonl` (the actual event
  shapes available to build against, per #71)
- The **real** `apps/command-center/` source — `MissionCommandCenter.tsx`,
  `VerdictComparePanel.tsx`, `AIParticleCore.tsx`, `LocalRepositoryIntake.tsx`,
  `SystemStatus.tsx`, `ModelGatewayStatus.tsx`, `LiveEventStatus.tsx`, `store.ts`,
  `global.css`, `index.astro` — not just the idealized panel set in the design system doc

**Open question for whoever picks this up** (named again in the handoff): confirm this spec
against the actual `#25`/`#52`/`#56` acceptance criteria once `gh` access is available, and flag
any criterion this document didn't anticipate. Everything below is checkable against the sources
listed, but a source I could not read is a source I could not check against.

### 0.1 The codebase has already diverged from the design system doc — this spec follows the real one

The design system doc (rev 2) specifies an idealized five-panel screen: a 10-row stage timeline,
a `FindingsList` with an always-expanded evidence block, and a `Candidate Compare` **overlay**
(DS-02) reached by `[ OPEN COMPARE ]`. The actual `MissionCommandCenter.tsx` today is a different,
real shape:

```
mission-shell
├─ command-bar (6 static chips — AI STATUS / AUTHORITY / FILES MAPPED / REPOSITORY / AUTOMATION / LAST UPDATE)
├─ mission-frame
│  ├─ core-panel        → AIParticleCore (a voice/text "local AI" console, 3 real controls)
│  └─ mission-panels
│     ├─ VerdictComparePanel   → an INLINE two-column grid, not an overlay
│     ├─ AnalysisRail          → repo / snapshot / baseline / ctest / regression / size / signal files
│     ├─ [stage progress]      → a flat <ul> of 9 stages (progress-track), not the 10-row timeline
│     └─ [live work]           → single most-recent finding/message readout
└─ resource-strip (status text only, no controls yet)

LocalRepositoryIntake  → HUMAN / LOCAL PATH inputs, an authorize checkbox, [DEV PATH SCAN], [CHOOSE BROWSER FOLDER]
SystemStatus / ModelGatewayStatus / LiveEventStatus → read-only status text, no controls
```

None of the P0 bottom-strip controls the design system specifies —
`[ AUTHORIZE + START ]`, `[ PAUSE ]`, `[ CANCEL MISSION ]`, `[ EMERGENCY TEARDOWN ]`,
`[ EXPORT EVIDENCE ]`, `[ OPEN COMPARE ]` — exist as built controls yet. `VerdictComparePanel` is
inline, and `MissionSnapshot.finding` is a **single** optional finding, not a list.

This is not a conflict to resolve by picking a side. Per this role's standing rule ("never
silently override or rewrite another role's prior work"), **this document specs against the real
DOM** as it exists today, and separately marks every place the design system's aspirational
control set (Authorize/Pause/Cancel/Teardown/Export/Compare) needs a keyboard path **once it is
built**, so the frontend developer isn't left guessing when those controls land. Nothing here
asks anyone to revert the real implementation to the idealized layout.

One more divergence, flagged but out of scope for this document to fix: `global.css` uses
`text-shadow` glow (`.eyebrow`, line 55-56) and gradient-mesh backgrounds (`.command-center`,
lines 9-12) that read as exactly the "glow" and "gradient" the design system's §2.4 prohibits
outright ("there is no glass, no bevel, no shadow and no glow anywhere in this system"). This
predates this task and touches none of #25/#52/#56's surfaces directly. Named in **Risks** below
rather than silently worked around or silently fixed.

---

## 1. #25 — Analysis Rail: findings by severity, dependency and compiler health

### 1.1 What exists and what this adds

`AnalysisRail` (built for #20) already renders repository/snapshot/baseline/ctest/
regression/size/signal-files, all wired to real event data. #25 is **not** a new sixth panel —
same precedent as the design system's §6.6 resource ledger: it is a chip-group extension of the
one rail that already exists, adding three new labelled regions beneath the existing
`analysis-rail__state` block:

```
[ ANALYSIS RAIL ]                                    [ BASELINE GREEN ]
Repository   local:pktcfg
Snapshot     a4f1c9de1203...9fe201
Baseline     passed from event stream
CTest        42 passed / 0 failed / 42 total
Regression   PASS - ctest
Size         4.2 MiB
Signal files 61 mapped signals / 118 files
─────────────────────────────────────────────────────────  ← existing, unchanged above this rule
[ FINDINGS BY SEVERITY ]
[ FINDING 01 ]  HEAP-BUFFER-OVERFLOW              [ ● CONFIRMED ]      ← new
                src/decode.c:118 · MEDIUM         [ VIEW EVIDENCE ]
─────────────────────────────────────────────────────────
[ DEPENDENCY HEALTH ]
[ — DEPENDENCY HEALTH · NOT RUN · no dependency scanner in this build ]   ← new
─────────────────────────────────────────────────────────
[ COMPILER HEALTH ]
[ — COMPILER HEALTH · NOT RUN · warning capture not built (P1-2) ]        ← new
```

### 1.2 The honesty ground truth (why the last two rows are permanently `NOT RUN`)

Checked directly against `store.ts`'s `MissionSnapshot` type and the committed fixture:

- `finding` is a **single optional field**, not a list. There is no severity-grouping data
  structure anywhere in the contract today. P0 produces at most one confirmed finding
  (design system §6.3), so "grouped by severity" is built as a **real list component that
  currently renders 0 or 1 rows** — the grouping structure exists so it is correct the day a
  second finding exists, but nothing here fabricates empty severity buckets to look
  comprehensive.
- **There is no dependency-scanning capability in this build at all.** Not cut-with-a-flag —
  never built, never scoped as P0 or P1. No event kind, no field, nothing in
  `packages/schemas/openapi.json` carries a dependency finding.
- **Compiler-warning capture is P1-2, explicitly cut** (`03-seven-day-plan.md`, `01-vision-and-
  p0-cut.md` §2). The `BASELINE` stage's `configure ok` / `build ok` events (visible in the
  fixture, `sequence` 12-13) prove the build **succeeded** — that is a different claim from
  "we captured and graded the compiler's warnings," and this rail must not conflate them. A
  clean build with warnings never surfaced is not the same as a build audited for warnings and
  found clean.

### 1.3 The design call: these two rows get gate-style `NOT RUN` treatment, not value-style em dash

D-023 and DS-03 (`04-design-system.md` §2.1, §15) draw a line: an **unproduced value** (a counter
whose producing step hasn't completed) is a quiet em dash in `--bd-text-secondary`; an **unrun
gate in a verdict matrix** is loud — `--bd-state-not-run`, the word `NOT RUN`, a mandatory inline
reason. The review question DS-03 gives for telling them apart is *"is this in a gate matrix?"*
Dependency health and compiler health are not members of the five-gate `VerificationRecord`
matrix, so a literal reading says em dash and quiet.

That reading is wrong here, and the reason is the same one D-009 exists for: **an entire class of
check that never ran, sitting in a panel titled "Analysis Rail," rendered as a quiet secondary-
grey line, reads exactly like "nothing to report" to someone skimming the dashboard** — which is
the specific overclaim-by-omission this whole project has a standing rule against. The rail's
job (per the task that produced #25) is to disclose analysis *coverage*, not just analysis
*results*. So this document extends the gate-style treatment — `--bd-state-not-run`, word
`NOT RUN`, mandatory inline reason — to these two rows, on the grounds that "a capability that
was never wired, presented next to ones that were" is structurally the same shape D-009 was
written to police, even though it sits outside the `VerificationRecord` schema. This is recorded
as **D-057** in `.project/decisions.md`, since it extends a rule to a location the rule's own
author (DS-03) didn't specify, and needs the same authority DS-03 got.

**Reason strings** — rendered verbatim, never composed by the frontend, matching the design
system's `GateResult.detail` discipline (§6.4.3):

| Row | Reason string | Source |
|---|---|---|
| Dependency health | `no dependency scanner in this build` | Static string — there is no backend field to source it from because there is no producer at all. **Open question for backend**, below. |
| Compiler health | `warning capture not built (P1-2)` | Mirrors the exact pattern already shipped for `[ 04 ] ANALYZE` — `no static analyzer configured in this build` (design system §6.2) — same honesty rule, same citation style. |

### 1.4 Findings-by-severity row — construction

Reuses the design system's existing finding-row and evidence-block specs (§6.3, §6.3a) rather
than inventing new ones — same 44px row, same `[ FINDING NN ]` bracket, same severity chip, same
`[ ● CONFIRMED ]` / `[ — REPORT · NOT YET CAPTURED ]` state rule. What's new here is only the
**severity-first sort key** and the **drill-down control**:

- Sort: `CRITICAL → HIGH → MEDIUM → LOW → INFO`, then discovery order within a severity. (P0's
  fixture emits `severity: MEDIUM` on the one finding it produces — see `FindingSummary` in
  `store.ts`.)
- Each row ends in a real `<button type="button">[ VIEW EVIDENCE ]</button>` — not a `<div
  onClick>` — that expands the same evidence block already specified in design system §6.3a
  (sanitizer trace + reproducer record) inline beneath the row. This is the drill-down to
  file:line the task calls for: `src/decode.c:118` is already a field on `FindingSummary.location`
  and is rendered as part of the existing evidence block, not duplicated here.
- Severity chip colour follows the existing state vocabulary (§5): `CRITICAL`/`HIGH` →
  `--bd-state-critical`; `MEDIUM` → `--bd-state-warning`; `LOW`/`INFO` → `--bd-text-secondary`.
  (No new colour — `MEDIUM` reuses warning amber, which is already load-bearing for `NOT RUN`
  elsewhere in this same rail; they are told apart by the mandatory word, per §5's own rule that
  colour is never the only channel.)

### 1.5 States for the extended rail

Additive to the existing `AnalysisRail` state machine (`idle | ready | running | degraded |
failed | passed`, already implemented) — none of these new states replace it; they govern only
the three new sub-regions.

| Region | Empty (before producer could run) | Zero / clean (producer ran, found nothing) | Populated | Degraded (stream stale) | Failed |
|---|---|---|---|---|---|
| Findings by severity | `[ FINDINGS · — ]`, "Findings appear when a sanitizer report is captured." | `[ FINDINGS · 0 ]`, "Stress test completed. No sanitizer-confirmed defect in this snapshot within the fuzzing budget." (exact wording from design system §6.3, reused verbatim — this is the one row where a genuine producer exists) | Rows as above, sorted by severity | Header gains `[ ! MAY BE INCOMPLETE ]`; already-captured evidence is not greyed (§6.3 rule, unchanged) | `[ × FINDINGS UNAVAILABLE ]` + error + `[ RETRY ]` |
| Dependency health | *(no empty state — there is no producer to be pending)* | *(unreachable — nothing will ever complete this)* | *(unreachable in this build)* | Unaffected by stream staleness — this is a build-time fact, not a live value | Unaffected — never fails, because it never runs |
| Compiler health | Same as dependency health: permanently `[ — COMPILER HEALTH · NOT RUN · warning capture not built (P1-2) ]` from first paint, never changes for the life of the mission | | | | |

The dependency/compiler rows having **no other state** is deliberate and is the whole point:
giving them a loading or running state would imply a producer that doesn't exist. They render
their one true state immediately and never move, which is itself the honest signal — a static
`NOT RUN` row next to a live-updating findings list is legible at a glance as "this one never
started," without needing any additional copy to say so.

### 1.6 Open questions for backend (named, not guessed at)

1. Is there any intent to add a `dependency_scan` event/report kind before the finale, even a
   stub? If never, the reason string above is correct as a permanent static string in the
   frontend. If a stub is planned, the frontend should read the reason from `GateResult.detail`-
   style backend data instead of hardcoding it, matching how `[ 04 ] ANALYZE`'s sub-line already
   works — **backend-developer** to confirm which.
2. Confirm the exact compiler-health reason string backend wants published. `warning capture not
   built (P1-2)` mirrors the existing `no static analyzer configured in this build` pattern but
   is drafted by this seat, not sourced from a `LOG` event — same open item the design system
   doc itself left open at §13 row 3a for the static-delta/renewed-fuzz strings, now with a third
   sibling.

### 1.7 Component inventory

| Component | New/extends | Notes |
|---|---|---|
| `AnalysisRail` | **extends** existing | Add the three new regions; do not touch the existing state machine or the strings `check-issue-20-analysis-rail.mjs` already asserts on |
| `SeverityFindingsList`, `SeverityFindingRow` | **new** | Reuses `EvidenceBlock` (design system §6.3a) on expand — does not reimplement it |
| `NotRunCoverageRow` | **new** | The shared component for the dependency-health and compiler-health rows — one component, two instantiations, so the `NOT RUN` rendering rule (word + colour + mandatory reason) can't drift between them |

---

## 2. #52 — Presentation mode

### 2.1 The doctrine this has to fit inside, not around

`docs/09-company/10-fallback-ladder.md` §2.5 is unambiguous and remains in force, unchanged by
this document: **#71's committed SSE fixture must never be streamed in front of a judge**, and
at the finale "there is no presentation mode to hide behind... #52 is in `CUT`." That is a
statement about the **finale**, and this pullback does not reopen it. What #25/#52/#56 are being
pulled back for is the internal closeout push — rehearsal, screenshots for the five-slide
submission, and internal walkthroughs before the finale — never a live judged run.

**Presentation mode's one and only sanctioned use: rehearsing the Command Center's look and
interaction against deterministic, clearly-labelled data, when no real mission or real judge is
in the room.** It reuses the exact fixture (#71) the fallback ladder already forbids from
finale display, and it exists specifically to give that fixture an on-screen disclosure it does
not have when run standalone (`sse_replay.py` only marks itself via HTTP header and an SSE
comment — neither is visible in the rendered UI). This is the gap #52 closes: not "a new way to
show mock data," but "the fixture's existing safeguards, finally visible on the screen they
protect."

### 2.2 How it is enabled — the part that has to be structurally hard to trigger by accident

The task's hard requirement: *impossible to enable accidentally during a real mission.* This
rules out a runtime checkbox, a query parameter, a keyboard shortcut, or any control reachable
from the page an operator uses during a live mission. The design:

- **A build-time flag, not a runtime toggle.** `PUBLIC_BD_PRESENTATION_MODE=true` is read once,
  at Astro build time, and **defaults to unset/false** — per D-049's standing rule that a default
  points at the humbler claim, "not presentation mode" is what you get for free. There is no
  code path in the finale/production bundle that reads this flag at runtime and flips behavior;
  the presentation-mode components are conditionally **imported at build time**, so a browser
  inspecting the shipped finale bundle cannot find the toggle at all, let alone flip it. (This is
  an implementation instruction for whoever builds it — it is not something this document can
  itself enforce, and per D-049 it is described as "intended" until a build-artifact test proves
  the code is actually absent. See the acceptance criterion in §2.7.)
- **A separate build artifact.** `command-center:presentation` is its own image tag / its own
  `.env.presentation`, built and run only for rehearsal, never the artifact deployed for the
  finale or committed as `latest`. There is exactly one place presentation mode can be turned on:
  the build command, run by a human, on a machine that is not the finale machine.
- **Refuses to bind to a real mission, at runtime, as a second independent lock.** Even inside a
  presentation-mode build, if the page is loaded with `?mission=<uuid>` pointing at a live
  control-api mission (i.e., `getMissionDetail` succeeds against a real, non-fixture backend),
  presentation mode **does not activate** — the mock walkthrough refuses to start and the page
  falls back to ordinary live behavior. This is the "cannot be triggered during a real mission"
  requirement made structural rather than a policy nobody checks: two independent conditions
  (build-time flag *and* no live mission bound) both have to be true, and the second one is
  checked against the actual backend response, not against operator intent.

### 2.3 The indicator — extends design system §2.6 exactly, then goes one step further

§2.6 already specifies the baseline: *"mocked values render with a persistent `[ ! MOCK DATA ]`
chip in `--bd-state-warning` fixed to the top strip, visible on every screen, not dismissible."*
This document implements that literally, and adds one thing §2.6 did not anticipate because it
was written before this task's specific requirement — **"visible in any screenshot taken while
it's active,"** including a cropped one.

**Primary disclosure — top-strip chip, exactly as specified:**

```
[ ! MOCK DATA · REHEARSAL, NOT LIVE · fixture: mission-pktcfg-001 ]
```

- `mono-md` (ROOM tier — legible at distance, matching every other ROOM-tier disclosure in this
  system), `--bd-state-warning`, fixed to a dedicated band **above** the existing `command-bar`,
  full viewport width, height 28px (fits inside the existing `--bd-space-5`/`--bd-space-6`
  rhythm — 28 = 24 + 4, no new spacing token needed).
- Cites the fixture by name, not a vague "demo mode" — matching design system §10's copy rule
  ("name the thing that happened, with its number"). If a different fixture is ever used, the
  string is generated from that fixture's own filename, never hand-typed.
- **Not dismissible.** No close control. §8's motion rules apply — static, no pulse, no flash
  (a critical alert may pulse its crop ticks *once*, per §8; this is not a critical alert, and it
  never animates at all).

**Secondary disclosure — a full-bleed watermark, new in this document.** A single fixed chip can
be cropped out of a screenshot focused on, say, just the Core or just the verdict panel. To make
the disclosure survive cropping, this document adds a repeating diagonal texture across the
entire viewport background whenever presentation mode is active — reusing the exact
`repeating-linear-gradient` construction already present in `global.css`'s existing background
(the 135°, 38px-pitch hazard-stripe pattern already used for the page's base texture), recoloured
from its current `--bd-c-rule-faint` tint to `--bd-c-warning` at low opacity (`color-mix(in srgb,
var(--bd-c-warning) 8%, transparent)`), and stamped with the literal words `MOCK DATA` repeated
along the diagonal at `mono-3xs`, `--bd-c-warning`, 15% opacity — legible enough to survive a JPEG
screenshot at any crop, faint enough not to fight the panels sitting on top of it. This is a
genuine **extension** beyond §2.6's literal text, because §2.6 was written to protect "every
screen you navigate to," not "every possible crop of a screenshot" — the crop-survival
requirement is new in #52's brief. Recorded as part of **D-058**.

### 2.4 Where it renders, and what data it labels

Every value on screen inside a presentation-mode build comes from the fixture replay server
(`packages/test-fixtures/sse_replay.py`), loopback-bound, already carrying
`X-Brahmadatta-Fixture: replay` and the `: FIXTURE REPLAY` SSE comment per its own README. This
document adds one field the store does not have today: `MissionSnapshot.mockSource: 'fixture-
replay' | null`, set **only** when the SSE connection's response actually carried
`X-Brahmadatta-Fixture: replay` — read from the real header, never inferred from the build flag
alone. The chip and watermark render if and only if `mockSource` is non-null. This means the UI's
disclosure is driven by the same independent signal that already exists to keep the fixture
honest server-side (per the fallback ladder's own §2.5 design), rather than by a second,
disconnected client-side flag that a bug could let drift out of sync with what's actually being
shown. This is the D-049-shaped property: **it is checkable** — a test can assert that
`mockSource` is only ever set when the header was present, and the chip's render condition can be
asserted against `mockSource` alone (see acceptance criteria, §2.7).

### 2.5 States

| Condition | Behaviour |
|---|---|
| Not a presentation-mode build | Zero cost — the components aren't imported, the flag isn't read, nothing changes |
| Presentation-mode build, no mission bound | Chip and watermark active; operator can walk the fixture end to end via `sse_replay.py --loop` |
| Presentation-mode build, `?mission=<uuid>` resolves to a real (non-fixture) mission | **Refuses to activate the mock walkthrough.** Page renders `[ × PRESENTATION MODE BUILD — REAL MISSION DETECTED, MOCK DISABLED ]` in `--bd-state-critical` at the top strip in place of the mock-data chip, and falls through to ordinary live rendering against the real mission. Never both at once. |
| Presentation-mode build, fixture connection lost | Same "stream stale" freeze behaviour as live mode (D-022 is unaffected by this document) — the mock data doesn't fake liveness either |

### 2.6 Where it cannot be triggered — explicit list, for review

- No control in the finale build's shipped JavaScript enables it — it is not present, not merely
  disabled (§2.2).
- No keyboard shortcut anywhere in §4's map enables, disables, or reveals it. This is called out
  again there so the two documents can't drift.
- No query parameter, cookie, or `localStorage` value enables it. The only lever is the build
  artifact chosen at deploy/run time by a human running a build command.
- It cannot coexist with a bound real mission (§2.2, §2.5).

### 2.7 Acceptance criteria this spec expects a named test to demonstrate (D-049 discipline)

Listed so "impossible to enable accidentally" is never asserted here without a test to point at:

1. A build of the finale/production artifact contains no reference to the presentation-mode
   components or flag, checkable by grepping the built bundle.
2. `mockSource` is set only when a test double's SSE response includes
   `X-Brahmadatta-Fixture: replay`, and never otherwise.
3. Loading a presentation-mode build with `?mission=` pointing at a real mission never renders
   the mock chip and never renders fixture data — it renders the "real mission detected" critical
   state instead.

### 2.8 Component inventory

| Component | New/extends | Notes |
|---|---|---|
| `PresentationModeChip` | new | Top-strip disclosure, §2.3 |
| `MockDataWatermark` | new | Full-bleed diagonal texture, §2.3 |
| `store.ts: MissionSnapshot.mockSource` | extends | One new field, driven only by the real SSE response header |

---

## 3. #56 — Keyboard operability of the Command Center

Design system §9 already establishes the ground rules this section builds on and does not
repeat unnecessarily: focus is always visible (`:focus-visible` — 2px `--bd-focus-ring` at 4px
offset, already in `tokens.css`'s base layer, already 12:1 contrast, no change needed), colour is
never the only channel, tab order matches visual order, `[ ESC ]` closes an overlay and returns
focus to the control that opened it, and — explicitly — the **command palette is cut** (§11).
This document does not reinstate it. Any global `Ctrl/Cmd+K`-style shortcut surface is out of
scope; reinstating it would be un-cutting a different item than the one this task authorized.
That is recorded as part of **D-059**.

What follows is the map §9 said was out of scope to build in full: exact tab order and shortcuts
across the **real** component tree (§0.1), plus the P0 control set the design system specifies
but that doesn't exist as built controls yet — both, so this is usable the moment either set of
controls is worked on.

### 3.1 Tab order — the real DOM, today

Numbered in document order; this is also the order a screen-reader user encounters via linear
navigation, since design system §9 requires tab order to match visual order and nothing here
introduces `tabindex` values that would break that.

| # | Element | Component | Activation |
|---|---|---|---|
| — | *(command-bar's 6 chips are static text, not focusable — nothing to tab to)* | `MissionCommandCenter` | — |
| 1 | `[ Activate local AI core ]` toggle | `AIParticleCore` | `Enter` / `Space` — starts/stops the mic-style mode cycle |
| 2 | `LOCAL AI CHANNEL` text input | `AIParticleCore` | Types a prompt |
| 3 | `[ ASK ]` submit | `AIParticleCore` | `Enter` (from the input, native form submit) or `Enter`/`Space` on the button directly |
| — | *(VerdictComparePanel, AnalysisRail's existing rows, progress-track, live-work — all static readouts today; no focusable elements until §3.2/§3.3's additions land)* | | |
| 4 | `HUMAN` text input | `LocalRepositoryIntake` | Types operator name |
| 5 | `LOCAL PATH` text input | `LocalRepositoryIntake` | Types a path |
| 6 | Authorization checkbox | `LocalRepositoryIntake` | `Space` toggles |
| 7 | `[ DEV PATH SCAN ]` | `LocalRepositoryIntake` | `Enter`/`Space` — triggers the scan |
| 8 | `[ CHOOSE BROWSER FOLDER ]` file picker | `LocalRepositoryIntake` | `Enter`/`Space` opens the native OS folder picker (native `<input type=file>` behaviour — no custom keyboard handling needed, and none should be added) |
| — | *(SystemStatus, ModelGatewayStatus, LiveEventStatus — all static readouts, nothing focusable)* | | |

**New, from §1 (Analysis Rail extension):**

| # | Element | Activation |
|---|---|---|
| 3a | `[ VIEW EVIDENCE ]` per finding row, inserted into tab order immediately after the finding it belongs to, in severity order | `Enter`/`Space` expands the evidence block inline (no navigation, no new page — matches design system §6.3a's "always adjacent, never behind a route" intent) |

### 3.2 The scrollable regions — a real gap in the current build

Two elements render as scrollable but are **not** natively keyboard-scrollable without a
`tabindex`, which is a common and easy-to-miss WCAG failure: the virtualized signal-file `<ol>`
(`virtual-signal-list__rows`) and, once built, the diff `<pre>` inside `VerdictComparePanel`
(currently rendered without an explicit scroll container, but the design system's §6.4.4 spec
calls for a 194px scroll region once the diff exceeds what fits). **Requirement, new in this
document:** every scrollable region gets `tabIndex={0}` and a `role` appropriate to its content
(`role="region"` with an `aria-label` naming what it holds), so it is a reachable tab stop, and
standard arrow-key/`Page Up`/`Page Down`/`Home`/`End` scrolling works inside it once focused —
this is native browser behaviour for a focusable overflow container and requires no custom key
handling, only the `tabIndex` and the CSS `overflow` that's already there.

### 3.3 The P0 control set — not built yet, mapped so it's built right the first time

These controls are specified in `04-design-system.md` §2.7, §3, §4.1 and §4.2 but do not exist as
wired buttons in the current codebase. This is the keyboard contract for them, so whoever
implements the bottom-strip control row (or the Authorize dialog, or `[ OPEN COMPARE ]`) is not
inventing focus order and shortcut behaviour from nothing.

**Bottom-strip control row, left-to-right tab order** (matches the visual order design system §3
already lays out):

| Control | Shortcut | Behaviour |
|---|---|---|
| `[ AUTHORIZE + START ]` | none reserved — this is the entry action, not a shortcut target | `Enter`/`Space` opens the confirmation dialog (design system §4.1 row 2). Default focus target when the dialog opens is the **Confirm** button, never a destructive one — there is nothing destructive in this dialog. |
| `[ OPEN COMPARE ]` | none reserved | `Enter`/`Space` opens the Candidate Compare overlay (§3.4 below). Only present/enabled once two `VerificationRecord`s exist, per design system §4.1 row 10. |
| `[ PAUSE ]` / `[ RESUME ]` | none reserved | `Enter`/`Space` toggles. Never the default-focused element on page load. |
| `[ CANCEL MISSION ]` | none reserved | **Destructive.** `Enter`/`Space` opens a confirm dialog naming the consequence in full (design system §4.2, already specified verbatim: *"Cancel mission 04. The sandbox is destroyed and any unexported evidence is lost. This cannot be undone."*). Rendered in `--bd-state-critical` per §2.7. **Never the default focus target on page load or after any other action.** |
| `[ EMERGENCY TEARDOWN ]` | none reserved | **Destructive, always enabled** even when other controls are disabled (design system §4.2). Same confirm-dialog pattern as Cancel, naming every resource that will be destroyed. Placed last in tab order specifically because "always enabled" must not mean "easiest to reach by accident" — it is reachable, not adjacent to the safe controls. |
| `[ EXPORT EVIDENCE ]` | none reserved | `Enter`/`Space` triggers export; control is disabled (with `aria-disabled` and a stated reason, per §2.1's disabled-control rule) while `[ ● EXPORTING ]` is in flight, and re-enabled on failure per design system §4.1 row 11. |

**No control in this row gets a bespoke keyboard shortcut (a letter/number mnemonic).** This
document deliberately does not add e.g. `P` for pause or `C` for cancel. Two reasons: (1) the
command palette that would have made mnemonics discoverable is cut (§11), so an undiscoverable
shortcut is worse than no shortcut — a keyboard user reaches every control by `Tab`, which is
the P1-10 bar ("basic keyboard operability," not full power-user tooling); (2) a single-letter
mnemonic on `[ CANCEL MISSION ]` in a dense dashboard with a live text/prompt input elsewhere on
the same page (`AIParticleCore`'s `LOCAL AI CHANNEL` field) is exactly the kind of accidental-
trigger risk this document is elsewhere trying to design out for presentation mode — the same
logic applies here. Tab-and-Enter is the whole shortcut surface for destructive controls, on
purpose.

**Confirm dialog — focus trap, for both Cancel and Emergency Teardown:**

- On open: focus moves to the dialog's safe default (**Confirm**'s sibling, the **Cancel-this-
  dialog** button — i.e., the button that does *not* perform the destructive action), per design
  system §2.7 ("never the default focus target").
- `Tab`/`Shift+Tab` cycle only between the dialog's own controls — a standard modal focus trap.
  Nothing outside the dialog is reachable while it's open.
- `Escape` always dismisses **without** performing the destructive action, and returns focus to
  the control that opened the dialog (design system §9's existing overlay rule, applied here).
- `Enter` activates whichever button currently has focus — never a global "Enter confirms the
  destructive action" shortcut, since that would make a stray `Enter` press (e.g., from finishing
  a scan-path entry elsewhere) dangerous if focus had drifted.

### 3.4 The Candidate Compare — today's inline grid, and the future overlay

**Today:** `VerdictComparePanel` renders inline, always visible when a mission has candidates —
there is no open/close state to map. Tab order runs left column top-to-bottom (provenance →
diff → gate matrix → footer), then right column, matching the visual two-column order already in
the DOM. The diff `<pre>` gets the scrollable-region treatment from §3.2.

**When DS-02's overlay is built** (the design system's specified `[ OPEN COMPARE ]` →
full-content-width overlay): on open, focus moves to the overlay's first focusable element
(the `[ ESC CLOSE ]` control, matching the overlay header's own layout in design system §6.4.1);
`Tab` is trapped inside the overlay exactly as the confirm dialog is trapped (§3.3); `Escape`
closes it and returns focus to whichever control opened it — the `[ OPEN COMPARE ]` button, or
the finding row that triggered it automatically on the second `VerificationRecord` landing
(design system §4.1 row 10). `[ OPEN FULL DIFF ]`, specified as "a mode of the same overlay, not
a second overlay" (design system §6.4.4), does not create a new focus trap — it swaps content
inside the existing one, and `[ ← BACK TO COMPARE ]` returns focus to where `[ OPEN FULL DIFF ]`
was.

### 3.5 Live regions — unchanged from design system §9, restated so it isn't re-litigated here

§9 already narrowed live regions to exactly one (the bottom-strip alert line, `role="alert"`),
having explicitly removed `aria-live="polite"` from the stage timeline and `role="alert"` from
verdict changes, with the reasoning recorded there (a 40-minute fuzz campaign narrated aloud;
the verdict is a large, tabbable, non-urgent readout). This document adds nothing to that set and
explicitly does not restore either removed region — a "restore it while we're here" move would
be a second un-cut riding on this task's authorization, which is #56's alone to spend.

### 3.6 Presentation mode's shortcut surface — the empty set, restated

Cross-referenced from §2.6: no keyboard shortcut in this document, anywhere, enables, disables,
reveals, or interacts with presentation mode. It is deliberately absent from every table above.

### 3.7 Skip link — not needed today, flagged for when it will be

WCAG guidance (and `ui-ux-pro-max`'s accessibility priority set) calls for a "skip to main
content" link ahead of any long, repeated, non-interactive block a keyboard user would otherwise
have to tab past. Today's real tab order (§3.1) has no such block — the command-bar chips aren't
focusable at all, so there's nothing to skip. **This will stop being true** the moment either (a)
the 10-row stage timeline gains per-row expand controls (design system §6.2), or (b) the
findings-by-severity list (§1.4 above) grows past one or two rows — at that point a keyboard user
tabbing from the top of the page to the bottom-strip controls passes through every stage/finding
row first. Flagged here as a forward requirement rather than specified now, so it isn't missed
when either of those ships: a `[ SKIP TO CONTROLS ]` link, visually hidden until focused (standard
skip-link pattern), as the first focusable element on the page once that condition is true.

---

## 4. Summary of extensions vs. reuse, for the reviewer

| Item | Reuses exactly | Extends (new rule, recorded as a decision) | Net-new component |
|---|---|---|---|
| #25 Analysis Rail | Finding row, evidence block, severity colour vocabulary, bracket grammar, `NOT RUN` visual construction (all from §6.3, §6.3a, §5, §2.1) | **D-057** — `NOT RUN` gate-style treatment applied to two rows that sit outside the `VerificationRecord` matrix | `SeverityFindingsList`, `NotRunCoverageRow` |
| #52 Presentation mode | The `[ ! MOCK DATA ]` chip concept, verbatim from §2.6 | **D-058** — crop-surviving full-bleed watermark; `mockSource` driven by the real SSE header, not the build flag alone; hard refusal to bind to a real mission | `PresentationModeChip`, `MockDataWatermark` |
| #56 Keyboard operability | Focus-visible token, tab-order-matches-visual-order rule, overlay Escape rule, disabled-control rule, destructive-control-never-default-focus rule (all from §9, §2.7, §4.2) | **D-059** — command palette stays cut; no bespoke shortcuts on destructive controls; scrollable-region `tabIndex` requirement (a genuine gap, not previously specified) | none — this section is pure interaction spec over existing/planned components |

---

*Decision records D-057, D-058 and D-059 are appended to `.project/decisions.md`.*
