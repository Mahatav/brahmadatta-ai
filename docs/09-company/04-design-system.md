# The P0 Screen Set and Design System

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Document | Company-workflow D1/D2 deliverable — GitHub issue #7 |
| Status | Frozen for the seven-day build. Amend by appending, never by silent edit. |
| Drafted by | `ui-ux-designer` seat |
| Date | 2026-08-07 |
| Governs | The five P0 panels (P0-13) and every token used to build them |
| Tokens | [`packages/ui-components/tokens.css`](../../packages/ui-components/tokens.css) |

## Standing, and what this supersedes

This document is the build specification for the Command Center. Where it disagrees with
[`docs/02-design/`](../02-design/) — and it disagrees substantially — **this document wins for
the competition MVP**, on two authorities:

1. **[D-017 and D-018](../../.project/decisions.md)** replaced the pack's visual direction with a
   flat engraved one drawn from the CEO's two references — D-017 supplying the field and the
   engraving, D-018 the rule-and-crop-mark construction, the bracketed monospace labels, the ASCII
   texture and the two typefaces. `docs/02-design/00-ui-design-direction.md`
   describes "thin luminous borders, nested glass panels, subtle grids… restrained glow". That
   look is not built. It is not toned down or reinterpreted — **there is no glass, no bevel, no
   shadow and no glow anywhere in this system.** §11 lists exactly what that costs.
