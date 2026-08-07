# Decision Log — Brahmadatta AI

Append-only. Never edit history; append a correction instead.

---

## D-001 · Repository is private · 2026-08-06 · Orchestrator

**Decision** — `Mahatav/brahmadatta-ai` created private.

**Options considered** — public (visibility, judges could browse) vs private (default-safe).

**Pros and cons** — Public would show the work and cost nothing to change later. Private avoids
publishing competition strategy, an unreviewed threat model, and demo target details before the
CEO has chosen to. Flipping private→public later is one command; the reverse does not un-index.

**Cost implications** — none.

**Security implications** — favors private. The repo will accumulate security-testing
methodology and, eventually, evidence artifacts.

**Scalability implications** — none.

**Recommendation** — private now; the CEO can open it at any point.

**Final approval authority** — CEO. Proceeding under the safe default until told otherwise.

---

## D-002 · `main` is protected · 2026-08-06 · Orchestrator

**Decision** — Branch protection on `main`: PRs required, force-push and deletion blocked,
required approving reviews set to 0, `enforce_admins` off.

**Options considered** — no protection (fast, matches a solo repo) vs protection as the git
workflow doc specifies.

**Pros and cons** — `docs/04-development/36-git-workflow.md` says no direct pushes to `main`,
so protection makes the documented rule real rather than aspirational. Review count is 0 because
the reviewers here are agent seats, not GitHub accounts — the actual review chain is enforced by
`.claude/COMPANY.md` and recorded on the PR, not by GitHub. `enforce_admins` is off so a broken
protection rule can never strand the repo during the 36-hour finale.

**Cost implications** — none.

**Security implications** — mildly positive; history cannot be rewritten.

**Scalability implications** — none.

**Recommendation** — as implemented.

**Final approval authority** — CTO (technical).

---

## D-003 · Company headcount is dynamic · 2026-08-06 · Orchestrator

**Decision** — Every seat except CEO and orchestrator starts on the bench. Roles are hired when
a phase needs them and retired when its gate passes, logged in `.claude/COMPANY.md` §4.
Concurrency capped at three active implementers.

**Options considered** — a fixed standing roster invoked every phase, vs on-demand hiring.

**Pros and cons** — A standing roster is simpler to reason about but costs a full agent
invocation per role per phase and blurs artifact ownership when two roles touch the same file.
On-demand hiring costs a routing decision each phase, in exchange for far fewer invocations.
The cap on concurrency comes from prior experience on another repo where a full company pass
died mid-implementation on a session limit.

**Cost implications** — materially lower. This is the main reason for the decision.

**Security implications** — neutral. The `cybersecurity` veto is unaffected; it is hired
whenever a gate requires it.

**Scalability implications** — positive; the roster grows by adding bench definitions.

**Recommendation** — as implemented.

**Final approval authority** — CEO (this is how he asked for the company to run).

---

## D-004 · Four Brahmadatta-specific seats added · 2026-08-06 · Orchestrator

**Decision** — Defined `security-research-engineer`, `compiler-toolchain-engineer`,
`ml-infra-engineer`, and `competition-strategist` in `.claude/agents/`, on the bench.

**Options considered** — stretch the general roster (`backend-developer` writes the fuzzing
worker, `ai-ml-engineer` covers GPU serving, `product-manager` covers submission materials) vs
define specialist seats.

**Pros and cons** — The general roster has no seat that owns a reproducer bar, a sanitizer
build matrix, a `git bisect run` contract, a self-hosted serving stack, or a judging rubric.
Handing those to a generalist means the hard constraints — no external inference API, no
confidence-gated verdicts, no unbenchmarked number quoted as measured — live only in review
comments rather than in the role's own hard rules. Cost is four more files to maintain.

**Cost implications** — none directly; these seats replace general-seat invocations rather than
adding to them.

**Security implications** — positive. `security-research-engineer` builds the product's
analysis capability and is explicitly separated from `cybersecurity`, which reviews *our* code —
so neither reviews its own work.

**Scalability implications** — neutral.

**Recommendation** — as implemented.

**Final approval authority** — CTO (technical).

---

## D-005 · Intake pre-filled from the doc pack · 2026-08-06 · Orchestrator

**Decision** — `.project/intake.md` was written from `docs/` rather than by interviewing the CEO,
with four genuinely-unanswered items marked DEFERRED and assumptions stated.

**Options considered** — run the standard intake questionnaire vs derive from the pack.

**Pros and cons** — The pack is the CEO's own specification and already answers idea, users,
problem, features, stack, scope, constraints, and schedule shape. Re-asking would be noise
against a standing instruction to interrupt only for decisions that genuinely need him. Risk is
that a derived answer misreads the pack; mitigated by citing the source document for every
answer so any role can check.

**Cost implications** — none.

**Security implications** — none.

**Scalability implications** — none.

**Recommendation** — as implemented. The four deferred items are batched for the CEO rather than
asked one at a time.

**Final approval authority** — CEO.

---

## D-006 · Scope is governed by a three-tier P0/P1/P2 cut · 2026-08-06 · `ceo` seat (draft)

**Decision** — Every in-scope item in `docs/01-product/03-mvp-scope-document.md` is ranked into
P0 / P1 / P2 in `docs/09-company/01-vision-and-p0-cut.md` §2. P2 is a pre-agreed cut list, not a
"won't build" list. The MVP scope document itself is left unedited.

**Options considered** — (a) leave all in-scope items equally mandatory as the pack has them;
(b) rank into three tiers now; (c) rank reactively, week by week, as slips occur.

**Pros and cons** — (a) is the status quo and requires no work, but means the first schedule slip
triggers an argument about priority at exactly the moment there is no time for one; it is how
8-week plans become 12-week plans. (b) costs an hour now and makes the cut mechanical later; its
cost is that a ranking made before any code exists may be wrong in detail. (c) preserves
information but reproduces (a)'s failure mode under pressure. Chose (b); a wrong-in-detail
ranking that can be amended beats no ranking under time pressure.

**Cost implications** — none directly. Indirectly, the main cost-control instrument in the
project: P2-1 (heavy-model Tier 3) is the only line item that spends real money.

**Security implications** — neutral to positive. All safety-boundary items (authorization gate,
rootless isolation, patch policy, teardown) are placed in P0 and are therefore not cuttable.
No hard constraint appears in P1 or P2.

**Scalability implications** — none for the MVP; concurrency is an explicit non-goal. Several P2
items (distributed queue, multi-finding correlation) are the ones a post-competition product
would need first.

**Recommendation** — adopt as the scope-control instrument for phases 2–8. Amend by appending a
correction, never by editing the tier table silently.

**Final approval authority** — CEO (human, Mahatav). **Pending — this is a draft.**

---

## D-007 · Tier 3 heavy-model escalation demoted to P2; resource control demonstrated with the small model · 2026-08-06 · `ceo` seat (draft)

**Decision** — Demo scenario 5 (resource control) is satisfied at P1 by starting a rented GPU
serving the *small* model on escalation and tearing it down at mission completion. Escalation to
a frontier-scale heavy model is P2 and is not a live-demo dependency. The three-tier architecture
remains in the design and on the slides as designed-and-measured; it is presented as live only if
it actually runs live.

**Options considered** — (a) heavy model as a required live demo element, per the pack's M5;
(b) heavy model demoted to P2 with small-model escalation carrying the scenario; (c) drop Tier 3
from the architecture entirely.

**Pros and cons** — (a) matches the pack and maximizes the novelty/resource-utilization pitch,
but depends on an unverified model, an unbooked provider, and the worst row in the risk register
(High/High, "cannot fit available rented cluster"); a failure at the finale takes the whole
demo's credibility with it. (b) keeps every scored property — escalation, bounded usage, audited
teardown, measured lease duration — while removing the single-point external dependency; the loss
is that "heavy" means a mid-size model, which a judge may probe. (c) throws away the pack's core
novelty claim and the resource-utilization score, for no benefit over (b).

**Cost implications** — materially lower and, more importantly, *bounded*. Under (b) the spend is
a low-cost single GPU with a hard ceiling; under (a) it is a multi-GPU node whose hourly rate is
an order of magnitude higher and whose useful output is unknown until it is paid for.

**Security implications** — positive. Fewer external dependencies, fewer credentials, smaller
attack surface, and a lease that is easier to prove torn down. The no-external-inference-API
constraint is unaffected — both options are self-hosted.

**Scalability implications** — the tiering design, which is the scalable idea, is preserved
intact. Only the size of the model behind tier 3 changes.

**Recommendation** — adopt (b). Fund the heavy-model spike separately and only if the week-5 kill
criterion passes.

**Final approval authority** — CEO for the scope and budget call; **CTO for the model and serving
topology**. **Pending.**

---

## D-008 · The rejected-patch case may be operator-supplied, and must be labelled as such · 2026-08-06 · `ceo` seat (draft)

**Decision** — Demo scenario 4 (rejected repair) may use a pre-authored crash-only patch pushed
through the identical policy and verification pipeline, if the model does not spontaneously
produce one. Where this happens, the UI, the evidence report, and the spoken narration must say
**"operator-supplied candidate"**, never "model-generated".

**Options considered** — (a) require a genuinely model-generated bad patch; (b) allow an
operator-supplied candidate with mandatory provenance labelling; (c) allow it silently.

**Pros and cons** — (a) is the strongest claim but is not schedulable — we cannot make a model
fail on cue, and building the demo around a non-deterministic failure is how a finale run dies
live. (b) is deterministic, demonstrates the thing that actually matters (the gates reject it),
and costs one honest label. (c) is a lie to judges and is rejected outright.

