# The P0 Screen Set and Design System

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Document | Company-workflow D1/D2 deliverable — GitHub issue #7 |
| Status | **Amended 2026-08-07** to clear the product review's conditions C1–C4 and C6–C8. C5 (phase order) resolved by D-038 on the same day — §7.1a. Frozen otherwise; §14 is the amendment record and §15 the decision records. |
| Drafted by | `ui-ux-designer` seat |
| Date | 2026-08-07 (rev 2) |
| Governs | The five P0 panels (P0-13) and every token used to build them |
| Tokens | [`packages/ui-components/tokens.css`](../../packages/ui-components/tokens.css) |
| Review | `product-manager` seat, APPROVE WITH CONDITIONS. Disposition of every condition in §14. |

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

**No ninth colour is added by this revision.** One semantic token is added over an existing
primitive:

| Semantic token | Aliases | Used by |
|---|---|---|
| `--bd-state-not-run` | `--bd-c-warning` | **Verification gates only.** A gate in a verdict matrix that did not execute. |

This reconciles a genuine conflict between this document and
[`06-architecture-spec.md` §5.4](06-architecture-spec.md), which requires `NOT_RUN` to render
"in amber with its reason string inline". The reconciliation is **DS-03** in §15, and the
resulting rule is narrow enough to state in one line:

- **An unproduced *value*** — a counter whose producing step has not completed — is an em dash
  in `--bd-text-secondary`. D-023 is unchanged. `[ FINDINGS · — ]`.
- **An unrun *gate in a verdict matrix*** is an em dash glyph, the word `NOT RUN`, the colour
  `--bd-state-not-run`, and a mandatory inline reason. D-009's protection is that an unrun gate
  is as loud as a failed one, and secondary grey is this system's colour of de-emphasis, which
  is the opposite of loud.

The em dash glyph is retained in both cases, so "not measured" is still carried by glyph and
word and never by colour alone. `NOT RUN` never uses a warning *word*, so it does not collide
with the warning state (§5).

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

**The advance-width assumption, stated so it can be checked.** Every column-count and panel-width
figure in this document is derived from a **0.6em monospace advance** — 9.0px at `mono-md`,
7.8px at `mono-sm`, 7.2px at `mono-xs`, 6.6px at `mono-2xs`. This supersedes the 0.52em figure
used in [D-020](../../.project/decisions.md) ("80 columns ≈ 624px at `mono-md`"), which was
optimistic; at 0.6em the same 80 columns is 720px, which is why §6.4 no longer promises 80
columns anywhere.

**First build task on any panel that does width arithmetic:** render a 60-character ruler string
in the shipped Fragment Mono woff2 and measure it. If the real advance differs from 0.6em by
more than 3%, the budgets in §3, §6.4 and §6.5 must be re-derived before the panel is built, not
after. This is thirty seconds of work and it is the difference between the compare fitting and
the compare wrapping on stage.

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
| Gate row | `[ + COMPILE · clang 18.1.3, exit 0 ]` `[ × REGRESSION · 40/42 · 2 FAILED ]` | Leading glyph from the glyph tokens, never colour alone. One gate per row, five rows, never chips wrapping. |
| Unrun gate | `[ — STATIC DELTA · NOT RUN · <reason> ]` | Em dash glyph, `--bd-state-not-run`, **reason mandatory and inline**, rendered verbatim from `GateResult.detail`. §2.1, DS-03. |
| Not-measured value | `[ FINDINGS · — ]` | Em dash, `--bd-text-secondary`, **never** a state colour. D-023. |
| Provenance | `[ PROVENANCE · MODEL-GENERATED ]` | `--bd-text`, never a state colour, no default, no third value. §6.4.2. |
| Resource | `[ + SANDBOX 01 · RELEASED ]` | One per resource kind. State follows a receipt, never an intention. §6.6. |
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
│           snapshot a4f1c9                  ·:·  radiating rays  ·:·        HEAP-BUFFER-   │
│           00:00:04      [ + OK ]                                           OVERFLOW       │
│    ─────────────────────────               ╭──── kavacha plating ──╮       parser.c:118   │
│    [ 02 ] INGEST                          │   ╱  yantra grid  ╲     │     [ ● CONFIRMED ] │
│           1 204 files                     │  ╱                 ╲    │    ────────────────  │
│           00:00:31      [ + OK ]          │ │     Analyze       │   │    [ EVIDENCE ·     │
│    ─────────────────────────              │  ╲ ─ 48px serif ─  ╱    │      SANITIZER ]    │
│    [ 03 ] BASELINE                         │   ╲              ╱     │    AddressSanitizer:│
│           ctest 42/42 passed                ╰──── chakra rim ──╯          heap-buffer-    │
│           00:02:11      [ + PASS ]         ─ 380 block + 44 label ─       overflow        │
│    ─────────────────────────                                              READ 4 @ +2     │
│    [ 04 ] ANALYZE            ◀ running     [ PHASE 02 OF 06 · ANALYZE ]     #0 parse_head…│
│           no static analyzer               [ ● LIVE · LAST EVENT +1s ]      #1 parse_pack…│
│           configured in this build                                          #2 LLVMFuzzer…│
│           00:01:08      [ > RUN ]          ──────────────────────────────  [ FRAMES 3/11 ]│
│    ─────────────────────────                                              [ FULL TRACE ]  │
│    [ 05 ] STRESS TEST        [ · QUEUED ]  [ VERDICT ]                    ────────────────│
│    [ 06 ] CORRELATE          [ · QUEUED ]  Pending    ─ Instrument Serif 72 [ EVIDENCE ·  │
│    [ 07 ] REMEDIATE          [ · QUEUED ]  ═══════════════════════════════   REPRODUCER ] │
│    [ 08 ] VERIFY             [ · QUEUED ]  [ — GATES · NONE RAN ]         minimized       │
│    [ 09 ] EXPORT EVIDENCE    [ · QUEUED ]  [ — COMPILE · NOT RUN · … ]    4 812 → 61 B    │
│    [ 10 ] TEARDOWN           [ · QUEUED ]  [ — REPRODUCER ELIMINATED · … ] replay — /5    │
│                                            [ — REGRESSION PRESERVED · … ]                 │
│    ↕ autoscroll pinned to newest           [ — STATIC DELTA · NOT RUN · … ]                │
│                                            [ — RENEWED FUZZ · NOT RUN · … ]                │
│ ──────────────────────────────────────────────────────────────────────────────────────── │
│   [ LOCAL · LOOPBACK ONLY ] [ EGRESS DENIED ] [ RESOURCES · 2 HELD ]                       │
│   [ EVENTS 1 284 ] [ ● SANDBOX 01 · RUNNING ] [ ● MODEL HOST · LEASED ]                    │
│                             ← 2 × 16px text lines │ one 44px control row →                 │
│                          [ OPEN COMPARE ] [ PAUSE ] [ CANCEL MISSION ] [ EXPORT EVIDENCE ] │
│ └ ─                                                                                   ─ ┘ │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

**Region budget at 1440×900.** Frame inset 32 → 1376 wide, 836 tall. Content padding 24 →
1328 × 788. Top strip 64, bottom strip 56, two 1px rules, 24 padding above and below the body →
body height 684. Three columns 336 / 608 / 336 with two 24px gutters = 1280, leaving 48 of slack
that the centre column absorbs first.

**Centre column, revised, and it now closes exactly:**

| Block | Height | Note |
|---|---:|---|
| Core block | **424** | 380px wheel + 44px label space (§6.1, §7) |
| Gutter | 24 | |
| Verdict panel | **236** | Verdict word, denominator, and all five gate rows (§6.5) |
| | **684** | = the body height, with zero slack |

The wheel shrank from 440 to 380 and the Core's centre word from 72px to 48px. That is not
cosmetic: at 440 the 72px word `Cancelled` measures roughly 272px against a 172px clear disc, so
the specification as originally written could not be built. The revision also stops the Core and
the verdict panel from shouting the same word at the same size 200px apart. **The verdict panel
is now the product's only 72px readout**, which is what the "single hero readout" rule in §2.2
always intended. Recorded as **DS-01**.