2. **[§6.7 of the P0 cut](01-vision-and-p0-cut.md#6-what-i-would-challenge-in-the-pack)** — the
   Command Center as specified is a multi-week frontend project competing with the pipeline, and
   when they collide the pipeline wins. So the screen set is the five P0 panels, not the
   thirty-two-entry component inventory.

The `docs/02-design/` pack is **left unedited**. This follows the precedent set by the P0 cut
document: the pack records what Brahmadatta AI is meant to be, and the cut is recorded here so it
reads as a decision with a reason attached rather than as an oversight. §11 itemises every entry
cut, merged or kept, one line each.

---

## 1. The direction

Two references, combined.

**From [hermes-agent.nousresearch.com](https://hermes-agent.nousresearch.com/):** one flat,
saturated, unmodulated colour field. Hairline white line-engraving as the only illustrative
element. Radiating ray geometry. A light Didone-ish serif at display size against monospace for
every utility label.

**From [clean-customer-760137.framer.app](https://clean-customer-760137.framer.app/):** hairline
rules forming a page frame with corner crop marks instead of boxed borders. Bracketed monospace
labels — literally `[About]`, `[Pricing]`. ASCII art as the illustration medium. Editorial
restraint and generous whitespace.

**The synthesis.** Panels are defined by thin rules and corner ticks rather than boxes. Every
utility label is a bracketed monospace string — `[ BASELINE ]`, `[ MISSION 04 ]`, `[ GATE 03 ]`.
The few large numbers and the verdict are set in light Instrument Serif. The Brahmadatta Core is
hairline engraving with ASCII-density shading — a chakra whose spokes are the six mission phases,
not a glowing progress ring.

The one thing a judge should remember: **a mission-control dashboard that looks like a printed
engineering plate, where the verdict is set like a headline in a broadsheet.**

### 1.1 The iconography rule — hard, no exceptions

The reference centres a rendered Greek deity. **Ours centres no Hindu one, and depicts no figure
at all.**
[`docs/00-overview/00-product-identity.md`](../00-overview/00-product-identity.md) requires
Brahmadatta be presented as a technology brand, "not as a deity, religious authority, or claim of
literal invincibility". That rule outranks the reference.

The permitted vocabulary is **objects and geometry from the Ramayana and Mahabharata, never
figures**: kavacha plating, the chakra and the chariot wheel, the bow and arrow, the conch, yantra
and mandala grid construction, and radiating rays.

Two constraints carry into every commit that touches artwork:

- **No depicted deities, figures, faces, hands, or anthropomorphic forms.** Not stylised, not
  abstracted, not "just a silhouette". If it reads as a person, it does not ship.
- **All linework original to this project.** Drawn as SVG paths for Brahmadatta, not traced,
  imported, or adapted from existing artwork. This extends the pack's existing ban on third-party
  branded interface assets.

A reviewer rejecting a PR on either ground does not need to argue the point.

---

## 2. Tokens

All values live in [`packages/ui-components/tokens.css`](../../packages/ui-components/tokens.css).
**No component may contain a hardcoded colour, size, or spacing value.** If a value is needed and
absent, it is added to the token file first.

### 2.1 Palette

Eight colours. Adding a ninth requires a decision record. Every ratio below is measured against
the field using the WCAG 2.1 relative-luminance formula.

| Token | Hex | Contrast on field | Use |
|---|---|---:|---|
| `--bd-c-field` | `#141C8C` | — | The single flat plane. HSL 236° 75% 31%. Everything sits directly on it. |
| `--bd-c-white` | `#F4F3EE` | **12.00:1** | Primary text, active rules, active crop ticks, focus ring |
| `--bd-c-veil` | `#9FA1C9` | **5.34:1** | Secondary text, bracket labels at rest, model self-report |
| `--bd-c-rule` | `#7276B5` | **3.16:1** | Informational hairline rules and crop ticks. Clears the 3:1 floor for non-text graphics. |
| `--bd-c-rule-faint` | `#4A50A4` | 1.8:1 | Construction lines only — yantra grid, unlit rays, row separators. Carries no meaning, so no floor applies. |
| `--bd-c-disabled` | `#6569AF` | 2.6:1 | Disabled controls. WCAG exempts these; always paired with a written reason. |
| `--bd-c-verified` | `#39E08A` | **7.77:1** | Verified, operational, gate passed |
| `--bd-c-warning` | `#FFB020` | **7.29:1** | Warning, escalation, degraded, held for human review |
| `--bd-c-critical` | `#FF6B66` | **4.80:1** | Critical *only*: failed gate, rejected verdict, unsafe condition |

The field is deliberately not the reference's `#0000F2`. That value is theirs, and at 47%
lightness it makes a dense dashboard painful to read for an hour and crushes the separation
between the three state colours. `#141C8C` is a genuine saturated chromatic plane — nobody will
mistake it for the near-black the pack originally called for — while leaving every state colour a
7:1 or better foothold.

`--bd-c-critical` is a bright coral rather than a deep red on purpose: a dark red disappears
against a dark saturated field, and red is the one colour that must never be missed.

### 2.2 Type

| Role | Family | Weight | Notes |
|---|---|---|---|
| Display | **Instrument Serif** | 400 | The only weight it ships. Its stroke contrast is high enough that at 48px+ it reads as the light Didone the reference calls for. Approved substitute for missing glyphs: Bodoni Moda 400. |
| Utility | **Fragment Mono** | 400 | Also a single weight. **Emphasis in mono is carried by case, tracking and colour — never by weight.** Do not let the browser synthesise a bold; it breaks the tick grid. |

Both are freely available and both must be **self-hosted as woff2 in the Astro build**. A Google
Fonts `@import` on a finale machine with no internet drops the entire dashboard to Times New
Roman. `font-display: swap` with the declared fallback stack.

**Scale.** Mono sizes are tight because the dashboard is dense; display sizes are large because
the finale is judged partly on someone reading this from across a room. Sizes marked **ROOM** are
the tier guaranteed legible at ~4 m — anything a judge must read from a distance uses one of them.

| Token | Size / line-height / tracking | Use |
|---|---|---|
| `mono-3xs` | 10 / 14 / +0.14em | Bracket micro-labels, uppercase only. Never for prose. |
| `mono-2xs` | 11 / 16 / +0.12em | Panel labels |
| `mono-xs` | 12 / 18 / +0.06em | Dense tabular data, sub-lines |
| `mono-sm` | 13 / 20 / +0.02em | Primary list rows, event lines |
| `mono-md` | 15 / 22 / 0 | Diff code, active state chips — **ROOM** |
| `mono-lg` | 18 / 26 / 0 | Active stage name, key values — **ROOM** |
| `mono-xl` | 24 / 30 / 0 | Mission clock — **ROOM** |
| `display-sm` | 32 / 1.0 | Panel-level display numbers |
| `display-md` | 48 / 0.98 | Secondary display — **ROOM** |
| `display-lg` | 72 / 0.94 | Verdict word, Core centre word — **ROOM** |
| `display-xl` | 104 / 0.92 | Reserved for a single hero readout. Unused in P0. |

All numerals are tabular (`font-variant-numeric: tabular-nums lining-nums`) so live counters do
not shimmy as digits change.

### 2.3 Spacing

4px base unit. No value outside the scale: **4, 8, 12, 16, 24, 32, 48, 64, 96**.

Page frame inset 32. Panel padding 24. Column gutter 24. List row 44. Nested event row 28.

### 2.4 Rules and ticks — the construction system

This is the load-bearing idea, and it replaces every border and panel background in the pack.

- **Nothing has a border. Nothing has a background. Nothing is rounded.**
  `--bd-radius` is `0` and is not to be overridden.
- **Two rule weights and no more.** `--bd-rule-hair` 1px for everything;
  `--bd-rule-heavy` 2px for exactly three things — the page frame's top rule, the verdict
  underline, and diff gutter marks.
- **The page frame.** A 1px rule inset 32px from all four viewport edges, **broken by a 24px gap
  at each corner** where the crop marks sit. Content lives inside the frame with 24px padding.
- **The crop mark.** Two 1px strokes, each 10px long, meeting at a panel's bounding-box corner —
  but each stopping 3px short, so the corner is *implied and never drawn*. Four per panel. This is
  what locates a panel; the panel itself is just aligned text on the field.
- **Tick colour is a state channel.** `--bd-tick` at rest, `--bd-tick-active` (white) when the
  panel is focused or its stage is running, the relevant state colour when the panel is in a
  warning or failed condition. This gives every panel a state signal that costs no pixels.
- **Region rules.** Full-bleed 1px rules separate the top strip, the body, and the bottom strip.
  Columns are separated by 24px of field, not by a rule — the crop marks already do that work.

Between them, these five rules mean the whole interface can be drawn with 1px strokes and text.
That is also why it is cheap to render under a live event feed, which is the practical argument
D-017 already made.

### 2.5 Bracket label grammar

Every utility label in the product is a bracketed monospace string. This is not decoration; it is
the system's one consistent affordance, and it must be applied literally.

| Form | Example | Rule |
|---|---|---|
| Panel / section title | `[ BASELINE ]` | Uppercase, `mono-2xs`, one space inside each bracket, `--bd-text-secondary` |
| Indexed item | `[ MISSION 04 ]` `[ FINDING 01 ]` `[ GATE 03 ]` | Zero-padded to two digits |
| State chip | `[ ● RUNNING ]` | 6px dot in the state colour, then the state **word** in the same colour. The word is the non-colour channel; the dot is a scan aid. |
| Gate chip | `[ + COMPILE ]` `[ × REGRESSION · 40/42 ]` | Leading glyph from the glyph tokens, never colour alone |
| Not measured | `[ — STATIC DELTA · NOT RUN ]` | Em dash, `--bd-text-secondary`, **never** a state colour |
| Control | `[ EXPORT EVIDENCE ]` | The brackets *are* the button. See §2.7. |

Interaction on a control: at rest the brackets and label are `--bd-text-secondary`; on hover both
become `--bd-text` over 150ms, **colour only — no transform, no size change, no layout shift.**
Focus adds a 2px `--bd-focus-ring` outline at 4px offset. Nothing is ever inserted or removed on
hover, so nothing reflows.

### 2.6 The two data-honesty rules, made visual

These implement the CLAUDE.md prohibition on decorative or fake metrics, and D-009's disclosure
requirement. They are checkable in review.

1. **The em dash is the not-measured glyph.** A value that has not been produced renders as `—`,
   in secondary text, never in a state colour. `[ FINDINGS · — ]` before analysis has run;
   `[ FINDINGS · 0 ]` only after it has completed and genuinely found none.
   **A zero is a result. It is never a placeholder.**
2. **Nothing advances on a timer.** Every progress indicator in this system steps only when an
   event arrives on the stream. There is no interpolation between events, no easing toward a
   predicted value, no idle animation that implies work. If the stream stalls, the display
   freezes and says so (§6.1, degraded state). A dashboard that keeps moving while the backend is
   dead is a fabricated metric with extra steps.

Presentation mode — the only place a labelled deterministic mock was ever permitted — is in the
`CUT` milestone per [the seven-day plan](03-seven-day-plan.md). **For the P0 build, therefore,
every number on screen is real telemetry with no exception path.** If presentation mode is ever
restored, mocked values render with a persistent `[ ! MOCK DATA ]` chip in `--bd-state-warning`
fixed to the top strip, visible on every screen, not dismissible.

### 2.7 Interaction targets and controls

Desktop, mouse and keyboard, 1440×900 and above. Even so, **every control gets a 44×44px minimum
hit area** and list rows are 44px tall, so the skill's touch-target floor is met without a
deviation to argue about. The visible label may be smaller than its hit area; the hit area is what
is tested.

Destructive controls — `[ CANCEL MISSION ]`, `[ EMERGENCY TEARDOWN ]` — require a confirmation
dialog naming the consequence in a full sentence, and render their label in
`--bd-state-critical`. They are never the default focus target.

---

## 3. Screen layout

One screen. 1440×900 baseline; extra viewport width is absorbed by the centre column, extra height
by the two rails. Below 1280px the layout is not supported — the pack's collapse-to-drawers
behaviour is cut (§11).

```
┌ 32px frame inset, 1px rule, 24px corner gaps ─────────────────────────────────────────────┐
│ ┌ ─                                                                                   ─ ┐ │
│                                                                                           │
│   Brahmadatta            [ MISSION 04 ]  [ ● RUNNING ]  [ REPO libparse@a4f1c9 ]           │
│   ─ Instrument Serif 24                            [ ELAPSED 00:14:22 ]  [ UTC 09:41:07 ] │
│ ──────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                           │
│  ┌ ─          336         ─ ┐   ┌ ─               608                ─ ┐   ┌ ─  336  ─ ┐  │
│    [ STAGE TIMELINE ]              [ BRAHMADATTA CORE ]                   [ FINDINGS · 1 ]│
│                                                                                           │
│    [ 01 ] AUTHORIZE                                                        [ FINDING 01 ] │
│           snapshot a4f1c9                    ·:·  radiating rays  ·:·      HEAP-BUFFER-   │
│           00:00:04      [ + OK ]                                           OVERFLOW       │
│    ─────────────────────────                ╭───── kavacha plating ─╮      parser.c:118   │
│    [ 02 ] INGEST                           │    ╱  yantra grid  ╲    │     [ ● CONFIRMED ]│
│           1 204 files                      │   ╱                 ╲   │    ───────────────  │
│           00:00:31      [ + OK ]           │  │     Analyze       │  │                    │
│    ─────────────────────────               │   ╲   ─ 72px serif ─ ╱   │    [ EMPTY BELOW ] │
│    [ 03 ] BASELINE                          │    ╲               ╱    │    No further      │
│           ctest 42/42 passed                 ╰───── chakra rim ──╯         findings.       │
│           00:02:11      [ + PASS ]                                                         │
│    ─────────────────────────               [ PHASE 02 OF 06 · ANALYZE ]                    │
│    [ 04 ] ANALYZE            ◀ running     [ ● LIVE · LAST EVENT +1s ]                     │
│           semgrep — not run                                                                │
│           00:01:08      [ > RUN ]          ──────────────────────────────                  │
│    ─────────────────────────                                                               │
│    [ 05 ] CORRELATE          [ · QUEUED ]  [ VERDICT ]                                     │
│    [ 06 ] STRESS TEST        [ · QUEUED ]  Pending          ─ Instrument Serif 72          │
│    [ 07 ] REMEDIATE          [ · QUEUED ]  [ GATE MATRIX · — ]                             │
│    [ 08 ] VERIFY             [ · QUEUED ]  No gate has executed yet.                       │
│                                                                                            │
│    ↕ autoscroll pinned to newest                                                           │
│ ──────────────────────────────────────────────────────────────────────────────────────── │
│   [ SESSION SECURE ]  [ EGRESS DENIED ]  [ SANDBOX 1 ]      [ OPEN DIFF ]  [ PAUSE ]       │
│   [ EVENTS 1 284 ]                                    [ CANCEL MISSION ]  [ EXPORT ]       │
│ └ ─                                                                                   ─ ┘ │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

**Region budget at 1440×900.** Frame inset 32 → 1376 wide, 836 tall. Content padding 24 →
1328 × 788. Top strip 64, bottom strip 56, two 1px rules, 24 padding above and below the body →
body height 684. Three columns 336 / 608 / 336 with two 24px gutters = 1280, leaving 48 of slack
that the centre column absorbs first.

The Core occupies a 440px-diameter block (outer radius 220) plus 60px of label space = 500 tall.
Verdict panel 124 tall. 500 + 24 + 124 = 648, inside the 684 available.

**The diff is not in this layout**, because a unified C diff needs roughly 80 columns — about
624px at `mono-md` — and neither rail is wide enough. It opens as a full-content-width overlay
(§6.4). See D-020 for the layout option that was rejected.

---

## 4. User journeys

The nine-step demo from [§3 of the P0 cut](01-vision-and-p0-cut.md#3-the-minimum-viable-demo),
expressed as what the operator does and what the screen does back.

### 4.1 Primary journey — the mission run

| Step | Entry point | Screen response | Success state | Failure / edge |
|---|---|---|---|---|
| 1 | Operator opens the Command Center with no mission | Every panel in its empty state. Core shows `Standby`. | — | API unreachable → top strip shows `[ × CONTROL API UNREACHABLE ]` critical, body shows the loading placeholder, no fabricated content |
| 2 | `[ AUTHORIZE + START ]` in the bottom strip | Confirmation dialog naming the repository, the snapshot hash and the egress policy | Mission created; Core rim draws; timeline gains `[ 01 ] AUTHORIZE` | Authorization declined → mission is not created; timeline stays empty; alert line states the reason |
| 3 | Automatic | `INGEST` arc shades; timeline row appends with real file count | `[ + OK ]` on the ingest row | Snapshot mismatch → row `[ × FAIL ]` critical, Core enters Failed, no further stage starts |
| 4 | Automatic | `BASELINE` row shows real `ctest` counts as they land | `[ + PASS · 42/42 ]` | Any baseline test fails → `[ × FAIL · 40/42 ]`, Core Failed. Baseline failure is terminal; the denominator for "regression preserved" does not exist. |
| 5 | Automatic | `STRESS TEST` arc ticks; event rows carry real exec counts | Sanitizer-confirmed crash → findings list gains `[ FINDING 01 ]` with `[ ● CONFIRMED ]` | No crash inside the budget → `[ ! NO FINDING · BUDGET EXHAUSTED ]` warning, mission ends cleanly with no verdict. **The panel does not show a zero as a result.** |
| 6 | Automatic, or `[ FINDING 01 ]` clicked | Diff overlay opens on the first candidate | Diff renders with provenance and policy chips | Policy rejects the candidate pre-verification → overlay header `[ POLICY · FAIL ]` critical, naming the failing rule; no gates run |
| 7 | Automatic | Gate chips resolve one at a time as each tool returns | `Verified`, gate matrix enumerating 3 of 5 with the two unrun gates as em dashes | Regression fails → `Rejected`, the failing chip is the only critical element, with counts inline |
| 8 | `[ OPEN DIFF ]` with two candidates present | Verdict panel splits into two 292px columns, one per candidate, hairline rule between | Verified and Rejected legible side by side — this is the money shot of the demo | Only one candidate → panel stays single-column, no empty second column |
| 9 | `[ EXPORT EVIDENCE ]` | Confirmation, then `[ ● EXPORTING ]`, then `[ + EXPORTED · report.md · report.json ]` with the paths | Files written | Export fails → `[ × EXPORT FAILED ]` critical with the error string verbatim, control re-enabled |

### 4.2 Secondary journey — operator intervenes

`[ PAUSE ]` → pauses **after the current stage**, never mid-tool. Chip becomes
`[ ● PAUSING · AFTER ANALYZE ]` warning, then `[ ● PAUSED ]`. Core's active arc freezes at its
real fraction and the ramp stops ticking. `[ RESUME ]` replaces `[ PAUSE ]`.

`[ CANCEL MISSION ]` → confirmation dialog: "Cancel mission 04. The sandbox is destroyed and any
unexported evidence is lost. This cannot be undone." On confirm the Core enters Cancelled and the
timeline appends a cancellation row with the operator's identity.

`[ EMERGENCY TEARDOWN ]` → always enabled, even when everything else is disabled. Confirmation
names every resource that will be destroyed. Post-teardown the bottom strip shows
`[ + ALL SANDBOXES RELEASED ]` — required by P0-14, and it is a scored criterion, so it is
displayed as an explicit confirmation rather than an absence.

---

## 5. State vocabulary

Applies to every panel, chip and row. The word is authoritative; the colour is redundant
reinforcement; the glyph is the third channel.

| State | Glyph | Word | Colour token | Meaning |
|---|---|---|---|---|
| Idle | `·` | `QUEUED` / `STANDBY` | `--bd-state-idle` | Not started |
| Loading | `·` | `LOADING` | `--bd-state-idle` | Fetching, nothing known yet |
| Running | `>` | `RUNNING` | `--bd-state-running` | Work in progress, events arriving |
| Pass | `+` | `OK` / `PASS` | `--bd-state-verified` | Completed successfully |
| Warning | `!` | named condition | `--bd-state-warning` | Degraded, escalated, or held |
| Fail | `×` | `FAIL` / `REJECTED` | `--bd-state-critical` | Terminal negative outcome |
| Not run | `—` | `NOT RUN` | `--bd-text-secondary` | Never a colour. Never a zero. |
| Disabled | `·` | reason text | `--bd-text-disabled` | Always paired with why |

**Empty is not loading and loading is not zero.** Three distinct renderings, and a panel must
never substitute one for another:

- **Empty** — a bracket label plus one plain sentence saying what would appear here and what
  produces it. Example: "Findings appear when a sanitizer report is captured."
- **Loading** — 1px placeholder rules at 40% and 65% width in `--bd-rule-construction`, three
  rows, no shimmer and no pulse. Space is reserved so nothing jumps when content lands.
- **Zero** — an actual measured count of zero, shown only after its producing step completed.

---

## 6. The five P0 panels

Each panel is specified to the level where nothing has to be invented. If a state, label or
value is missing below, that is a defect in this document — raise it rather than guessing.

### 6.1 Panel 1 — Brahmadatta Core

Centre column, top. 440px diameter, `--bd-col-centre` wide block, 500px tall. See §7 for the
geometry.

**Content, top to bottom:** the chakra; inside its clear centre disc the current state word in
Instrument Serif 72px; beneath the wheel `[ PHASE 02 OF 06 · ANALYZE ]` in `mono-md`; beneath that
the liveness chip.

**States**

| State | Rendering |
|---|---|
| Empty (no mission) | Rim and plating drawn in `--bd-rule-construction` only. No arc shading, no rays. Centre reads `Standby` in `--bd-text-secondary`. Below: `[ NO ACTIVE MISSION ]` and "Authorize a repository to begin." |
| Loading (connecting to stream) | Rim drawn, centre reads `Connecting`, liveness chip `[ · OPENING STREAM ]`. No arc shading — the phase states are unknown and must not be guessed at. |
| Running | Completed arcs shaded `#`, active arc shaded `:` and filled to its **real** reported fraction, pending arcs empty. Rays lit only within completed arcs. Centre reads the active phase name. Chip `[ ● LIVE · LAST EVENT +1s ]`. |
| Degraded (stream stale) | No event for >10s: the ramp stops ticking, arcs freeze exactly where they are, chip becomes `[ ! STREAM STALE · LAST EVENT +23s ]` in warning, and the four crop ticks of the centre column turn warning-coloured. **The wheel does not advance.** |
| Verified | Rim ramp becomes continuous `#` all the way round and a second concentric circle is drawn at r=226. Centre reads `Verified` in `--bd-state-verified`. |
| Rejected | The REMEDIATE spoke's divider extends 40px outward, breaking the rim — the wheel is visibly broken at one spoke. Centre reads `Rejected` in `--bd-state-critical`. |
| Human review | Arc shading pauses at the current segment; a hairline chord is drawn across the centre disc. Centre reads `Held` in `--bd-state-warning`, with the triggering policy rule named beneath. |
| Failed | All rays drop to `--bd-rule-construction`; rim ramp becomes `X`. Centre reads `Failed` in `--bd-state-critical`, with the failing stage named beneath. |
| Cancelled | Rim ramp becomes sparse `-`; rays removed. Centre reads `Cancelled` in `--bd-text-secondary`. |
| Error (Core cannot render) | Fall back to a text block: `[ × CORE RENDER FAILED ]` plus the phase list as plain bracketed rows. The mission remains operable. |

### 6.2 Panel 2 — Stage timeline

Left rail, 336 × 684, full body height. The authoritative narrative of the run, and the panel a
judge reads to check that the sequence actually happened.

Chronological, oldest at top, newest appended at the bottom, autoscroll pinned to the newest row.
Scrolling up releases the pin and shows `[ v 3 NEW ]` as a control at the bottom edge; clicking it
re-pins.

**Stage row — 48px, two lines.**

```
[ 03 ]  BASELINE                    [ + PASS ]
        ctest 42/42 · 00:02:11
```

Line 1: index bracket (`mono-3xs`, secondary) · stage name (`mono-sm`, primary; `mono-lg` and
white while running) · state chip, right-aligned. Line 2: the real substantive result — never a
generic "completed" — plus elapsed, in `mono-xs` secondary. Row separator: 1px
`--bd-rule-construction`.

**Event row — 28px, one line, indented 24px.** Rendered only when a stage is expanded. Carries
raw telemetry: `00:01:44  fuzz exec 1 284 003 · 0 new crashes`.

**States**

- **Empty:** `[ NO MISSION ]` and "Start a mission to populate the timeline." No rows, no zeros.
- **Loading:** three placeholder rule rows.
- **Running:** the active row's crop ticks turn white and its stage name goes `mono-lg`.
- **Degraded:** stream stale → a single warning row is appended in place:
  `[ ! STREAM STALE ] the timeline may be incomplete`. Existing rows are never altered or removed.
- **Failed:** the failing row is critical; every row below it renders `[ · NOT REACHED ]` in
  secondary — not `[ × FAIL ]`, because they did not fail, they never ran.
- **Overflow:** above 200 rows, the oldest are virtualised out with
  `[ … 148 EARLIER EVENTS ]` as an expand control at the top.

### 6.3 Panel 3 — Findings list

Right rail, 336 × 684.

Header: `[ FINDINGS · 1 ]`. Before analysis has run the count is `—`, not `0`.

Sort order: confirmed before unconfirmed, then severity, then discovery order. In P0 there is
normally exactly one row, and the panel must look deliberate rather than sparse — the empty space
below the single row carries the `[ EMPTY BELOW ]` label and one sentence, which is honest and
also reads as composition rather than as a broken grid.

**Finding row — 44px.**

```
[ FINDING 01 ]  HEAP-BUFFER-OVERFLOW          [ ● CONFIRMED ]
                parser.c:118 · read 4 @ +2 · ASan
```

Selection: the selected row's crop ticks turn white and a 2px left rule appears. Selection opens
the diff overlay for that finding's candidate, if one exists.

**States**

- **Empty, before analysis:** `[ FINDINGS · — ]`, "Findings appear when a sanitizer report is
  captured."
- **Empty, after analysis completed clean:** `[ FINDINGS · 0 ]`, "Analysis completed. No
  sanitizer-confirmed defect in this snapshot." — a measured result, phrased as one.
- **Loading:** two placeholder rule rows.
- **Unconfirmed finding:** `[ ! UNCONFIRMED ]` in warning, with "observed, not sanitizer-confirmed"
  on the sub-line. An unconfirmed finding is never counted in the header total; the header reads
  `[ FINDINGS · 1 · +2 UNCONFIRMED ]`.
- **Degraded:** stale stream → header gains `[ ! MAY BE INCOMPLETE ]`.
- **Failed:** the fetch failed → `[ × FINDINGS UNAVAILABLE ]` with the error string and a
  `[ RETRY ]` control. Never an empty list, which would read as "no findings".

### 6.4 Panel 4 — Diff view

A full-content-width overlay, 1328 × 684, inset inside the page frame so the top strip and the
mission clock stay visible. Opened by `[ OPEN DIFF ]`, by selecting a finding, or automatically on
entering the REMEDIATE stage. Closed by `[ ESC ]` or `[ CLOSE ]`. Z-index `--bd-z-overlay`.
Background is the field — the overlay is opaque, not translucent; there is no glass in this system.

**Header, one row, separated from the body by a 1px rule:**

```
[ CANDIDATE 01 ]   [ PROVENANCE · MODEL-GENERATED ]   [ POLICY · PASS ]
parser.c           files 1/1 · changed lines 8/25 · allowlist ok        [ ESC CLOSE ]
```

`[ PROVENANCE · … ]` is **mandatory and adjacent to the candidate ID**, per
[D-008](../../.project/decisions.md). Values are exactly `MODEL-GENERATED` or
`OPERATOR-SUPPLIED`. There is no third value and no default; a candidate without provenance
renders `[ × PROVENANCE MISSING ]` in critical and the diff body is suppressed. Wiring a candidate
record without a provenance field is a bug in the API, and this panel is where it becomes visible.

**Model self-report block** — bottom-left of the header column, under its own 1px rule, in
`--bd-model-selfreport` (which is deliberately the same value as ordinary secondary text):

```
[ MODEL SELF-REPORT ]
confidence 0.71 · not a verdict · no gate reads this value
```

It is in a different panel from the verdict, separated by a rule, never coloured with a state
colour, and it carries its own disclaimer in the label. That is the visual half of the
non-negotiable rule that a patch is never accepted on model confidence.

**Body** — unified diff, Fragment Mono `mono-md` 15/22. Four columns: old line number
(`mono-xs`, secondary), new line number, 2px gutter mark, content.

| Line kind | Gutter | Text | Left rule |
|---|---|---|---|
| Added | `+` | `--bd-state-verified` | 2px `--bd-state-verified` |
| Removed | `−` | `--bd-text-secondary` | 2px `--bd-state-critical` |
| Context | ` ` | `--bd-text` | none |
| Collapsed | — | `[ … 34 LINES ]`, expandable | none |

Removed lines are deliberately de-emphasised in secondary text rather than shouted in coral: the
addition is the story, red is reserved for failure, and a whole removed block in critical colour
would misrepresent a working patch as an alarm. The `+`/`−` gutter marks mean colour is never the
only channel.

**States**

- **Empty:** `[ NO PATCH CANDIDATE ]`, "A diff appears when the model returns a candidate that
  passes patch policy."
- **Loading:** placeholder rules in the body; the header renders as soon as metadata lands.
- **Policy failure:** header `[ POLICY · FAIL ]` in critical, with the failing rule stated in full
  — "changed lines 61 exceeds cap 25". Diff body still renders, greyed to secondary, so the
  operator can see what was refused. No gates run and the verdict panel stays `Pending`.
- **Degraded — truncated:** above 2 000 lines, `[ ! TRUNCATED · 2000 OF 4118 LINES ]` in warning
  pinned to the top of the body, with `[ DOWNLOAD FULL PATCH ]`.
- **Failed — render error:** `[ × RENDER FAILED · SHOWING RAW ]` in critical, then the raw patch
  text unstyled. Never a blank panel.
- **Two candidates:** a `[ CANDIDATE 01 ] [ CANDIDATE 02 ]` selector in the header. The demo's
  side-by-side comparison happens in the verdict panel (§6.5), not here — two 660px diffs side by
  side are unreadable.

### 6.5 Panel 5 — Verdict panel

Centre column, below the Core. 608 × 124 in the main layout; 336 wide in the overlay's right
column.

```
[ VERDICT ]
Verified                                      ← Instrument Serif 72px
[ GATE MATRIX · 3 OF 5 RAN ]
[ + COMPILE ]  [ + REPRODUCER ELIMINATED ]  [ + REGRESSION PRESERVED · 42/42 ]
[ — STATIC DELTA · NOT RUN ]  [ — RENEWED FUZZ · NOT RUN ]
```

The verdict word is the largest text in the product and the single thing a judge should read from
across the room. It is set in the display serif, underlined by a 2px rule in the verdict's state
colour running the full panel width.

**The gate matrix is not optional and is never collapsed.** [D-009](../../.project/decisions.md)
requires that a verdict enumerate the gates that actually ran wherever it is displayed. The
`· 3 OF 5 RAN` disclosure is part of the label, not a footnote, and the two unrun gates render
as em dashes in secondary — never green, never absent. A `Verified` that hides an unrun gate is a
defect, and this is the panel where it would be caught.

**States**

| State | Verdict word | Colour | Matrix |
|---|---|---|---|
| Empty | `Pending` | secondary | `[ GATE MATRIX · — ]`, "No gate has executed yet." |
| Running | `Running` | white | Executing gate `[ > COMPILE · RUNNING ]`, remainder `[ · QUEUED ]` |
| Verified | `Verified` | verified | All executed gates pass; unrun gates as em dashes |
| Rejected | `Rejected` | critical | The failing chip is the **only** critical element, with counts inline: `[ × REGRESSION PRESERVED · 40/42 · 2 FAILED ]` |
| Human review | `Held` | warning | Executed gates as-is, plus the triggering policy rule named in full |
| Failed | `Failed` | critical | `[ GATE MATRIX · 0 OF 5 RAN ]` plus the stage that failed |
| Degraded | verdict as computed | as computed | A warning banner above: `[ ! VERDICT MAY BE STALE · RELOAD ]`. The verdict itself is **not** greyed out — a stale verdict is still the last true verdict. |

**Two-candidate compare** (demo step 8): the panel splits into two 292px columns with a 1px rule
between, each with its own verdict word and its own complete gate matrix, `[ CANDIDATE 01 ]` and
`[ CANDIDATE 02 ]` as column headers. "Verified" and "Rejected" in 72px serif, side by side, each
with its own enumerated matrix, is the strongest single frame in the demo.

---

## 7. The Brahmadatta Core — chakra geometry

Original SVG linework. No raster assets, no third-party paths, no figures. Radii below are for the
440px-diameter block; scale proportionally.

| Element | Radius | Stroke | Behaviour |
|---|---|---|---|
| Ray corona | 202 → 220, 48 strokes at 7.5° | 1px | Rays inside a **completed** arc are `--bd-rule`; all others `--bd-rule-construction`. The corona grows with real completion only. |
| Chakra rim | 190 → 198 (an 8px band) | 1px both circles | Divided into six 60° arcs by six radial spokes. The band is where the phase state is drawn. |
| Kavacha plating | 130 → 178 | 1px | Twelve trapezoidal plates as hairline outlines, alternating orientation — armour lamellae. **Purely structural: never animated, never state-carrying**, so it cannot be mistaken for data. |
| Yantra construction | ≤ 120 | 1px `--bd-rule-construction` | Two interpenetrating equilateral triangles inscribed in the circle, plus the resulting six-point star polygon. Static. |
| Centre disc | ≤ 86 | none | Clear field. Holds the state word. **Nothing figural ever appears here.** |

### 7.1 The six phases

Clockwise from 12 o'clock, one 60° arc each:

`INGEST → ANALYZE → CORRELATE → STRESS TEST → REMEDIATE → VERIFY`

Phase state is expressed as **ASCII-density shading inside the arc band** — monospace glyphs set
along the arc path at a 4px pitch. Not a fill, not a gradient, not a glow.

| Phase state | Ramp glyph | Fill |
|---|---|---|
| Pending | ` ` (empty) | Band empty; only the spoke dividers are drawn |
| Running | `:` | Filled to the **real reported fraction**. Never interpolated, never eased toward a guess. |
| Complete | `#` | Full arc |
| Skipped | `-` | Full arc, sparse — used for cut gates such as static delta |
| Failed | `X` | Full arc |

The running arc's ramp shifts by one glyph pitch every 800ms. **This is the only continuous
animation in the product, and it is a liveness indicator rather than decoration: it ticks because
events are arriving, and it stops when they stop.** A frozen ramp is information. Under
`prefers-reduced-motion: reduce` the ramp is static and liveness is carried by the
`[ ● LIVE · LAST EVENT +1s ]` counter instead.

### 7.2 Mapping to the backend state machine

The orchestrator's states
(`docs/03-technical/16-system-architecture-document.md`) do not map one-to-one onto six arcs.
The mapping is fixed here so the frontend and the API agree:

| Mission state | Arc affected | Arc state |
|---|---|---|
| `CREATED`, `VALIDATING` | none | Core shows `Standby` / `Validating`, rim drawn, no shading |
| `SNAPSHOTTED` | INGEST | complete |
| `BASELINE` | INGEST | complete; centre reads `Baseline` |
| `TRIAGE` | ANALYZE | running → complete |
| `CORRELATE` | CORRELATE | running → complete |
| `STRESS_TEST` | STRESS TEST | running → complete |
| `PATCH` | REMEDIATE | running → complete |
| `VERIFY` | VERIFY | running |
| `VERIFIED` | VERIFY | complete; terminal rendering per §6.1 |
| `REJECTED` | VERIFY | complete; rim broken at the REMEDIATE spoke |
| `HUMAN_REVIEW` | current | frozen at its real fraction |
| `FAILED` | current | failed (`X`) |
| `CANCELLED` | all | sparse `-` |

Baseline has no arc of its own because there are six spokes and the workflow has more steps than
that; it is a stage row in the timeline and a centre-word state. If the API later needs a seventh
phase, the wheel does not gain a spoke — the timeline gains a row. **Six is a design constant.**

---

## 8. Motion

| Event | Duration | Property |
|---|---|---|
| Hover, focus | 150ms | colour only — never transform, never size |
| State chip change, arc step | 200ms | colour and opacity |
| Overlay open / close | 300ms | opacity only |
| Core ramp tick | 800ms per glyph pitch | the only continuous animation |

No flashing. No continuous rotation. No idle animation of any kind. A critical alert may pulse its
crop ticks **once** and then hold. Under `prefers-reduced-motion: reduce` every duration above
collapses to 0ms and the ramp holds static.

---

## 9. Accessibility

The PM ranked full WCAG conformance as P2-11 and basic keyboard operability as P1-10, both cut for
the seven-day build. That governs *scope*, not quality — everything below costs nothing extra to
build correctly the first time, so it is in P0 by default.

- **Contrast.** Every text pair in §2.1 is measured and clears 4.5:1; every informational line
  clears 3:1. Construction lines and disabled controls are the two documented exemptions.
- **Colour is never the only channel.** Every state carries a word and a glyph as well
  (§5). This is checkable by rendering greyscale.
- **Focus is always visible.** 2px `--bd-focus-ring` outline at 4px offset on every interactive
  element. `outline: none` without a replacement is a review rejection.
- **Semantic structure.** Panels are `<section>` with an `aria-label` matching their bracket
  label. The timeline is an ordered list. Live regions: the timeline and the alert line use
  `aria-live="polite"`; a verdict change and any critical alert use `role="alert"`.
- **Icon-only controls** — there are almost none by design, since every control is a bracketed
  word — but any that exist carry `aria-label`.
- **Tab order matches visual order:** top strip → left rail → centre → right rail → bottom strip.
  `[ ESC ]` closes the overlay and returns focus to the control that opened it.
- **Reduced motion** is respected as specified in §8.
- **Not in scope:** screen-reader narration of the Core's geometry beyond a text summary
  (`aria-label` giving phase, state and elapsed), full keyboard operation of the diff, and any
  responsive behaviour below 1280px.

---

## 10. Copy tone

Operational, specific, and never reassuring. Three rules:

1. **Name the thing that happened, with its number.** "ctest 42/42 passed", not "Baseline
   healthy". "changed lines 61 exceeds cap 25", not "Patch policy violation".
2. **Never claim more than the tools proved.** "Reproducer eliminated" is a gate result.
   "Vulnerability fixed" is a claim, and it is not ours to make.
3. **No exclamation, no encouragement, no personality.** The system does not congratulate the
   operator and it does not apologise. Error text quotes the underlying error verbatim rather than
   paraphrasing it into something friendlier and less useful.

Every string is uppercase inside brackets and sentence case outside them. Sentences in empty and
error states end with a full stop.

---

## 11. What was cut from the component inventory

[`docs/02-design/33-ui-component-inventory.md`](../02-design/33-ui-component-inventory.md) lists
32 components across three groups. Of those, **8 survive as named components, 9 are merged into
something else, and 15 are cut outright.** That file is left unedited; this table is the record.

### Global components

| Entry | Disposition | Reason |
|---|---|---|
| `CommandBar` | **Merged** → top strip | Becomes bracket chips, not a component |
| `MissionStatusBadge` | **Merged** → `StateChip` | One chip primitive serves every state everywhere |
| `ThreatLevelIndicator` | **Cut** | A derived "threat level" over a single finding is precisely the decorative aggregate the no-fake-metrics rule exists to stop |
| `ElapsedMissionTimer` | **Merged** → `MissionClock` | |
| `SecureSessionIndicator` | **Kept** as a bracket chip | It is a safety claim, and it costs one string |
| `CommandPalette` | **Cut** | Keyboard operability is P1-10, in `CUT` |
| `ConfirmationDialog` | **Kept** | Required for every destructive control |
| `EvidenceDrawer` | **Cut** | Replaced by the diff overlay plus the exported report. A drawer *and* an overlay is two disclosure mechanisms for one job |
| `ToastAndAlertStack` | **Cut** | Replaced by one persistent alert line in the bottom strip. A stack of transient toasts loses information during a live run, which is the opposite of what a mission log is for |

### Mission components

| Entry | Disposition | Reason |
|---|---|---|
| `BrahmadattaCore` | **Kept** | P0 panel 1 |
| `PhaseRing` | **Merged** → `BrahmadattaCore` | The rim band *is* the phase ring |
| `MissionProgressRail` | **Cut** | The stage timeline is the progress rail; two would disagree with each other |
| `RepositoryStatusPanel` | **Merged** → top strip chips | Repo and snapshot hash are two strings, not a panel |
| `BaselineHealthPanel` | **Merged** → timeline `BASELINE` row | Carries the real ctest counts, which is all it ever had |
| `StaticFindingsPanel` | **Cut** | Semgrep and the static-delta gate are in `CUT` |
| `VulnerabilityQueue` | **Merged** → `FindingsList` | P0 has one finding; a queue of one is a list |
| `FuzzingActivityPanel` | **Cut as a panel** | Real exec counts appear as event rows under STRESS TEST. A dedicated panel for one number invites decorative charting |
| `PatchGenerationPanel` | **Merged** → diff overlay header | |
| `VerificationMatrix` | **Kept**, renamed `GateMatrix` | Now mandatory inside the verdict panel per D-009 |
| `GitBisectTimeline` | **Cut** | Bisect is in `CUT` |
| `SystemAlertPanel` | **Cut** | One alert line in the bottom strip |
| `GpuClusterHealthPanel` | **Cut** | D-015 cut the rented GPU entirely |
| `RegressionTestPanel` | **Merged** → `[ + REGRESSION PRESERVED · 42/42 ]` gate chip | |
| `ArtifactVaultPanel` | **Cut** | Becomes the `[ EXPORT EVIDENCE ]` control plus its result chip |

### Visualization components

| Entry | Disposition | Reason |
|---|---|---|
| Severity donut | **Cut** | A donut chart of one finding is decoration wearing a chart's clothes |
| Coverage sparkline | **Cut** | Coverage visualization is P2-6 |
| Execution-rate waveform | **Cut** | The canonical decorative dashboard metric. Fuzz exec/s appears as a number in an event row, where it can be read and cited |
| Test-results ring | **Cut** | Redundant with the gate chip's `42/42`, and a ring cannot be quoted in an evidence report |
| GPU utilization / memory graph | **Cut** | No GPU (D-015) |
| Commit timeline | **Cut** | Bisect is in `CUT` |
| Diff viewer | **Kept** → `DiffView` | P0 panel 4 |
| State-machine timeline | **Kept** → `StageTimeline` | P0 panel 2 |

### Also cut, from elsewhere in `docs/02-design/`

| Entry | Source | Reason |
|---|---|---|
| Screens 1, 3, 5, 6 (Mission Setup, Finding Detail, Evidence Report, System/GPU Health) | `31-dashboard-screen-specification.md` | P0-13 specifies five panels on one screen. Setup collapses into the authorize dialog; finding detail into the finding row plus the diff overlay; the evidence report is an exported file, not a screen; GPU health has no GPU |
| Presentation mode | `10-wireframes.md` §5 | In `CUT`. Consequence recorded in §2.6: there is now no sanctioned place for mock data at all |
| Collapse-to-drawers below 1280px | `00-ui-design-direction.md` | Desktop-first at 1440×900+; the finale runs on a known machine |
| Sound design | `34-ui-state-and-motion-specification.md` | Off by default in the pack already; not built |
| Glass panels, luminous borders, restrained glow | `00-ui-design-direction.md` | Superseded by D-017. This is the largest single departure in this document |

### What replaces them — the P0 component inventory

| Component | Panels |
|---|---|
| `FrameAndTicks` | Every panel — the page frame and crop-mark primitive |
| `BracketLabel` | Every panel |
| `StateChip` | Every panel |
| `PanelHeader` | Every panel |
| `EmptyState`, `PlaceholderRules` | Every panel |
| `BrahmadattaCore`, `PhaseArc` | 1 |
| `StageTimeline`, `StageRow`, `EventRow` | 2 |
| `FindingsList`, `FindingRow` | 3 |
| `DiffView`, `DiffLine`, `ProvenanceChip`, `ModelSelfReport` | 4 |
| `VerdictReadout`, `GateMatrix`, `GateChip` | 5 |
| `MissionClock`, `StreamLiveness` | Top strip |
| `CommandStrip`, `ConfirmDialog` | Bottom strip |

Twenty-two components, of which seven are primitives shared by everything. That is the entire
frontend surface for the seven-day build.

---

## 12. Build notes for the frontend developer

Not prescriptive about framework — that belongs to the software-architect — but these follow from
the design and would be expensive to retrofit.

1. **One SSE connection shared across islands**, per CLAUDE.md. Five panels reading one event
   store; no panel opens its own stream.
2. **The store holds only what the stream said.** No derived progress, no predicted completion, no
   client-side timers advancing anything. The stale detector is the one timer, and it only ever
   *degrades* the display.
3. **Self-host both fonts as woff2.** A CDN `@import` that fails on the finale machine drops
   everything to Times New Roman.
4. **The Core is one SVG**, sized by viewBox, with the ASCII ramp as `<textPath>` on arc paths.
   SVG before WebGL, per the stack table.
5. **Crop marks are a shared primitive**, not four absolutely-positioned divs per panel. They are
   used on the order of fifty times.
6. **Test `proxy_buffering off`** on the SSE location before believing any of the live behaviour
   here. Behind a default nginx config the ramp will tick in development and freeze in the demo.

---

## 13. Open questions

Owners named. These block nothing today but will cost rework if they are answered late.

| # | Question | Owner |
|---|---|---|
| 1 | Does the event payload carry a **fractional progress value** per phase, or only discrete transitions? The Core's running arc needs a real fraction; without one it renders as a filled-to-nothing `:` band, which is honest but much less legible. | backend-developer / software-architect (issue #6, frozen contract) |
| 2 | Is `provenance` a required non-nullable field on the patch-candidate record? §6.4 suppresses the diff without it. D-008 assumes it exists. | backend-developer |
| 3 | Are the two unrun gates (static delta, renewed fuzz) present in the API's gate-matrix payload as explicit `not_run` entries, or absent? The verdict panel must enumerate them either way, so absent means the frontend hardcodes the full list of five. | backend-developer |
| 4 | Confirmed finale display resolution and whether the demo runs on a projector. The **ROOM** type tier is sized for ~4 m on a 1440 display; a projector at 1920 changes the numbers. | CEO / competition-strategist |
| 5 | Is a second patch candidate guaranteed to exist at demo time, or is the two-column verdict compare conditional? It is specified as conditional, but if it is guaranteed the layout can be tuned for it. | product-manager |

---

*Decision records for the non-trivial calls in this document: D-019 … D-023 in
[`.project/decisions.md`](../../.project/decisions.md). The direction they implement is D-017 and
D-018, both CEO-decided.*