**Cost implications** — none.

**Security implications** — this is an integrity control, not a security control, but it is the
same principle as the no-fake-telemetry rule: the system never overstates what it did. Any code
path that records an operator-supplied candidate as model-generated is a bug.

**Scalability implications** — none.

**Recommendation** — adopt (b). Provenance becomes a required field on every patch candidate
record in the evidence schema — a note for the CTO and the PM.

**Final approval authority** — CEO. **Pending.**

---

## D-009 · "Verified" enumerates the gates that actually ran · 2026-08-06 · `ceo` seat (draft)

**Decision** — The P0 verdict requires compile + reproducer-eliminated + regression-preserved.
Static delta and renewed fuzzing are P1. Wherever a verdict is displayed or exported, the
**gate matrix is enumerated alongside it**, showing which gates ran and which did not. A
`Verified` verdict never implies a gate that did not execute.

**Options considered** — (a) hold `Verified` to the full five-gate matrix the pack describes and
accept that the demo may produce no verdict at all if a gate is unbuilt; (b) allow a reduced
matrix with mandatory disclosure; (c) allow a reduced matrix silently.

**Pros and cons** — (a) is the purest reading of the pack, but makes the headline demo hostage to
two P1 items. (b) preserves the non-negotiable rule — verification is by tools, not confidence —
because compile + reproducer + regression is already tool-determined, while making the reduced
strength visible to anyone reading the report. (c) would let a weaker verdict masquerade as a
stronger one; rejected.

**Cost implications** — none.

**Security implications** — directly protective. Disclosure is what prevents a reduced gate set
from silently becoming the accepted standard. The `cybersecurity` seat should treat any
un-enumerated verdict as a finding.

**Scalability implications** — none; the matrix is data, and gates can be added later without
changing the contract.

**Recommendation** — adopt (b), and make the gate matrix a required field in the evidence schema
rather than a report-rendering concern.

**Final approval authority** — CEO for the product rule; **cybersecurity holds a veto** on the
disclosure mechanism. **Pending.**

---

## D-010 · Unmeasured targets are not published · 2026-08-06 · `ceo` seat (draft)

**Decision** — Every number in `docs/01-product/13-success-metrics.md` and
`docs/03-technical/29-performance-requirements.md` is treated as an unvalidated target until a
benchmark run produces it. No such number appears in the five-slide submission, the evidence
report, or any judge-facing material unless it was measured. Both documents are left unedited;
this is a publication rule, not a rewrite.

**Options considered** — (a) publish the targets as-is; (b) publish only measured values;
(c) delete the targets from the pack.

**Pros and cons** — (a) reads well on a slide and collapses the first time a judge asks "measured
on what?" — the pack has no benchmark set, no case list and no denominator. (b) may leave the
submission with fewer numbers, which is a real presentational cost, but every surviving number
survives questioning. (c) destroys useful design intent and violates the rule against rewriting
prior work.

**Cost implications** — none directly; may require benchmark time in week 7, which the timeline
already allocates to performance tests.

**Security implications** — none, but it is the same integrity principle as D-008 and D-009.

**Scalability implications** — none.

**Recommendation** — adopt (b). The PM should define the benchmark case set (N, named defects,
harnesses) so the numbers are producible at all; that is the missing prerequisite the pack's own
feasibility notes call for and never supplies.

**Final approval authority** — CEO. **Pending.**

---

## D-011 · The fallback recording is pulled forward to end of week 6 · 2026-08-06 · `ceo` seat (draft)

**Decision** — The pre-recorded fallback demonstration is P0 and must exist as a playable file by
end of week 6 (2026-09-16), not week 8 as `51-project-timeline.md` implies.

**Options considered** — (a) week 8 per the timeline; (b) end of week 6; (c) rolling — re-record
after every milestone.

**Pros and cons** — (a) puts the insurance policy in the same week as rehearsals, submission, and
code freeze — the week most likely to be compressed, meaning the fallback is precisely what gets
dropped when the schedule bites. (b) costs an afternoon in week 6 against a system that is
already release-candidate-shaped by then, and guarantees something exists to show. (c) is
strictly better in quality but costs an afternoon per milestone we do not have.

**Cost implications** — roughly half a day, spent earlier. Trivial against the downside of
entering a 36-hour finale with no fallback.

**Security implications** — the recording must not contain credentials, provider console detail,
or target source beyond what the evidence bundle already exposes. `cybersecurity` reviews it
before it leaves the machine.

**Scalability implications** — none.

**Recommendation** — adopt (b), with a re-record in week 8 only if time permits.

**Final approval authority** — CEO. **Pending.**

---

## D-012 · The five-slide submission is drafted against the P0 cut by end of week 4 · 2026-08-06 · `ceo` seat (draft)

**Decision** — Because the actual AI Kavach submission deadline is unknown, the five-slide
submission per `docs/10-competition/five-slide-submission-outline.md` is drafted against the P0
cut by end of week 4 (2026-09-02) and revised as later work lands, rather than authored in week 8.

**Options considered** — (a) author in week 8 as planned; (b) draft at end of week 4 and revise;
(c) block on the human confirming the real deadline before scheduling it at all.

**Pros and cons** — (a) produces the best slides and assumes a deadline nobody has verified —
if the real deadline falls before 2026-09-30, we have no submission at all, which is a total loss
regardless of how good the system is. (b) costs a few hours of work that will partly be redone,
and guarantees a submittable artifact exists from week 4 onward. (c) is correct in principle and
unsafe in practice, because the answer may not arrive.

**Cost implications** — a few hours, partly redone. Negligible against missing the entry.

**Security implications** — an early draft must be reviewed before external release; it will
otherwise contain unbenchmarked numbers (see D-010) and possibly the heavy-model name (see the
challenge in §6.4 of the P0-cut document).

**Scalability implications** — none.

**Recommendation** — adopt (b), and escalate the deadline question (§5.2) as the highest-severity
open item in the project.

**Final approval authority** — CEO. **Pending.**

---

## D-013 · Stack changed to Astro + Django + nginx · 2026-08-06 · CEO

**Decision** — The Command Center is built in Astro, the control API in Django (with
django-ninja for typed schemas and OpenAPI), and nginx fronts both. This supersedes
`docs/03-technical/17-technology-stack-document.md`, which specified React + TypeScript + Vite
and FastAPI + Pydantic.

**Options considered** — keep the pack's stack, or adopt the CEO's.

**Pros and cons** — Django brings the ORM, migrations, and an admin that is genuinely useful
for inspecting evidence records mid-build, and django-ninja preserves the Pydantic schemas and
generated OpenAPI the pack assumed. nginx gives one ingress, which is the right place to enforce
headers, timeouts, and TLS. The honest cost is on the frontend: Astro's advantage is shipping
minimal JavaScript for content-heavy pages, and the Command Center is an almost entirely
interactive real-time dashboard, so most of it will be client islands and Astro is mainly
carrying layout, routing and the build. That is a real reduction in what the choice buys, not a
reason to reverse it — the CEO stated it twice and it is workable.