**The bottom strip carries a resource ledger** (§6.6), which is the surface teardown was missing
on the success path. `[ SESSION SECURE ]` is retired: the finale runs on `http://localhost`
(CEO, #92) and a chip claiming a secure session over plain HTTP is a fabricated safety claim of
exactly the kind §2.6 exists to stop. `[ LOCAL · LOOPBACK ONLY ]` says the true thing and is a
stronger claim in context.

**The diff is not in this layout.** A unified C diff at `mono-md` needs about 9px per column; the
336px rails hold 34 columns and the 608px centre holds 64. It opens in the **Candidate Compare
overlay** (§6.4), which is also where the two-candidate comparison happens — see DS-02 for why
the comparison moved out of the verdict panel.

---

## 4. User journeys

The nine-step demo from [§3 of the P0 cut](01-vision-and-p0-cut.md#3-the-minimum-viable-demo),
expressed as what the operator does and what the screen does back.

### 4.1 Primary journey — the mission run

The **Demo** column maps each row onto the numbered step in
[§3 of the P0 cut](01-vision-and-p0-cut.md#3-the-minimum-viable-demo). Every one of the nine
steps now has at least one row, which is the check this table failed at review.

| # | Demo | Entry point | Screen response | Success state | Failure / edge |
|---|---|---|---|---|---|
| 1 | — | Operator opens the Command Center with no mission | Every panel in its empty state. Core shows `Standby`. | — | API unreachable → top strip shows `[ × CONTROL API UNREACHABLE ]` critical, body shows the loading placeholder, no fabricated content |
| 2 | **2** | `[ AUTHORIZE + START ]` in the bottom strip | Confirmation dialog naming the repository, the snapshot hash and the egress policy | Mission created; Core rim draws; timeline gains `[ 01 ] AUTHORIZE`; ledger gains `[ ● SANDBOX 01 · STARTING ]` | Authorization declined → mission is not created; timeline stays empty; alert line states the reason |
| 3 | **2** | Automatic | `INGEST` arc shades; timeline row appends with real file count | `[ + OK ]` on the ingest row | Snapshot mismatch → row `[ × FAIL ]` critical, Core enters Failed, no further stage starts |
| 4 | **3** | Automatic | `BASELINE` row shows real `ctest` counts as they land | `[ + PASS · 42/42 ]` | Any baseline test fails → `[ × FAIL · 40/42 ]`, Core Failed. Baseline failure is terminal; the denominator for "regression preserved" does not exist. |
| 5 | — | Automatic | `ANALYZE` row runs and completes finding nothing, by construction | `[ + COMPLETE · NO ANALYZER ]`, sub-line `no static analyzer configured in this build` | Stage errors → `[ × FAIL ]` with the error verbatim. **It never reports `0 findings`**, which would claim a clean static analysis that was never performed (§6.2, C8) |
| 6 | **4** | Automatic | `STRESS TEST` arc ticks; event rows carry real exec counts | Sanitizer-confirmed crash → findings list gains `[ FINDING 01 ]` with `[ ● CONFIRMED ]` | No crash inside the budget → `[ ! NO FINDING · BUDGET EXHAUSTED ]` warning, mission ends cleanly with no verdict. **The panel does not show a zero as a result.** |
| 7 | **4** | Automatic, on `FINDING_RECORDED` and on minimization completing | The findings rail's **evidence block** fills: sanitizer report with the top stack frames naming the vulnerable function, then the reproducer's minimization and replay record (§6.3) | `[ ● ASan CONFIRMED ]` plus `replay 5/5 from a clean build` and `[ + DETERMINISTIC ]` | Replay successes < attempts → `[ ! NON-DETERMINISTIC · 3/5 ]` in warning. `reproducible` is never inferred; it is `successes == attempts` or it is not claimed |
| 8 | **5** | Automatic | Timeline `REMEDIATE` row appends one event row per patch attempt, each naming its provenance | Candidates persist as they are produced; the row reads `2 candidates · 1 policy-passing` | Policy rejects a candidate pre-verification → that candidate's compare column shows `[ POLICY · FAIL ]` critical naming the failing rule; no gates run for it |
| 9 | **6, 7** | Automatic | Gate rows resolve one at a time as each tool returns, in the centre verdict panel | `Verified`, `[ 3 OF 5 GATES RAN ]`, all five rows enumerated with the two unrun gates in `--bd-state-not-run` and their reasons inline | Regression fails → `Rejected`; the failing row is the only critical element, with counts inline |
| 10 | **6, 7** | `[ OPEN COMPARE ]`, or automatically when the second `VerificationRecord` lands | The **Candidate Compare overlay** opens at 1328 × 684: two 652px columns, each with its own provenance chip, verdict, five-row gate matrix and diff (§6.4) | `Verified` and `Rejected` in 72px serif side by side, each above its own enumerated matrix and its own provenance label — the money shot | One candidate only → the degraded single-column state: candidate left, full sanitizer and reproducer evidence right. Never an empty column |
| 11 | **8** | `[ EXPORT EVIDENCE ]` | Confirmation, then `[ ● EXPORTING ]`, then `[ + EXPORTED · report.md · report.json ]` with the paths | Files written; timeline row `[ 09 ] EXPORT EVIDENCE` closes `[ + OK ]` | Export fails → `[ × EXPORT FAILED ]` critical with the error string verbatim, control re-enabled |
| 12 | **9** | Automatic on every terminal transition (§6.6) | Timeline appends `[ 10 ] TEARDOWN` with **one event row per resource**; the ledger chips flip as each `TEARDOWN_CONFIRMED` arrives; the Core gains its release line | `[ + ALL RESOURCES RELEASED · 2 OF 2 ]` in the bottom strip, `[ + SANDBOX 01 · RELEASED ]` and `[ + MODEL HOST · RELEASED ]` in the ledger, matching rows in the timeline | Any resource unconfirmed → `[ ! RESOURCES · 1 OF 2 RELEASED ]` in warning and the unreleased chip stays `[ ● … · HELD ]`. **The roll-up never rounds up.** Release failure → `[ × SANDBOX 01 · RELEASE FAILED ]` critical with the error verbatim and `[ EMERGENCY TEARDOWN ]` promoted to the primary control |

Step 12 is the fix for the review's C1. Teardown previously appeared only on the emergency path
in §4.2, which meant a mission that completed correctly had nowhere to show that its sandbox and
its model-host lease were released — for an uncuttable requirement (P0-14) that is also a scored
competition criterion. It now has three surfaces, all on the success path, all reading the same
`TEARDOWN_CONFIRMED` events: the timeline rows, the ledger (§6.6), and the Core's release line
(§6.1). Recorded as **DS-04**.

### 4.2 Secondary journey — operator intervenes

`[ PAUSE ]` → pauses **after the current stage**, never mid-tool. Chip becomes
`[ ● PAUSING · AFTER ANALYZE ]` warning, then `[ ● PAUSED ]`. Core's active arc freezes at its
real fraction and the ramp stops ticking. `[ RESUME ]` replaces `[ PAUSE ]`.

`[ CANCEL MISSION ]` → confirmation dialog: "Cancel mission 04. The sandbox is destroyed and any
unexported evidence is lost. This cannot be undone." On confirm the Core enters Cancelled and the
timeline appends a cancellation row with the operator's identity.

`[ EMERGENCY TEARDOWN ]` → always enabled, even when everything else is disabled. Confirmation
names every resource that will be destroyed. It resolves into **the same resource ledger** the
success path uses (§6.6) — there is one teardown surface, not an emergency one and a normal one,
because two would disagree with each other at exactly the moment that matters.

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
| Not run — **a gate** | `—` | `NOT RUN` | `--bd-state-not-run` | A verification gate that did not execute. **Reason string mandatory and inline.** As loud as a failure, per D-009 and architecture spec §5.4. |
| Not measured — **a value** | `—` | none | `--bd-text-secondary` | A counter whose producing step has not completed. Never a zero, never a state colour. D-023. |
| Disabled | `·` | reason text | `--bd-text-disabled` | Always paired with why |

The two `—` rows are the only place in this system where the same glyph carries two meanings, and
the split is deliberate: see §2.1 and **DS-03**. In review, the question that separates them is
*"is this in a verdict's gate matrix?"* If yes, it is amber with a reason. If no, it is secondary
and silent.

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

**§6.6 is not a sixth panel.** P0-13 names five and this document still builds five. The resource
ledger is a chip group in the bottom strip, alongside `[ EGRESS DENIED ]` and `[ EVENTS ]`, sized
in chips rather than in body height. It is specified at panel depth because P0-14 is uncuttable
and a scored criterion, not because it is being promoted. §6.3a is likewise a block inside panel
3, not a restored Finding Detail screen — see DS-05.

### 6.1 Panel 1 — Brahmadatta Core

Centre column, top. **380px diameter**, `--bd-col-centre` wide block, **424px tall** (380 wheel +
44 label). See §7 for the geometry, and DS-01 for why it shrank.

**Content, top to bottom:** the chakra; centred on the wheel's centre, the current state word in
Instrument Serif **48px** (`display-md`, ROOM tier); beneath the wheel a 44px label block holding
two `mono-md` lines.

**The centre word is permitted to overrun the clear disc.** At 48px the longest word in the
vocabulary, `Cancelled`, measures roughly 181px against a 148px disc. It overruns onto the yantra
construction, and that is fine and intended — the yantra is drawn in
`--bd-rule-construction` at 1.8:1 precisely so a display word can sit over it and still clear
4.5:1. It must **never** overrun onto the kavacha plating (inner diameter 224 at this scale); if a
future state word would, shorten the word, not the plating.

**The 44px label block, two lines, `mono-md`:**

| Mission phase | Line 1 | Line 2 |
|---|---|---|
| Running | `[ PHASE 02 OF 06 · ANALYZE ]` | liveness chip — `[ ● LIVE · LAST EVENT +1s ]` |
| Terminal (any) | `[ PHASE 06 OF 06 · COMPLETE ]` | **release line** — `[ + RESOURCES RELEASED · 2 OF 2 ]` in `--bd-state-verified`, or `[ ! RESOURCES · 1 OF 2 RELEASED ]` in warning, or `[ — RESOURCES · AWAITING TEARDOWN RECEIPT ]` while confirmations are outstanding |

The release line replaces the liveness chip on terminal states because the stream is closed and a
liveness chip would then be either stale or fabricated. It reads the same `TEARDOWN_CONFIRMED`
events as the ledger (§6.6) and the timeline; the three surfaces cannot disagree because there is
one source. This is one of C1's three surfaces.

**States**

| State | Rendering |
|---|---|
| Empty (no mission) | Rim and plating drawn in `--bd-rule-construction` only. No arc shading, no rays. Centre reads `Standby` in `--bd-text-secondary`. Below: `[ NO ACTIVE MISSION ]` and "Authorize a repository to begin." |
| Loading (connecting to stream) | Rim drawn, centre reads `Connecting`, liveness chip `[ · OPENING STREAM ]`. No arc shading — the phase states are unknown and must not be guessed at. |
| Running | Completed arcs shaded `#`, active arc shaded `:` and filled to its **real** reported fraction, pending arcs empty. Rays lit only within completed arcs. Centre reads the active phase name. Chip `[ ● LIVE · LAST EVENT +1s ]`. |
| Degraded (stream stale) | No event for >10s: the ramp stops ticking, arcs freeze exactly where they are, chip becomes `[ ! STREAM STALE · LAST EVENT +23s ]` in warning, and the four crop ticks of the centre column turn warning-coloured. **The wheel does not advance.** |
| Verified | Rim ramp becomes continuous `#` all the way round and a second concentric circle is drawn at r=195. Centre reads `Verified` in `--bd-state-verified`. |
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

**Ten stage rows, fixed, always all present.** The list does not grow or shrink with what the
backend happens to emit; a stage that has not started is `[ · QUEUED ]`, which is information.

```
[ 01 ] AUTHORIZE        [ 06 ] CORRELATE
[ 02 ] INGEST           [ 07 ] REMEDIATE
[ 03 ] BASELINE         [ 08 ] VERIFY
[ 04 ] ANALYZE          [ 09 ] EXPORT EVIDENCE
[ 05 ] STRESS TEST      [ 10 ] TEARDOWN
```

Rows 09 and 10 are new in this revision. **Row 10 is the primary surface for C1** — teardown is a
stage of the mission, it appears in the narrative on every path including the successful one, and
it carries one nested event row per released resource:

```
[ 10 ]  TEARDOWN                    [ + OK ]
        2 of 2 resources released · 00:00:03
        00:41:07  sandbox 01 released · receipt 7f2c…
        00:41:09  model host lease released · receipt b104…
```

Those event rows are auto-expanded on terminal states — the one exception to "event rows render
only when a stage is expanded" — because the release receipt is a scored deliverable and it must
not be behind a click during a demo. Ten rows × 48 + separators ≈ 490 of the 684 available, so
the expanded teardown group fits without scrolling on the terminal frame.

Teardown does **not** gain a Core spoke. §7.2's rule stands: when the workflow gains a step, the
timeline gains a row and the wheel does not. Six is a design constant.

**Stage row — 48px, two lines.**

```
[ 03 ]  BASELINE                    [ + PASS ]
        ctest 42/42 · 00:02:11
```

Line 1: index bracket (`mono-3xs`, secondary) · stage name (`mono-sm`, primary; `mono-lg` and
white while running) · state chip, right-aligned. Line 2: the real substantive result — never a
generic "completed" — plus elapsed, in `mono-xs` secondary. Row separator: 1px
`--bd-rule-construction`.

**Event row — 28px, one line, indented 24px.** Rendered when a stage is expanded, and
automatically for `[ 10 ] TEARDOWN` on terminal states. Carries raw telemetry:
`00:01:44  fuzz exec 1 284 003 · 0 new crashes`.

**The `[ 04 ] ANALYZE` row, stated exactly, because this is where the review found an overstatement.**
Its sub-line is not `semgrep — not run`. Semgrep is not integrated at all in the seven-day scope
(#22 cut, P1-2), so "not run" implies a configured tool that was skipped, which is a more
flattering claim than the truth. The row renders:

```
[ 04 ]  ANALYZE                     [ + COMPLETE · NO ANALYZER ]
        no static analyzer configured in this build · 00:01:08
```

That sub-line string is **the `LOG` event the TRIAGE stage is required to emit** by
[architecture spec §2.5](06-architecture-spec.md) — the UI renders the backend's own words rather
than composing its own, so the dashboard and the evidence bundle cannot drift apart. The chip is
`[ + COMPLETE · NO ANALYZER ]`, never `[ + COMPLETE · 0 FINDINGS ]`: a zero here would claim a
clean static analysis that was never performed, which is §2.6's first rule verbatim. This is C8.

**States**

- **Empty:** `[ NO MISSION ]` and "Start a mission to populate the timeline." No rows, no zeros.
- **Loading:** three placeholder rule rows.
- **Running:** the active row's crop ticks turn white and its stage name goes `mono-lg`.
- **Degraded:** stream stale → a single warning row is appended in place:
  `[ ! STREAM STALE ] the timeline may be incomplete`. Existing rows are never altered or removed.
- **Failed:** the failing row is critical; every row below it renders `[ · NOT REACHED ]` in
  secondary — not `[ × FAIL ]`, because they did not fail, they never ran. `[ 10 ] TEARDOWN` is
  the **one exception**: it still runs and still reports, because teardown does not depend on the
  happy path (architecture spec §6.7).
- **Event overflow:** an expanded stage renders **its most recent 50 event rows**, with
  `[ … 431 EARLIER EVENTS ]` as a non-collapsing disclosure line at the top of the group. There
  is no virtualization and no windowing machinery. 50 is chosen because it is the threshold
  above which the `ui-ux-pro-max` guideline set calls for virtualization — sitting at it means
  plain rendering stays correct. The real number this has to survive is a 40-minute fuzz campaign
  at one throttled event per 5 s ≈ 480 rows (architecture spec §3.2), all under one stage.

### 6.3 Panel 3 — Findings list

Right rail, 336 × 684.

Header: `[ FINDINGS · 1 ]`. Before analysis has run the count is `—`, not `0`.

Sort order: severity, then discovery order. In P0 there is normally exactly one row.

**Finding row — 44px.**

```
[ FINDING 01 ]  HEAP-BUFFER-OVERFLOW          [ ● CONFIRMED ]
                parser.c:118 · read 4 @ +2 · ASan
```

Selection: the selected row's crop ticks turn white and a 2px left rule appears. Selection opens
the Candidate Compare overlay scoped to that finding, if a candidate exists.

### 6.3a The evidence block — where demo step 4's evidence lives

This closes the review's C2. Demo step 4 produces two artifacts the whole verdict rests on: a
**sanitizer stack trace naming the vulnerable function**, and a **reproducer that replays 5/5
from a clean build**. Neither landed in the finding row or the diff overlay, and §11 had cut the
Finding Detail screen on the grounds that detail collapses into those two. It did not. This is
the evidence a judge asks to see the moment you say "confirmed".

It goes in the space the previous revision filled with `[ EMPTY BELOW ]` and a sentence about
there being nothing there. That was composition standing in for content; roughly 600px of the
right rail was being spent to look deliberate. It is now spent on the proof.

**Rendered directly beneath the selected finding row**, always expanded, never behind a control.
Two blocks separated by a hairline rule.

```
────────────────────────────────────────
[ EVIDENCE · SANITIZER ]
AddressSanitizer: heap-buffer-overflow
READ of size 4 at 0x602000000114
  #0 parse_header        parser.c:118
  #1 parse_packet        parser.c:204
  #2 LLVMFuzzerTestOneIn fuzz_parser.c:12
[ FRAMES 3 OF 11 ]      [ FULL TRACE ]
────────────────────────────────────────
[ EVIDENCE · REPRODUCER ]
minimized 4 812 → 61 bytes
replay 5/5 from a clean build
[ + DETERMINISTIC ]
```

| Element | Type | Rule |
|---|---|---|
| Block label | `mono-2xs`, secondary | `[ EVIDENCE · SANITIZER ]`, `[ EVIDENCE · REPRODUCER ]` |
| Error class + access | `mono-sm`, `--bd-text` | Verbatim from the ASan report's first two lines. Never paraphrased. |
| Stack frame | `mono-xs`, `--bd-text` | `  #N  function  file:line`. The rail holds 43 characters at `mono-xs`; function truncates to 20 with no ellipsis glyph inserted mid-identifier — truncate and let `[ FRAMES n OF N ]` carry the disclosure. **Hex addresses are dropped in the rail** and retained in the artifact and the export; the frame's job here is naming the function, which is the claim demo step 4 makes. |
| Frame count | `mono-2xs`, secondary | `[ FRAMES 3 OF 11 ]` — mandatory whenever frames are elided. Never silently truncate a stack trace. |
| `[ FULL TRACE ]` | control | Opens the raw `sanitizer_report` artifact in the compare overlay's evidence column at full width. |
| Minimization | `mono-sm` | `minimized 4 812 → 61 bytes`. Both numbers real, both from the artifact record. |
| Replay | `mono-sm` | `replay 5/5 from a clean build` |
| Determinism chip | `mono-md`, ROOM | See the state table below |

**Determinism chip states** — this is the one the honesty rules bite hardest on, because
`Reproducer.reproducible` is set from `successes == attempts` and is never inferred
(architecture spec §5.1):

| Condition | Chip | Colour |
|---|---|---|
| Replay completed, all attempts succeeded | `[ + DETERMINISTIC · 5/5 ]` | verified |
| Replay completed, some attempts failed | `[ ! NON-DETERMINISTIC · 3/5 ]` | warning |
| Replay completed, none succeeded | `[ × NOT REPRODUCIBLE · 0/5 ]` | critical |
| Replay has not run yet | `[ — REPLAY · NOT RUN ]`, sub-line `replay — /5` | secondary (a value, not a gate — §5) |
| Minimization ran, replay not started | `minimized 4 812 → 61 bytes` renders; the replay line renders `replay — /5` | secondary |

**States for the panel as a whole**

- **Empty, before the stress test has produced anything:** `[ FINDINGS · — ]`, "Findings appear
  when a sanitizer report is captured." No evidence block.
- **Empty, after the stress test completed with no crash:** `[ FINDINGS · 0 ]`, "Stress test
  completed. No sanitizer-confirmed defect in this snapshot within the fuzzing budget." — a
  measured result, phrased as one, with the budget named because "we didn't find one" and "we
  didn't look long enough" are different claims.
- **Loading:** two placeholder rule rows in the list, three in the evidence block. Space is
  reserved so the block does not push the layout when it lands.
- **Evidence pending:** the finding row is present but the sanitizer artifact has not been
  persisted → `[ EVIDENCE · SANITIZER ]` renders with `[ — REPORT · NOT YET CAPTURED ]` in
  secondary. The finding is **not** shown as `[ ● CONFIRMED ]` until the report exists —
  "confirmed" is a claim about an artifact, not about a crash having happened.
- **Degraded:** stale stream → header gains `[ ! MAY BE INCOMPLETE ]`. The evidence block is
  **not** greyed: already-captured evidence is still true evidence.
- **Failed:** the fetch failed → `[ × FINDINGS UNAVAILABLE ]` with the error string and a
  `[ RETRY ]` control. Never an empty list, which would read as "no findings".
- **Overflow:** more findings than the rail holds → the list scrolls and the evidence block
  follows selection. Only one evidence block is ever rendered at a time.

**Removed in this revision: the unconfirmed-finding state.** `[ ! UNCONFIRMED ]` and the
`[ FINDINGS · 1 · +2 UNCONFIRMED ]` header have no producer in the seven-day scope — findings
originate only from sanitizer-confirmed crashes, and the one stage that could produce an
unconfirmed observation (TRIAGE) runs empty by construction (architecture spec §2.5). A state
with no producer is a state the developer has to invent behaviour for and QA cannot reach. It is
recorded in §11 so it is recoverable if a producer ever appears. This is C7.

### 6.4 Panel 4 — Candidate Compare overlay

Formerly "Diff view". Renamed and restructured, because the previous specification contained a
contradiction the review caught (C3): `[ OPEN DIFF ]` opened an overlay that covered the verdict
panel that was supposed to be doing the comparing, and the compare's arithmetic did not carry —
`Verified` at 72px serif measures around 242px against the 292px column it was given, and five
gate chips do not stack in 124px of panel.

**The comparison moves into the overlay.** The overlay is where the width is. Recorded as
**DS-02**.

A full-content-width overlay, **1328 × 684**, inset inside the page frame so the top strip and the
mission clock stay visible. Opened by `[ OPEN COMPARE ]`, by selecting a finding, or automatically
when the second `VerificationRecord` lands. Closed by `[ ESC ]` or `[ CLOSE ]`. Z-index
`--bd-z-overlay`. Background is the field — the overlay is opaque, not translucent; there is no
glass in this system.

**Two candidates is the default, not a conditional.** PR #74 merged with both patch candidates
committed as files, so candidate B produces a real gate matrix on every run. Single-column is
now the **degraded** state, specified below.

#### 6.4.1 Structure and arithmetic

```
┌ overlay 1328 × 684 ────────────────────────────────────────────────────────────────────┐
│ [ FINDING 01 · EVIDENCE ]                                              [ ESC CLOSE ]   │  16
│ HEAP-BUFFER-OVERFLOW · parser.c:118 · READ 4 @ +2 · #0 parse_header                     │  22
│ [ ● ASan CONFIRMED ]  [ + REPRODUCER REPLAY 5/5 ]  [ MINIMIZED 4 812 → 61 B ]           │  22
│ ─────────────────────────────────────────────────────────────────────────────────────  │  21
│ ┌ ── 652 ────────────────────────┐ │ ┌ ── 652 ────────────────────────┐                │
│   [ CANDIDATE 01 ]               │ │   [ CANDIDATE 02 ]                                 │  16
│   [ PROVENANCE · MODEL-GENERATED]│ │   [ PROVENANCE · OPERATOR-SUPPLIED ]               │  22 ROOM
│   [ POLICY · PASS · 8/25 lines ] │ │   [ POLICY · PASS · 6/25 lines ]                   │  20
│   ─────────────────────────────  │ │   ─────────────────────────────                    │  17
│   Verified                       │ │   Rejected            ─ 72px serif ─               │  68 ROOM
│   ═══════════════════════════    │ │   ═══════════════════════════                      │   2
│   [ 3 OF 5 GATES RAN ]           │ │   [ 3 OF 5 GATES RAN ]                             │  26 ROOM
│                                  │ │                                                    │   8
│   [ + COMPILE · clang 18.1.3 ]   │ │   [ + COMPILE · clang 18.1.3 ]                     │  22
│   [ + REPRODUCER ELIM · 5/5 ]    │ │   [ + REPRODUCER ELIM · 5/5 ]                      │  22
│   [ + REGRESSION · 42/42 ]       │ │   [ × REGRESSION · 40/42 · 2 FAILED ]              │  22
│   [ — STATIC DELTA · NOT RUN · …]│ │   [ — STATIC DELTA · NOT RUN · … ]                 │  22
│   [ — RENEWED FUZZ · NOT RUN · …]│ │   [ — RENEWED FUZZ · NOT RUN · … ]                 │  22
│   ─────────────────────────────  │ │   ─────────────────────────────                    │  17
│   [ DIFF · parser.c ]            │ │   [ DIFF · parser.c ]                              │  16
│   files 1/1 · changed lines 8/25 │ │   files 1/1 · changed lines 6/25                   │  18
│   118 │+│ if (off + len <= cap) {│ │   118 │+│ len = 0;                                 │ 194
│   119 │ │   memcpy(d, s, len);   │ │   119 │ │   memcpy(d, s, len);                     │  scroll
│   [ … 6 LINES ]  [ OPEN FULL ]   │ │   [ … 4 LINES ]  [ OPEN FULL ]                     │  18
│   ─────────────────────────────  │ │   ─────────────────────────────                    │  17
│   [ MODEL SELF-REPORT ]          │ │   [ MODEL SELF-REPORT ]                            │  16
│   confidence 0.71 · not a verdict│ │   n/a · operator-supplied                          │  18
│ └────────────────────────────────┘ │ └────────────────────────────────┘                │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

**Widths.** 652 + 24 gutter + 652 = 1328. A 1px `--bd-rule` runs vertically down the centre of the
gutter, floor to ceiling of the column region — the one place in this system where a rule
separates columns rather than crop marks, because the whole point of the frame is that these two
things are being *set against* each other.

**Heights.** Header 81 (16 + 22 + 22 + 8 + 1px rule + 12). Columns 603. Column budget:

| Element | Type | Height |
|---|---|---:|
| `[ CANDIDATE 0N ]` | `mono-2xs` | 16 |
| `[ PROVENANCE · … ]` | `mono-md` **ROOM** | 22 |
| `[ POLICY · … ]` | `mono-sm` | 20 |
| gap 8 · rule 1 · gap 8 | | 17 |
| verdict word | `display-lg` **ROOM** | 68 |
| verdict underline | 2px, verdict colour, full 652 | 2 |
| `[ 3 OF 5 GATES RAN ]` | `mono-lg` **ROOM** | 26 |
| gap | | 8 |
| gate matrix, **five rows** | `mono-md` **ROOM**, 22 each | 110 |
| gap 8 · rule 1 · gap 8 | | 17 |
| `[ DIFF · file ]` + meta sub-line | `mono-2xs` + `mono-xs` | 34 |
| diff body, scroll region, 8 full rows visible | `mono-md` | 194 |
| overflow disclosure | `mono-xs` | 18 |
| gap 8 · rule 1 · gap 8 | | 17 |
| `[ MODEL SELF-REPORT ]` + line | `mono-2xs` + `mono-xs` | 34 |
| | | **603** |

Closes exactly. At `mono-md` the 652px column holds 72 characters, which is enough for
`[ — STATIC DELTA · NOT RUN · CUT FROM THE SEVEN-DAY BUILD (P1-2) ]` at 65 — so **the reason
string fits inline on the gate row at ROOM size**, which is what architecture spec §5.4 asks for
and what the previous chip-based layout could not deliver.

#### 6.4.2 Provenance — mandatory, on both columns

This is the review's C4, and it was the most serious omission: §6.4 declared provenance mandatory
and then the compare columns dropped it. The compare is the frame a judge photographs, and both
[D-008](../../.project/decisions.md) (the rejected candidate may be operator-supplied) and D-020
(replayed model responses) depend on the label travelling with the claim. A photograph of two
verdicts without provenance is a photograph that misattributes one of them.

- `[ PROVENANCE · … ]` renders in **every** column, at `mono-md` (ROOM tier), **above the verdict
  word** and directly under the candidate ID. Above, not below, because it must be inside any
  crop of the verdict.
- Values are exactly `MODEL-GENERATED` or `OPERATOR-SUPPLIED`. No third value, no default, no
  abbreviation, no icon substitution.
- A candidate with no provenance field renders `[ × PROVENANCE MISSING ]` in critical, **and that
  column's verdict word and diff body are suppressed** and replaced with "This candidate's
  provenance is not recorded. Its verdict is withheld." The other column is unaffected. A missing
  provenance field is an API bug and this is where it becomes visible on stage rather than in a
  log.
- **Columns are ordered by candidate index, never by verdict.** Candidate 01 is always left. The
  compare must not be arrangeable to flatter — putting `Verified` on the left every time would be
  a presentation choice masquerading as a data one.
- Provenance is `--bd-text` at rest and is **never** given a state colour. It is a fact about
  origin, not an outcome, and colouring `OPERATOR-SUPPLIED` amber would read as a defect.

#### 6.4.3 Gate matrix rows

Five rows, always, in fixed order: `COMPILE`, `REPRODUCER ELIMINATED`, `REGRESSION PRESERVED`,
`STATIC DELTA`, `RENEWED FUZZING`. Never sorted, never collapsed, never behind a control, never
reordered so the passes group at the top.

| Status | Row | Colour |
|---|---|---|
| Pass | `[ + REGRESSION PRESERVED · 42/42 · BASELINE 42/42 ]` | verified |
| Fail | `[ × REGRESSION PRESERVED · 40/42 · 2 FAILED ]` | critical |
| Not run | `[ — STATIC DELTA · NOT RUN · <reason> ]` | `--bd-state-not-run` |
| Error | `[ ! COMPILE · ERROR · <reason> ]` | warning |
| Running | `[ > COMPILE · RUNNING ]` | running |
| Queued | `[ · RENEWED FUZZING · QUEUED ]` | idle |

`<reason>` is `GateResult.detail` and is **rendered verbatim from the API, never composed in the
frontend** — architecture spec §5.4 [Δ #42] makes it a required field on any `NOT_RUN` or
`ERROR` result, so the UI never has to invent one. If it arrives empty the row renders
`[ — STATIC DELTA · NOT RUN · REASON NOT SUPPLIED ]` in critical, because an undisclosed reason
defeats the whole mechanism D-009 depends on.

#### 6.4.4 Diff body

Unified diff, Fragment Mono `mono-md` 15/22, inside a 194px scroll region. Four columns: old line
number (`mono-xs`, secondary), new line number, 2px gutter mark, content. Line numbers and mark
occupy 82px, leaving 546px ≈ **60 columns of code** per compare column.

| Line kind | Gutter | Text | Left rule |
|---|---|---|---|
| Added | `+` | `--bd-state-verified` | 2px `--bd-state-verified` |
| Removed | `−` | `--bd-text-secondary` | 2px `--bd-state-critical` |
| Context | ` ` | `--bd-text` | none |
| Collapsed | — | `[ … 34 LINES ]`, expandable in place | none |
| Over-long line | `↳` | as its kind | as its kind |

Removed lines are deliberately de-emphasised in secondary text rather than shouted in coral: the
addition is the story, red is reserved for failure, and a whole removed block in critical colour
would misrepresent a working patch as an alarm. The `+`/`−` gutter marks mean colour is never the
only channel.

**Over 60 columns:** the line soft-wraps **once**, with `↳` in the gutter of the continuation, to
120 columns. Beyond 120 it truncates with `[ +N CHARS ]` at `mono-xs` in secondary. It never
introduces a horizontal scrollbar inside the column — a horizontally scrolling diff inside a
side-by-side compare is unusable, and the escape hatch is `[ OPEN FULL DIFF ]`.

**`[ OPEN FULL DIFF ]`** swaps that one column to the overlay's full 1328px for that candidate
alone — 138 columns of code, 20 visible rows — with `[ ← BACK TO COMPARE ]` in the header. It is a
**mode of the same overlay, not a second overlay**, which is the specific mistake C3 identified.
Nothing in this system opens an overlay on top of an overlay.

#### 6.4.5 States

- **Empty:** `[ NO PATCH CANDIDATE ]`, "A diff appears when the patch stage produces a candidate."
- **Loading:** placeholder rules in the diff region; header, provenance, policy and verdict render
  as soon as their metadata lands. Space for all five gate rows is reserved from the start so the
  matrix does not push the diff down as gates resolve.
- **Verification in progress:** the verdict word reads `Running` in white, the denominator reads
  `[ — GATES · 1 OF 5 RESOLVED ]`, and unresolved rows read `[ · QUEUED ]`. **The verdict word is
  never optimistic** — nothing reads `Verified` until the record does.
- **Policy failure on a candidate:** that column's `[ POLICY · FAIL ]` in critical with the failing
  rule in full — "changed lines 61 exceeds cap 25". The verdict word reads `Not verified` in
  secondary with "no gate ran; the candidate was refused before verification", and the gate matrix
  renders all five rows as `NOT RUN` with `refused by patch policy` as the reason. The diff body
  still renders, greyed to secondary, so the operator can see what was refused.
- **Diff truncation** — folded into the policy-failure path, and reachable only there. The 25-line
  changed-line cap means a policy-*passing* diff cannot be large, so the previous standalone
  2 000-line truncation state was unreachable (C7). A refused candidate has no such cap: above
  **200 rendered lines** the body shows `[ ! TRUNCATED · 200 OF 4118 LINES ]` in warning pinned to
  the top of the region, with `[ DOWNLOAD FULL PATCH ]`.
- **Failed — render error:** `[ × RENDER FAILED · SHOWING RAW ]` in critical, then the raw patch
  text unstyled, in that column only. Never a blank column.
- **Degraded — one candidate only.** The default is two. If only one candidate exists, the left
  column renders as specified and **the right 652px becomes the evidence column**:
  `[ EVIDENCE · FINDING 01 ]`, the full sanitizer report at `mono-sm` (all frames, addresses
  included, 20+ rows fit), then the reproducer record — minimization, replay attempts, replay
  successes, artifact hashes. The header's compressed evidence line stays. There is never an
  empty column and the degraded frame carries *more* evidence than the default one, not less.
- **Degraded — three or more candidates:** the two most recent are shown; the header gains
  `[ 4 CANDIDATES · SHOWING 01, 02 ]` with `[ CANDIDATE ▸ ]` selectors on each column header. Not
  expected in P0 (P2-7 cut candidate ranking) but specified because the fan-out in architecture
  spec §2.3 makes it structurally possible.

#### 6.4.6 Model self-report

Bottom of each column, under its own 1px rule, in `--bd-model-selfreport` (deliberately the same
value as ordinary secondary text):

```
[ MODEL SELF-REPORT ]
confidence 0.71 · not a verdict · no gate reads this value
```

For an operator-supplied candidate it reads `n/a · operator-supplied`. It is separated from the
verdict by a rule and by the entire gate matrix, never coloured with a state colour, and it
carries its own disclaimer in the label. That is the visual half of the non-negotiable rule that a
patch is never accepted on model confidence — and it is structurally true as well as visually
true, because the verifier cannot see provenance or confidence by signature (architecture spec
§4.2.7).

### 6.5 Panel 5 — Verdict panel

Centre column, below the Core. **608 × 236.** This panel shows the **mission's** verdict —
`derive_mission_outcome` over the candidate set (architecture spec §2.3), so a run with one
verified and one rejected candidate reads `Verified` here. The per-candidate verdicts live side by
side in the compare overlay (§6.4).

```
[ VERDICT ]                                                                    16
Verified                                        ← Instrument Serif 72px        68
══════════════════════════════════════════════  ← 2px, verdict colour, 608w     2
[ 3 OF 5 GATES RAN ]                            ← mono-lg, ROOM                26
[ + COMPILE · clang 18.1.3, exit 0 ]                                           20
[ + REPRODUCER ELIMINATED · minimized input, 5/5 clean ]                       20
[ + REGRESSION PRESERVED · 42/42 · BASELINE 42/42 ]                            20
[ — STATIC DELTA · NOT RUN · NO STATIC ANALYZER IN THIS BUILD (P1-2) ]         20
[ — RENEWED FUZZ · NOT RUN · POST-PATCH FUZZING NOT BUILT (P1-3) ]             20
                                            + 4 gap + 8 gap + 12 gap =        236
```

The verdict word is the largest text in the product and the single thing a judge should read from
across the room. It is set in the display serif, underlined by a 2px rule in the verdict's state
colour running the full panel width.

**The denominator sits inside the underline, at ROOM size.** Architecture spec §5.4 requires the
verdict *string* to carry the denominator — "VERIFIED — 3 of 5 gates ran", not "VERIFIED" — so a
judge photographing one panel gets the caveat with the claim. Setting a 72px serif word and a
qualifier on one baseline is fragile at two type scales, so the qualifier is the line immediately
below the underline at `mono-lg` (ROOM), inside the same visual block. It cannot be cropped out of
a photograph of the verdict, which is the property the rule is actually protecting.

**The gate matrix is five rows, one gate per row, and is never collapsed.**
[D-009](../../.project/decisions.md) requires that a verdict enumerate the gates that actually ran
wherever it is displayed; architecture spec §5.4 adds that all five render at the same type size
and column position, with the `NOT_RUN` reason inline. Five rows at `mono-sm` in 608px gives 77
characters per row, which fits the longest reason string with room to spare — this is why the
previous two-row chip layout was replaced. A `Verified` that hides an unrun gate is a defect, and
this is the panel where it would be caught.

**States**

| State | Verdict word | Colour | Denominator | Matrix |
|---|---|---|---|---|
| Empty | `Pending` | secondary | `[ — GATES · NONE RAN ]` | All five rows `[ — <GATE> · NOT RUN · verification has not started ]` |
| Running | `Running` | white | `[ — GATES · 1 OF 5 RESOLVED ]` | Executing gate `[ > COMPILE · RUNNING ]`, remainder `[ · QUEUED ]` |
| Verified | `Verified` | verified | `[ 3 OF 5 GATES RAN ]` | Executed gates pass; unrun gates in `--bd-state-not-run` with reasons |
| Rejected | `Rejected` | critical | `[ 3 OF 5 GATES RAN ]` | The failing row is the **only** critical element, counts inline: `[ × REGRESSION PRESERVED · 40/42 · 2 FAILED ]` |
| Human review | `Held` | warning | `[ 3 OF 5 GATES RAN ]` | Executed gates as-is, plus the triggering policy rule named in full |
| Failed | `Failed` | critical | `[ 0 OF 5 GATES RAN ]` | All five `NOT RUN` with the failing stage as the reason |
| Degraded | verdict as computed | as computed | as computed | A warning line replaces the `[ VERDICT ]` label: `[ ! VERDICT MAY BE STALE · RELOAD ]`. The verdict itself is **not** greyed out — a stale verdict is still the last true verdict. |

**With two candidates** (demo steps 6 and 7) the panel's `[ VERDICT ]` label becomes
`[ VERDICT · 2 CANDIDATES ]` and gains `[ OPEN COMPARE ]` on the same line. The panel keeps
showing the mission outcome and the *winning* candidate's matrix; the side-by-side comparison is
§6.4. The label states which candidate the matrix belongs to —
`[ VERDICT · 2 CANDIDATES · MATRIX: CANDIDATE 01 ]` — because a matrix shown without naming its
candidate is exactly the ambiguity D-009 exists to prevent.

### 6.6 The resource ledger — teardown's surface on the success path

New in this revision. This is the primary fix for the review's C1: P0-14 is uncuttable, teardown
is a scored competition criterion and the subject of demo scenario 5, and the previous
specification gave it a surface only on the emergency path. A mission that completed correctly
had nowhere to say its sandbox and its model-host lease were released. The old `[ SANDBOX 1 ]`
chip also could not express a model-host lease at all — it counted sandboxes.

Bottom strip, left region, two lines. One chip per leased resource, plus a roll-up.

```
[ LOCAL · LOOPBACK ONLY ]  [ EGRESS DENIED ]  [ + ALL RESOURCES RELEASED · 2 OF 2 ]
[ EVENTS 1 284 ]  [ + SANDBOX 01 · RELEASED ]  [ + MODEL HOST · RELEASED ]
```

**The bottom strip's two regions have different vertical structures**, and this is a correction to
rev 1, which stacked controls on two 28px lines and quietly broke §2.7's 44px hit-target floor.

| Region | Structure |
|---|---|
| Left — status and ledger | Two `mono-2xs` text lines, 16px each, vertically centred in the 56px strip. Not interactive, so no hit-target floor applies. |
| Right — controls | **One 44px control row**, vertically centred, spanning the full height of both text lines. Labels at `mono-sm`; the hit area is 44px tall regardless. |

Widths at 1440, `mono-2xs` at 6.6px/char and `mono-md` at 9px/char: line 1 left measures 634px,
line 2 left 453px, and the control row 300–350px depending on state. Against 1328 there is over
300px of clear field between them, which is what stops the ledger and the controls colliding when
a chip lengthens (`RUNNING` → `RELEASE FAILED` is +7 characters).

**Resource chip states.** Every one of these follows a receipt, never an intention —
architecture spec §6.7: *"A mission is not reported as released in the UI until a
`TEARDOWN_CONFIRMED` event exists with `released=true`."*

| Condition | Chip | Colour |
|---|---|---|
| Not yet leased | `[ — SANDBOX · NOT LEASED ]` | secondary |
| Starting | `[ · SANDBOX 01 · STARTING ]` | idle |
| Held and running | `[ ● SANDBOX 01 · RUNNING ]` | running |
| Held, mission terminal, no receipt yet | `[ ● SANDBOX 01 · HELD ]` | warning |
| Receipt received | `[ + SANDBOX 01 · RELEASED ]` | verified |
| Release failed | `[ × SANDBOX 01 · RELEASE FAILED ]` | critical, with the error verbatim on the alert line |
| Model host, leased | `[ ● MODEL HOST · LEASED ]` | running |
| Model host, released | `[ + MODEL HOST · RELEASED ]` | verified |
| Model host never used | `[ — MODEL HOST · NEVER LEASED ]` | secondary |

**Roll-up chip**, `mono-md` (ROOM), so the release claim is readable from across the room during
scenario 5:

| Condition | Chip | Colour |
|---|---|---|
| Nothing leased yet | `[ RESOURCES · — ]` | secondary |
| Held during the run | `[ RESOURCES · 2 HELD ]` | running |
| Teardown in progress | `[ ● RELEASING · 1 OF 2 ]` | running |
| All receipts in | `[ + ALL RESOURCES RELEASED · 2 OF 2 ]` | verified |
| Partial | `[ ! RESOURCES · 1 OF 2 RELEASED ]` | warning |
| Any failure | `[ × RESOURCE RELEASE FAILED · 1 OF 2 ]` | critical |

**The roll-up never rounds up.** It reads `2 OF 2` only when two `TEARDOWN_CONFIRMED` events with
`released=true` exist. A missing receipt is a warning, not a rounding error, and "all released" is
never displayed as an absence of evidence — it is displayed as the presence of receipts. Both the
denominator and the numerator come from the event log.

**Its three surfaces cannot disagree.** The ledger, the timeline's `[ 10 ] TEARDOWN` rows (§6.2)
and the Core's release line (§6.1) all read the same `TEARDOWN_CONFIRMED` event set from the same
store. There is no second count anywhere.

**`[ LOCAL · LOOPBACK ONLY ]` replaces `[ SESSION SECURE ]`.** The finale runs on
`http://localhost` with the repository private (CEO, #92). A chip reading `SESSION SECURE` over
plain HTTP is a safety claim the transport does not support, and §2.6 does not carve out an
exception for claims that are merely flattering rather than numeric. `[ EGRESS DENIED ]` is
unchanged and is the claim that actually matters — it is testable
(`tests/security/test_egress.py`) and it is about the sandbox, not the browser.

---

## 7. The Brahmadatta Core — chakra geometry

Original SVG linework. No raster assets, no third-party paths, no figures. Radii below are the
**380px-diameter block** (DS-01). The `viewBox` stays at 440 and the SVG is scaled by 0.8636 in
layout, so the numbers in the path data are the round ones and only one figure changes if the
block is resized again.

| Element | Radius @380 | Radius @440 viewBox | Stroke | Behaviour |
|---|---:|---:|---|---|
| Ray corona | 174.5 → 190 | 202 → 220, 48 strokes at 7.5° | 1px | Rays inside a **completed** arc are `--bd-rule`; all others `--bd-rule-construction`. The corona grows with real completion only. |
| Chakra rim | 164 → 171 | 190 → 198 (an 8px band) | 1px both circles | Divided into six 60° arcs by six radial spokes. The band is where the phase state is drawn. |
| Kavacha plating | 112 → 154 | 130 → 178 | 1px | Twelve trapezoidal plates as hairline outlines, alternating orientation — armour lamellae. **Purely structural: never animated, never state-carrying**, so it cannot be mistaken for data. |
| Yantra construction | ≤ 104 | ≤ 120 | 1px `--bd-rule-construction` | Two interpenetrating equilateral triangles inscribed in the circle, plus the resulting six-point star polygon. Static. |
| Centre disc | ≤ 74 | ≤ 86 | none | Clear field. Holds the state word, which at `display-md` may overrun onto the yantra but never onto the plating (§6.1). **Nothing figural ever appears here.** |

The ASCII ramp's glyph pitch scales with the block: 4px at 440 becomes 3.45px at 380. Round to
**3.5px** and accept the 1.4% drift over a 60° arc — a fractional pitch causes visible glyph
jitter on the `textPath`, which would read as motion that means nothing.

### 7.1 The six phases

Clockwise from 12 o'clock, one 60° arc each:

`INGEST → ANALYZE → STRESS TEST → CORRELATE → REMEDIATE → VERIFY`

### 7.1a Phase order — RESOLVED by D-038

`STRESS TEST` occupies arc 3 and `CORRELATE` arc 4. The CTO ruled on 2026-08-07; this seat
had left it deliberately unchosen because two authoritative sources disagreed, and the arcs
are fixed 60° geometry.

The argument that settled it is worth keeping here, because it is not the obvious one. Under
the P0 cut, Semgrep (#22) and compiler-warning capture (#23) are both cut — so `ANALYZE`
produces **nothing**. Ordering `CORRELATE` before `STRESS TEST` would light an arc and advance
it for a stage running with zero inputs. That is decorative telemetry, which this product bans
outright. The old ordering was not merely less tidy; under the cut it was a fake progress
indicator.

`CLAUDE.md`'s workflow sentence is stale and is amended by the CEO rather than superseded
silently. The 79-document pack keeps its boilerplate footer; an erratum line in
`docs/README.md` is folded into #9.

**Condition attached to the ruling: the phase order is served, not hardcoded.** A
`PHASE_ORDER` array of string literals here puts the ordering in two places — `contracts/enums.py`
and the Core — and a future reorder changes one silently. The nine `MissionStage` members
project onto six arcs, and it is that *mapping* that must come from the contract, the same way
`POSTURE_BY_STATE` already exists so the UI never invents its own. Derive it from the generated
types so #6's CI diff catches divergence at build time.

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
that; it is a stage row in the timeline and a centre-word state. The same is true of export and
teardown, which are timeline rows 09 and 10 (§6.2). If the API later needs a seventh phase, the
wheel does not gain a spoke — the timeline gains a row. **Six is a design constant.**

**This mapping is unaffected by §7.1a.** It maps mission state → arc *by name*, so it stays
correct whichever way the CTO rules on the positions of CORRELATE and STRESS TEST. Only the arc
*positions* and the timeline row *indices* move.

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
  label. The timeline is an ordered list.
- **Live regions — narrowed to exactly one, in response to C7.** The review's objection is fair:
  a live-region programme is a slice of P1-10/P2-11, both cut. Two of the three are dropped and
  one is kept.

  | Region | Previously | Now | Why |
  |---|---|---|---|
  | Stage timeline | `aria-live="polite"` | **removed** | The timeline appends up to one event per 5 s for forty minutes. A live region over that stream narrates a fuzz campaign aloud. Removing it is right on its own merits, cut or no cut. |
  | Verdict change | `role="alert"` | **removed** | The verdict is a focus target reachable by tab and it is the largest text on screen. It does not need to interrupt. |
  | Bottom-strip alert line | `role="alert"` | **kept** | One attribute on one element. P2-11 is "full WCAG conformance pass" — an audit programme with a cost — not a prohibition on writing a correct attribute. The alert line is the only surface that carries a critical failure with no other channel, and the `ui-ux-pro-max` guideline set ranks announced error messages High under its top-priority Accessibility category. Removing it would mean a sandbox release failure is silent to anyone not watching the bottom-left corner. |

  This is a net reduction of two of three, and what remains is one attribute rather than a
  programme. If the PM still wants it gone, it is one line and this table records what is lost.
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
| Screens 1, 3, 5, 6 (Mission Setup, Finding Detail, Evidence Report, System/GPU Health) | `31-dashboard-screen-specification.md` | P0-13 specifies five panels on one screen. Setup collapses into the authorize dialog; **finding detail into the finding row plus the evidence block (§6.3a)** — rev 1 claimed it collapsed into "the finding row plus the diff overlay", which the review correctly found to be untrue, and §6.3a is the correction; the evidence report is an exported file, not a screen; GPU health has no GPU |
| Presentation mode | `10-wireframes.md` §5 | In `CUT`. Consequence recorded in §2.6: there is now no sanctioned place for mock data at all |
| Collapse-to-drawers below 1280px | `00-ui-design-direction.md` | Desktop-first at 1440×900+; the finale runs on a known machine |
| Sound design | `34-ui-state-and-motion-specification.md` | Off by default in the pack already; not built |
| Glass panels, luminous borders, restrained glow | `00-ui-design-direction.md` | Superseded by D-017. This is the largest single departure in this document |

### Also cut in rev 2, from this document's own first revision

Recorded here rather than deleted silently, so each is recoverable if its producer appears.

| Entry | Was in | Cut because | Recoverable if |
|---|---|---|---|
| Unconfirmed-finding state — `[ ! UNCONFIRMED ]`, `[ FINDINGS · 1 · +2 UNCONFIRMED ]` | §6.3 | No producer. Findings originate only from sanitizer-confirmed crashes; TRIAGE runs empty by construction (architecture spec §2.5) | A stage ever emits an observation without a sanitizer artifact |
| Timeline 200-row virtualization — `[ … 148 EARLIER EVENTS ]` as a virtualised window | §6.2 | Moot: #31 is cut, stage rows are a fixed ten. Replaced by a 50-row event window with an explicit count, which is not virtualization | Event volume per stage exceeds what a 50-row window plus a count can honestly represent |
| Standalone diff truncation state — `[ ! TRUNCATED · 2000 OF 4118 LINES ]` at 2 000 lines | §6.4 | Unreachable: the 25-line changed-line cap means a policy-passing diff cannot approach it | — folded into the policy-failure path at 200 lines, where a refused oversized candidate makes it genuinely reachable |
| `aria-live="polite"` on the stage timeline; `role="alert"` on verdict change | §9 | Re-inserted a slice of cut P1-10/P2-11, and the timeline one would narrate a forty-minute fuzz campaign aloud | P1-10 or P2-11 leaves `CUT` |
| `[ SESSION SECURE ]` chip | §3, bottom strip | The finale runs on `http://localhost` (#92). A secure-session claim the transport does not support is a fabricated safety claim | The finale ever runs over TLS |
| `[ EMPTY BELOW ]` filler in the findings rail | §6.3 | The space it occupied is now the evidence block (§6.3a). Composition replaced by content | — |
| 72px verdict word inside the Core | §6.1 | Could not be built — the word overran the disc at 440px — and duplicated the verdict panel's hero readout | — |

### What replaces them — the P0 component inventory

| Component | Panels | New in rev 2 |
|---|---|---|
| `FrameAndTicks` | Every panel — the page frame and crop-mark primitive | |
| `BracketLabel` | Every panel | |
| `StateChip` | Every panel | |
| `PanelHeader` | Every panel | |
| `EmptyState`, `PlaceholderRules` | Every panel | |
| `BrahmadattaCore`, `PhaseArc` | 1 | |
| `StageTimeline`, `StageRow`, `EventRow` | 2 | |
| `FindingsList`, `FindingRow` | 3 | |
| `EvidenceBlock`, `StackFrameRow`, `ReproducerRecord` | 3, 4 | **yes** — C2 |
| `CandidateCompare`, `CandidateColumn` | 4 | **yes** — C3 |
| `DiffView`, `DiffLine`, `ProvenanceChip`, `ModelSelfReport` | 4 | |
| `VerdictReadout`, `GateMatrix`, `GateRow` | 4, 5 | `GateChip` → `GateRow`; the matrix is rows, not chips (§6.5) |
| `ResourceLedger`, `ResourceChip` | Bottom strip | **yes** — C1 |
| `MissionClock`, `StreamLiveness` | Top strip | |
| `CommandStrip`, `ConfirmDialog` | Bottom strip | |

**Twenty-nine components**, of which seven are primitives shared by everything. Seven were added
to clear the review's three blocking conditions: three for the step-4 evidence surface, two for
the compare, two for the resource ledger. That is the entire frontend surface for the seven-day
build.

`ProvenanceChip` is used **twice per compare frame** — once per candidate column — and is the
component with the strictest contract in the set: it has no default value, no empty state, and
no rendering path that omits it. See §6.4.2.

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

Four added in rev 2:

7. **Measure the font before you build a column.** Every width figure in §3, §6.4 and §6.5 assumes
   a 0.6em advance. Render a 60-character ruler string in the shipped Fragment Mono woff2 and
   measure it. Thirty seconds now; a wrapping compare on stage otherwise. (§2.2, DS-06)
8. **Drive the Core's six arcs from one `PHASE_ORDER` array.** The position of CORRELATE and
   STRESS TEST is with the CTO and is not settled (§7.1a). Six fixed 60° arcs read from one array
   makes the eventual ruling a one-line edit. Hardcoding the sequence into six path definitions
   makes it a day.
9. **One teardown count, three renderings.** The ledger, the timeline rows and the Core's release
   line all derive from the same `TEARDOWN_CONFIRMED` event set. Do not let any of them keep its
   own counter — three counters is how "all released" and "1 of 2 released" end up on screen at
   the same time, in the frame that is being scored. (§6.6)
10. **Reserve the gate matrix's five rows from first paint.** All five render from the empty state
    onward, as `NOT RUN` with reasons. If rows are appended as gates resolve, the diff below them
    walks up the column while a judge is reading it, and the panel briefly shows a matrix that is
    shorter than five — which is the exact appearance D-009 forbids. (§6.4.5)

---

## 13. Open questions

Owners named. Answered ones are struck through with the answer, kept for the record.

| # | Question | Owner | Status |
|---|---|---|---|
| 1 | Does the event payload carry a **fractional progress value** per phase, or only discrete transitions? The Core's running arc needs a real fraction; without one it renders as a filled-to-nothing `:` band, which is honest but much less legible. | backend-developer / software-architect (issue #6) | **Open.** Architecture spec §3.2 says `percent_complete` is nullable and stays null for fuzzing, which answers it for one phase and not the others. |
| 2 | Is `provenance` a required non-nullable field on the patch-candidate record? §6.4.2 suppresses the column without it. | backend-developer | **Open, and now blocking a judge-facing frame.** Provenance appears twice in the compare (C4). If it can be null, §6.4.2's suppression path will fire on stage. |
| 3 | Are the two unrun gates present in the API's gate-matrix payload as explicit `not_run` entries, or absent? | backend-developer | **Answered by architecture spec §5.4:** `GateMatrix` has fixed arity, five named fields, defaulting to `NOT_RUN`. The frontend does not hardcode the list. |
| 3a | **New.** `GateResult.detail` is required on `NOT_RUN` per §5.4 [Δ #42] — what exact strings will it carry for `STATIC_DELTA` and `RENEWED_FUZZING`? The UI renders it verbatim (§6.4.3) and will not compose one. | backend-developer | **Open.** Suggested: `no static analyzer configured in this build (P1-2)` and `post-patch fuzzing not built (P1-3)`. The backend owns the wording; C8 is about not overstating it. |
| 4 | Confirmed finale display resolution and whether the demo runs on a projector. The **ROOM** tier is sized for ~4 m on a 1440 display. | CEO / competition-strategist | **Open.** Now costlier: the compare (§6.4) and the resource ledger (§6.6) both put ROOM-tier text in fixed-width columns that were sized against 1440. |
| 5 | ~~Is a second patch candidate guaranteed at demo time?~~ | product-manager | **Answered: guaranteed.** PR #74 merged with both candidates committed as files, so candidate B produces a real gate matrix every run. §6.4 is built compare-first with single-column as the degraded state. |
| 6 | **New.** What is the measured advance width of the shipped Fragment Mono woff2? Every column budget in §3, §6.4 and §6.5 assumes 0.6em. | frontend-developer | **Open, cheap, and first.** Thirty seconds with a ruler string. See §2.2. |
| 7 | **New.** Does a `TEARDOWN_CONFIRMED` event distinguish a sandbox from a model-host lease, and does it carry a receipt identifier? §6.6 renders one chip per resource kind and shows the receipt in the timeline event row. | backend-developer | **Open.** If the event carries only a count, the ledger degrades to one chip and loses the model-host lease — which is the specific gap C1 identified. |
| 8 | ~~CORRELATE vs STRESS TEST order~~ — **RESOLVED by D-038**: STRESS TEST is arc 3, CORRELATE arc 4. Under the P0 cut ANALYZE produces nothing, so the old order would have advanced an arc for a stage with zero inputs. | CTO | Closed 2026-08-07. |

---

## 14. Amendment record — rev 2, clearing the product review

The `product-manager` seat returned APPROVE WITH CONDITIONS on eight conditions, three blocking.
Disposition of each, with where the change landed.

| # | Condition | Disposition | Where |
|---|---|---|---|
| **C1** | **Blocking.** Teardown has no surface on the successful path; the chip cannot express a model-host lease. | **Cleared.** Three surfaces, all on the success path, all reading the same `TEARDOWN_CONFIRMED` events: a resource ledger with one chip per resource kind, timeline rows `[ 09 ]`/`[ 10 ]` with per-resource receipt event rows, and a release line on the Core's terminal state. The roll-up never rounds up. | §6.6, §6.2, §6.1, §4.1 step 12, DS-04 |
| **C2** | **Blocking.** Step 4's ASan trace and 5/5 replay record land nowhere. | **Cleared.** An always-expanded evidence block in the findings rail, occupying the space rev 1 spent on `[ EMPTY BELOW ]` filler, plus a compressed evidence line in the compare overlay header so the photographed frame is self-contained, plus the full report in the compare's degraded-state evidence column. | §6.3a, §6.4.1, §4.1 step 7, DS-05 |
| **C3** | Compare contradiction: the overlay covered the panel doing the comparing; the arithmetic did not carry. | **Cleared, PM's fix taken.** The comparison moved into the overlay at 2 × 652. `[ OPEN FULL DIFF ]` is a *mode of the same overlay*, never a second overlay. Full column budget published and it closes at 603 exactly. | §6.4, DS-02 |
| **C4** | **Blocking.** The compare drops the provenance chip. | **Cleared.** `[ PROVENANCE · … ]` on both columns, `mono-md` ROOM, **above** the verdict word so it cannot be cropped out. No default, no third value; a missing field suppresses that column's verdict and diff. Columns ordered by index, never by verdict. | §6.4.2 |
| **C5** | Spoke order contradicts architecture spec §2.2. | **Deliberately not resolved.** Order left exactly as it was; a marked block records which way each source points, the cost of a late fix, and the instruction to build the arcs from a single `PHASE_ORDER` array until the CTO rules. | §7.1a, §13 row 8 |
| **C6** | `NOT_RUN` amber in the spec, neutral in the tokens. | **Cleared, architecture spec wins.** New semantic token `--bd-state-not-run` over the existing amber primitive — no ninth colour. The em dash glyph is retained, so the channel is still glyph + word + colour. The rule splits cleanly: an unproduced *value* stays secondary (D-023 intact); an unrun *gate in a verdict matrix* is amber with a mandatory inline reason (D-009, §5.4). | §2.1, §5, §6.4.3, `tokens.css`, DS-03 |
| **C7** | Four de-scoped items. | **Three removed, one narrowed and kept.** Unconfirmed finding: removed, no producer. 200-row virtualization: removed, replaced by a 50-row event window with an explicit count. Diff truncation: standalone state removed, folded into the policy-failure path at 200 lines where it is genuinely reachable. Live regions: two of three removed; one `role="alert"` kept on the alert line, with the trade stated. | §6.3, §6.2, §6.4.5, §9, §11 |
| **C8** | `semgrep — not run` overstates. | **Cleared.** The ANALYZE row now renders the backend's own `LOG` string, `no static analyzer configured in this build`, and the chip reads `[ + COMPLETE · NO ANALYZER ]`, never `0 FINDINGS`. Gate reason strings come from `GateResult.detail` verbatim. | §6.2, §4.1 step 5, §13 row 3a |

**Three defects this seat found while clearing the above**, none raised in the review:

1. **The Core's 72px centre word could not be built.** `Cancelled` at 72px measures ~272px against
   a 172px clear disc at the 440 block. Fixed by shrinking the wheel to 380 and the centre word to
   48px, which also removes a duplicate hero readout and makes the centre column close at exactly
   684. (§3, §6.1, §7, DS-01)
2. **`[ SESSION SECURE ]` was a false claim.** The finale runs on `http://localhost` (#92).
   Replaced with `[ LOCAL · LOOPBACK ONLY ]`. (§6.6)
3. **The bottom strip broke its own 44px hit-target floor.** Rev 1 stacked controls on two 28px
   lines inside a 56px strip, which §2.7 forbids in the same document. Controls are now one 44px
   row spanning both text lines. (§6.6)

---

## 15. Decision records for rev 2

Kept **in this document** rather than in `.project/decisions.md`, at the orchestrator's direction
— several seats are contending over that file. Numbered `DS-nn` so they cannot collide with the
`D-0nn` series. If the CTO or PM wants them merged into the central log later, they are portable
as written.

### DS-01 · The Core is 380px and its centre word is 48px

**Decision** — The Brahmadatta Core's block shrinks from 440 to 380px diameter, its label space
from 60 to 44px, and the centre state word from `display-lg` 72px to `display-md` 48px. The
verdict panel grows from 124 to 236px. The centre column then closes at exactly 684.

**Options considered** — (a) keep 440/72 and let the centre word overrun the plating; (b) keep 440
and drop the centre word to 48; (c) 380 block with a 48px centre word and the reclaimed height
given to the verdict panel; (d) drop the centre word from the Core entirely and let the phase
label carry the state.

**Pros and cons** — (a) is unbuildable as specified: `Cancelled` at 72px is ~272px against a 172px
disc, and letting a display word cross the kavacha plating destroys the one element in the Core
that is purely structural, which is what stops the plating being read as data. (b) is buildable
but wastes the fix — the verdict panel still cannot hold five gate rows in 124px, so §5.4 of the
architecture spec stays violated. (c) fixes both in one move: the word fits, the plating stays
clean, the verdict panel gets the 236px it needs for a five-row matrix with reasons inline, and
the product ends up with a **single** 72px hero readout instead of two competing ones 200px apart.
(d) is the most disciplined but loses the thing that makes the Core read as an instrument rather
than a diagram — the word in the middle is what a judge looks at first.

**Cost implications** — none. The SVG `viewBox` stays 440 and is scaled in layout, so no path data
changes. The verdict panel's five-row matrix is a simpler component than the wrapping chip layout
it replaces.

**Security implications** — none.

**Scalability implications** — mildly positive. A smaller SVG at the same stroke weight is fewer
pixels to repaint under a live event feed.

**Recommendation** — (c), as implemented. Reversible: the block size is one token.

**Final approval authority** — CTO for the buildability finding; CEO under D-017/D-018 if the
smaller wheel is judged to weaken the visual direction. Flagging it that way rather than assuming.

### DS-02 · The two-candidate comparison lives in the overlay, at 2 × 652

**Decision** — The side-by-side comparison moves out of the centre-column verdict panel and into
the overlay, which is renamed the Candidate Compare overlay. Two 652px columns with a 24px gutter
and a centred hairline rule = 1328. Each column carries that candidate's provenance, policy,
verdict, full five-row gate matrix, diff and model self-report. Two candidates is the default;
single-column is a degraded state. `[ OPEN FULL DIFF ]` is a *mode* of the same overlay.

**Options considered** — (a) rev 1's layout — compare in the 608px verdict panel at 2 × 292, diff
in a separate overlay; (b) the PM's proposed fix, compare rendered at overlay width 2 × 652;
(c) a dedicated compare *screen*; (d) compare in the panel, but at `display-md` 48px so the words
fit in 292px.

**Pros and cons** — (a) is self-contradicting and that is why it was flagged: `[ OPEN DIFF ]`
opened an overlay directly over the panel doing the comparing, so the operator could see the diffs
or the verdicts but never both, and the arithmetic failed anyway — `Verified` at 72px is ~242px in
a 292px column with no room for chips beside it, and five gate rows do not fit in 124px.
(b) resolves the contradiction at its root by putting the comparison where the width already is,
and it turns out to close exactly: 652 holds 72 characters at `mono-md`, which is enough for the
longest `NOT_RUN` reason string inline at ROOM size — something no other option achieves.
(c) is a sixth screen against a P0 that names five panels, and it would need its own routing,
empty states and reconnect handling. (d) keeps the panel but halves the verdict word, which
demotes the single most photographed element in the demo to save a layout that is wrong anyway.

**Cost implications** — lower than rev 1. One overlay component in two modes replaces an overlay
plus a splitting verdict panel. The verdict panel becomes simpler, not more complex.

**Security implications** — none directly, but positive for integrity: provenance, policy status,
gate matrix and model self-report now appear in the same frame as the verdict they qualify, so a
photograph of the claim contains its caveats. That is the same principle as D-008 and D-009.

**Scalability implications** — the fan-out in architecture spec §2.3 permits N candidates. Two
columns is a display choice, and §6.4.5 specifies the N>2 behaviour rather than leaving it to be
invented.

**Recommendation** — (b), as implemented, which is the PM's own proposed fix taken as offered.

**Final approval authority** — PM, since it changes user-facing screen structure; CTO if the
frontend disputes the column arithmetic.

### DS-03 · An unrun gate is amber; an unproduced value stays secondary

**Decision** — `--bd-state-not-run` is added as a semantic token aliasing `--bd-c-warning`, and is
used **only** for verification gates in a verdict matrix, always with the em dash glyph, the word
`NOT RUN`, and a mandatory inline reason. Unproduced *values* elsewhere in the product remain an
em dash in `--bd-text-secondary`.

**Options considered** — (a) keep rev 1's rule — `NOT_RUN` always secondary — and ask the
architect to change §5.4; (b) adopt §5.4's amber everywhere an em dash appears; (c) split the
rule by context, amber for gates only; (d) invent a fourth state colour for "not run".

**Pros and cons** — (a) preserves D-023's clean single rule, but it loses the argument on the
merits: D-009's entire protection is that an unrun gate is as visible as a failed one, and
secondary grey is this system's colour of *de-emphasis*. Rendering an undisclosed gate in the same
value as a sub-line is the opposite of what D-009 asks for. (b) is consistent but wrong at the
other end — `[ FINDINGS · — ]` before analysis has run would go amber, which reads as a warning
about a mission that is proceeding normally, and the product would be amber for most of the demo.
(c) costs one sentence of rule and is checkable in review with a single question — *"is this in a
gate matrix?"* — while keeping the em dash as a non-colour channel in both cases, so nothing
regresses on the colour-is-never-the-only-channel rule. (d) breaks the eight-colour ceiling for a
distinction two existing colours already carry.

**Cost implications** — one token line. No component change beyond the gate row.

**Security implications** — this is an integrity control of the same family as D-009. A verdict
matrix that renders an unrun gate quietly is the failure mode D-009 was written to prevent, and
the `cybersecurity` seat should treat a secondary-coloured `NOT_RUN` gate as a finding when it
reviews judge-facing output.

**Scalability implications** — none.

**Recommendation** — (c), as implemented. The architecture spec wins the conflict on the merits,
and D-023 survives intact for the case it was actually written about.

**Final approval authority** — CTO, since it reconciles this document to the architecture spec;
CEO only if D-023's wording needs amending in the central log, which it does not — the split is
narrower than D-023's scope.

### DS-04 · Teardown is a stage, a ledger and a receipt, not a chip

**Decision** — Teardown gets three surfaces on the success path: timeline row `[ 10 ] TEARDOWN`
with one auto-expanded event row per released resource carrying its receipt; a bottom-strip
resource ledger with one chip per resource *kind* plus a roll-up; and a release line on the Core's
terminal label. All three read the same `TEARDOWN_CONFIRMED` events. The roll-up displays
`N OF N` only when N receipts exist.

**Options considered** — (a) rev 1 — one `[ + ALL SANDBOXES RELEASED ]` chip on the emergency path
only; (b) a dedicated teardown panel; (c) the timeline row alone; (d) the ledger alone; (e) all
three, from one event source.

**Pros and cons** — (a) is the state the review rejected, and correctly: a correct mission had no
release surface at all, and a chip that counts sandboxes cannot express a model-host lease.
(b) needs body height the centre column does not have — it closes at exactly 684 — and would make
teardown a *panel* competing with the five P0 panels for a judge's attention. (c) is honest and
free but scrolls; the release claim is a scored criterion and demo scenario 5's whole subject, and
burying it in a scrolling rail during the frame where it is being judged is a scoring mistake.
(d) is visible but has no room for the receipts. (e) costs one small component and one label line;
each surface is doing a different job — narrative, at-a-glance, and terminal confirmation — and
the single event source is what stops them disagreeing, which is the real risk of showing a fact
three times.

**Cost implications** — one `ResourceLedger` component and one label line on an existing panel.
No new panel, no layout change.

**Security implications** — positive and material. P0-14 is a hard safety constraint. Displaying
"released" from an *intention* rather than a *receipt* would be a fabricated safety claim, and the
"never rounds up" rule is what prevents it. This mirrors architecture spec §6.7 exactly.

**Scalability implications** — the ledger is per resource *kind*, not per instance, so a run with
four sandboxes shows `[ + SANDBOXES · 4 OF 4 RELEASED ]` rather than four chips. Specified.

**Recommendation** — (e), as implemented.

**Final approval authority** — PM for the surface count (user-facing scope); `cybersecurity` seat
should review the "receipt not intention" rule as part of any PR touching the ledger, since it is
a safety claim.

### DS-05 · Step 4's evidence goes in the findings rail, not a restored detail screen

**Decision** — The sanitizer stack trace and the reproducer replay record render in an
always-expanded evidence block beneath the selected finding, in the right rail. A compressed
three-fact line repeats in the compare overlay's header. The full raw report renders in the
compare's degraded single-candidate evidence column. The cut Finding Detail screen stays cut.

**Options considered** — (a) restore Screen 3, Finding Detail, from
`31-dashboard-screen-specification.md`; (b) reinstate the cut `EvidenceDrawer`; (c) an expanded
block in the findings rail; (d) a left evidence column inside the compare overlay.

**Pros and cons** — (a) reverses a P0-13 scoping decision to fix a content gap, which is a large
answer to a small question, and it costs routing plus its own empty and error states. (b) was cut
for a stated reason — a drawer *and* an overlay is two disclosure mechanisms for one job — and
reinstating it would contradict this document's own §11 rather than extend it. (c) uses space that
rev 1 was already spending on an `[ EMPTY BELOW ]` label and a sentence about there being nothing
there; roughly 600px of rail was buying composition, and it now buys the evidence the verdict
rests on. It is also always visible, with no click between a judge's question and its answer.
(d) would work but costs 100px of every compare column, which the budget in §6.4.1 does not have —
and the evidence is identical for both candidates, so per-column is the wrong place for it.

**Cost implications** — three small components, no new screen, no routing.

**Security implications** — positive. This is the evidence that makes `[ ● CONFIRMED ]` a checkable
claim rather than an assertion. The `[ FRAMES 3 OF 11 ]` disclosure is the same integrity family
as D-009: never silently truncate a stack trace.

**Scalability implications** — one evidence block renders at a time, following selection. Frame
count is bounded by the disclosure line, not by the rail.

**Recommendation** — (c), as implemented, with (d)'s space used only in the degraded single-
candidate state where it is free.

**Final approval authority** — PM, since it adds user-facing content to a scoped panel set.

### DS-06 · Width arithmetic is derived from a 0.6em advance and must be measured before build

**Decision** — Every column-count figure in this document assumes a 0.6em monospace advance. This
supersedes D-020's 0.52em figure. Measuring the shipped woff2 against a 60-character ruler string
is the first build task on any panel that does width arithmetic.

**Options considered** — (a) keep D-020's 0.52em and inherit its 80-column promise; (b) assume
0.6em and publish the check; (c) specify in `ch` units and let the browser resolve it.

**Pros and cons** — (a) is optimistic in the direction that fails on stage — if the real advance
is wider than assumed, the compare wraps during the demo. (b) assumes the common case and makes
the assumption falsifiable in thirty seconds, before anything is built on top of it. (c) is
elegant and would eliminate the problem, but the layout is a fixed pixel grid at 1440 with panels
sized in px and a 4px spacing scale, so mixing `ch` into the column budget reintroduces exactly
the uncertainty this decision removes.

**Cost implications** — thirty seconds, once.

**Security implications** — none.

**Scalability implications** — none.

**Recommendation** — (b). If the measured advance differs by more than 3%, §3, §6.4 and §6.5 are
re-derived before build, not after.

**Final approval authority** — frontend-developer, on measurement. This is a correction to prior
work by this seat, recorded rather than silently applied.

---

*Decision records for the non-trivial calls in rev 1: D-019 … D-023 in
[`.project/decisions.md`](../../.project/decisions.md). Records for rev 2 are DS-01 … DS-06 in
§15 of this document, held here at the orchestrator's direction while several seats contend over
the central log. The direction all of them implement is D-017 and D-018, both CEO-decided.*