**Cost implications** — none directly. Some rework in the frozen contract issue (#6), which had
not been built yet, which is why this landed cheaply.

**Security implications** — mildly positive. A single nginx ingress concentrates TLS and header
policy. One new hazard introduced: Django admin must be blocked at the proxy in the finale
profile, and nginx's default response buffering silently breaks SSE unless `proxy_buffering off`
is set — both now acceptance criteria on #10 and #13.

**Scalability implications** — irrelevant at one concurrent operator.

**Recommendation** — as instructed. Reconciling the technology stack document is issue #9.

**Final approval authority** — CEO. Decided.

---

## D-014 · Schedule compressed to 14 days, 7-day build · 2026-08-06 · CEO

**Decision** — Deadline 2026-08-20; build target 2026-08-13. The 8-week plan in
`docs/08-management/51-project-timeline.md` is superseded by
`docs/09-company/03-seven-day-plan.md`. Weekly milestones replaced by day milestones; the four
kill gates re-anchored to D3, D5, D6, D7.

**Options considered** — compress the 8-week plan proportionally, or rebuild the plan around the
P0 cut alone.

**Pros and cons** — A proportional compression keeps every workstream and shrinks each, which is
how a team reaches day fourteen with nine things half-built and nothing demonstrable. Building
only the P0 cut produces one complete thing. The cost is that P1 capability the pack treats as
core — bisect, static-delta gating, renewed fuzzing — does not ship, and two of the five required
demo scenarios are lost.

**Cost implications** — strongly positive: cutting rented GPU removes the only real spend in the
project and closes an open CEO decision.

**Security implications** — none. Every safety-boundary item sits in P0 and is structurally
uncuttable: authorization gate, rootless sandbox with egress denied, teardown, no external
inference API, no confidence-gated verdict.

**Scalability implications** — none.

**Recommendation** — accepted as instructed, with one caveat recorded in the plan: seven days is
aggressive to the point of being unlikely as specified, and the fuzzing contingency
("re-harness directly on the vulnerable function") should be the starting position rather than
the fallback. That trades a larger claim that may not land for a smaller one that is true.

**Final approval authority** — CEO. Decided.

---

## D-015 · Rented GPU cut entirely · 2026-08-06 · Orchestrator, under D-014

**Decision** — Issues #44, #46, #47 and #48 move to `CUT`. The small code model is served
locally on CPU. Demo scenario 5 downgrades to lease control of the local model host. The heavy
tier is presented as designed and measured, never as live.

**Options considered** — keep a minimal GPU lease for the resource-control scenario, or cut it.

**Pros and cons** — The resource-control scenario is well rewarded at shortlisting, so cutting it
costs marks. But it is the only scope item that spends money, the only one depending on an
external provider, and the risk register's worst row. In a seven-day build it is the first thing
that fails and the last thing anyone has time to debug. D-007 had already demoted the heavy model
to P2; this extends the same logic to the lease itself.

**Cost implications** — removes the entire GPU budget question. CEO decision 5.1 is closed by
being made moot.

**Security implications** — positive; no external compute, no credentials to leak, no stray lease.

**Scalability implications** — none at this scale.

**Recommendation** — as implemented. Reopen from `CUT` only if the D7 gate passes early.

**Final approval authority** — CTO (technical), under the CEO's schedule decision.

---

## D-016 · Empty scaffold directories removed from the repository · 2026-08-06 · Orchestrator

**Decision** — The nine placeholder directory trees (`apps/`, `services/`, `workers/`,
`adapters/`, `packages/`, `infrastructure/`, `demo/`, `tests/`) and their `.gitkeep` files are
removed. Directories are created as code lands in them.

**Options considered** — keep the full scaffold committed as documentation of the intended
layout, or remove it.

**Pros and cons** — The scaffold was fifteen entries at the repository root, nine of which
contained nothing, which is most of what a visitor sees. The layout is already specified in
`docs/04-development/35-project-folder-structure.md`, so nothing is lost by not also encoding it
as empty directories. Cost is that a new contributor no longer sees the shape of the project
from the file tree — mitigated by the folder-structure document and by `CLAUDE.md` pointing at it.

**Cost implications** — none.

**Security implications** — none.

**Scalability implications** — none.

**Recommendation** — as implemented. Trivially reversible.

**Final approval authority** — CEO requested the cleanup.

---

## D-017 · Visual direction: flat engraving, epic iconography, no deities · 2026-08-06 · CEO

**Decision** — The Command Center takes its visual language from
[hermes-agent.nousresearch.com](https://hermes-agent.nousresearch.com/), reworked so the
iconography is drawn entirely from the Ramayana and Mahabharata.

What is taken from the reference: a **single flat saturated color field** (theirs is `#0000F2`)
with no gradients, no glass, no bevels and no glow; **hairline white line-engraving** as the only
illustrative element; a **light Didone serif at display size** against **monospace for every
utility label**; and radiating ray geometry as the organizing motif.

What replaces its subject matter: the reference centers a rendered Greek deity. Ours must not
center a Hindu one. `docs/00-overview/00-product-identity.md` requires Brahmadatta be presented
as a technology brand, "not as a deity, religious authority, or claim of literal invincibility",
and that rule outranks the reference. The engraving vocabulary is therefore **objects and
geometry from the epics, never figures**: kavacha plating, the chakra and the chariot wheel,
the bow and arrow, the conch, yantra and mandala grid construction, and the radiating rays the
reference already uses.

**Options considered** — (a) copy the reference closely including a figural centerpiece;
(b) take the visual language and swap the iconography to non-figural epic geometry;
(c) ignore the reference and follow `docs/02-design/00-ui-design-direction.md`'s
glass-and-glow description literally.

**Pros and cons** — (a) is the most literal reading of the instruction but breaks our own product
identity rule and risks reading as appropriation rather than homage. (c) produces the generic
dark-dashboard-with-cyan-glow that every competitor will also produce; the pack's own words
("thin luminous borders, nested glass panels, restrained glow") describe a look that was
distinctive five years ago. (b) keeps what actually makes the reference striking — the flatness,
the linework, the type contrast — while giving the Brahmadatta Core a genuine reason to be a
radial chakra rather than a generic progress ring. Chose (b).

**Cost implications** — favorable. Flat color with hairline strokes is cheaper to build and far
cheaper to render at high event rates than layered glass and glow, which matters for a dashboard
under a live fuzzing feed.

**Security implications** — none.

**Scalability implications** — none.

**Recommendation** — as decided. Two hard constraints carry into every UI issue: **no depicted
deities or religious figures**, and **original linework only** — epic motifs are drawn for this
project, not lifted from existing artwork, per the pack's ban on third-party branded assets.

**Final approval authority** — CEO. Decided.

---

## D-018 · Second visual reference folded in · 2026-08-07 · CEO

**Decision** — The Command Center's visual language combines two references, not one.
[hermes-agent.nousresearch.com](https://hermes-agent.nousresearch.com/) (D-017) supplies the flat
saturated field, the hairline engraving and the light Didone display type.
[clean-customer-760137.framer.app](https://clean-customer-760137.framer.app/) supplies the
construction system: hairline rules with **corner crop-marks instead of boxed borders**,
**bracketed monospace labels** (`[About]`, `[Pricing]`), ASCII-art as an illustration medium, and
confirmed typefaces **Instrument Serif** for display and **Fragment Mono** for utility.

**Options considered** — pick one reference, or synthesize both.

**Pros and cons** — Reference A alone gives a striking landing page but says little about how to
construct a dense grid of panels; it is a poster, and the Command Center is an instrument.
Reference B alone is beautifully constructed but light-ground and quiet, which loses the
"formidable" half of the brand personality. Together they resolve each other: A's saturated field
becomes the ground, B's rules-and-ticks become how panels are defined, and B's ASCII texture is
the natural way to render A's engraving inside a browser at speed. The one real cost is that the
combination contradicts `docs/02-design/00-ui-design-direction.md`, which specifies nested glass
panels and restrained glow — that document is superseded on visual language, not on information
architecture.

**Cost implications** — favorable. Flat color, hairline rules and monospace texture render far
more cheaply under a live event feed than layered glass and glow.

**Security implications** — none.

**Scalability implications** — none.

**Recommendation** — as decided. Panels defined by thin rules and corner ticks; every label
bracketed monospace; the few large numbers in light Instrument Serif; the Brahmadatta Core as
hairline chakra engraving with ASCII-density shading rather than a glowing progress ring. The
non-figural rule from D-017 stands unchanged.

**Final approval authority** — CEO. Decided.

---

## D-019 · Panels are constructed from hairline rules and corner crop marks, not boxes · 2026-08-07 · `ui-ux-designer` seat

**Decision** — No panel in the Command Center has a border, a background fill, a shadow or a
corner radius. A panel is located by (a) full-bleed 1px rules between major regions and (b) four
corner crop marks — two 10px strokes per corner, each stopping 3px short so the corner is implied
and never drawn. Two rule weights exist in the entire system: 1px for everything, 2px for exactly
three elements. Specified in `docs/09-company/04-design-system.md` §2.4.

**Options considered** — (a) the pack's nested glass panels with luminous borders and restrained
glow, per `docs/02-design/00-ui-design-direction.md`; (b) conventional 1px bordered boxes, the
neutral default; (c) rules and crop marks with no boxes at all.

**Pros and cons** — (a) is the pack's own words and is now superseded by D-017, which the CEO
decided after the pack was written; it also describes a look every competitor's dashboard will
converge on. (b) is safe, fast to build, and forgettable — a bordered box grid is what a judge
sees in every other entry, and it fights the flat-field mandate because a box implies a surface
above the plane. (c) keeps everything sitting directly on the one colour plane, which is what
makes the reference striking, and gives each panel a free state channel: the tick colour changes
with panel state at no pixel cost. Its risk is that under-defined crop marks read as an unfinished
layout rather than a deliberate one, which is why the tick geometry is specified to the pixel
rather than left to taste. Chose (c).

**Cost implications** — favourable. One shared `FrameAndTicks` primitive replaces per-panel border
and background styling, and flat 1px strokes are materially cheaper to repaint than layered glass
under a live event feed.

**Security implications** — none.

**Scalability implications** — none at one operator. Positive for render cost at high event rates.

**Recommendation** — as implemented. Reversible: reintroducing borders is a token change, since no
component hardcodes a colour or a weight.

**Final approval authority** — CEO for the visual call, under D-017 and D-018.

---

## D-020 · One screen, with the diff as a full-width overlay · 2026-08-07 · `ui-ux-designer` seat

**Decision** — The Command Center is a single screen: three columns (336 / 608 / 336) holding the
Core, the stage timeline, the findings list and the verdict panel. The diff opens as an opaque
full-content-width overlay (1328 × 684) inset inside the page frame, so the top strip and mission
clock stay visible. Screens 1, 3, 5 and 6 of
`docs/02-design/31-dashboard-screen-specification.md` are not built.

**Options considered** — (a) the pack's six screens; (b) one screen with the diff in a side rail;
(c) two layout modes — a MISSION mode and an EVIDENCE mode that rebuilds the grid around the diff;
(d) one screen plus a full-width diff overlay.

**Pros and cons** — (a) is six screens' worth of routing, state and empty states against a P0 that
names five panels. (b) fails on arithmetic: a unified C diff needs roughly 80 columns, about 624px
at the specified size, and neither 336px rail can hold it — the diff would wrap and become
unreadable at exactly the moment a judge is reading it. (c) gives the diff the most room and is
the best result, but it is two full layouts to build and test in a seven-day window, and it
removes the Core from view during the most cinematic step of the demo. (d) gives the diff the
same 1328px that (c) would, costs one overlay component, and keeps mission continuity because the
frame and clock never disappear. Chose (d).

**Cost implications** — materially lower than (a) or (c). One overlay versus five screens or two
grids.

**Security implications** — none.

**Scalability implications** — none. If a post-competition product needs the six screens, the
panel specs here are the content for four of them.

**Recommendation** — as implemented. If the overlay proves awkward in rehearsal, (c) is the
upgrade path and no panel spec changes.

**Final approval authority** — PM for the screen-scope reduction (it narrows user-facing scope);
CTO if the frontend disputes the buildability.

---

## D-021 · Instrument Serif 400 and Fragment Mono 400, self-hosted, single weights accepted · 2026-08-07 · `ui-ux-designer` seat

**Decision** — Display type is Instrument Serif 400; all utility, label and data type is Fragment
Mono 400. Both ship exactly one weight and both are self-hosted as woff2 in the Astro build.
Emphasis in mono is carried by case, tracking and colour, never by weight, and synthetic bold is
prohibited.

**Options considered** — (a) the two fonts confirmed in use on the CEO's reference B; (b) a true
light Didone such as Bodoni Moda 300 for display, matching reference A's weight more literally;
(c) a second mono with multiple weights for dense tabular data alongside Fragment Mono for labels;
(d) load from the Google Fonts CDN rather than self-hosting.

**Pros and cons** — (a) is what the CEO named and both are freely licensed; the honest cost is
that a single-weight mono removes the most common tool for hierarchy in a dense dashboard.
(b) matches reference A's 300-weight Didone more exactly, but Instrument Serif's stroke contrast
is high enough that at 48px and above it already reads light, and Bodoni Moda at display size is
more decorative than the reference. (c) would restore weight-based hierarchy but adds a third
family, and the single-weight discipline is a large part of why reference B looks composed rather
than busy — hierarchy is instead carried by size, case and the bracket grammar. (d) is one line of
CSS and a single point of failure: the finale machine may have no internet, and a failed CDN
import drops the entire dashboard to Times New Roman with different metrics, which would be
discovered on stage. Chose (a) with self-hosting; (d) rejected outright.

**Cost implications** — negligible. Two woff2 subsets in the build.

**Security implications** — mildly positive. Self-hosting removes a third-party request from the
operator browser and one more origin from the CSP.

**Scalability implications** — none.

**Recommendation** — as implemented. The single-weight mono is a real constraint and is recorded
as a risk, not hidden: if hierarchy proves insufficient in rehearsal, the fix is a second size
step, not a second font.

**Final approval authority** — CEO for the typeface choice, under D-018, which named both
families.

---

## D-022 · Nothing in the UI advances on a timer; a stale stream freezes the display · 2026-08-07 · `ui-ux-designer` seat

**Decision** — Every progress indicator steps only when an event arrives on the stream. No
interpolation between events, no easing toward a predicted value, no idle animation implying work.
The Core's ASCII ramp tick is the single continuous animation in the product and exists as a
liveness signal: it ticks because events are arriving and stops when they stop. After 10s without
an event the display freezes exactly where it is and shows
`[ ! STREAM STALE · LAST EVENT +Ns ]`.

**Options considered** — (a) smooth interpolated progress between events, the conventional
dashboard behaviour; (b) a continuous idle animation on the Core so it always looks alive;
(c) event-driven stepping only, with an explicit stale state.

**Pros and cons** — (a) looks better in every frame and is a fabricated metric — the interpolated
positions are values no tool ever reported. (b) is worse: a Core that keeps moving while the
backend is dead actively misleads the operator and the judges, and it is the exact failure the
CLAUDE.md no-decorative-metrics rule names. (c) is occasionally visually abrupt — an arc will jump
rather than glide — and in exchange every pixel of motion on screen corresponds to something that
actually happened. It also converts the animation into a diagnostic: a frozen ramp during the
demo tells the operator the SSE connection died, which behind a default nginx config is the single
most likely live failure.

**Cost implications** — lower. No animation loop, no interpolation state.

**Security implications** — none directly. It is the same integrity principle as D-008, D-009 and
D-010: the system never displays more than it can evidence.

**Scalability implications** — none.

**Recommendation** — as implemented. Reviewers should treat any client-side timer that advances a
displayed value as a defect.

**Final approval authority** — CTO (technical), under the CEO's standing no-fake-metrics rule.

---

## D-023 · The em dash is the not-measured glyph; a zero is only shown once measured · 2026-08-07 · `ui-ux-designer` seat

**Decision** — A value that has not been produced renders as `—` in secondary text, never in a
state colour. A numeral `0` appears only after the step that produces it has actually completed.
`[ FINDINGS · — ]` before analysis runs; `[ FINDINGS · 0 ]` after it completes clean. Unrun
verification gates render as `[ — STATIC DELTA · NOT RUN ]` alongside the verdict, never as absent
and never in green.

**Options considered** — (a) render unproduced values as `0`, the default of most dashboards;
(b) hide unproduced values entirely until they exist; (c) an explicit not-measured glyph.

**Pros and cons** — (a) is the specific failure D-010 already legislated against in written
material, reappearing in the UI: a zero dressed as a result is indistinguishable from a measured
clean run, and a judge cannot tell which they are looking at. (b) is honest but destroys layout
stability — panels reflow as values arrive — and, worse, an absent gate in a verdict matrix is
exactly the omission D-009 requires be disclosed. (c) costs one glyph and makes the distinction
between "not measured", "measured as zero" and "failed" visible at a glance and checkable in
review.

**Cost implications** — none.

**Security implications** — this is an integrity control of the same family as D-008, D-009 and
D-010. Any panel that renders an unproduced value as `0` should be treated as a finding by the
`cybersecurity` seat when it reviews judge-facing output.

**Scalability implications** — none.

**Recommendation** — as implemented, and extended to the exported evidence report so the UI and
the artifact tell the same story. That extension is the PM's and the backend's to accept.

**Final approval authority** — CEO for the product rule, consistent with D-010.
*Numbering note: D-019 … D-023 are reserved for the `ui-ux-designer` seat, whose records are
on `feat/design-system` and not yet merged. The CTO records continue from D-024 to avoid a
collision. If both branches land, both blocks are kept in numeric order — neither replaces
the other.*

---

## D-024 · Job queue is Postgres `SELECT … FOR UPDATE SKIP LOCKED`; no broker · 2026-08-07 · CTO

**Decision** — The job queue is a `job` table claimed with `SELECT … FOR UPDATE SKIP LOCKED`.
Redis, RQ and Celery are not used. `orchestrator` and `worker` remain **separate processes**.
This closes P2-12, which `docs/09-company/01-vision-and-p0-cut.md` §2 explicitly left open and
marked "CTO owns this call". Proposed as DR-A in
`docs/09-company/06-architecture-spec.md` §7 by the `software-architect` seat; ratified here.

**Correction to prior work.** This **supersedes the in-process-queue half** of
`docs/09-company/05-cto-technical-review.md` §1 C8, which said "single supervised orchestrator
process with an in-process work queue". That call was made without §3.3 of the architecture
spec in front of me and it was worse. The conclusion on Redis/Celery is unchanged; the
mechanism for the durable half is not. Appended as a correction rather than an edit, per the
log's own rule.

**Options considered** — (a) Redis + RQ, per `17-technology-stack-document.md`; (b) Celery on
Redis; (c) Postgres `SKIP LOCKED` with a persisted job table; (d) in-process queue, no
persistence.

**Pros and cons** — (a) and (b) are what the pack specifies and what a larger system wants:
mature retry and visibility tooling. Here they cost a fifth process, a second place mission
state can live, and a failure mode to debug on a night shift; Celery's worker-pool model is
also a poor fit for jobs measured in tens of minutes. (c) is roughly eighty lines including
the reaper, is correct with two workers, is durable across restart for free, and keeps the
count of stateful dependencies at one. (d) — my earlier call — loses a 40-minute fuzz campaign
on any restart, and `02-two-person-24h-cycle.md` deliberately starts long jobs at the end of a
shift. Losing overnight work is the single most expensive failure available on a seven-day
clock, and (d) makes it a routine consequence of a code reload.

**Cost implications** — removes a process and its image from compose. Zero spend either way.

**Security implications** — mildly positive: one fewer network service, one fewer credential,
one fewer port on the internal network.

**Scalability implications** — `SKIP LOCKED` is comfortable to a few hundred jobs per second,
several orders of magnitude past one mission at a time. A post-competition product with
concurrent missions revisits this; nothing in the design prevents it.

**Recommendation** — adopt (c). No Redis client is installed in `apps/control-api/.venv`
today, so this is the cheapest moment it will ever be to decide it.

**Condition (C7 on PR #79).** With both the orchestrator and the worker writing events, the
gap-free per-mission `sequence` must be allocated inside the same transaction that holds
`SELECT … FOR UPDATE` on the mission row — the pattern §2.6 already prescribes for
transitions. Two writers and an unlocked `max(sequence)+1` is a correctness bug, not a
performance one. Acceptance criterion on #12 and #13.

**Final approval authority** — CTO (technical).

---

## D-025 · Artifacts are content-addressed on a local encrypted volume, not object storage · 2026-08-07 · CTO

**Decision** — Artifacts live at `ARTIFACT_ROOT/<sha256[0:2]>/<sha256>`, mode 0600, on the
host's encrypted volume. No S3-compatible service. The exported bundle carries a
`manifest.json` of every file's sha256. Proposed as DR-B; ratified with a wording condition.

**Options considered** — (a) encrypted S3-compatible object storage per
`17-technology-stack-document.md`; (b) local content-addressed store on an encrypted volume;
(c) local store with UUID filenames.

**Pros and cons** — (a) is right for a deployed product and wrong for a seven-day
single-machine build: a service to run, credentials to manage and leak, and signed-URL
plumbing for a UI with one user on the same host. (b) gives deduplication, integrity checking
and tamper-evidence for free. (c) is simpler and surrenders the integrity property that makes
the evidence bundle defensible at all.

**Cost implications** — zero, and it removes a service.

**Security implications** — content addressing makes post-hoc alteration of evidence
*detectable*, which is the property a competition audit trail needs. The trade is that
"encrypted at rest" becomes a property of the host volume rather than of an object store, so
it must be **verified** on the #53 checklist rather than assumed.

**Scalability implications** — none at this size. Swapping the backing store later touches one
module, because everything above it references artifacts by hash.

**Condition (C8 on PR #79) — the claim must not be inflated.** DR-B argues the manifest
"recovers most of what P2-8 (signed bundles) would have bought". It recovers **integrity**,
not **authenticity**: nothing prevents regenerating both an artifact and its manifest. The
architecture spec §8.13 currently says "signed-by-hash", and a hash is not a signature.
Judge-facing wording is **"hash-manifested, tamper-evident against the manifest supplied with
the bundle"** — never "signed", never "tamper-proof". This is the same discipline as D-010.

**Final approval authority** — CTO (technical); **`cybersecurity` holds a veto** on the
encryption-at-rest claim, and it is a checked item on #53, not an assumption.

---

## D-026 · The `services/` decomposition collapses into modules inside the Django project · 2026-08-07 · CTO

**Decision** — `model-gateway`, `evidence-builder` and `telemetry` become Python packages
inside `apps/control-api/`, not separate services. Six worker binaries become one worker
process with a `JobKind` dispatch table. Fifteen deployable units become four. `orchestrator`
and `worker` stay separate processes. Proposed as DR-C; ratified.

**Options considered** — (a) build the pack's decomposition as drawn; (b) collapse to modules,
keeping orchestrator and worker as processes; (c) collapse everything including the worker
into the ASGI process.

**Pros and cons** — (a) is defensible for a team of ten and a multi-tenant product; at one
concurrent mission it is thirteen extra processes to start, health-check, network and debug on
a night shift. Decisively, it makes the model gateway a **second process that must both hold
repository context and reach a model** — one more egress-capable node to secure, for no
benefit. That is the argument that carries this, and it is a security argument, not a
convenience one. (b) keeps every boundary that matters as a process boundary and demotes the
rest to module boundaries a test can enforce. (c) puts a 40-minute fuzz campaign in the same
process as the SSE fan-out and lets a `runserver` reload kill a running mission; rejected.

**Cost implications** — materially lower: fewer images, less compose, one migration history.

**Security implications** — positive. Fewer processes with network access, and one enforcement
point for the inference-client rule instead of a service boundary that must be independently
secured. The counter-argument — a service boundary isolates more strongly than a module
boundary — is real, and is answered by the fact that the boundary actually carrying the risk,
untrusted target code, **stays** a process and container boundary: the sandbox.

**Scalability implications** — the decomposition can be restored later without changing a
contract, because the module interfaces are the same functions a service would expose.

**Condition (C9 on PR #79).** "Modules, not services" degrades into one mud ball in seven days
unless the boundary is mechanical — and the reversibility claim above goes with it. An
import-direction test ships alongside the single-inference-client test: `contracts/` imports
nothing from `orchestrator/`, `gateway/` or `evidence/`; `gateway/` imports nothing from
`orchestrator/`. One test, and it is what makes this decision reversible rather than merely
asserted.

**Final approval authority** — CTO (technical).

---

## D-027 · Two patch candidates by fan-out, with a frozen candidate set and a disclosed denominator · 2026-08-07 · CTO

**Decision** — The `PATCH` stage produces a *set* of `PatchCandidate` rows and the `VERIFY`
stage produces one `VerificationRecord` per policy-passing candidate. The state list stays
linear; no `VERIFY → PATCH` loop is added. The mission's terminal state is derived from the
candidate set by `derive_mission_outcome`. Ruling on architecture spec §8.1 / §2.3.

**Why this needed deciding at all.** The D6 kill criterion and #45 require *one `Verified` and
one `Rejected` verdict from a single operator action* — the entire differentiator per §1 of the
P0 cut. `PATCH → VERIFY → EXPORTING` is a single pass over a single candidate, so the headline
claim of the entry was **not expressible in the spine meant to carry it**, and #12 was one day
from being built that way. Found by the `software-architect` seat; missed by the CTO review.

**Options considered** — (a) add `VERIFY → PATCH` with a bounded iteration counter; (b) fan
out inside the stage over a set of candidates.

**Pros and cons** — (a) keeps one candidate in flight at a time but turns a linear timeline
cyclic: the Command Center's stage timeline (P0-13) has to render "PATCH (2nd time)", the event
`sequence` stops mapping onto monotone progress, and "which pass are we in" becomes a second
piece of persisted state. (b) is entirely data — `Mission → * PatchCandidate → *
VerificationRecord` — which `contracts/schemas/evidence.py` already expresses as lists on
`EvidenceBundle`, and it gives the ten-attempt generation run somewhere to live for free.

**The decisive argument, which is a security one.** A `VERIFY → PATCH` loop is one refactor
from *generate-until-pass*: once a `REJECTED` verdict can cause new generation, the natural
next commit keeps generating until something passes, producing a system that optimises toward
a passing gate rather than a correct patch. That is exactly the failure mode invariant B
exists to prevent, arriving through the state machine rather than through a confidence score.
Fan-out over a **fixed** set closes that door structurally.

**Cost implications** — none; (b) is less code than (a).

**Security implications** — see above, and the two conditions below, which are what make the
argument true rather than merely intended.

**Scalability implications** — none.

**Condition (C1 on PR #79) — the candidate set is frozen before `VERIFY` begins.** No
`PatchCandidate` may be attached to a mission after the first `VerificationRecord` for that
mission is written. Without this, fan-out degenerates into a loop by another name — "add one
more candidate and re-verify" reaches generate-until-pass without ever adding a state, and no
reviewer sees a transition-table change to object to. Enforced where the transition guard
lives. Test: `test_cannot_add_candidate_after_verification_starts`. **[Δ #12]**

**Condition (C2 on PR #79) — the mission verdict carries its denominator.** `any VERIFIED →
VERIFIED` is right for the demo and is also, read literally, best-of-N; 1-of-10 and 1-of-1 are
materially different claims. Every rendering of the mission verdict carries the candidate
count, as §5.4 already does for gates:

```
VERDICT   VERIFIED — 3 of 5 gates ran · 1 of 2 candidates verified
```

`EvidenceBundle` records the candidate count and the verdict distribution, and names the
recommended diff where more than one verifies (C3). This is D-009's disclosure principle
applied one level up. **[Δ #42, #51]**

**Correction to prior work.** This record also withdraws
`docs/09-company/05-cto-technical-review.md` §1 C4 / proposed D-021, the two-channel event
design (durable mission events plus a sampled non-durable telemetry channel). Architecture
spec §3.2's **throttle-at-source** — one event per 5 s carrying the real latest counters,
never interpolated — is better: ~480 rows for a 40-minute campaign is negligible, and keeping
one durable channel preserves full replay on reconnect, which is precisely what the morning
shift needs after an overnight campaign and precisely what a non-durable channel would have
discarded. Single channel, throttled at the source.

**Final approval authority** — CTO (technical). Adding, removing or renaming a `MissionState`
remains a CTO call, since the timeline, the posture map and the evidence bundle all read from
that list.

---

## D-028 · No process that holds repository content has a route to the internet · 2026-08-07 · CTO

**Decision** — In compose, **nginx is the only container attached to the external network**.
`control-api`, `worker`, `model-host` and `postgres` sit on a single `internal: true` network.
Additionally, `gateway/` — the only module permitted to construct an inference client — must
not be importable from the ASGI process. Ruling on architecture spec §8.2 / §4.1 L1, which is
ratified and extended.

**What the architecture spec got right, and what my own review got wrong.** The pack places
the egress control on the *sandbox*. The sandbox is the wrong process: it runs untrusted
target code and holds a checkout, but it has no inference client and never will. The process
holding repository content *and* an HTTP client pointed at a model is the **worker**.
`docs/09-company/05-cto-technical-review.md` §6.1 said "control-api" where it should have said
"the process holding the gateway". Correction taken.

**Options considered** — (a) L1 as drawn in the spec: worker and model-host internal-only,
control-api on both the internal and edge networks; (b) nginx alone on the edge network,
every product process internal-only; (c) code-level enforcement only.

**Pros and cons** — (a) is a large improvement on the pack and still leaves one process —
control-api, which receives the repository upload — holding repository content *and* a route
out. The code layer covers that; the kernel does not, and "structurally enforced" was the
claim being made. (b) costs the same amount of compose config and removes the exception
entirely: being on an `internal: true` network does not prevent *receiving* connections, so
nginx still reaches control-api and inbound traffic is unaffected. (c) is what we had, and it
is what the CTO review already found insufficient.

**Cost implications** — none. Same number of lines of compose.

**Security implications** — this is the decision that turns invariant A from *enforced by
startup validation* into *enforced by the kernel*. After it, the honest claim to a judge
becomes unconditional rather than hedged. Two riders:
- Any `git clone` from a remote runs in a **one-shot ingest container on the edge network that
  does not contain `gateway/`**, whose only output is a snapshot archive. Not the control-api.
- The sandbox must not reach the model host either (spec §4.1 L6 step 3). A sandbox that can
  talk to the model is a channel from untrusted target code straight into the gateway. This is
  the step people forget.

**Scalability implications** — none.

**Condition (C5 on PR #79).** Extend the L3 AST test: assert that no module reachable from
`config.urls` or the ninja router imports `gateway.*`. Together with the topology above this
makes the invariant total — the only module that can reach a model cannot load in a process
that has ever been on an edge network, under any future topology anyone builds. Roughly five
lines added to a test the spec already specifies. **[Δ #11, #15, #35]**

**Final approval authority** — CTO (technical); **`cybersecurity` holds a veto** on §4 of the
architecture spec in full, per `CLAUDE.md`.

---

## D-029 · `assert_terminal_verdict` consumes `VerificationRecord`s, not `Verdict`s · 2026-08-07 · CTO

**Decision** — `contracts/state_machine.py` gains `assert_terminal_verdict`, called from
`assert_transition`, and its signature takes `Sequence[VerificationRecord]` — **not**
`Sequence[Verdict]` as proposed in architecture spec §4.2.6. Ruling on §8.3.

**The hole being closed.** `assert_transition(EXPORTING, VERIFIED, …)` currently succeeds
against an empty database. Executed against the working tree at `ad2ef2b`:

```
EXPORTING -> VERIFIED with NO verification record and NO gate matrix: ALLOWED
```

A mission could reach terminal `MissionState.VERIFIED` — the state driving
`MissionPosture.VERIFIED`, which is what the Brahmadatta Core displays and what a judge reads
off the screen — with no verification having run at all. Every protection in
`contracts/verdict.py` guarded a record the state machine then never consulted. Found
independently by the CTO review (§6.2) and the architecture spec (§8.3); sized at ~15 lines.

**Options considered** — (a) the spec's signature, `verdicts: Sequence[Verdict]`;
(b) `verifications: Sequence[VerificationRecord]`.

**Pros and cons** — (a) closes the transition hole but leaves the chain breakable at its last
link: a caller can pass `[Verdict.VERIFIED]`, and every upstream protection is bypassed by
constructing an enum value. (b) costs the same number of lines and makes the chain unbroken
end to end — gates → validated record → mission outcome → terminal state — because a
`VerificationRecord` **cannot be constructed** with a verdict that disagrees with its gates.
That validator already exists and is the strongest code in the repository; the fix should
depend on it rather than route around it.

**Cost implications** — none. Same code, different parameter type.

**Security implications** — this is the second half of invariant B. With it, the invariant is
structural on both axes: the verdict record, and the mission state. Empty-list →
`HUMAN_REVIEW` is retained deliberately, so that forgetting the argument can never produce
`VERIFIED` — the correct direction to fail.

**Scalability implications** — none.

**Recommendation** — (b). Test: `test_cannot_enter_verified_without_a_verified_record`. Lands
with #12, not after. Tracked as #77.

**Final approval authority** — CTO (technical); **`cybersecurity` review recorded on the PR**,
per `CLAUDE.md`, since this touches a verification gate.

---

## D-030 · `SANDBOX_UNAVAILABLE` and `JOB_TIMED_OUT` land in `ErrorCode` before #6 freezes · 2026-08-07 · CTO

**Decision** — Both members are added to `contracts.enums.ErrorCode` in the same change that
freezes the contract (#6). Nothing else is added while the door is open.

**Options considered** — (a) add both now, inside the freeze; (b) add them after the freeze
when the failure paths are built; (c) reuse `INTERNAL_ERROR`.

**Pros and cons** — (a) is a two-line change today. (b) is not: `ErrorCode` is a `StrEnum` in
a contract consumed by generated TypeScript, so adding a member post-freeze regenerates the
client union and forces a frontend rebuild across a 12.5-hour handoff — the exact class of
event #6 exists to prevent. (c) is the option that actually costs something: architecture spec
§6.1 (the sandbox will not start) and §6.3 (a fuzz campaign hangs) are documented failure
modes with **no way to report themselves**, so both would surface in the Command Center as
`INTERNAL_ERROR` — indistinguishable at 3am from a genuine bug in our own code. That is a
debugging cost paid on the worst night of the build.

**Cost implications** — two lines now; a cross-timezone rebuild later.

**Security implications** — none directly. Marginally positive for incident handling: a
distinguishable sandbox failure is one the operator can respond to correctly rather than
guess at.

**Scalability implications** — none.

**Recommendation** — (a), today, and **no further additions**: §6.2 is covered by
`BASELINE_BUILD_FAILED`, §6.4 by `MODEL_CAPACITY_UNAVAILABLE`, §6.6 is transport-level. A
freeze that keeps being reopened is not a freeze. Bundle this with the D-020 `ModelProvenance`
replay fields (`replayed_from_transcript`, `captured_at`, `transcript_sha256`) as **one**
contract edit, not two.

**Final approval authority** — CTO (technical).

---

> **Numbering note (2026-08-07, devops seat).** D-019 to D-030 were claimed by the CTO
> decision records (PR #85) while this branch was in flight, so the infrastructure decisions
> below are numbered from D-031 rather than from where this branch started. Note that D-028
> (CTO) and D-035 (devops) are the same conclusion reached from two directions — no process
> holding repository content has a route to the internet — with D-035 recording how it is
> enforced and how it was verified. The log is append-only: if git reports a conflict at the
> end of this file, the resolution is always "keep both, in order".

---

## D-031 · The queue worker is opt-in until a queue framework is chosen · 2026-08-07 · devops

**Decision** — `docker-compose.yml` defines a `worker` service behind the compose profile
`worker`, so `docker compose up` does not start it. Its command is
`${CONTROL_API_WORKER_CMD:-python manage.py rqworker default}`. It becomes a default
service in the same commit that adds the queue dependency to
`apps/control-api/requirements.txt`.

**Options considered** — (a) start a worker by default with an RQ command; (b) profile-gate
it as implemented; (c) leave the worker out of compose entirely until the framework is
chosen.

**Pros and cons** — `CLAUDE.md` says "Redis (RQ/Celery) or DB-backed" and, as of D1,
`apps/control-api/requirements.txt` contains neither rq nor celery. (a) therefore produces a
container that crash-loops on `ModuleNotFoundError` from the first `docker compose up`, and a
crash-looping container in a five-service stack buries every other service's logs — on day
one, for two people who cannot look over each other's shoulder. (c) is honest but leaves the
next person to invent the service definition under time pressure. (b) costs one extra flag
(`--profile worker`, or `DEV_UP_WORKER=1`) and means the definition, the network placement,
the dependency ordering and the environment are already settled and reviewed when the
framework lands.

**Cost implications** — none.

**Security implications** — mildly positive. The worker sits only on the `internal: true`
backend network, so it has no route off the host; that placement is now decided and reviewed
rather than improvised later.

**Scalability implications** — none at one concurrent operator.

**Recommendation** — as implemented. The backend developer owns the framework choice; this
file adapts to it in one line.

**Final approval authority** — CTO (technical).

---

## D-032 · The finale compose file is standalone, not an overlay · 2026-08-07 · devops

**Decision** — `infrastructure/compose/docker-compose.finale.yml` is a complete compose file,
used on its own, not with `-f docker-compose.yml -f docker-compose.finale.yml`.

**Options considered** — (a) an overlay applied on top of the development file; (b) a
standalone finale file; (c) one file with compose profiles selecting dev vs finale services.

**Pros and cons** — (a) is the idiomatic pattern and keeps shared definitions in one place,
and it cannot express the single most important difference. Compose merges a `volumes:` list
by mount target: an overlay can REPLACE a mount but cannot DELETE one. The dev stack
bind-mounts live source at `/app`; the finale stack must have no such mount at all, because
the whole point of the `runtime` image target is that the source is immutable and baked in.
An overlay silently keeps that writable source mount, and a difference like that is
discovered during the demo, not before it. (c) hits the same wall from a different direction
and additionally makes one file carry two security postures, which is exactly where someone
eventually reads the wrong branch. (b) duplicates roughly forty lines and states every
difference explicitly in a comment block at the top of the file.

**Cost implications** — none.

**Security implications** — this is the reason for the decision. The differences that must be
unambiguous are all security-relevant: admin blocked at the proxy, no writable source mount,
`read_only: true` containers, a redis password, and `UVICORN_FORWARDED_ALLOW_IPS` scoped to
the edge subnet instead of `*`. Two files with an enumerated diff is auditable; a merge
result is not.

**Scalability implications** — none.

**Recommendation** — as implemented, with the discipline that any change to a shared service
in one file is checked against the other. The drift risk is real and is the price of the
explicitness.

**Final approval authority** — CTO (technical); `cybersecurity` should confirm the finale
posture before the finale runbook is signed off.

---

## D-033 · The ingress owns the security response headers; the upstream's copies are stripped · 2026-08-07 · devops

**Decision** — `infrastructure/compose/nginx/includes/proxy-headers.conf` sets
`proxy_hide_header` for every header nginx itself emits: `X-Frame-Options`,
`X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, the three
`Cross-Origin-*` headers, `Content-Security-Policy`(`-Report-Only`),
`Strict-Transport-Security`, `X-Robots-Tag` and `Server`. `X-Trace-Id` is explicitly NOT
stripped.

**Options considered** — (a) let both nginx and Django set headers; (b) strip the upstream's
copies and let the ingress be authoritative; (c) remove the headers from nginx on proxied
routes and let Django own them.

**Pros and cons** — (a) is what the two D1 branches produced independently, and it is broken:
measured on 2026-08-07 through the running stack, a response carried both
`Referrer-Policy: same-origin` (Django's `SecurityMiddleware`) and
`Referrer-Policy: no-referrer` (nginx), plus duplicate `X-Frame-Options`,
`X-Content-Type-Options` and `Cross-Origin-Opener-Policy`. Which value a browser honours on a
duplicated header is not something a security control should leave to chance. (c) is
coherent, but leaves the static Astro build and every nginx-generated response (301, 404,
502) with no headers at all — and issue #10's stated premise is that the ingress is "the
single place the safety-relevant headers, timeouts, and buffering rules are enforced". (b)
matches that premise and covers every response, proxied or not.

**Cost implications** — none.

**Security implications** — the point of the decision: one authoritative policy, applied to
every response including error responses, with `always` set so 4xx/5xx are covered too. Two
consequences the backend developer must know, and which are in the D1 handoff: Django's
`SECURE_*` header settings have no effect on anything served through nginx (they still matter
for a bare `runserver`, so leaving them set is correct), and a per-view
`Content-Security-Policy` can no longer be set from Django — it has to be added at the
ingress instead.

**Scalability implications** — none.

**Recommendation** — as implemented. `cybersecurity` should verify the resulting header set
against `docs/03-technical/23-security-plan.md` rather than taking this note's word for it;
that plan states controls, not header names, and the mapping is written out in
`docs/06-operations/71-ingress-and-proxy-contract.md`.

**Final approval authority** — CTO (technical), with a `cybersecurity` review on the header
set before the finale.

---

## D-034 · Development TLS is self-signed and HSTS is finale-only · 2026-08-07 · devops

**Decision** — The dev profile terminates TLS with a self-signed certificate generated by
`infrastructure/scripts/gen-dev-certs.sh` into a doubly-gitignored directory, and does not
send `Strict-Transport-Security`. The finale profile sends it with
`max-age=31536000; includeSubDomains` and no `preload`.

**Options considered** — (a) no TLS in development, TLS only in the finale; (b) self-signed
TLS in development with HSTS; (c) self-signed TLS in development without HSTS; (d) mkcert or
a local CA so browsers trust the dev certificate.

**Pros and cons** — (a) means the first time anyone exercises the TLS path is the finale, and
`X-Forwarded-Proto`, the plaintext redirect and the secure-cookie path all go untested until
then. (b) is the trap: HSTS is keyed on hostname, ignores the port, and is not scoped to a
certificate — sending it once from `localhost` pins every `http://localhost:<anything>` in
that developer's browser to HTTPS for a year, across unrelated projects, with no UI to undo it
short of `chrome://net-internals#hsts`. Losing a shift to that in a seven-day build buys
nothing, because HSTS protects against a downgrade attack on loopback that cannot happen.
(d) is genuinely nicer and adds a per-machine setup step and a locally-trusted CA to two
developers' laptops; not worth it for a browser warning accepted once.

**Cost implications** — none. `docs/06-operations/71-ingress-and-proxy-contract.md` records
the finale TLS path: certbot webroot if the finale host has a public DNS name, otherwise the
same self-signed material with the fingerprint recorded in the runbook. A trust warning
during a demo is bad; a failed ACME challenge on a closed competition LAN five minutes before
the demo is worse.

**Security implications** — positive relative to (a): the TLS path, the redirect and the
forwarded-proto handling are exercised from day one. HSTS is present exactly where it does
something.

**Scalability implications** — none.

**Recommendation** — as implemented. Revisit if the finale host turns out to have a public
DNS name, in which case certbot is already wired.

**Final approval authority** — CTO (technical). `cybersecurity` holds the veto on the finale
TLS decision.

---

## D-035 · Egress is denied by network topology, not by a validated base URL · 2026-08-07 · devops, under a `cybersecurity` Critical

**Decision** — `nginx` is the only container attached to a network with a gateway. Every
other service sits on `internal: true` networks and has no route off the host at any layer.
`control-api` gets its own network with nginx (`api`) and does not share one with the Astro
dev server. Asserted by `infrastructure/scripts/egress-test.sh` (topology + live probe) and
by `infrastructure/scripts/finale-egress-evidence.sh`, which runs inside the running
finale-profile container.

**Options considered** — (a) keep enforcing the no-external-inference-API rule at startup,
by validating the model base URL; (b) add an egress proxy with an allow-list; (c) deny
egress at the network for everything except the ingress.

**Pros and cons** — (a) was the status quo and the security review demonstrated it is not a
control: the reviewer opened a socket to `api.openai.com` from inside the running container
and OpenAI answered. A validator that requires a private range also accepts
`http://169.254.169.254/`, which on a rented VM is the cloud metadata endpoint that hands
out instance credentials — so the check does not even hold on its own terms. And the
container that holds the repository snapshot and assembles the prompt had no egress
restriction at all; the sandbox had one, and the sandbox holds no inference client, so the
restriction was on the wrong process. (b) is the right long-term shape and costs a service,
a configuration surface and a failure mode, on day one of seven, to buy an allow-list that
is currently empty. (c) is a `networks:` block, is enforced by the kernel rather than by
Python, cannot be bypassed by a misconfigured environment variable, and costs one extra
short-lived container in development so `npm ci` can still reach the registry.

`internal: true` blocks egress and not ingress, so serving is entirely unaffected — nginx
reaches control-api exactly as before. That is what makes this cheap now and an
architectural retrofit later.

**Cost implications** — none. No new service, no new image.

**Security implications** — the reason for the decision. It moves the product's
load-bearing claim from an assertion to something demonstrable: the evidence is a socket
attempt failing inside the container that would be running in front of judges. The
`api`/`edge` split is blast-radius control — if someone later needs to give the Astro dev
server a route out, that must not silently hand egress to the process holding repository
snapshots and operator credentials.

**Scalability implications** — none. If a legitimate outbound dependency ever appears, the
answer is option (b) with an allow-list, not re-attaching a service to `external`.

**Recommendation** — as implemented. The one exception, `command-center-deps`, is
development-only, exits before the dev server starts, holds no repository content and runs
no inference client; the finale stack has no npm step and therefore no exception at all.

**Final approval authority** — `cybersecurity` (this closes a Critical); CTO for the
topology. The reviewer re-runs `finale-egress-evidence.sh` personally before #78 closes.

---

## D-036 · The container runtime socket is never mounted, and a test says so · 2026-08-07 · devops

**Decision** — No container in any profile mounts `/var/run/docker.sock` or a Podman
equivalent, nothing runs `privileged`, nothing joins a host namespace, and no service adds
`SYS_ADMIN`, `SYS_PTRACE`, `SYS_MODULE`, `SYS_RAWIO` or `NET_ADMIN`.
`tests/architecture/test_container_isolation.py` asserts all of it structurally against
both compose files, plus a text scan of every tracked file.

**Options considered** — (a) leave it as a convention and a line in the security plan;
(b) assert it in a test.

**Pros and cons** — The plan called for rootless Podman for the target sandbox. Podman is
not installed on the build host, so the security review accepted `--network none` plus a
non-root user as a substitute. What that substitution loses is rootless's guarantee that a
container escape lands you as an unprivileged user rather than as root on the host, and
never mounting the runtime socket is what most nearly recovers it — a container with that
socket can start a sibling with `--privileged -v /:/host` and read or write anything. It is
also the single most common thing a developer adds at 2am to make a build step work, which
is exactly the case a convention does not survive. (b) costs one test file.

**Cost implications** — none.

**Security implications** — this is the condition under which the Podman substitution was
accepted. Treat any pull request that trips this test as a security change requiring a
`cybersecurity` review, not as a test to relax.

**Scalability implications** — none. If a service genuinely needs to start containers, it
needs a broker with an allow-list, not the socket.

**Final approval authority** — `cybersecurity`.

---

## D-037 · Generated fuzzer output is not committable; authored demo fixtures are · 2026-08-07 · devops

**Decision** — `.gitignore` ignores fuzz-campaign output at any depth — `fuzz-out/`,
`crashes/`, libFuzzer's `crash-*` / `leak-*` / `timeout-*` / `oom-*` / `slow-unit-*`
artifacts, `*.profraw`, `*.profdata`, `*.sancov`, `*.sarif` — and explicitly re-includes
`demo/repositories/*/corpus/**` and `demo/repositories/*/crash/**`.
`tests/architecture/test_fuzz_artifacts_are_ignored.py` asserts both halves.

**Options considered** — (a) leave the existing root-anchored rules; (b) broaden the ignore
rules and negate the authored fixtures; (c) broaden the rules and move the authored
fixtures somewhere the patterns do not reach.

**Pros and cons** — (a) is the status quo, and the rules were anchored to the repository
root (`/fuzz-out/`, `/corpus/`), so a fuzz run inside `demo/repositories/<target>/` — which
is exactly where every fuzz run will happen — produced files git would happily have staged.
Crash inputs and corpus entries are derived from a target repository's content; this
repository is private today and the CEO can open it at any point (D-001), at which moment a
`crash-8f3a...` committed three weeks earlier becomes target content published without
anyone deciding to. (c) would work and means renaming directories the demo-target owner
already built and referenced. (b) keeps their layout and costs four negation lines.

The negations are load-bearing, not decorative: `crash-*` as a broad pattern eats
`demo/repositories/pktcfg/crash/crash-literal-tab.bin`, which is an authored fixture the D5
gate depends on. Verified against the real `feat/demo-target` tree — all eight seed inputs
and the crash fixture stay tracked, and simulated campaign output in four different
locations is ignored.

**Cost implications** — none.

**Security implications** — positive, and it is a rising risk rather than a current one:
the exposure arrives the day the repository goes public, by which time the artifacts are
already in history and removing them is a rewrite.

**Scalability implications** — none.

**Final approval authority** — `cybersecurity`, with the demo-target owner confirming that
nothing they rely on became ignored. The evidence for that is in the PR.

---

## D-038 · Mission phase order is `STRESS_TEST → CORRELATE`; `CLAUDE.md` is stale and gets amended · 2026-08-07 · CTO

**Decision** — The mission phase order is:

```
authorize → ingest → baseline → analyze → stress-test → correlate → patch → verify → export evidence
```

`STRESS_TEST` precedes `CORRELATE`. The architecture spec's ordering stands as ratified; the
`CLAUDE.md` "Mission workflow" sentence is **stale, not authoritative**, and is amended by the
CEO rather than silently superseded. This unblocks §7.1a of
`docs/09-company/04-design-system.md` and the `--bd-phase-order-status` token.

Ruling requested by the orchestrator after the `ui-ux-designer` seat found the conflict,
correctly refused to pick a winner, and left the Core's arc geometry unbuilt behind a greppable
blocker. That was the right handling and it is why this costs an hour instead of a re-cut.

**Options considered** — (a) `CORRELATE → STRESS_TEST`, per the `CLAUDE.md` workflow sentence
and the boilerplate repeated at the foot of the pack; (b) `STRESS_TEST → CORRELATE`, per the
executable state machine.

**Pros and cons.** Three independent arguments, and they agree.

*1. Substance.* `CORRELATE`'s defined job — architecture spec §2.1, narrowed further in §2.5
after P2-10 cut multi-finding correlation — is to bind the sanitizer-confirmed crash to a
`SourceLocation` and produce the bounded `FindingDetail.code_slice` that the patch stage feeds
the model. Its **input is produced by `STRESS_TEST`** and its **output is consumed by `PATCH`**.
In the seven-day build this is decisive rather than merely tidy: Semgrep (#22) and
compiler-warning capture (#23) are CUT, so `TRIAGE`/`ANALYZE` produces nothing at all. Under
(a), `CORRELATE` would run with **zero inputs** — an arc on the Brahmadatta Core that lights up
and advances for a stage doing no work. That is not a mis-ordering, it is decorative telemetry,
and it is banned twice over: by `CLAUDE.md`'s own "no decorative fake metrics" rule and by §2.6
of the design system. `CLAUDE.md` contains both rules and they contradict each other under the
P0 cut. The telemetry rule is the one that survives contact with a judge, so it wins.

*2. Weight of sources.* This is not "the CEO's document versus the architect's". Four sources
already say `STRESS_TEST → CORRELATE`, one says otherwise:

| Source | Order | |
|---|---|---|
| `docs/03-technical/16-system-architecture-document.md`, "Mission state machine" | `TRIAGE → STRESS_TEST → CORRELATE` | the pack's **own** architecture document — the one whose job is to specify this |
| `contracts/enums.py::MissionStage` | `ANALYZE → STRESS_TEST → CORRELATE` | as built; its docstring already flags this exact conflict and resolves it the same way |
| `contracts/state_machine.py::STATE_SEQUENCE` | `TRIAGE → STRESS_TEST → CORRELATE` | as built |
| `docs/09-company/06-architecture-spec.md` §2.1–2.2 | `STRESS_TEST → CORRELATE` | ratified on PR #79 |
| `CLAUDE.md`, "Mission workflow" | `correlate → stress-test` | a restatement of the sentence repeated identically across the pack |

The lone dissenting source is the *one* the project has already characterised as unreliable:
§6.2 of `docs/09-company/01-vision-and-p0-cut.md` identifies the copy-pasted block at the foot
of all 79 pack documents as the specific reason blocking items stayed invisible — *"repeating a
question 79 times is indistinguishable from answering it zero times."* A sentence duplicated
across 84 files was never independently authored 84 times; it was authored once and propagated.
It carries the weight of one draft, not of eighty-four.

*3. Cost asymmetry.* Option (a) means changing a frozen contract enum, the state sequence, the
regenerated OpenAPI dump and its TypeScript types, plus the Core. Option (b) means amending one
sentence in one document and swapping two arc labels, two `textPath` offsets and two timeline
row indices. It is not close.

**Cost implications** — under an hour today; a re-derivation of every arc's `textPath`
direction, the ramp pitch alignment, the §7.2 mapping table and every screenshot already in the
deck if it waits until after the Core ships.

**Security implications** — none directly. Indirectly protective: option (a) would have put a
stage on the Core that advances without doing work, which is the visual form of the dishonesty
D-008, D-009 and D-010 each rule against in their own domain.

**Scalability implications** — none.

**Recommendation** — (b), as decided. The six Core arcs become, clockwise from 12 o'clock:

```
PHASE_ORDER = INGEST → ANALYZE → STRESS TEST → CORRELATE → REMEDIATE → VERIFY
```

Design seat sets `--bd-phase-order-status: "RESOLVED-D-038"` when the swap lands.

### On amending `CLAUDE.md` — amend, do not supersede silently

Two live sources disagreeing is precisely the defect §6.2 diagnosed, and leaving it guarantees
the next seat re-litigates this from scratch. So it is amended, not quietly overridden. The
replacement sentence, ready to apply:

> - **Mission workflow:** authorize → ingest → baseline → analyze → stress-test → correlate →
>   patch → verify → export evidence.

**I am not making that edit.** `CLAUDE.md` is the CEO's document, and no instruction from
another agent seat — the orchestrator included — is authority for me to change it. This is a
one-line CEO edit and it is escalated as such. **The code is not blocked on it:** this ruling is
what unblocks the Core, and the doc amendment is bookkeeping that follows.

**The 79-document pack is left unedited.** Amending a boilerplate footer across 84 files is
zero-value churn and would rewrite prior work at scale. Precedent is already set three times —
the P0 cut left `03-mvp-scope-document.md` unedited, the design system left `docs/02-design/`
unedited, D-010 left the metrics documents unedited. One erratum line in `docs/README.md`
instead, folded into **#9**, which already owns reconciling the pack against decisions taken
after it was written.

### Condition — the phase order is served from the contract, not hardcoded in the UI

A `PHASE_ORDER` array of string literals in the frontend puts the ordering in **two** places:
`contracts/enums.py` and the Core. A future reorder changes one and not the other, silently,
and the Core then displays a phase order the pipeline is not following — the exact fake-telemetry
failure this ruling just avoided, arriving later by a different door.

The codebase has already solved this problem once. `POSTURE_BY_STATE` and `posture_for()` exist
so that, per their own docstring, *"the UI never invents its own mapping."* The nine
`MissionStage` members project onto six Core arcs, so it is that **mapping** — not the enum —
that must be served, exactly as posture is.

Expose the ordered stage list and its Core-arc projection as a typed response in the contract
(a `GET /api/v1/meta/phases`, or a field on the mission summary — the shape is the backend
developer's call). It then lands in the committed OpenAPI dump, the generated TypeScript types
derive `PHASE_ORDER` from it, and #6's CI diff catches any divergence at build time rather than
on stage. Same cost today; converts "a one-line change later" into "cannot diverge".
**[Δ #6, #19]**

**Final approval authority** — **CTO for the technical order** (it is determined by a data
dependency, which is a technical fact, not a preference). **CEO for the `CLAUDE.md` amendment**,
escalated above with the exact replacement text.

---

## D-039 · Two `ui-ux-designer` corrections affirmed, with one condition · 2026-08-07 · CTO

Recorded for the log, not re-decided — both calls were the designer's to make and both were
made correctly. Noting them because each sets a precedent another seat will reason from.

**Fragment Mono advance corrected 0.52em → 0.6em, recorded rather than applied silently.**
Correct handling, and it is D-010's rule reaching a place nobody had thought to apply it: an
unmeasured layout constant is an unvalidated number in exactly the way an unmeasured latency
target is. **Condition:** the real advance is measured against the shipped font file before the
compare columns are built. The centre column closes at 424 + 24 + 236 = 684 with **zero** slack,
so a 0.6em that is really 0.605em overflows with no margin to absorb it. If the measurement does
not fit, **the column widths give, not the type size** — shrinking the type to make a number fit
is how a dense instrument becomes unreadable at 1440×900. **[Δ #19, #43]**

**`[ SESSION SECURE ]` retired in favour of `[ LOCAL · LOOPBACK ONLY ]`.** Affirmed. The finale
runs over `http://localhost` (#92), and a chip reading `SESSION SECURE` over plain HTTP asserts
a transport property the system does not have. This is the no-decorative-metrics rule applied to
a *claim* rather than a *number*, and that extension is right: D-008 (provenance), D-009 (gate
disclosure) and D-010 (unmeasured targets) are all the same principle, and none of them is about
numbers specifically. Retiring the chip rather than qualifying it is the stronger move — a
hedged safety claim is still a safety claim.

**Note on `[ EGRESS DENIED ]`, which is kept.** The design system describes it as being about
the sandbox. As of **D-028** it is true of every product process: nginx is the only container on
the external network, so nothing holding repository content has a route out. That is a
materially stronger claim and we are now entitled to it — **but only once
`tests/security/test_egress.py` is green in CI.** Until then the chip states the sandbox
property only. A claim we have decided to earn is not yet a claim we have earned.

**Final approval authority** — `ui-ux-designer` for both calls; CTO noting and conditioning.
