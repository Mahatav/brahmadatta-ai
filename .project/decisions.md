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
## D-040 · Interim bearer-token auth; sessions and MFA deferred · 2026-08-07 · `backend-developer` seat

**Decision** — Operator authentication for the seven-day build is one bearer token per role
(operator, reviewer, administrator), supplied by the environment, compared in constant time, with
no configured token meaning that role cannot authenticate at all. Session auth, MFA for
administrators, and per-project membership checks from
`docs/03-technical/22-authentication-and-authorization-plan.md` are **not** built.

**Options considered** — (a) build the full plan; (b) leave every endpoint open and add auth
later; (c) bearer tokens now, fail closed, with the gap recorded.

**Pros and cons** — (a) is a day of work for a single named operator on one machine, and the
competition is not scored on our login page. (b) is how an "add auth later" ticket reaches day
fourteen unstarted, and it would leave the authorization-gate tests passing against an API anyone
on the network can drive. (c) gives real 401/403 behaviour that the frontend builds against from
D1 and that the security review on D8–11 can harden, without spending D1 on it.

**Cost implications** — none.

**Security implications** — The gap is real and is named here rather than discovered later: no
MFA, no session revocation, no per-project membership check, and a token that leaks is valid until
the environment changes. Mitigating factors: the API is bound to localhost behind nginx, there is
one operator, and the API fails closed with no tokens configured. `cybersecurity` owns the call on
whether this is sufficient for the finale.

**Scalability implications** — none.

**Recommendation** — accept for the build, revisit at the D8–11 security checklist (#53).

**Final approval authority** — `cybersecurity` seat, with the CTO on the schedule trade.

---

---

*Renumbered from D-026 on merge: the `cto` seat had already taken that number on `main`. Content unchanged.*

---

## D-041 · A substituted path must be inexpressible as the primary one · 2026-08-07 · `backend-developer` seat

**Decision** — The CEO's approved fallbacks (#81 subprocess jail, #82 model replay, #83
reproducer replay) are carried in the contract as required, validated provenance rather than as
optional flags. `FindingSummary.discovery_method`, `FuzzingReport.mode` and
`SandboxStatus.isolation_mode` are required with no default; `ModelProvenance`'s three replay
fields are all-or-nothing; `GateResult.evidence_source` means a gate may only `PASS` on a tool
that actually ran; and `EvidenceBundle.substitutions` lists every fallback used with a mandatory
reason.

**Options considered** — (a) a single boolean `is_fallback` on the mission; (b) optional
provenance fields the pipeline sets when it remembers; (c) required, validated provenance at
every substitution point, with the primary claim unrepresentable from a substituted path.

**Pros and cons** — (a) is one bit for four different substitutions and tells a judge nothing
about which one happened. (b) is the version that fails: the fallback path is taken at 2am on the
day the primary one broke, by whoever is still awake, and an optional field is exactly what does
not get set then. (c) costs a required field at four call sites and makes the dishonest record
impossible to construct — a replayed corpus cannot be reported as a live campaign, and a run
whose fuzzer never executed cannot claim the renewed-fuzz gate. The cost is that the orchestrator
must supply these values; that is the intent.

**Cost implications** — none.

**Security implications** — positive. `IsolationMode` means a weaker containment path is visible
in the evidence bundle rather than implied by silence, which matters because the subprocess jail
is materially weaker than a rootless container.

**Scalability implications** — none.

**Recommendation** — as implemented. The corresponding requirement on the orchestrator — that it
actually populate these — belongs to #12, #81, #82 and #83.

**Final approval authority** — CTO (technical); the fallbacks themselves were approved by the CEO.

*Renumbered from D-027 on merge: the `cto` seat had already taken that number on `main`. Content unchanged.*

---

## D-042 · Generated fuzzer output is not committable; authored demo fixtures are · 2026-08-07 · devops

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

*Renumbered from D-037 on merge — the `cto` seat took that number on `main` first. Content unchanged.*

---

## D-043 · Contract rules enforced by types, not by review · 2026-08-07 · `backend-developer` seat

**Decision** — The three hard product rules that guard the entry (no verdict from model
confidence, no stage without authorization, no hosted inference endpoint) are expressed in the
schemas and in Django system checks, not as conventions plus code review. Concretely:
`derive_verdict(gates: GateMatrix) -> Verdict` has no parameter a confidence value could occupy;
gate schemas set `extra="forbid"`; `VerificationRecord` re-derives its verdict in a validator and
refuses to serialize when the stored verdict does not follow from its gates;
`assert_stage_can_run` takes a required, non-defaulted authorization argument; and a hosted
inference URL fails `manage.py check` and therefore fails boot.

**Options considered** — (a) document the rules and rely on review; (b) enforce at the service
layer when the orchestrator lands; (c) enforce in the contract schemas now.

**Pros and cons** — (a) is what the doc pack already does, and it is why the CTO's review found
`EXPORTING -> VERIFIED` reachable with no verification record at all: eleven documents repeat the
rule and nothing enforced it. (b) defers the guarantee to code written on days two to six under
time pressure, by the person least likely to be re-reading the safety documents. (c) costs a few
hours on D1 and makes the violation unrepresentable — a `VERIFIED` record over a failed
regression gate cannot be constructed, let alone returned. The cost of (c) is rigidity: a
legitimate future need to record something the schema forbids requires a contract change and a
regenerated OpenAPI dump. At fourteen days that rigidity is the feature.

**Cost implications** — none.

**Security implications** — strongly positive. The authorization gate, the sandbox egress policy
(`Literal["deny"]`) and the model-routing boundary are all now failures at construction or
startup rather than at demo time. The residual risk is that the *orchestrator* may not call these
functions; that is recorded as a blocking acceptance criterion on #12.

**Scalability implications** — none at one operator.

**Recommendation** — as implemented.

**Final approval authority** — CTO (technical).

---

*Renumbered from D-024 on merge: the `cto` seat had already taken that number on `main`. Content unchanged.*

---

*Renumbered from D-038 on merge — the `cto` seat took that number on `main` first. Content unchanged.*

---

## D-044 · Mission verdict derived from the set of candidate verdicts · 2026-08-07 · `backend-developer` seat

**Decision** — A mission carries N patch candidates and N verification runs, each with its own
gate matrix and verdict. The mission's terminal state is derived from the whole set by
`derive_mission_verdict`, and `MissionVerdictSummary` carries the per-candidate breakdown
alongside it with a validator that refuses any summary whose counts or mission verdict do not
follow from its candidates.

**Options considered** — (a) one candidate per mission, second candidate as a second mission;
(b) N candidates with the mission verdict taken from the last verification to finish; (c) N
candidates with the mission verdict derived from the set, breakdown mandatory.

**Pros and cons** — (a) is what a single-pass `PATCH → VERIFY → EXPORTING` implies, and it makes
the D6 criterion — one `Verified` and one `Rejected` from a *single* operator action —
structurally unreachable, losing the differentiator. (b) is the cheapest change and is a bug
waiting for the demo: whichever run finished last would decide what the judge sees. (c) makes the
side-by-side view the default shape of the data and makes "one Verified among several" impossible
to state without also stating the rejections.

The reduction rule is opinionated and is written down rather than assumed: any
`HUMAN_REVIEW_REQUIRED` outranks everything; otherwise one `VERIFIED` is enough, because the
mission's question is "does a repair that holds exist", not "did every candidate pass".

**Cost implications** — none. Caught before the freeze; the rework was under an hour.

**Security implications** — none directly. Mildly positive for honesty: a `VERIFIED` mission
verdict can never hide a rejected candidate.

**Scalability implications** — none.

**Recommendation** — as implemented. The matching fan-out inside the PATCH and VERIFY stages is
the orchestrator's half and belongs to #12 and #80.

**Final approval authority** — CTO (technical).

---

*Renumbered from D-025 on merge: the `cto` seat had already taken that number on `main`. Content unchanged.*

---

*Renumbered from D-039 on merge — the `cto` seat took that number on `main` first. Content unchanged.*

---


---

## D-045 · The verdict guard loads its own evidence; a caller-supplied set cannot be trusted · 2026-08-07 · CTO

**Ruling on BUG-003 (C6) and BUG-004 (a)(b)(c). FIX, before #12 merges.**

**Reproduced by execution** against `origin/main` @ `8955f60`, independently of QA:

```
BUG-003 duck-typing: any object with .verdict satisfies the guard?
  ALLOWED  <-- reproduces: guard duck-types, no gate matrix required
C6d: records from ANOTHER mission -> VERIFIED?
  RESULT: ALLOWED  <-- mission_id is NOT checked
```

The good news first, also by execution: the original #77 hole is **closed**.
`EXPORTING → VERIFIED` with no records is refused with `VerificationRequiredError`, and one
`VERIFIED` plus one `REJECTED` record correctly yields `VERIFIED` — the D6 demo works. What
remains is narrower and is my own condition's fault, not the implementer's.

**My C6 was written as though a type annotation were a mechanism. It is not.** I wrote *"take
`Sequence[VerificationRecord]` and read `record.verdict`"*, the implementer did exactly that,
and Python enforced nothing. A class with a single `verdict` attribute and no gate matrix
anywhere satisfies the guard. This project has now learned the same lesson three times — an
annotation is documentation, a validator is enforcement — and it should stop being a surprise.

**Decision** — three changes, in two different places, because they cannot all live in one.

*In `contracts/state_machine.py` (cheap, do now):*
1. `isinstance(record, VerificationRecord)` on every element, raising `VerificationRequiredError`
   on a lookalike. Test: `test_guard_rejects_a_lookalike_without_a_gate_matrix`.
2. Every record's `mission_id` must equal the mission being transitioned. The guard currently
   has no mission id at all, so one is added as a required parameter. `AuthorizationRecord`
   already carries exactly this concept in `covers_snapshot`; this is the same idea applied to
   evidence. Test: `test_another_missions_verification_does_not_justify_this_verdict`.
3. De-duplicate by `record.id` before deriving, so the same record supplied twice cannot
   outvote a record supplied once.

*In the orchestrator (#12) — and this is the part that matters:*

**The completeness of the record set cannot be checked by a function that is handed the set.**
BUG-004(c) — dropping a `REJECTED` record reaches `VERIFIED` — is undetectable from inside a
pure function given only what it was given. No amount of validation in `contracts/` closes it,
and a guard that looks total while missing this is worse than one that is honestly partial.

Therefore: `assert_verdict_is_evidenced` is called **only** from a code path that loaded the
records itself, by mission id, **inside the same transaction that holds `SELECT … FOR UPDATE`
on the mission row** — the pattern D-024's condition C7 already requires for event-sequence
allocation. `contracts/` keeps the pure derivation; the completeness guarantee lives at the
database boundary because that is the only place it can live.

**Options considered** — (a) validate harder inside `contracts/`; (b) pass a repository/loader
into the guard; (c) keep the pure guard and require the caller to be a transaction-scoped
loader.

**Pros and cons** — (a) fixes (a) and (b) and cannot fix (c); shipping it alone would leave a
guard advertising a property it does not have. (b) is the textbook answer and drags a
persistence dependency into a contract package that is deliberately free of one — and
`contracts/` is consumed by the OpenAPI export, so it must stay importable without a database.
(c) keeps the layering, puts the guarantee where the data is, and costs one comment and one
review checklist item. At one mission on one machine, (c) is sufficient and (b) is not worth
the coupling.

**Cost implications** — roughly fifteen lines in `contracts/` and one structural rule in #12.

**Security implications** — this is the second half of invariant B. Without it the guard checks
that the evidence it was shown is real, but not that it was shown all of it — which is the
difference between "no verdict without evidence" and "no verdict against the evidence".

**Scalability implications** — none.

**Final approval authority** — CTO (technical); **`cybersecurity` review recorded on the PR**,
since this is a verification gate.

---

## D-046 · The candidate set is frozen in the database, and the rule is stated in the contract · 2026-08-07 · CTO

**Ruling on BUG-004(d) / C1. FIX, before #12 merges.** Confirmed unmet: no freeze exists
anywhere in `contracts/`, and `test_cannot_add_candidate_after_verification_starts` does not
exist.

This is the condition I said I cared most about and the reasoning has not changed: without it,
*"add one more candidate and re-verify"* reaches generate-until-pass **without any
transition-table change for a reviewer to object to**. It is the one failure mode in this
system that leaves no diff to catch it.

**Decision** — the freeze is enforced where it can be, and stated where it will be read.

- *Database (#12, the enforcement):* `Mission.verification_started_at`, set when the first
  `VerificationRecord` is written. The candidate-insert path raises if it is set. This is the
  real mechanism, because "has verification started" is state, and state lives in the store.
- *Contract (`contracts/`, the statement):* `assert_candidate_set_open(verifications)` raising
  when any verification exists. It is not sufficient on its own — same reasoning as D-045 —
  but it puts the rule in the file a developer reads before writing the insert, and it gives
  the named test somewhere to live.
- Test `test_cannot_add_candidate_after_verification_starts` ships with #12. Not optional, and
  not a follow-up issue.

**Options considered** — (a) contract-level only; (b) database-level only; (c) both.

**Pros and cons** — (a) is unenforceable, per D-045. (b) is sufficient and invisible: the next
person to read `contracts/state_machine.py` sees a fan-out with no stated bound and reasonably
concludes there isn't one. (c) costs one extra function.

**Cost implications** — one column, one guard, one test.

**Security implications** — this is what makes D-027's fan-out ruling true rather than
intended. Without it the fan-out is a loop with the loop edge left implicit.

**Scalability implications** — none.

**Deferral considered and rejected.** A deferral with an owner and a date would be a legitimate
answer at this schedule, and for BUG-018 it nearly was. Not for this one: the cost of doing it
during #12 is a column and twenty lines, and the cost of doing it after D6 is unpicking a
verification path that has already produced the demo. The asymmetry is too large.

**Final approval authority** — CTO (technical).

---

## D-047 · A paused mission resumes only into the state it paused from · 2026-08-07 · CTO

**Ruling on BUG-005. FIX, before #12 merges.** Reproduced:

```
BUG-005: BASELINE -> PAUSED legal?  True
BUG-005: PAUSED -> EXPORTING legal? True
BUG-005: PAUSED -> EXPORTING            ALLOWED  (never entered PATCH or VERIFY)
BUG-005: EXPORTING -> VERIFIED          ALLOWED  <-- reproduces
```

**Decision** — `_RESUMABLE` stops being a fixed set. `paused_from` is persisted on the mission
and `TRANSITIONS[PAUSED]` resolves to exactly that one state, plus the aborts. This was already
specified — architecture spec §9 lists `paused_from` in the backend developer's work — and
simply was not built.

**A second consequence nobody has named.** With a fixed `_RESUMABLE`, pause is not only a
forward skip, it is a **backward** one: a mission paused in `VERIFY` may resume into `BASELINE`,
re-run the baseline, and write a second `BaselineReport` into the evidence bundle for the same
snapshot. `BaselineReport` is the denominator for "regression preserved" (P0-5), so a bundle
containing two of them for one mission is not merely untidy — it makes the central verification
claim ambiguous to anyone auditing it. Binding resume to `paused_from` closes both directions
at once.

**Options considered** — (a) `paused_from`; (b) narrow `_RESUMABLE` to the states that cannot
skip work; (c) defer, on the grounds that pause is an operator action nobody will misuse.

**Pros and cons** — (a) is exact and is already designed. (b) requires reasoning about which
skips are safe, every time a state is added, forever. (c) is tempting because the operator is
one trusted person — and it is wrong for the reason the whole state machine exists: the guard
is not there because we expect misuse, it is there so the property is true without depending on
who is at the keyboard at 3am on D6. `MissionState.PAUSED` is explicitly retained in the
architecture spec for exactly that scenario.

**Cost implications** — one field, one lookup. Smaller than (b).

**Security implications** — closes the last route to a terminal verdict that skipped the work,
and prevents a duplicate baseline from muddying the evidence bundle.

**Scalability implications** — none.

**Final approval authority** — CTO (technical).

---

## D-048 · `recommended_patch_id` is added and derived, in one batched contract change · 2026-08-07 · CTO

**Ruling on BUG-018 / C3. FIX, batched.** Confirmed unmet — `EvidenceBundle` carries
`patches` and `verifications` and nothing that says which diff we are claiming.

**Decision** — add `recommended_patch_id: UUID | None`, and make it **derived and validated**,
not free-form: a `model_validator` requiring that, when set, it names a patch in `patches`
whose verification verdict is `VERIFIED`; and that when exactly one candidate verified, it is
that one. Same reasoning the architecture spec applied to `gates_not_run` in its §8.6 — a
hand-set field sitting next to the data that already contains the truth is a field that can
lie, and it is exactly the kind that gets filled in at 2am on D7.

**Options considered** — (a) add it now, batched; (b) add it now, on its own; (c) defer to
D8–11 and let the report renderer pick.

**Pros and cons** — (a) and (b) are the same code. The difference is that this touches the
frozen contract, so it regenerates the OpenAPI dump and the TypeScript types and forces a
frontend rebuild across the 12.5-hour handoff. **Two other contract edits are already queued
behind that same cost** — D-020's `ModelProvenance` replay fields and D-030's two `ErrorCode`
members. Three separate regenerations is three handoff interruptions for one change's worth of
value. (c) is the deferral, and it fails on a detail: with two candidates verified the renderer
has no basis to choose, so deferring the field defers the decision to whoever writes the
report, at the worst possible moment.

**Cost implications** — one field and a validator. **The batching is the decision:** D-020,
D-030 and this land as **one** contract change, one regeneration, one handoff note.

**Security implications** — minor and real. An evidence bundle that shows two verified patches
without naming the one we stand behind invites a judge to pick the wrong one and ask why we
shipped it.

**Scalability implications** — none.

**Final approval authority** — CTO (technical).

---

## D-049 · Provenance defaults point at the humbler claim; and we stop writing aspiration as achievement · 2026-08-07 · CTO

Recorded on the back of BUG-007/008 and #103, which were sent for the record. Both deserve a
standing rule rather than a one-off fix, because this is the **fourth** instance of the same
pattern.

**Part 1 — defaults.** `ModelProvenance`'s replay fields default to "live" and
`GateResult.evidence_source` defaults to `TOOL_EXECUTION`. **A default is a claim the system
makes on your behalf when you say nothing**, and every provenance default here currently
points at the *stronger* claim — model-generated rather than replayed, tool-executed rather
than asserted. That is the wrong direction, and it is the direction that produces an overclaim
by omission on the one night nobody is checking.

**Rule:** every provenance, evidence-source and measurement field defaults to the weaker
claim, or has no default and must be stated. This is D-008 (provenance labelling), D-009 (gate
disclosure) and D-010 (unmeasured targets) generalised: the system never overstates what it
did, including by staying silent. **[Δ #6, batched per D-048]**

**Part 2 — the wording, and the pattern.** QA reports that the #87 PR body calls the provenance
rules *"structurally impossible"* to violate, and then reproduced violations. **Fix both**, and
fix the sentence today, because that wording reaches a slide.

More importantly, that is now four:

| Where | Claimed | Actually |
|---|---|---|
| CTO review, invariant A | "the system cannot reach the internet" | startup validation only — corrected in D-028 |
| Architecture spec §8.13 | "signed-by-hash" | hash-manifested; a hash is not a signature — D-025 |
| Design system | `[ SESSION SECURE ]` over `http://localhost` | retired — D-039 |
| #87 PR body | "structurally impossible" | reproduced by QA in two places |

Four different seats, including mine, all writing the aspiration in the tense of the
achievement. This is not four coincidences, it is a habit, and it is the single most dangerous
one available to a team whose entire pitch is *"we do not overstate what the tools proved"*.

**Standing rule, applying to every seat and every artifact that leaves the repository:** a
property is described as enforced only when a **named test** demonstrates it. Until then the
wording is "intended", "validated at startup", "by convention" — whichever is true. Reviewers
should treat "impossible", "cannot", "guaranteed" and "proven" as requiring a test reference
in the same sentence.

**Part 3 — #103, the interpreter-dependent OpenAPI dump.** QA's call is right and the reason
it gives is the right reason: a version pin holds only until someone runs it locally on a newer
interpreter, which is literally how this was found. Fix it in the exporter — normalise the
generated document — not in `requirements.txt`.

The cost is larger than it looks and it is worth naming. The committed dump is the contract
seam (#6), and its CI diff is the mechanism that makes a contract change break the build
instead of the demo. **A check that fails for reasons unrelated to the contract is worse than
no check**, because the first time it cries wolf someone adds a bypass, and after that a real
drift sails through. Acceptance criterion: the dump is byte-identical across 3.12 and 3.13, and
CI proves it on both.

**Part 4 — the SSE probe.** QA is right that a 16-stream probe against a stub closing after
0.5 s is not a pass, and saying so rather than claiming the coverage is the correct behaviour.
The test that would settle it does not need #12: hold N connections open, where N is **twice**
the ASGI thread-pool size, and time an ordinary API request issued alongside them. Pass is the
ordinary request completing under one second. `infrastructure/scripts/testing/sse-stub.py`
already exists; making it *hold* rather than close is a small change and it answers the
question days earlier than waiting for real events. **[Δ #13]**

**Final approval authority** — CTO (technical) for Parts 1, 3 and 4; Part 2's standing rule
applies to every seat, and `cybersecurity` and `qa-engineer` should both treat a breach of it
as a finding.

---

## D-050 · One endpoint policy, in `contracts/`, and the gateway's implementation is the survivor · 2026-08-07 · CTO

**Decision** — The endpoint policy is consolidated into a single module in `contracts/`,
imported by both the model gateway and the control API. `services/model-gateway/gateway/endpoint_policy.py`
(PR #111) is the implementation that survives; `contracts/model_policy.py` is replaced by it,
not merged with it. The 60-case bypass table moves with it and becomes the module's own test.

**The argument is not "duplication might drift". The duplication has already produced a hole,
and the hole is in the layer that gates boot.**

`contracts/checks.py::check_model_endpoints` calls `assert_local_inference_endpoint` from
`contracts/model_policy.py` and raises a Django `Error`, which stops `manage.py check`,
`runserver` and ASGI startup. That is the boot gate for invariant A — and it is wired to the
**weaker** of the two implementations. Concretely, today:

```
GATEWAY  mismatches: 0 of 60
CONTROL  mismatches: 34 of 60
```

`SMALL_MODEL_BASE_URL=https://my-llm-proxy.internal/v1` **boots cleanly**, because the control
API's check waves it through — and is then refused by the gateway at call time, mid-mission.
Of the two possible arrangements that is strictly the worse one: the process starts, the
operator believes the configuration is good, and the failure surfaces during a run on D6
rather than at startup. D-028 already established that this invariant must fail as early and
as structurally as available; a stricter check sitting downstream of a looser boot gate is the
opposite of that.

**A second reason, and it is the one that would have bitten later.** The C5 / L3
single-inference-client test walks `apps/`. The gateway sits in `services/`, so **the test
that enforces "exactly one module may construct an inference client" does not see the module
that constructs the inference client.** Whatever else is decided, the enforcement scope has to
cover wherever that client actually lives.

**Options considered** — (a) leave both, fix `contracts/model_policy.py` separately to match;
(b) gateway imports the control API's module; (c) control API imports the gateway's module;
(d) one module in `contracts/`, imported by both.

**Pros and cons** — (a) is two implementations of one invariant maintained in lockstep by
hand, which is not an invariant, it is a coincidence with good intentions; the 34-of-60 number
is what that looks like after two days. (b) makes the boot gate the weaker rule permanently.
(c) is forbidden by C5 — `api` must not import `gateway` — and correctly so. (d) is what C5
permits and, as the orchestrator read it, what C5's own docstring describes: both sides may
import `contracts`. The prohibition is directional and only one direction is barred.

**Cost implications** — one file move, one deletion, one import change on each side. The test
comes with it.

**Security implications** — this is the decision. One implementation, one boot gate, one
60-case table, and the strictest available rule at the earliest available moment.

**Scalability implications** — none.

**Condition — the consolidated module must stay importable without Django.** Verified today:
`contracts/model_policy.py` → `contracts/errors.py` → `contracts/enums.py` → stdlib. **Zero
Django anywhere in that chain**, which is exactly why sharing it is clean and why it must stay
that way. If the module ever acquires a `ninja.Schema` or `django.conf` import it stops being
importable by the gateway, and the duplication returns by necessity rather than by choice. Add
`test_endpoint_policy_imports_without_django` — a subprocess import with no
`DJANGO_SETTINGS_MODULE` — so that regression is caught by a test rather than by someone
re-deriving this reasoning in three days.

**Condition — the bypass table gates both columns.** CI currently drives its exit code from
the gateway column only; the control-API column is *reported*, not gated. After consolidation
there is one column and it gates. A measurement nobody can fail is a document.

**Note on authorship.** The `ml-infra-engineer` seat declining to edit another seat's file was
right, and flagging the two divergences rather than quietly winning was more right. The seat's
reading of C5 was over-cautious — C5 bars `api → gateway`, not `gateway → contracts` — but
over-cautious on a security boundary, surfaced for a ruling, is the correct failure direction.

**Final approval authority** — CTO (technical); **`cybersecurity` holds the veto** on §4 of the
architecture spec, and this is squarely inside it. The seat reviewing #110 should get the same
table.

---

## D-051 · Where two implementations of an allowlist disagree, the stricter one wins · 2026-08-07 · CTO

**Decision** — Both of the gateway's deliberate divergences are adopted. Private DNS suffixes
no longer pass on the suffix alone, and the reserved documentation ranges are denied. The three
currently-`ALLOWED` control-API cases that flip to denied are **expected output, not
regressions**.

**The general rule, stated once so it does not need re-arguing.** For an allowlist guarding a
hard invariant, when two implementations disagree the stricter one wins by default and the
burden of proof sits on the looser one. The asymmetry is not close:

| | Cost |
|---|---|
| False negative — a legitimate local endpoint refused | caught at boot, fixed by naming it in one environment variable |
| False positive — a hostile endpoint permitted | repository content leaves the building, discovered never |

**On the private suffixes.** This retires my own wording in D-028, where I wrote that the
name-based check *"proves the hostname is inside the boundary"*. It does not even do that.
Nobody owns `.internal`, `.local`, `.svc` or `.test`, and the case that settles it is
`api.openai.com.evil.test`, which the old rule permitted. The correct model is the gateway's:
**declaration grants trust, not the suffix.** `MODEL_SERVICE_NAMES` is the operator naming what
is inside the boundary, and `_DECLARABLE_SUFFIXES` stops the declaration itself from becoming a
one-line hole.

**On the documentation ranges.** Adopted, and the PR's own sentence is the best argument in it
and should survive into the security review verbatim: *"not globally routable" and "inside our
trust boundary" are different properties and only the second one is the question being asked.*
The old module conflated them, which is the same root cause as `169.254.169.254` passing —
already fixed, same lesson, second instance.

**The three flipped cases are a required declaration, not a breakage.** The compose service
name for the model host keeps working the moment it is listed in `MODEL_SERVICE_NAMES`. That
is a configuration change surfaced at startup, which is precisely the cheap side of the table
above. It must be in `.env.example` and in the D1 setup path before #12 needs a model, so that
the first person to hit it reads a declaration prompt rather than debugging a refusal.

**Options considered** — (a) adopt both tightenings; (b) adopt the documentation ranges only,
keeping suffix-passing for developer convenience; (c) keep the looser rule and revisit after
the competition.

**Pros and cons** — (b) is the tempting middle and it keeps the exact hole #78 was filed
about. (c) trades the project's single most-repeated product rule for a small amount of setup
friction. (a) costs one environment variable.

**Cost implications** — one `MODEL_SERVICE_NAMES` entry, documented once.

**Security implications** — closes `my-llm-proxy.internal`, `evil.internal`, `sneaky.svc`,
`redirector.local` and `api.openai.com.evil.test`, all of which pass today.

**Scalability implications** — none.

**Final approval authority** — CTO (technical).

---

## D-052 · `services/model-gateway/` is a package-location divergence from D-026; corrected, but not on the critical path · 2026-08-07 · CTO

**Raised here because nobody raised it, and consolidating the policy would have papered over
it.** D-026 (ratifying DR-C) placed the model gateway as a Python package **inside**
`apps/control-api/`, and the architecture spec §4.1 L3 named the path `apps/control-api/gateway/client.py`.
PR #111 builds it at `services/model-gateway/`, with its own `pyproject.toml`,
`requirements.txt` and `pytest.ini`.

**Decision** — D-026 stands; it is not overturned. The gateway package moves to
`apps/control-api/gateway/` and the two requirements files merge. **This does not block
#111**, and it is scheduled as a follow-up with an owner and a date rather than held over a
merge — the same standard I required of others in D-045…D-048, applied to my own decision.

**Is it actually a violation?** Partly, and being precise matters. There is no Dockerfile and
no compose entry, so it is not yet a second *process* — which is what D-026's security
argument was about ("a second process that must both hold repository context and reach the
model"). It is a **packaging** divergence, not yet a deployment one. That is why it is a
follow-up and not a blocker.

**Why it still has to be corrected, in order of weight:**

1. **The C5 test walks `apps/`.** The enforcement scope for the single-inference-client rule
   excludes the directory containing the inference client. This is the one that matters and
   D-050 fixes the policy half of it; the client half needs the move.
2. **Two requirements files are two dependency sets.** The gateway is the single component
   that must never acquire an outbound HTTP dependency by accident. One dependency file is a
   control surface; two is a place for one to appear unreviewed.
3. **A separate `pytest.ini` means the control-API test run does not execute the gateway's
   tests.** Post-consolidation, a change to the shared policy module would not run the 60-case
   table unless CI happens to invoke both suites. That is the same fragility D-049 Part 3
   named for the OpenAPI dump: a check that can silently not run is worse than one that fails.

**What is genuinely good about the current layout, and must be preserved through the move:**
the gateway's tests skip cleanly and *visibly* (`-rs`) when `apps/control-api/` is absent. A
skip nobody sees is a test that quietly stopped asserting — that instinct is right and the
merged layout should keep it.

**Options considered** — (a) move now, blocking #111; (b) move as a scheduled follow-up;
(c) overturn D-026 and keep `services/`.

**Pros and cons** — (a) costs the ml-infra seat rework in the middle of D2–D3 for a
correctness gain that D-050 already delivers most of. (c) was argued and rejected on security
grounds in D-026, and nothing in #111 is new evidence against that reasoning — the PR did not
argue for the location, it simply used it. (b) takes the urgent half now and the tidy half on a
date.

**Cost implications** — a directory move and one requirements merge. Hours, not days.

**Security implications** — item 1 above is the security content; the rest is hygiene.

**Scalability implications** — none. D-026's reversibility clause is unaffected.

**Owner and date** — `ml-infra-engineer`, **by end of D4 (2026-08-10)**, tracked as a new
issue. If D4 is under pressure it slips to the D8–11 buffer, and the C5 test scope is widened
to cover `services/` in the meantime as a one-line stopgap — **that widening is not optional
and lands with #111**, because it is the part that is actually load-bearing.

**Final approval authority** — CTO (technical).

---

## D-053 · One subprocess jail, in `packages/sandbox/`, built from #113's implementation · 2026-08-08 · CTO

**Decision** — `services/sandbox/jail.py` (PR #113) is the canonical implementation. It moves
to `packages/sandbox/` rather than staying in `services/`. `adapters/cpp/jail.py` (PR #120) is
retired; `adapters/cpp/pipeline.py` and `workers/baseline/run.py` import the consolidated
module instead. `#120`'s D3 critical-path work — #16/#17/#27, everything except its own
`jail.py` and `tests/test_jail.py` — is **not blocked** and merges on its own schedule.

**Read by direct comparison, not a bypass table.** This is not last night's `model_policy` /
`endpoint_policy` split — there is no 60-case adversarial table to run, because a resource
jail is not an allowlist and "wrong" here mostly means "untested" rather than "bypassed". So
the ruling rests on reading both, and the difference is not close:

| | #113 (`services/sandbox/`) | #120 (`adapters/cpp/`) |
|---|---:|---:|
| `jail.py` | 548 lines | 351 lines |
| `test_jail.py` | 370 lines, 23 tests | 123 lines, 10 tests |
| Error taxonomy | `LimitKind` enum; distinct `CpuExceededError` / `MemoryExceededError` / `WallClockExceededError` / `CancelledError`, each independently raisable and testable | one `JailEscape`, the rest generic `AdapterError` subclasses for build/toolchain concerns unrelated to the jail |
| Escape coverage | path outside jail, symlink escape, cwd outside jail — each its own test | cwd outside jail, symlink escape — parity on the two that matter most |
| Cleanup / cancellation | tested on success, on failure, on cancel, cancel-from-another-thread, and refusal to accept further commands after cancel or close | not covered |
| Orphan handling | `test_timeout_kills_grandchildren_leaving_no_orphans` — the property the module's own header calls out as the reason for `os.setsid()` | forked-child killed, not specifically tested for grandchildren |
| Documented property→test table | yes, in the module docstring, matching D-049's standing rule verbatim: *"every property below is claimed only where a named test demonstrates it"* | described in prose, not tabulated against tests |
| `contracts` coupling | none — `ISOLATION_MODE` is a **mirrored string constant** with a comment explaining why, matching D-050's condition exactly | none — same discipline, correctly anticipates D-026 in a comment |

Both are careful, both are Django-free, both correctly treat this as the #81 fallback and not
the #15 container path. #113 is simply the more complete implementation of the same design,
and it is also the one actually filed against #81's scope. There is no case here for keeping
#120's as the base and porting properties into it; it is the smaller document.

**On location — this is not a repeat of D-052.** D-052 moved the model gateway *into*
`apps/control-api/` because the gateway is the module that must live inside the
single-inference-client enforcement boundary (C5) — a security argument tied to one specific
process. The jail has no such tie. Its consumers are `adapters/cpp/` and, next,
`workers/fuzzing/` (#28) — both worker-side, neither inside the Django project, and forcing
them to import out of `apps/control-api/` would be backwards: primitive OS-level isolation
should not depend on a specific web application's package layout.

`packages/` is the existing answer to exactly this shape of problem — `packages/schemas/` is
already the shared dependency root for `apps/command-center/`, and this very PR (#113) already
puts Python utilities in `packages/test-fixtures/` without a Django dependency. The original
`docs/04-development/35-project-folder-structure.md` even reserved a `packages/policy/` slot
for a cross-cutting concern of this shape — not renamed, because "policy" already denotes two
other things in this codebase (`contracts/model_policy.py`'s successor and patch policy), and
reusing established vocabulary (`services/sandbox/`, `SANDBOX_POLICY`, #81, #15) costs nothing
and avoids a collision. `packages/sandbox/` is also the right home for #15's container path
when it lands, per #113's own README, which already frames the split as one component with two
implementations behind `IsolationMode`.

**Options considered** — (a) keep both, #120 wins because it merges first; (b) keep both,
#113 wins because it is more complete, #120's jail.py deleted in place at `adapters/cpp/`;
(c) consolidate into `packages/sandbox/`, built from #113.

**Pros and cons** — (a) throws away the better-tested implementation for the accident of merge
order. (b) fixes the completeness problem and leaves the location problem: `services/sandbox/`
is a name this project has already twice discovered means "an ASGI-adjacent Django-project
module" (`services/model-gateway/` → `apps/control-api/gateway/`, D-026), and a bare resource
jail imported by two worker-side packages does not belong inside `services/` any more than
inside `apps/`. (c) fixes both at once and costs a directory move.

**Cost implications** — a directory move, an import-path update in two files
(`adapters/cpp/pipeline.py`, `workers/baseline/run.py`), and one CI path update. Hours.

**Security implications** — neutral to positive. Consolidating onto the more thoroughly tested
implementation, with its orphan-process and cancellation guarantees, is a strict improvement
for the same reason D-050 was: a weaker implementation sitting anywhere reachable is a weaker
implementation someone will eventually reach.

**Scalability implications** — none.

**Sequencing, so #120's critical-path work is not held hostage.** `packages/sandbox/` is a
move plus one field addition (D-054) on top of already-merged-quality code — it is the smaller
and faster-moving piece. It merges first. `#120` then drops `adapters/cpp/jail.py` and
`adapters/cpp/tests/test_jail.py` and repoints its two call sites before merging. If that
reordering costs more than a few hours because of D3 schedule pressure, `#120` may merge with
its own `jail.py` as a **declared interim measure**, with a same-day follow-up issue to delete
it and repoint the imports — the same standard D-052 set for its own packaging divergence, not
a looser one for someone else's.

**One integration detail flagged, not resolved here.** The two implementations use different
vocabularies at the API surface — `JailPolicy` vs `JailLimits`, a `LimitKind` enum vs plain
result fields. Reconciling `adapters/cpp/pipeline.py`'s and `workers/baseline/run.py`'s call
sites to the surviving shape is real work, not a rename, and it is `security-research-engineer`'s
and `compiler-toolchain-engineer`'s to do together — the public API of the surviving module is
not something I am dictating past what D-054 requires of it.

**Final approval authority** — CTO (technical).

---

## D-054 · `limits_applied` is adopted, and it is computed by trying, not by naming the platform · 2026-08-08 · CTO

**Decision** — #120's design — a queryable field on the result reporting which resource
limits actually took effect, rather than a hard `skipif` in the test suite — is adopted and
folded into the surviving implementation from D-053. Its **computation method is not**
adopted as written and is replaced with #113's already-existing attempt-and-catch pattern,
made visible per run instead of only through a separate diagnostic call.

**Why the field is worth keeping — the coordinator's instinct is correct.** #113's own author
independently found the same fact #120 documents — `RLIMIT_AS` does not reliably apply on
Darwin — and encoded it as `pytest.mark.skipif(IS_DARWIN, ...)` with a comment asking a future
reader to remove the skip if Darwin ever starts honouring the limit. That is honest about the
test, and it is invisible in the one place a judge or an operator would actually look: the
evidence bundle from an actual run. A skip in a test file answers "does this repository know
about the platform gap"; a field on the result answers "did *this run* have the protection it
claims to have" — and only the second question is the one D-049's standing rule cares about.

**Why the computation is wrong as submitted.** `_limit_names()` in #120 derives its answer
from `sys.platform != "darwin"` — a static fact about the machine, checked before any
`setrlimit` call is attempted. That is the same category of error #113's own module docstring
calls out about `setrlimit`'s return value: *"setrlimit succeeding proves nothing."* The
platform-name check is one level worse — it does not even call `setrlimit` and check the
outcome, it assumes the outcome from the platform string. Two concrete cases it gets wrong:

- **A locked-down Linux CI runner** (a container with a parent cgroup or an already-lowered
  hard limit) can refuse `RLIMIT_AS` or `RLIMIT_NPROC` for reasons that have nothing to do with
  Darwin. `_limit_names()` reports these as applied because the platform is not `"darwin"`.
  That is a false claim of protection, which is the direction this project has spent the last
  two rulings closing off, not opening.
- Conversely, if a future macOS release does start honouring `RLIMIT_AS` — #113's own skip
  comment anticipates exactly this — `_limit_names()` would keep reporting it as *not* applied
  on Darwin, understating a protection that is actually there. Less dangerous than the first
  case, but it is the same root cause: a name is not a measurement.

**The fix, and it is small.** #113's `_run_command` already attempts `RLIMIT_AS` and
`RLIMIT_NPROC` per limit inside a `try`/`except (ValueError, OSError): pass` in the child, with
a comment pointing the caller at the separate `probe_limits()` function for exactly this
question. Change the child to record which of those attempts succeeded — a bitmask or a small
tuple written to the pipe already carrying the exit status back to the parent — and populate
`JailResult.limits_applied` from it, rather than from a platform check. `probe_limits()` stays
as the pre-flight, ahead-of-any-mission diagnostic; `limits_applied` becomes the per-run,
after-the-fact record. They answer different questions and both are worth having.

**Options considered** — (a) adopt #120's field and its platform-name computation as written;
(b) keep #113's design, add `limits_applied` computed from the real attempt outcome;
(c) drop the field, keep only `probe_limits()`.

**Pros and cons** — (a) ships a field whose name promises more than a platform check can
deliver, and the CI runner case above is not hypothetical — several of this project's own
runners are containerized. (c) loses exactly the property the coordinator is right to want
kept: a reader of one run's evidence, not the test suite, learning what protected that run.
(b) costs recording one already-computed fact instead of discarding it.

**Cost implications** — under an hour: the try/except already exists, only the outcome needs
to survive the child-to-parent boundary it already crosses for the exit code.

**Security implications** — this is the same principle as D-049's standing rule applied to a
resource limit instead of a provenance claim: a property is reported as held only when it was
actually observed to hold, not inferred from a fact adjacent to it.

**Scalability implications** — none.

**Final approval authority** — CTO (technical).

---

## D-055 · The rule that produced yesterday's `model_policy` consolidation now has a name, and it applies going forward · 2026-08-08 · CTO

Recorded because this is the second time in one day the same shape has appeared, and the
second occurrence is what makes it a pattern rather than an incident.

**The shape:** two seats, working from the same issue or the same invariant, in parallel
branches neither can see, produce two implementations of one boundary-enforcing rule. Both are
careful. Neither is wrong in isolation. The danger is not either implementation — it is that
the system as merged would enforce **whichever one is imported from the call site that happens
to run first**, which is not a decision anyone made.

**Standing instruction, effective now, for every seat:** before implementing a boundary-shaped
concern that D-026 or D-028 already named as cross-cutting — egress policy, isolation,
authorization, verification gating, provenance labelling — check `.project/decisions.md` and
the open PR list for an existing or in-flight implementation before writing a second one.
Where two exist anyway despite that check, as here, **flag the duplication in the PR body
rather than silently choosing a side**, exactly as both seats did today. That habit is what
turned two potential silent regressions into two cheap rulings instead of two retrofit costs
discovered on D6.

**Not a new process, a naming of the existing one.** D-050 through D-052 already did this for
`model_policy`. This record exists so the *next* occurrence — and there will be one, this is
the third boundary-shaped module in as many days — gets checked against a named precedent
instead of re-discovered from scratch.

**Final approval authority** — CTO (technical); this is process guidance, not a technical
control, and does not require `cybersecurity` sign-off the way D-053/D-054 do.

---

## D-056 · #113 merges now; SEC-38 and SEC-35 are binding conditions on #28, not on this PR · 2026-08-08 · CTO

**Decision** — `packages/sandbox` merges with SEC-38 (MEDIUM) and SEC-35 (MEDIUM) open,
tracked as **blocking Definition-of-Done items on #28** rather than as a reason for a third
fix-and-reverify pass on #113. `cybersecurity`'s round-3 verdict is PASS WITH CONDITIONS, no
Critical, and the seat that found both explicitly routed the timing call here rather than
asserting a block — that is the correct use of the veto: it is held for Criticals, not spent
gating a merge order it has no better information than the CTO to decide.

**What was actually re-verified, read in full before ruling, not summarized from the
coordinator's message.** `docs/09-company/08-security-review.md` §18, on
`review/security-sandbox-jail`:

- **SEC-33, the reason D-053 chose this implementation, is closed for its primary vector** —
  the original `os.setsid()` PoC, rerun with and without a real reaper (`docker run --init`),
  plus four lifecycle-timing variants (immediate, mid-flight, near-boundary, at-boundary). All
  held. The fix's own account of a zombie-vs-alive false positive was independently reproduced
  by polling `/proc/<pid>/stat` for six seconds, not accepted on the strength of the report.
- **SEC-34, SEC-36 — closed, re-run against the actual CI shell block and the actual test,
  not re-read.**
- **SEC-38 (new) — a probabilistic race under rapid, repeated fork-and-detach**, roughly
  1-in-10 to 1-in-15 iterations, reproducing at the module's real default
  `kill_grace_seconds=5.0`. Root cause: the final sweep's re-walk is anchored on the jail's own
  child pid, which is itself already dead by the time of that walk, so a descendant that
  reparents in the gap between two 0.1s poll iterations can go briefly invisible — one level
  deeper than the bug SEC-33's fix closed, found by attacking the fix's own retry mechanism
  rather than the original vector again.
- **SEC-35 (reopened) — the fix's own test uses `dd`, which does not ignore `SIGXFSZ`; CPython
  does, by default, confirmed both inside and outside the jail** (`signal.getsignal(SIGXFSZ) ==
  SIG_IGN` at interpreter start). A real `RLIMIT_FSIZE` stop against a Python-based target
  produces a plain `OSError`, not the signal, and `limit_hit` falls through to `NONE` — the
  original bug, for a target class this project's own stack makes plausible rather than exotic.

**Why merge-now-gate-on-#28 is correct, not merely convenient.**

1. **Neither finding is reachable on the path that is waiting to merge.** Confirmed by
   inspection: nothing on `main` calls `packages.sandbox` today. `#16`/`#17`/`#27`'s repointed
   `adapters/cpp/pipeline.py` and `workers/baseline/run.py` invoke `Jail.run()` against
   `cmake`/`ctest` — an authored, non-adversarial build, not a process that forks a detached
   child every 20ms for the specific pattern SEC-38 needs, and not one that writes past the
   512 MiB `max_file_bytes` default in ordinary operation, which is what SEC-35's
   misclassification requires as a precondition. `#28`, the fuzzing worker, is exactly the
   context where a target's behavior is adversarial by construction and both preconditions
   become live. Neither issue is exploitable on the merged path; both are exploitable on the
   path that has not been built yet.
2. **SEC-35 does not weaken the isolation invariant.** The jail still stops the process at the
   limit — the property `#81`/D-053 exist to guarantee is intact. What is wrong is the
   *evidence*: a run correctly stopped is misreported as stopped for no recorded reason. That
   is an accuracy defect in the gate-matrix-adjacent telemetry, not an escape, and it belongs in
   the same category D-049's standing rule already treats seriously without treating as a merge
   blocker — a claim can be wrong without being a security hole.
3. **Cost of waiting is not free.** `#16`/`#17`/`#27`'s toolchain repoint and `#71`/`#81`'s
   fixture work are both idle behind this PR while D3 runs. A third fix-and-reverify cycle for
   two findings that require a precondition nothing on the critical path produces is schedule
   spent defending against a threat that does not yet exist, at the direct cost of the day it
   does need to exist by.

**Conditions, and they are binding rather than advisory — the same standard D-046 set for
`contracts/` and D-052 set for the gateway's package location.**

1. **`#28`'s Definition of Done includes closing SEC-38 and SEC-35, re-verified by
   `cybersecurity` specifically, not merely fixed and self-reported.** A named regression test
   for **rapid repeated** detachment (not a single-detachment case — that is what closed SEC-33
   and is insufficient here by the review's own finding) and one for a **Python-based** target
   hitting `RLIMIT_FSIZE` (not `dd` — that is what closed the wrong half of SEC-35). `#28`
   cannot merge without both. This is filed on the issue directly, not left to be rediscovered
   from a security-review doc a future implementer may not open.
2. **The module says so at the point of use.** `packages/sandbox/jail.py`'s own docstring
   already carries a "read this before using it for anything" section with a property→test
   table (the discipline D-049 named as the standing rule and this module was the first to
   follow). Two rows are added: SEC-38 and SEC-35, each pointing at the tracking issue, each
   stating in one line what is not yet true. A caller reads the risk where the code is, not
   only in a document three links away.
3. **No caller may invoke this jail against generated or fuzzer-derived input before #28
   closes both.** This is already true by construction — `#28` is the only thing that would do
   so and it is the thing gated — but stating it here means a future shortcut ("just point the
   fuzz worker at the existing jail for now, we'll fix the race later") is a decision that has
   to be argued against this record, not made quietly.

**On the review process itself, worth naming rather than passing over.** This is the second
time in this project that a re-verification pass has caught its own first-pass overclaim before
it reached a decision — the fix report said "all four fixed"; the review's own re-attack found
two of four only partially true, and said so in its own verdict rather than letting the stronger
claim stand. That is D-049's standing rule operating exactly as intended, on the reviewer's own
prior work as readily as on anyone else's. Worth pointing at when the next seat asks whether the
rule is real.

**Options considered** — (a) third fix pass, re-verify, merge after; (b) merge now, SEC-38/
SEC-35 tracked informally as follow-up issues with no binding relationship to #28; (c) merge
now, SEC-38/SEC-35 as hard Definition-of-Done gates on #28 specifically, stated in the module
and on the issue.

**Pros and cons** — (a) is correct in the abstract and wrong for this schedule: it spends D3
time defending a precondition that does not exist on the path waiting to merge. (b) is the
failure mode D-045's "an unruled condition is not a legitimate answer" reasoning was written
against — a follow-up issue with no merge relationship to the thing that makes it dangerous is
exactly how a condition survives as a comment and not as a gate. (c) costs two sentences in a
docstring and one line on an issue, and it is what makes "gate on #28" true rather than stated.

**Cost implications** — none beyond the docstring note and the issue update, both today.

**Security implications** — this is the decision. Both findings are real and neither is
downgraded in severity by this ruling; what changes is when they must be closed, not whether.

**Scalability implications** — none.

**Final approval authority** — CTO (technical); `cybersecurity`'s PASS WITH CONDITIONS stands
and this record is the disposition of those conditions it asked the CTO to make.

---

## D-057 · Dependency and compiler health get `NOT RUN` gate-style treatment outside the verdict matrix · 2026-08-16 · `ui-ux-designer`

**Decision** — In the Analysis Rail's new "dependency health" and "compiler health" rows
(#25), an entire class of check that never ran renders with the same visual weight as an unrun
*gate* in a verdict matrix — `--bd-state-not-run`, the word `NOT RUN`, a mandatory inline
reason — even though neither row is a member of the five-gate `VerificationRecord` schema DS-03
was written about. Full spec in
[`13-cut-pullback-design-spec.md`](13-cut-pullback-design-spec.md) §1.3.

**Options considered** — (a) apply D-023's literal rule: anything outside a verdict matrix is an
unproduced *value*, rendered as a quiet em dash in `--bd-text-secondary`; (b) extend DS-03's
gate-style treatment to these two rows specifically; (c) omit the rows entirely until a real
producer exists.

**Pros and cons** — (a) is the literal reading of DS-03's own review question ("is this in a
gate matrix?" — no) but produces exactly the failure this project has a standing rule against:
a capability that was never wired, sitting next to ones that were, rendered in the system's own
colour of de-emphasis. A skimming reader cannot tell "we looked and found nothing" from "we
never looked" if both are quiet grey. (b) costs one extended rule and keeps the distinction
checkable — a reviewer's question becomes "is this disclosing a check that could have run and
did not," which is broader than "is this in a `VerificationRecord`" but is the same underlying
concern D-009 was written for. (c) is the safest reading of "don't fabricate a state with no
producer," but an *omitted* row is the one thing D-009 was written to prevent — a missing line
in a panel titled "Analysis Rail" reads as "there was nothing to check," which is false; there
was something to check and it was never built.

**Cost implications** — none; one shared component (`NotRunCoverageRow`) for both rows.

**Security implications** — positive, same family as D-009 and D-023: prevents an unbuilt
capability from reading as a clean result by omission or by de-emphasis.

**Scalability implications** — none. If a dependency scanner or compiler-warning capture is
ever built, the row's state machine gains real states without changing its visual grammar.

**Recommendation** — (b), as implemented.

**Final approval authority** — CTO, since it reconciles this document to DS-03 the way DS-03
itself reconciled the design system to the architecture spec; `product-manager` for the
user-facing framing (a panel disclosing what it does *not* cover is a scope statement).

---

## D-058 · Presentation mode is re-admitted from `CUT` for internal rehearsal only, gated at build time · 2026-08-16 · `ui-ux-designer`

**Decision** — #52 (presentation mode) is specified for pullback, scoped strictly to
pre-finale rehearsal, screenshots and internal walkthroughs — never the finale, never in front
of a judge. It is enabled only by choosing a distinct build artifact
(`command-center:presentation`), defaults off, cannot be toggled at runtime, and independently
refuses to activate if a real (non-fixture) mission is bound to the page. Disclosure is a
persistent top-strip chip (per `04-design-system.md` §2.6, unchanged) plus a new full-bleed
diagonal watermark so the disclosure survives a cropped screenshot. Full spec in
[`13-cut-pullback-design-spec.md`](13-cut-pullback-design-spec.md) §2.

**Options considered** — (a) leave #52 cut, as `10-fallback-ladder.md` §2.5 currently states
("no presentation mode to hide behind"); (b) re-admit it as originally scoped in
`01-vision-and-p0-cut.md` P1-7 — a competition presentation toggle, reachable from the running
app; (c) re-admit it narrowly, gated at build time, for rehearsal only, with the finale doctrine
in §2.5 left completely unchanged.

**Pros and cons** — (a) is the safe, already-decided position and is what the orchestrator's
task explicitly asked to reconsider given schedule room; leaving it cut forfeits pullback work
that was requested. (b) is what P1-7 originally meant and is the version that is genuinely
dangerous: a toggle reachable from the running app is a toggle that can be reached
accidentally, which is the specific failure `10-fallback-ladder.md` §2.5 was written to prevent
("it looks exactly like a real mission, which is what makes it useful in week one and dangerous
at hour 30"). (c) gets the rehearsal value P1-7 wanted without reopening the finale risk: the
mock surface only exists in a build artifact nobody would run at the finale, and even inside
that build it refuses to pretend to be a real mission. The cost is two independent gates to
build and test rather than one flag.

**Cost implications** — one additional build target/env file; no runtime cost in the finale
build, which does not import the presentation-mode code at all.

**Security implications** — this is the load-bearing part of the decision. The gap this closes
is real: today `sse_replay.py`'s own safeguards (loopback bind, header, SSE comment) are
server-side only and invisible in the rendered UI, so a tired operator reusing it for a quick
look has no on-screen reminder. The two independent gates (build artifact choice + real-mission
refusal) are what make "cannot be enabled accidentally during a real mission" a checkable
property rather than an assertion, per D-049. `10-fallback-ladder.md` §2.5 and §4 are otherwise
completely unchanged by this decision — the finale still runs the artifact that does not
contain this code at all.

**Scalability implications** — none.

**Recommendation** — (c), as implemented. `cybersecurity` should review the build-time
exclusion (§2.7's acceptance criteria in the design spec) before this is treated as shipped,
since "the code is absent from the bundle" is exactly the kind of claim D-049 says needs a named
test, not a description.

**Final approval authority** — `product-manager`, since this reopens user-facing scope that was
previously and deliberately cut; CEO if the PM judges the rehearsal/finale boundary itself needs
a business call rather than a design one. `10-fallback-ladder.md`'s finale doctrine is
unaffected and needs no re-approval.

---

## D-059 · Keyboard operability ships without reinstating the command palette or adding destructive-control mnemonics · 2026-08-16 · `ui-ux-designer`

**Decision** — #56's keyboard map (`13-cut-pullback-design-spec.md` §3) is built entirely on
`Tab`/`Shift+Tab`/`Enter`/`Space`/`Escape` and native focus order. No global command-palette
shortcut is reinstated (it stays cut per `04-design-system.md` §11), and no destructive control
(`[ CANCEL MISSION ]`, `[ EMERGENCY TEARDOWN ]`) gets a single-letter mnemonic.

**Options considered** — (a) build #56 alone, tab-and-enter only; (b) build #56 and also
reinstate the cut `CommandPalette` (`Ctrl/Cmd+K`) since a keyboard pass is already touching
every control; (c) tab-and-enter, plus mnemonic shortcuts on the bottom-strip controls for
power-user speed.

**Pros and cons** — (b) is a real temptation once every control has to be reachable by
keyboard anyway, but it is a second un-cut item riding on an authorization that named three
specific issues, not "keyboard work in general" — and the palette was cut for a stated reason
(P1-10 is basic operability, not full tooling) that this task did not revisit. (c) makes
destructive actions faster to reach exactly where speed is least wanted, and an undiscoverable
mnemonic (with no palette to list it) fails the P1-10 bar for a different reason: a shortcut
nobody can find is not "keyboard operable" in the sense the cut item meant. (a) is the literal
scope of #56 and is what a single-operator P1-10 bar actually requires — every control reachable
by `Tab`, nothing reachable by accident.

**Cost implications** — lower than (b) or (c); no new global key-handling layer.

**Security implications** — mildly positive for (a): destructive controls stay behind an
explicit focus-and-activate sequence with no shortcut path that a stray keypress elsewhere on
the page (e.g., in `AIParticleCore`'s text input) could trigger.

**Scalability implications** — none.

**Recommendation** — (a), as implemented.

**Final approval authority** — `product-manager`, since declining to reinstate a cut item is a
scope call; `cto` if a future accessibility pass argues P1-10's bar has moved.

---

## D-060 — Design brief for #154 (wiring the 7 stubbed mission routers): three non-obvious
calls made before either backend engineer starts

Posted as a comment on #154 before hiring. Full brief there; this record is the disposition
of the calls in it that are not simply "confirm what's already built."

### 1. `preflight` is non-mutating; `start` is the only endpoint of the four that calls
`orchestrator.transitions.transition()`

**Decision** — `POST /missions/{id}/preflight` reads the locked mission row and its active
authorization, runs the same checks `assert_transition` would run (authorization present /
active / covers the snapshot, adapter supported, policy limits sane), and returns
`PreflightReport` (`passed`, `checks`, `blocking_codes`) **without** calling `transition()` or
writing `Mission.state`. `POST .../start` is the sole call that drives the mission out of
`SNAPSHOTTED`/`VALIDATING` into the running workflow.

**Options considered** — (a) preflight itself drives `SNAPSHOTTED → VALIDATING` (suggested by
`EventType.PREFLIGHT_COMPLETED` already existing and firing on that target in
`orchestrator/transitions.py`); (b) preflight is a read-only report, start is the only mutator.

**Pros and cons** — (a) reuses an event type that already looks purpose-built for this and
would make the "check" and "commit" the same call, which is fewer moving parts. It also means
an operator retrying a failed preflight (fixing a policy value, calling it again) is retrying a
state transition, not a report — a second call after the first already advanced the mission
would need special-cased idempotency the schema gives no field for (`PreflightReport` has none),
where StartRequest does. (b) matches what the endpoint's name and response shape actually
promise — a report, not a commitment — and is safely re-runnable by construction, at the cost of
leaving `EventType.PREFLIGHT_COMPLETED` either unused for now or re-purposed to fire from `start`
instead.

**Cost implications** — none; this determines which of two already-planned handlers contains a
few lines of read-only checking logic, not new scope.

**Security implications** — (b) is the humbler default per the standing rule on defaults: a
"preflight" that silently commits a state change on a dry-run-shaped call is the overclaim-by-
omission shape that rule exists to catch, one level removed (a UI or script that polls
`/preflight` to display current readiness would be mutating the mission's own progress by
polling it). (a) is not unsafe — the same lock and authorization checks still run inside
`transition()` — but it is the more surprising contract for a caller.

**Scalability implications** — none.

**Recommendation / ruling** — (b). If `software-architect` or `engineering-manager` sees a
concrete reason the transition table already commits to (a) — e.g. downstream code depends on
`PREFLIGHT_COMPLETED` firing from this specific call — raise it before the transitions engineer
starts; this is a resolvable-in-five-minutes disagreement, not one to silently code around.

**Final approval authority** — CTO (technical).

### 2. `idempotency_key` on mission create is net-new implementation, not existing wiring

**Decision** — `MissionCreateRequest.idempotency_key` has no backing column and no consuming
code anywhere in the repo today (confirmed by grep across `apps/control-api`); the only
existing idempotency implementation in this area (`create_mission_snapshot`) works by content-
hash comparison, not by a key field. The create engineer must add: a migration giving `Mission`
an `idempotency_key` column with a **conditional** unique constraint (`UniqueConstraint(...,
condition=Q(idempotency_key__isnull=False))`, not a plain `unique=True`, since most rows will
have none), and the same savepoint-plus-`IntegrityError`-catch pattern already used for the
`Artifact` race in `authorization/service.py::create_mission_snapshot` — attempt the insert,
catch the unique violation, return the winning row's summary rather than a raw 500 or a check-
then-act read.

**Options considered** — (a) `if Mission.objects.filter(idempotency_key=key).exists(): return
existing` then create (check-then-act); (b) DB-level conditional unique constraint plus
catch-and-return-the-winner on the race.

**Pros and cons** — (a) is simpler to write and correct in the non-racing case, but is exactly
the TOCTOU window #154 was filed to ask about closing for mission creation specifically — two
concurrent creates with the same key both pass the `exists()` check and both create a row. (b)
costs one migration and mirrors a pattern already proven correct and reviewed elsewhere in this
codebase, so it isn't a novel pattern for a reviewer to evaluate.

**Cost implications** — one migration, reviewed as part of the create-mission PR.

**Security implications** — this is the SEC-15-adjacent case named in the assignment: creation
allowed to race with the same idempotency key produces two `Mission` rows for what the operator
believed was one request. (b) closes it at the database, the only place that's actually
race-proof.

**Scalability implications** — negligible; one indexed nullable column.

**Recommendation / ruling** — (b), mandatory. (a) is not an acceptable substitute — flag it in
review if seen.

**Final approval authority** — CTO (technical).

### 3. `orchestrator/transitions.py::transition()` doesn't translate `Mission.DoesNotExist` —
fix before wiring any of the four transition-calling endpoints

**Finding, not really a choice** — `transition()`'s own `Mission.objects.select_for_update()
.get(pk=mission_id)` has no `except Mission.DoesNotExist` (unlike `authorization/service.py::
_lock_mission`, which does and raises `MissionNotFoundError`). Every existing caller
(`authorize_mission`, `create_mission_snapshot`) pre-locks through its own guard first, so this
path has never actually been hit by a bad id in production or review. `preflight`/`start`/
`pause`/`cancel` would be the first callers to invoke `transition()` directly — a bad mission_id
would fall through to the generic `Exception` handler in `api/errors.py` and come back as an
unlabeled 500, not the `404` every other mission-not-found path returns.

**Ruling** — fix once, at the source, mirroring `_lock_mission`'s catch, before wiring the four
endpoints on top of it. This is cheaper and more correct than each of the four handlers
duplicating an existence pre-check (which would also reopen the exact check-then-act window
`authorization/service.py`'s own docstring warns against). Owned by the transitions engineer,
since it's a one-line change in the file both new endpoints they're building call into.

**Final approval authority** — CTO (technical); low enough stakes not to need a fuller record,
included here because it blocks correct behavior on day one otherwise.

### 4. #50 live rehearsal (2026-08-17) — two finale-profile infra bugs, fixed on the spot; a third, larger gap, reported not fixed

**Context** — First live attempt at the #50 D7 gate since #154 wired all 7 remaining
mission-lifecycle HTTP routers. Full findings in `.project/evidence/d7-gate-50-live-run-2026-08-17.{json,md}`.

**Decision (devops-engineer authority — environment setup, containerization)** — Fixed two
newly-discovered, small, clearly-scoped infrastructure bugs without asking, consistent with
this repo's existing pattern of fixing the two prior stale-image/TLS environment bugs on
sight:

1. `demo/repositories` was never bind-mounted into `control-api` in either compose profile,
   so `SNAPSHOT_SOURCE_ROOT`-based snapshot ingestion (the only way to hand the container a
   local demo target like `pktcfg`) had never actually worked containerized. Fixed: read-only
   mount added to both `docker-compose.finale.yml` and `docker-compose.yml`.
2. `ARTIFACT_ROOT` pointed inside the finale image's `read_only: true` filesystem; repointing
   it at a named volume then hit Docker's default root-owned-volume behavior against a
   non-root, `cap_drop: ["ALL"]` container. Fixed: named volume plus a build-time
   `mkdir`+`chown app:app` in `control-api.Dockerfile`'s `runtime` stage (relying on Docker's
   documented volume-seeding-from-image behavior), which also silently fixes the identical,
   previously-latent bug in the pre-existing `evidence` volume — never exercised before today
   because nothing had reached mission teardown/export until #154 made `start` reachable.

**Options considered for bug 2** — (a) grant `CHOWN`/`DAC_OVERRIDE` at runtime and chown in an
entrypoint script before dropping to `app`; (b) bake the directories into the image at build
time, owned correctly, and rely on Docker's volume-seeding behavior; (c) drop `read_only:
true` / `cap_drop: ["ALL"]` for these two paths.

**Pros and cons** — (a) works but requires adding an entrypoint script and granting two
capabilities at runtime that the finale hardening posture (SEC-04/SEC-38) deliberately does
not currently grant — expands runtime attack surface for a permissions problem that is really
a build-time one. (b) costs two lines in a Dockerfile already owned by devops per its own
header comment, adds nothing at runtime, and needed no capability changes. (c) would quietly
undo hardening decided upstream by prior security review specifically to fix this one
narrow gap — clearly wrong.

**Cost implications** — negligible; no new capabilities, no new base image, ~10s extra build time.

**Security implications** — (b) is a strict improvement: it closes a real-world "the app can't
even write its own evidence" failure mode without touching `cap_drop: ["ALL"]` / `read_only:
true`, which stay exactly as strict as the last security review left them.

**Scalability implications** — none; both are small named volumes.

**Recommendation / ruling** — (b), implemented. Not sent for cybersecurity re-review before
landing, on the basis that it changes zero runtime capabilities or network posture and only
affects two previously-broken, previously-unreachable write paths — flagging here so
cybersecurity can veto or wave through in the normal review cadence rather than this being
silently absorbed.

**Final approval authority** — CTO (technical); flag for cybersecurity awareness given SEC-04/
SEC-38 touch the same file.

**The gate itself still fails.** A third, much larger gap was found and left unfixed by design
per this session's explicit instructions: no HTTP endpoint or automatic process advances a
mission past `VALIDATING` — the actual stage-execution code (`workers/baseline`,
`workers/fuzzing`, `orchestrator/candidates.py`, `orchestrator/verification.py`) exists and is
tested but has no caller. This is reported, not fixed — it is the same size and review shape
as #154 itself, squarely backend/orchestration engineering, not a devops call. See the
evidence files for the full technical detail and static + empirical confirmation.

**Final approval authority (staffing the fix)** — CTO / engineering-manager, per this
project's normal issue-staffing process; not decided here.
## D-061 — Design brief for #168 (mission-stage driver: nothing advances a mission past `VALIDATING`)

Posted as a comment on #168 before hiring, same shape as D-060's brief for #154. Read
`.project/evidence/d7-gate-50-live-run-2026-08-17.md` first — this record assumes it.

**The one finding that reframes the whole brief.** #168's own text asks the driver-shape
question (sync-in-request / poller / RQ) as if it were open. It is not. `docs/09-company/
06-architecture-spec.md` §1.1 and §3, ratified in **D-024** (2026-08-07, this log) and
**D-026**, already specify a Postgres `SELECT … FOR UPDATE SKIP LOCKED` job queue, a two-
process split (`orchestrator` owns `Mission.state` and enqueues jobs; `worker` executes one
job at a time and never writes state), a full failure-mode table (§6), an idempotency/retry
contract (§3.3–3.4), and a `Job` Django model (`missions/models.py`, `JobKind`/`JobState`/
`lease_owner`/`lease_expires_at`/`deadline_at`/`MAX_ATTEMPTS_BY_KIND`) that implements that
schema exactly — migrated, tested at the model level, and **never once referenced by any
producer or consumer anywhere in the codebase** (confirmed by grep: zero hits outside
`missions/models.py` and `missions/tests/test_models.py`). This is the same shape as
`workers/baseline`/`workers/fuzzing`/`orchestrator/candidates.py`/`orchestrator/
verification.py` — real, designed, and in the `Job` table's case fully schema-complete —
with no caller. #168 is not "design the driver". It is **"finish issue #12"**: implement the
orchestrator tick loop and the worker claim/dispatch loop against a queue design that was
already decided, and wire them to the stage code that already exists. Below reaffirms the
ratified design against the current codebase rather than re-litigating it, and states what is
new work versus what is "go build what §3 already specifies."

### 1. Driver shape: reaffirm D-024; do not build RQ, do not run the pipeline synchronously

**Decision** — DB-backed lease/poll queue (`Job` table, `SKIP LOCKED`), two processes
(`orchestrator`, `worker`), per D-024/D-026/architecture-spec §1.1 and §3. Not
synchronous-in-request. Not RQ/Celery.

**Options considered** — (a) synchronous-in-request: `POST /start`'s handler runs the whole
pipeline before responding; (b) a poller/DB-queue (the ratified design); (c) RQ/Celery on
Redis, per the stale compose scaffolding.

**Pros and cons** — (a) is the simplest code to write and is exactly wrong here for a reason
independent of D-024's own argument: `workers/fuzzing/run.py`'s own default
`budget_seconds=1800` (30 minutes, and the D4 kill criterion explicitly budgets a 30-minute
fuzz window) would hold an ASGI request open for half an hour. `start_mission`'s router
already returns `Status(202, ack)` — a 202 Accepted, not a 200 — which is the API's own
existing signal that this was designed as "accepted for async processing," not "completed
inline"; (a) would make that response a lie. It would also violate the `control-api` process's
own stated boundary in architecture-spec §1.1's process table: "Must never: … Block on
anything longer than a DB query." (c) is what the current `docker-compose.finale.yml`
`worker` service's `command: ${CONTROL_API_WORKER_CMD:-python manage.py rqworker default}`
assumes, and it is dead scaffolding: `django-rq` is not in `requirements.txt`, no `redis` Python
client is either (checked directly — `requirements.txt` has no redis dependency at all, not
even a bare client), `django_rq` is not in `INSTALLED_APPS`, and the `rqworker` management
command therefore does not exist in this codebase today — the service would crash on its
first line if the `worker` profile were ever activated. Devops has already flagged this exact
gap inline in the compose file's own comment (`ARTIFACT_ROOT` block, `worker` service:
"`CONTROL_API_WORKER_CMD`'s default (`manage.py rqworker`) has no `django_rq` in
requirements.txt and was never reached by this rehearsal") — this ruling makes it
authoritative rather than a comment: **do not add `django-rq`; delete the assumption.** (b) is
what `Job`, `MAX_ATTEMPTS_BY_KIND`, and architecture-spec §3 already fully specify, costs zero
new runtime dependencies (Django's ORM has supported `select_for_update(skip_locked=True)`
natively since 2.0 — no library to add), is durable across a process restart with nothing in
memory (the exact property the "overnight contract" §3.3 exists for, and this project's own
`02-two-person-24h-cycle.md` schedule assumes it), and fits the single-mission-at-a-time
constraint P2-12 already named as the reason Redis is unnecessary here.

**Cost implications** — (b) is cheaper than (c): one fewer container image, one fewer network
service, one fewer credential (`REDIS_PASSWORD`) to manage. `REDIS_URL` is currently declared
in both compose profiles and consumed by **zero** Python code (grepped); it is vestigial and
can be dropped from the stack once this lands — flagged as a follow-up cleanup, not blocking.

**Security implications** — positive, per D-024's own analysis, unchanged: one fewer
network-reachable stateful service inside `backend`/`api`.

**Scalability implications** — none relevant at one mission at a time; D-024 already covers
the post-competition path if that changes.

**Recommendation** — build (b), to the letter of architecture-spec §3, as two new pieces:
`manage.py run_orchestrator` (tick loop: claim nothing, only enqueues jobs on entry to a
job-backed state, reaps expired leases, watches `deadline_at`, and is the **only** code path
outside `authorization/service.py`'s existing calls that may invoke
`orchestrator.transitions.transition()` off a job's terminal result) and `manage.py
run_worker` (claim loop: `SKIP LOCKED`, heartbeat, `JobKind` dispatch table into the existing
stage modules). Compose needs two changes beyond the `worker` command fix: add an
`orchestrator` service (does not exist in either compose profile today — checked directly),
and repoint `worker`'s `command` at `manage.py run_worker`. Both are devops-scoped once the
management commands exist.

**Final approval authority** — CTO (technical); this closes P2-12/D-024's remaining "flagged as
business-cheap, not decided" thread for this specific consumer.

### 2. Failure semantics: the vocabulary is fully built; the gap is only who produces it

**Decision** — Use architecture-spec §6 verbatim as the failure-mode table; every `ErrorCode`
and `MissionState` target it names already exists in `contracts/enums.py`
(`BASELINE_BUILD_FAILED`, `BASELINE_FLAKY`, `SANDBOX_UNAVAILABLE`, `NO_REPRODUCIBLE_FINDING`,
`MODEL_CAPACITY_UNAVAILABLE`, `JOB_TIMED_OUT`, etc. — checked directly, all present). No new
contract work is needed here, only the executors that raise them correctly.

**The one real trap for an implementer, found by reading the transition table, not the prose.**
§6.3(a) says "if zero crashes → mission → `HUMAN_REVIEW`" after a `FUZZ` job times out inside
its budget. Read literally against `MissionState` that means `STRESS_TEST → HUMAN_REVIEW` —
but `contracts/state_machine.TRANSITIONS[MissionState.STRESS_TEST]` is `{CORRELATE, PAUSED} |
_ABORTS` and has **no `HUMAN_REVIEW` member**. Only `CORRELATE`, `PATCH`, and `VERIFY` have
`HUMAN_REVIEW` as a legal target. This is not a state-machine bug — `contracts/
state_machine.py` is frozen (D-060's own precedent: CTO/software-architect own that table, not
a downstream engineer) — it means the *orchestrator's* job-result handling for a `FUZZ` job
with zero crashes must still enqueue `CORRELATE` (transition `STRESS_TEST → CORRELATE`), and
the **`CORRELATE` executor** is where "nothing to bind" decides `HUMAN_REVIEW` and the
orchestrator enqueues that transition instead of `PATCH`. An implementation that tries to
transition straight from `STRESS_TEST` to `HUMAN_REVIEW` on zero crashes will hit
`InvalidStateTransitionError` (409) the first time QA runs exactly the scenario §6.3(a)
describes, on a target that fuzzes clean. Flagging this now because it is a five-minute fix if
known up front and a confusing debugging session if found live, same category as D-060 §3.

**Other confirmed mappings, briefly** (§6.2/§6.4, cross-checked against the live table): a
`BASELINE` job failing configure/build → `Mission.FAILED` via the `_ABORTS` path (`BASELINE`
has no non-abort target but `TRIAGE`, so `FAILED` is reachable from it — confirmed);
`VERIFY`'s compile-gate failure is a legitimate `REJECTED` verdict via
`derive_verdict`/`derive_mission_outcome`, never `FAILED` — do not conflate "our system broke"
with "the patch was bad," per §6.2's own explicit warning.

**Recommendation** — no contract changes required; each `JobKind` executor (task breakdown
below) is responsible for choosing the *stage* result correctly against the existing table, not
for inventing new states or codes.

**Final approval authority** — CTO (technical); the "which state does a zero-crash timeout
actually reach" mapping above is binding on the `CORRELATE`/orchestrator engineer, not a local
judgment call.

### 3. Idempotency/retry: the `Job` row's own fields are the discipline; two rules that are easy to get backwards

**Decision** — Two non-negotiable rules for whoever writes the orchestrator tick loop and the
worker dispatch table, mirroring D-060 §3's "found by reading the code, ruled once, applies to
every implementer" shape:

1. **The worker never calls `orchestrator.transitions.transition()`.** Architecture-spec §1.1's
   process table is explicit: `worker` "Must never: Write `Mission.state`." Only the
   orchestrator's tick loop, reading a job's terminal `state`/`result`, may call `transition()`
   — mirroring exactly how `orchestrator/transitions.py`'s own module docstring already frames
   itself as "the only writer of `Mission.state`" and how `missions/lifecycle.py`'s `SEC-16`
   write-guard enforces it structurally today. A worker with the mission id already in hand and
   a stage that just succeeded will be tempted to call `transition()` directly to save a hop —
   that collapses the two-process boundary the whole design exists to keep (§3.2: "a job emits
   many events and causes exactly one transition," read by the orchestrator, not decided by the
   worker) and reintroduces exactly the kind of split-brain write path SEC-16 was built to
   close for the HTTP handlers in #154.
2. **Before a `JobKind` executor runs real work, check whether this stage's terminal artifact
   already exists for this mission, and skip straight to reporting success if it does.** This is
   what makes a crash-and-restart safe without extra bookkeeping: `BaselineReport` has a real
   unique constraint per mission (checked directly in `missions/models.py`), so a worker that
   died after writing the report but before its `Job` row reached `SUCCEEDED` must not blindly
   re-run `run_baseline_stage` on restart — it would hit the constraint. The check-first pattern
   is one query per executor, not new infrastructure. `PATCH_GENERATE` is the one kind where
   this is *not* the right rule, by design (D-027's fan-out means multiple `PatchCandidate` rows
   are the intended outcome of one stage) — that executor's own idempotency unit is "did *this
   specific attempt number* already produce a candidate," using the job's `attempt` field, not
   "has PATCH ever produced anything for this mission."

**Options considered** — for rule 2: (a) always re-run the stage function on any retry
(idempotent by re-execution); (b) check for an existing terminal artifact first, skip if
present. (a) is simpler but is wrong for exactly the two stages that have a DB uniqueness
constraint backing their "one per mission" invariant (`BaselineReport`;
`Mission.verification_started_at`'s freeze for the candidate set makes a bare re-run of
`PATCH_GENERATE` after verification has started a `CandidateSetFrozenError`, which is correct
behavior but means the executor must check that state before assuming a clean retry is safe).

**Cost implications** — one existence check per executor; already-established query patterns
(`Mission.objects.select_for_update()`, or a plain read where no write follows).

**Security implications** — none beyond what SEC-16/D-046 already close; this ruling keeps the
new code inside those existing guarantees rather than opening a second path around them.

**Scalability implications** — none at one worker, one mission.

**Recommendation / ruling** — both rules mandatory. Flag any PR that has a worker call
`transitions.transition()` directly, or a `JobKind` executor with no pre-execution check
against its own terminal artifact (except `PATCH_GENERATE`, which uses `attempt`-scoped
idempotency instead), for correction before merge.

**Final approval authority** — CTO (technical).

### 4. Concrete task breakdown

Foundation, sequential, blocks everything else (recommend one engineer, or two working the two
halves in parallel since they share no files):

- **T0 — orchestrator tick loop + job enqueue.** New `orchestrator/queue.py` (or similarly
  named module in the existing `orchestrator/` package, which already owns `Mission.state`):
  `enqueue_job(mission_id, kind, payload, deadline_at, ...)`, the `SKIP LOCKED`-aware lease
  reaper, the deadline watchdog, and the one function that reads a job's terminal row and calls
  `transitions.transition()`. Plus `manage.py run_orchestrator`. This is the piece nothing else
  can be tested end-to-end without.
- **T0b — snapshot materialization.** `authorization/archive.py` has `enumerate_members` and
  `build_tar_from_directory` but **no function that safely extracts a stored `Artifact`'s tar
  back into a scratch directory** (checked directly — grepped for `extract`/`unpack_archive`,
  zero hits). Every stage executor below needs a real on-disk `source_dir` to hand
  `workers/baseline`/`orchestrator/verification.run_verification`; today there is no code path
  that produces one from `ARTIFACT_ROOT/<sha256>`. Small, self-contained, reuses the existing
  `_is_safe_member_name` guard, no dependency on T0 — independently implementable in parallel
  by a second engineer.

Once T0/T0b land, each `JobKind` executor is independently implementable in parallel (wiring an
existing, tested function into the dispatch table plus the failure-mapping from §2):

- **T1 — `BASELINE`/`SANITIZER_BUILD`.** Wraps `workers/baseline/run_baseline_stage`; §6.2
  failure mapping; writes `BaselineReport`.
- **T2 — `FUZZ`/`MINIMIZE`.** Wraps `workers/fuzzing/run_fuzzing_stage`; §6.3 timeout/stall
  handling; throttled progress per §3.2. **New work, not just wiring:** there is no
  `record_finding`-shaped function anywhere in the codebase today (grepped) — a crash in
  `FuzzingOutcome` never becomes a `Finding` row. This executor (or T3) has to write it.
- **T3 — `TRIAGE`(`ANALYZE`)/`CORRELATE`.** Per architecture-spec §2.5: `TRIAGE` is a near-stub
  (`STAGE_STARTED` → a `LOG` event reading "No static analyzers configured in this build" →
  `STAGE_COMPLETED`, empty `AnalyzerTool` coverage, no fabricated count — Semgrep/compiler-diag
  are both CUT). `CORRELATE` is real but narrow: bind the sanitizer-confirmed crash to a
  `SourceLocation`/`FindingDetail.code_slice`, and — per §2 above — this is where the
  zero-crash → `HUMAN_REVIEW` decision actually lives, not at `STRESS_TEST`.
- **T4 — `PATCH_GENERATE`.** `services/model-gateway/` (top-level, standalone) still exists
  outside `apps/control-api/`, contradicting **D-026** ("becomes `apps/control-api/gateway/`, a
  Python package imported only by the worker") — checked directly, the move was never done and
  nothing in compose references `services/model-gateway` at all (one dead reference in an
  endpoint-policy test script only). Recommend completing the D-026 move as part of this task
  rather than importing across the old path, so there is one gateway location, not two. Calls
  `orchestrator.candidates.record_patch_candidate` per attempt; implements the fan-out (§2.3)
  and §6.4's degradation ladder.
- **T5 — `VERIFY`.** Wraps `orchestrator/verification.run_verification` +
  `orchestrator/candidates.record_verification`; per-gate progress per §3.2. The most "just
  wire it" of the seven — both underlying functions are complete and tested.
- **T6 — `EXPORT`.** This is #30/#32, and it is a **hard dependency of #168 closing #50, not a
  parallel nice-to-have** — see the flagged gap below. Assembles `EvidenceBundle` from
  `orchestrator/evidence_repository.py`'s already-real per-table readers
  (`get_baseline_report`, `get_fuzzing_report`, `list_findings`, `list_patch_candidates`,
  `get_patch_verification` — all exist and are exercised by the read-only evidence router
  today), writes `report.md`/`report.json`/`manifest.json`/the tarball per architecture-spec
  §5.3, and turns `GET /missions/{id}/evidence` and `POST /missions/{id}/export`'s current
  `NotImplementedYetError` stubs into real responses.
- **T7 — `TEARDOWN`.** Smallest of the seven: `orchestrator/teardown.py` is already real and
  already invoked on commit for `CANCELLING`/every terminal state (`orchestrator/
  transitions.py::_run_teardown_after_commit`) — this is mostly making sure a `TEARDOWN`
  `JobKind` exists for symmetry with the spec's dispatch table, not new teardown logic.

Devops-scoped, can run any time in parallel with T1–T7 once the management-command entry
points exist: fix the `worker` service's `command` (drop `rqworker`), add the missing
`orchestrator` service to both compose profiles (does not exist today in either), drop the now
provably-vestigial `REDIS_URL`/`redis` service once `run_worker`/`run_orchestrator` are proven
against it (follow-up, not blocking).

**Not in this breakdown, flagged as a related-but-separate scope call for
engineering-manager:** `preflight_mission` today implements none of architecture-spec §6.1's
sandbox-start check ("start a `--network=none` container running `true`... the single most
valuable preflight check... ~2 s") or §6.4's model-host health check ("the cheapest catch in
the system... 10 s timeout"). Neither exists in `missions/service.py::preflight_mission` today
(checked directly against its current four checks: `legal_transition`, `resume_origin`,
`verdict_evidenced`, `authorization_and_stage`). Recommend adding both while the `Jail`/gateway
wiring is being built anyway for T1/T4, but this is additive to #168's acceptance criteria, not
required to close it — a call for engineering-manager to sequence, not a blocker I'm imposing
here.

### 5. Summary of latent gaps found before implementation starts (the #154-`DoesNotExist`-equivalent catches)

1. Compose's `worker` service still targets `rqworker`/`django-rq`, which is not a dependency
   and would crash on activation — do not extend it, replace it (§1).
2. No `HUMAN_REVIEW` edge exists from `STRESS_TEST` in the frozen transition table — a
   zero-crash fuzz timeout must route through `CORRELATE` first, not straight to `HUMAN_REVIEW`
   (§2).
3. No snapshot-archive-to-worktree extraction utility exists anywhere — every stage executor
   needs one and none is built (§4, T0b).
4. No `Finding`-recording function exists anywhere — fuzzing crashes never become `Finding` rows
   today (§4, T2).
5. `services/model-gateway/` was never moved into `apps/control-api/gateway/` per D-026, and
   nothing wires it in — a second, unwired "gateway" pocket of real code (§4, T4).
6. The `EXPORT` job (#30/#32) is a hard dependency of #168 actually closing #50, not
   parallelizable slack — without it the driver reproduces the exact "stuck forever" bug one
   stage later, at `EXPORTING`, and nothing in `assert_verdict_is_evidenced` would catch a
   transition that skipped writing real evidence content, since it only checks that
   verification records exist, not that an export ran (§4, T6).
7. The worker-must-never-call-`transition()` / check-before-re-run discipline (§3) is exactly
   the kind of rule an implementer optimizing for "fewest moving parts" will get backwards under
   deadline pressure — called out explicitly for review to catch.

**Final approval authority (this whole brief)** — CTO (technical). Staffing count and sequencing
of T0–T7 against the roster is engineering-manager's call per this project's normal process;
the ordering constraint (T0/T0b block T1–T7; T6 is not optional slack) is binding.

## D-062 — Staffing plan for #168 against D-061, and the MVP scope call

Posted as a comment on #168. Full plan there; this is the decision-record shape for the
non-trivial calls in it, per engineering-manager's own process rules.

**Decision** — Staff T0 (foundation, critical path) and T0b (foundation, independent) in
parallel starting Day 1 (08-17), alongside T1/T5/T7 written against a pre-agreed executor
interface contract (defined before T0 physically merges, so those three don't block on it),
compose fixes (devops, parallel), and T4 started Day 1 rather than Day 2 since it is the
long pole. T2/T3/T6 follow on Day 2 once T0/T0b land. Day 3 (08-19) is reserved as an
integration/QA buffer, not new feature work, ahead of the 08-20 deadline.

**Options considered** — (a) build the full D-061 scope as literally specified (all 7
executors, T4 including the complete D-026 `services/model-gateway` → `apps/control-api/
gateway/` relocation, plus devops's `REDIS_URL` cleanup and the two additive preflight
checks CTO flagged) in strict T0/T0b-then-T1–T7 sequence; (b) the staggered-parallel plan
above with T4 de-scoped to a stub gateway call against the *current* `services/model-gateway`
import path, deferring the D-026 relocation past 08-20.

**Pros and cons** — (a) matches D-061 to the letter and leaves no follow-up debt, but does
not fit in 3 days without cutting the Day 3 integration buffer to near zero, and this exact
issue (#168) exists *because* a fully-built, fully-tested-in-isolation piece (the `Job`
model) was never exercised end-to-end before being called done — cutting the one pass that
would catch the same failure mode again is the wrong tradeoff under this deadline. (b) fits
in 3 days if Day 1's parallel tracks start on time and T0 does not slip, and still delivers
every stage of the real state sequence (`BASELINE → … → EXPORTING → verdict`) for the #50
demo — PATCH_GENERATE is not skippable, only its gateway import path is deferred. Its cost is
one extra follow-up ticket (the D-026 move) and a real deviation from D-061 §4's explicit
recommendation to fold that move into T4, which is why it's flagged for CTO sign-off rather
than decided unilaterally here.

**Cost implications** — (b) costs one deferred refactor (the package move), re-opened as a
fast-follow after 08-20. No new infrastructure either way.

**Security implications** — none beyond what D-061 already covers; T4-lite still calls
`record_patch_candidate` for real and does not touch the SEC-16 write-guard boundary either
way.

**Scalability implications** — none; single-mission-at-a-time throughout, matching D-061.

**Recommendation** — (b). Flag as a genuine finding, not a caveat: the full literal D-061
scope is at real risk of not landing clean by 08-20 alongside a real integration pass. T0
slipping past end of Day 1 is the failure mode that collapses the schedule and should trigger
an immediate re-open of this scope conversation rather than a Day 3 discovery.

**Final approval authority** — engineering-manager owns staffing/sequencing per D-061's own
closing line. The T4-lite deferral specifically needs CTO sign-off, since it deviates from
D-061 §4's explicit recommendation to complete the D-026 move inside T4 — posted as an open
question on #168, not decided unilaterally here.

## D-063 — T0b: snapshot-archive extraction (#168), and where it lives · 2026-08-16 · `backend-developer` seat

Numbered assuming **D-061** (CTO brief for #168) and **D-062** (staffing plan) land from
`docs/d061-d062-driver-brief` ahead of this branch merging; renumber on conflict, the
content is what matters. D-061 §4 named this task directly: `authorization/archive.py`
has `enumerate_members` and `build_tar_from_directory` but no function that safely
extracts a stored snapshot archive back into a scratch directory, and every stage
executor from `BASELINE` onward needs one. This record covers the two calls D-061 left
to the implementer: which module the extractor and its Django-aware caller live in,
and how the two halves divide the work.

**Decision** — Two functions in two modules, not one:

1. `authorization.archive.extract_archive(archive_path, dest_dir)` — the actual,
   safety-checked extraction. Pure filesystem I/O, no Django import, sibling of
   `build_tar_from_directory` in the same module and reusing its `_is_safe_member_name`
   guard exactly as D-061 asked. Takes two paths, returns an `ArchiveInfo`, knows
   nothing about missions, artifacts, or settings.
2. `orchestrator.snapshot.materialize_snapshot(mission_id, *, workspace_root=None)` —
   the Django-aware wrapper: resolves a mission's latest `Snapshot` row to a real file
   under `ARTIFACT_ROOT` (checked against the filesystem directly, not inferred from
   the `Artifact` index row alone), allocates a fresh
   `<workspace_root>/<mission_id>/<uuid4>` directory, and calls `extract_archive`.

**Options considered** — (a) one Django-aware function directly in
`authorization/archive.py`, matching D-061's literal suggestion of "alongside its
sibling `build_tar_from_directory`"; (b) the two-module split above; (c) a new
top-level `workers`-style package (`workers/materialize/`), mirroring `workers/
baseline`'s "no Django" boundary (D-026) more strictly than (b) does.

**Pros and cons** — (a) is the smallest diff and matches D-061's suggested location
literally, but couples `authorization/archive.py` — a module every archive-handling
code path already imports, including `authorization.service`'s synchronous request
handlers — to Django ORM queries it does not otherwise need, and makes the safety-
critical extraction logic itself harder to unit-test in isolation from a database. (c)
keeps the Django boundary D-026 draws for `workers/*` maximally clean, but
`workers/baseline/run_baseline_stage` never queries the database itself either — it
receives an already-resolved `source_dir: Path` — so there is no actual caller inside
`workers/` that would import a Django-aware materializer; putting it there would just
relocate the Django-vs-not question without resolving it, and `orchestrator/` already
owns exactly this shape of work (`orchestrator/verification.py` takes a resolved
`worktree: Path`, `orchestrator/repository.py` already has `latest_snapshot_sha256`,
which this function reuses directly). (b) keeps `extract_archive` importable and
testable with zero database dependency — the round-trip, malicious-member, and
corrupt-archive tests in `authorization/tests/test_archive.py` need no `django_db`
marker at all — while giving the mission/`ARTIFACT_ROOT`-resolving half a home
(`orchestrator/`) that already owns the equivalent resolution step for verification's
worktree, and that a future `JobKind` dispatch table (T0's `orchestrator/queue.py`,
per D-061 §1) can call directly without importing `authorization.service`.

**Cost implications** — none; no new dependencies, no new settings beyond
`SNAPSHOT_WORKSPACE_ROOT` (a plain path setting, same shape as `ARTIFACT_ROOT`/
`SNAPSHOT_STAGING_ROOT` it sits beside in `config/settings/base.py`).

**Security implications** — `extract_archive` re-validates every member independently
of whether its caller already ran the archive through `enumerate_members` (it does
not assume that happened), applying three checks per member before anything is
written for *any* member in the archive: `_is_safe_member_name` (path-traversal /
zip-slip), member-type refusal (symlinks and hardlinks per SEC-26's existing
reasoning, plus device nodes and FIFOs, which `enumerate_members` does not currently
special-case but have the identical "no legitimate reason to exist in a snapshot"
justification), and a resolved-path containment check independent of and in addition
to the lexical name check (`_resolved_target_or_raise`) — defense in depth against
anything the lexical check's `PurePosixPath`-based reasoning does not catch (a
Windows-drive-qualified name is not recognized as absolute by `PurePosixPath` and
would otherwise slip past check 1 alone, though it is harmless on this project's
Linux-only deployment target either way). Extracted file/directory modes are never
taken from the archive header — fixed to `0644`/`0755` regardless of what a
(potentially hostile) archive's own metadata claimed, closing off a setuid-bit or
world-writable-directory smuggling path `tarfile.extractall`'s default behavior would
otherwise allow through on this project's target interpreter (3.12; PEP 706 filtering
does not default on until 3.14, same gap `enumerate_members`'s own docstring already
names). `materialize_snapshot` fails closed on both points where "recorded" and
"actually present" can diverge: no `Snapshot` row, and a `Snapshot` row whose digest
has no file under `ARTIFACT_ROOT` — checked against the filesystem directly rather
than trusting the `Artifact` index row's mere existence as a proxy for it.

**Scalability implications** — none; one archive extracted into one fresh directory
per call, no shared or reused state between calls.

**Recommendation / ruling** — (b), implemented as described. `SnapshotExtractionFailedError`
added to `authorization/errors.py` reusing `ErrorCode.INTERNAL_ERROR` — D-030's frozen
vocabulary rule, same pattern `contracts.errors.MissionStateWriteError` already uses —
for the one failure class that is neither a caller mistake nor an unsafe archive: a
genuine `OSError` while writing an already-validated member to disk (disk full,
permission denied). Both new error classes reuse existing `ErrorCode` members; no
contract change.

**Final approval authority** — CTO (technical), per D-061's own closing line that
staffing/sequencing calls for #168 are engineering-manager/CTO's, not a downstream
engineer's; flagged here rather than decided unilaterally, since the module-location
call is exactly the kind of thing D-061 left open for "your call."

## D-064 — T0b: extraction-size ceiling for `extract_archive`, fixing the round-4 review's HIGH-1 decompression-bomb finding · 2026-08-16 · `backend-developer` seat

**Decision** — `authorization.archive.extract_archive` (and its `_extract_tar`/
`_extract_zip` helpers) now takes a required `max_bytes: int` keyword argument and
enforces it two ways: (1) a cheap pre-check against each member's *declared* size
(`member.size` / `info.file_size`) before any byte is read, and (2) a running total
of bytes *actually written*, tracked cumulatively across every member in the call
(`_copy_within_budget`), checked on every fixed-size chunk during the write pass
itself and raising `UnreadableArchiveError` the instant it would cross `max_bytes`.
`orchestrator.snapshot.materialize_snapshot` — the only caller — passes
`max_bytes=settings.SNAPSHOT_MAX_BYTES`, reusing the existing 512 MiB ingest-side
ceiling rather than introducing a second, independently-chosen number.

**Trigger** — cybersecurity's adversarial review of PR #170
(https://github.com/Mahatav/brahmadatta-ai/pull/170#issuecomment-5312674678) built a
real `tar.gz` (one zero-filled member, 2 GiB declared/actual, ~2 MB on disk, ~1029:1
ratio) and confirmed `extract_archive` wrote the full 2 GiB to disk with no ceiling,
no warning, no refusal (HIGH-1, not Critical — no containment/path/symlink boundary
broken, pure availability impact). Not exploitable today through the only wired
snapshot source (`source="git"`, which writes an uncompressed tar with no ratio to
exploit) but live the moment `materialize_snapshot` — already called directly by T1,
being built in parallel — reaches any non-server-built archive.

**Options considered**

(a) Declared-size pre-check only (reject if `member.size`/`info.file_size` alone
exceeds `max_bytes`, nothing else).
(b) Running actual-bytes-written check only, no pre-check.
(c) Both, layered — pre-check as a cheap first pass, running check as the binding
enforcement during the write loop.

**Pros and cons of each**

(a) Cheap, no change to the write loop. But insufficient alone against the review's
own PoC shape in principle (a member could under-declare its size while the
decompressor produces more) — though investigation in this session found CPython's
`tarfile`/`zipfile` both already bound `.read()` to the header's declared size
internally (`_FileInFile.read`, `ZipExtFile._read1`), so a *single* member cannot
currently defeat (a) alone via the stdlib's own read path. Still leaves the
cross-member case wide open: many individually-honest, individually-under-cap
members can sum past the ceiling, and a per-member check never sees a total.
(b) Correct and sufficient on its own, but wastes decompression work on an archive
whose very first member header already declares more than the ceiling — no reason
to start reading before refusing.
(c) Strictly better than either alone: cheap rejection for the common/obvious case,
binding enforcement (cumulative, checked against actual bytes) for the case (a)
structurally cannot see, and does not depend on relying on `tarfile`/`zipfile`'s
current internal truncation behavior continuing to hold across future Python
versions — the task's own instruction (item 3) called for exactly this, and it
matches the "layered, not either-or" shape the rest of this module already uses for
its other checks (name-safety + resolved-path containment, independently).

**Cost implications** — none. No new dependency, no new setting — `SNAPSHOT_MAX_BYTES`
already existed for the ingest side; this reuses it rather than adding a second
number. Runtime cost is one comparison per chunk already being read/written, and the
declared-size pre-check is a single integer comparison per member before any I/O.

**Security implications** — closes HIGH-1. Verified live in this session against a
600 MiB zero-fill `tar.gz` (~1029:1 ratio, ~600 KiB on disk) using the real
production default (`max_bytes=536_870_912`): refused in 0.35s, `dest_dir` not left
behind. Also verified the cross-member case in isolation (three honestly-declared,
individually-under-cap 900,000-byte members whose sum exceeds a 2,000,000-byte cap)
is refused only by the running check, confirming the pre-check alone would have
missed it — see `test_extract_archive_refuses_when_no_single_declared_size_exceeds_the_cap_but_their_sum_does`
in `authorization/tests/test_archive.py`. Two Low findings from the same review
(missing dedicated tests for a zip symlink member and a tar FIFO member on the
*extraction* path specifically — the property was already independently verified by
the reviewer's own manual attack, and by `enumerate_members`'s existing tests for the
zip-symlink case) closed as test-coverage gaps:
`test_extract_archive_refuses_a_zip_symlink_member`,
`test_extract_archive_refuses_a_tar_fifo_member`.

**Scalability implications** — none; the ceiling bounds worst-case disk usage per
extraction call to `SNAPSHOT_MAX_BYTES`, which is a scalability *improvement* over
the prior unbounded behavior (the shared-blast-radius disk-exhaustion risk the review
flagged: extraction happens on the control-api host's own filesystem, ahead of any
sandbox, so one hostile snapshot could previously have taken down Postgres and the
whole control plane, not just its own mission).

**Recommendation / ruling** — (c), implemented as described. `UnreadableArchiveError`
reused for the size-ceiling refusal (its own docstring in `authorization/errors.py`
already anticipated this: "...or is larger than the ceiling") rather than a new
sibling error class — no `ErrorCode` contract change, consistent with D-063's own
"both new error classes reuse existing `ErrorCode` members" precedent.

**Final approval authority** — CTO (technical), same routing as D-063; this is a
fix to code D-063 already put through that process, not a new architectural call.
## D-065 — T0 implementation calls: one-job-per-stage idempotency, TRIAGE driven directly by the orchestrator, and the split between the executor interface and its reference policy · 2026-08-17 · `backend-developer` seat

Three calls made while implementing D-061/D-062's T0 (`orchestrator/executors.py`,
`orchestrator/queue.py`, `manage.py run_orchestrator`/`run_worker`, PR #171), each
non-trivial enough to record rather than leave implicit in code comments alone.

### 1. "Does a `Job` row exist for (mission, kind)" is the whole idempotency check — no new column

**Decision** — `ensure_jobs_enqueued` enqueues a job for a mission's current
job-backed state only if no `Job` row exists at all for that `(mission, kind)` pair —
not "no row in a live state." A retry (worker crash, stall) reuses the *same* row via
`retry_job`/`reap_expired_leases` moving it back to `QUEUED`, never a second row.

**Options considered** — (a) a new boolean/timestamp column on `Job` (e.g.
`consumed_at`) marking "this terminal job already produced a transition"; (b) the
existence check above, relying on the one-job-per-mission-per-kind invariant the
architecture spec's own design already implies (fan-out lives *inside* one `PATCH_
GENERATE`/`VERIFY` job, per §3.4; `BaselineReport`'s real unique constraint is the
storage-level version of the same "one per mission" rule for `BASELINE`); (c) delete
or archive a terminal job's row once dispatched.

**Pros and cons** — (a) is the most explicit but is schema I do not own — `Job` is
the database-engineer's fully-migrated model (D-061's own framing: "already migrated
and tested... zero callers"), and adding a column to service an implementation detail
of the orchestrator's own bookkeeping is exactly the kind of change my role's scope
explicitly defers ("request changes rather than making them"). (c) would make `Job`
rows unsuitable as the audit trail architecture spec §3.3.1 requires ("partial output
is persisted... the morning shift never inherits a job whose only output was in a
dead process's memory" — a deleted row is not inspectable the morning after). (b)
costs nothing extra and falls directly out of a property the frozen design already
establishes elsewhere (fan-out-inside-one-job, `BaselineReport`'s uniqueness) — the
new idempotency check is a restatement of an existing invariant, not a new one.

**Cost implications** — none.

**Security/scalability implications** — none beyond what the existing invariant
already covers.

**Recommendation / ruling** — (b), implemented. Flag for whoever builds T1/T2 that
this reasoning is written into `orchestrator/queue.py`'s module docstring
("Enqueue") — a `JobKind` whose own design needs more than one row per mission per
visit to a state (none currently do) would need this reconsidered, not silently
worked around.

**Final approval authority** — CTO (technical); low stakes, recorded because a wrong
guess here reproduces #168's own failure shape one stage later (a duplicate-enqueue
bug or a stuck mission), which is exactly the class of bug this whole issue exists to
close.

### 2. `TRIAGE` is driven directly by the orchestrator tick, not left unimplemented pending a `JobKind`

**Decision** — `orchestrator.queue.advance_through_triage` emits `TRIAGE`'s three
required events (`STAGE_STARTED`, a `LOG` reading "No static analyzers configured in
this build", `STAGE_COMPLETED` — architecture spec §2.5) and transitions `TRIAGE ->
STRESS_TEST` directly from the tick loop, rather than leaving `TRIAGE` stuck with no
driver until T3 (owns `CORRELATE`, adjacent per D-062's task list) builds one.

**Options considered** — (a) leave `TRIAGE` unhandled by T0, matching D-062's literal
task assignment (`TRIAGE`/`CORRELATE` = T3, Day 2); (b) drive it directly from the
tick loop now, since `JobKind` has no `TRIAGE` member at all (checked directly —
`missions/models.py`'s `JobKind` choices) and nothing about emitting three
deterministic, no-branching events needs a sandboxed worker.

**Pros and cons** — (a) matches the staffing plan to the letter and avoids
second-guessing a task boundary that isn't mine to move, but leaves a mission
provably stuck at `TRIAGE` — the identical bug shape #168 itself is about — until T3
lands, which defeats T0's own acceptance bar ("a mission... genuinely progresses...
without manual intervention," #168's acceptance criteria) for every mission that
reaches `BASELINE`'s far side before T3 merges. (b) closes that gap immediately, at
the cost of one orchestrator-owned function whose behavior T3 did not design and may
want to change (e.g. wanting `TRIAGE` to have a real `JobKind` after all, for
uniformity, once T3 is actually staffed and looking at the whole picture).

**Cost implications** — none; no new dependency, ~40 lines already written and
tested (`orchestrator/tests/test_queue_tick.py`).

**Security implications** — none; the three events are fixed strings with no
operator- or model-derived content.

**Scalability implications** — none.

**Recommendation / ruling** — (b), implemented, explicitly flagged in `orchestrator/
queue.py`'s docstring as "T0 additive scope... flag for T3's review and replace if a
different design is wanted" — not presented as settled. This is within my role's
explicit authority ("module-internal structure of `orchestrator/`... the `JobKind`
dispatch mechanism," architecture spec §1.4, "Backend developer decides") since it
neither adds nor renames a `MissionState` or transition (`TRIAGE -> STRESS_TEST` is
already in the frozen table) — only decides who drives an already-legal edge and how.

**Final approval authority** — CTO (technical) to confirm the reading above is
correct, or engineering-manager to fold this explicitly into T3's scope as "replace,
not build from scratch," per D-061's own closing line that staffing/sequencing calls
are engineering-manager's.

### 3. The executor interface ships one real, tested reference policy (`FUZZ`), not zero

**Decision** — `orchestrator/executors.py` registers a real `TransitionPolicy` for
`JobKind.FUZZ` (always routes a terminal, non-infra-fault job to `CORRELATE`) rather
than shipping every kind, including `FUZZ`, as a `NotImplementedError` stub — the
literal reading of D-062's "one stub entry per JobKind."

**Options considered** — (a) every kind stubbed, no exceptions, matching D-062's
sentence exactly; (b) `FUZZ`'s transition policy implemented for real, everything
else (including `FUZZ`'s own *executor* — the actual libFuzzer campaign runner)
stubbed.

**Pros and cons** — (a) is the more literal reading and avoids any risk of T0
pre-empting T2/T3's real design. (b) is what my task's own instructions weighed
this against directly: prioritize, in order, "the executor interface contract," "the
claim/lock discipline with a real test," "the dispatch-and-transition wiring" — and
name the `STRESS_TEST -> CORRELATE` trap as a required test, specifically. That trap
cannot be exercised end-to-end through the real dispatcher (`orchestrator.queue.
dispatch_terminal_jobs`, calling the real `transitions.transition()`) against a
*stub* that only raises — the strongest test available for a stub is "dispatch logs
and skips it," which proves the stub mechanism, not the routing decision. D-061 §2
and D-062 both single out this specific routing question by name as the trap most
likely to be gotten wrong under deadline pressure; shipping only a contract-table
assertion (no dispatcher-level proof) would leave the actual behavior an implementer
gets wrong unverified by anything except a static fact about the transition table.

**Cost implications** — none; ~15 lines, already reviewed against the architecture
spec's exact wording in the module's own docstring, which also states plainly that
the two `job.result` keys it reads (`infra_failure`, `crashes_found`) are
provisional and that T2/T3 should adjust in review rather than treat this as frozen.

**Security implications** — none.

**Scalability implications** — none.

**Recommendation / ruling** — (b), implemented, with the deviation from "every kind
stubbed" stated explicitly in three places (the module docstring, the `#168` issue
comment posting the interface, and here) so it is never mistaken for a silent
overreach into T2's or T3's actual scope — the `FUZZ` *executor* (the campaign
runner itself) and the `CORRELATE` policy (the "nothing to bind -> `HUMAN_REVIEW`"
decision) remain entirely unbuilt and unclaimed by T0.

**Final approval authority** — CTO (technical); flagged for T2/T3 to confirm or
correct the provisional `job.result` shape in code review rather than silently
inherit it as frozen.


## D-068 — T7 (`JobKind.TEARDOWN` executor + transition policy) implementation choices

Posted while implementing #168 T7, against D-061 §4's brief ("smallest of the seven ... not
new teardown logic") and the live `#50` gate evidence (`.project/evidence/
d7-gate-50-live-run-2026-08-17.md`, the `CANCELLING → CANCELLED` gap).

**Decision 1 — reuse `orchestrator/teardown.py` verbatim; wrap it, do not re-implement it.**
`teardown.teardown_started_compute` (#72) already releases sandbox/model-host resources,
already emits one `TEARDOWN_CONFIRMED` event per resource (success or failure, never
swallowed), and is already idempotent by construction (`DockerSandboxReaper`/
`ModelHostReaper` both return `()` when there is nothing left to release; a fully-empty
outcome set reports a synthetic `no-started-compute` receipt). `orchestrator/
teardown_executor.py` is a thin `Executor`/`TransitionPolicy` pair over it — no new
resource-release code. Confirmed by reading `orchestrator/teardown.py` and its existing test
file (`orchestrator/tests/test_teardown.py`) before writing anything.

**Options considered** — (a) new resource-release logic scoped to the `JobKind.TEARDOWN`
executor, independent of `teardown.py`; (b) call `teardown.teardown_started_compute`
directly and translate its return value into `ExecutorResult`.

**Pros and cons** — (a) would duplicate real, tested, already-idempotent cleanup code for no
benefit and risks the two mechanisms (the existing synchronous `_run_teardown_after_commit`
hook in `orchestrator/transitions.py`, and a new job-based one) disagreeing about what "safe
to release" means. (b) has exactly one moving part to keep correct and inherits the existing
mechanism's idempotency and honest-disclosure guarantees for free.

**Recommendation / ruling** — (b). Matches D-061 §4's explicit instruction.

**Decision 2 — the transition policy owns architecture-spec §2.2 R3, verbatim.**
`CANCELLING → CANCELLED` only when the terminal `TEARDOWN` job both `SUCCEEDED` and its
`result` shows zero failed resources (a real receipt); otherwise `CANCELLING → FAILED`. Every
other teardown-triggering target (`VERIFIED`/`REJECTED`/`HUMAN_REVIEW`/`FAILED`/`CANCELLED`)
already has an empty outgoing edge in `contracts.state_machine.TRANSITIONS`, so the policy
returns `None` for those — nothing further to route, mirroring how `_fuzz_transition_policy`
(T0's reference implementation) treats a job outcome that does not, by itself, justify a
transition.

**Decision 3 — `ExecutorResult.result` carries the itemised per-resource receipt; `outcome`
stays a single FAILED bit for a partial failure, never a silent SUCCEEDED.** `JobOutcome` has
no "partially succeeded" member and none was added (would be a breaking change to a contract
T0 owns). Honesty under that constraint means: `outcome=FAILED` the moment any resource
fails, `error_code=ErrorCode.INTERNAL_ERROR` (no dedicated teardown/leak code exists in
`contracts.enums.ErrorCode` — flagged below, not decided unilaterally), and `result` carries
`outcomes` (one dict per resource, `released` flag included), `released_count`,
`failed_count`, `total`, so nothing downstream — the transition policy, a future export step,
an operator reading `Job.result` — has to guess which resource, if any, might still be
running.

**Decision 4 — no query-based idempotency guard; rely on the mechanism's own no-op
behaviour.** D-061 §3's rule ("check for your stage's terminal artifact before doing real
work") does not have a literal equivalent for `TEARDOWN` — there is no `TeardownReport` row
with a uniqueness constraint. Re-running `teardown_started_compute` is already a safe no-op
(proved by `test_second_teardown_run_is_a_safe_no_op`), so no pre-execution existence check
was added. Flagged explicitly rather than silently treated as "does not apply", per D-061
§3's own instruction to name this obligation for every executor.

**Cost implications** — none; zero new runtime dependencies, no schema change.

**Security implications** — none beyond what SEC-16/#72's existing review already covers;
this module never writes `Mission.state` directly (enforced structurally by
`missions/lifecycle.py`) and never calls `orchestrator.transitions.transition()`.

**Scalability implications** — none; single-mission-at-a-time, matching D-061/D-062.

**Open question flagged for CTO, not decided here** — `ErrorCode.INTERNAL_ERROR` is used for
"a resource failed to release." Architecture spec §6's failure table does not name a
teardown/leaked-compute code, and D-061 §2 rules "no new contract work is needed" against the
codes that table *does* name — TEARDOWN was outside that table's scope. A dedicated code
(e.g. `TEARDOWN_INCOMPLETE`) would be more precise for an operator or the eventual evidence
bundle to key off of, but adding one to `contracts.enums.ErrorCode` is a shared-contract
change outside T7's authority.

**Also flagged, not decided here** — whether `transitions._requires_teardown`'s existing
synchronous call (`_run_teardown_after_commit`) should be replaced by, kept alongside, or
made to also enqueue, a `Job(kind=TEARDOWN)` once `orchestrator/queue.py` (T0) exists. Running
both is safe (idempotent), but is not this task's call to make either way.

**Final approval authority** — CTO (technical), for the two open questions above; the four
implementation decisions themselves are within backend-developer's scope per D-061's own
task breakdown for T7.

## D-066 — T1 (`JobKind.BASELINE` executor): the failure mapping, the cancellation gap, and a cross-package import fix D-061/D-062 did not anticipate · 2026-08-16 · `backend-developer`

T1's own scope (D-062's staffing plan): wire `workers/baseline/run.run_baseline_stage` into
`orchestrator/executors.py`'s `JobKind.BASELINE` executor and transition-policy contract
(T0, already merged to this branch). Three calls made while doing that, none of them decided
by D-061/D-062 explicitly.

### 1. The failure mapping: `SUCCEEDED` only on a green baseline; `BASELINE_BUILD_FAILED` vs `BASELINE_FLAKY` split by which step failed

**Decision** — `_baseline_executor` (`workers/baseline/dispatch.py`) reports
`JobOutcome.SUCCEEDED` only when `BaselineOutcome.passed` is `True`. Every red baseline —
configure/build failure *or* a build that succeeded but `ctest` reported any failure —
reports `JobOutcome.FAILED`, `retry=False`, and one of two `ErrorCode`s:
`BASELINE_BUILD_FAILED` when `configure_ok`/`build_ok` is `False`, `BASELINE_FLAKY`
otherwise. `_baseline_transition_policy` mirrors this: `TRIAGE` only for a terminal
`SUCCEEDED` job whose `result["passed"]` is `True`; `FAILED` for everything else except a
`CANCELLED` job, which returns `None`.

**Options considered** — (a) report `JobOutcome.SUCCEEDED` for any completed run regardless
of pass/fail (since `run_baseline_stage` itself never raises on a red result — "a red
baseline is a valid, complete result, not an exception," per its own docstring) and let the
transition policy alone decide `TRIAGE` vs `FAILED`; (b) fold the pass/fail judgment into
`JobOutcome` itself, per the option chosen.

**Pros and cons** — (a) is defensible read literally against `run_baseline_stage`'s own
docstring, and is exactly the shape `VERIFY`'s compile-gate failure uses elsewhere in this
same module's docstring ("a legitimate `REJECTED` verdict... never `FAILED`... do not
conflate 'our system broke' with 'the patch was bad'"). It is wrong here specifically because
architecture spec §6.2 does not leave `BASELINE` the same latitude `VERIFY` gets: "`ctest` on
the pristine tree reports any failure → `BASELINE_FLAKY` → `FAILED`. This is non-negotiable:
without a green baseline, 'regression preserved' has no denominator." A red baseline is not a
lesser verdict state the way a rejected patch is — the whole downstream pipeline (`D-009`'s
denominator) is undefined without it, so `Mission.FAILED` is the only honest target, and
`ExecutorResult.error_code`/`retry` exist specifically to carry *why* a `FAILED` outcome
happened, which (b) uses and (a) would have to invent a second channel for. (b) also matches
`MAX_ATTEMPTS_BY_KIND[BASELINE] == 1` and §6.2's own "Not retried: a build failure is a
result, and retrying it hides it" — `retry=False` on a `FAILED` outcome says that directly,
where a fabricated `SUCCEEDED` would have nothing to say it at all.

**Cost implications** — none; same amount of code either way.

**Security implications** — none.

**Scalability implications** — none.

**Recommendation** — (b), as implemented. Documented at length in `workers/baseline/
dispatch.py`'s own module docstring so a T2–T7 author skimming this module for a template
does not copy the `VERIFY`-shaped judgment onto a stage architecture spec §6 treats
differently.

**Final approval authority** — CTO (technical) per D-061 §2's own closing line ("no contract
changes required; each `JobKind` executor... is responsible for choosing the *stage* result
correctly against the existing table") — flagging for confirmation since it is read from
§6.2's prose rather than quoted verbatim.

### 2. Cooperative cancellation: real for "not yet started," fake would be worse than absent for "already running"

**Decision** — `_baseline_executor` checks `ctx.cancel_requested()` exactly once, before
calling `run_baseline_stage`, and reports `JobOutcome.CANCELLED` without doing any real work
if it is already set. No check exists once `run_baseline_stage` has been called; a
cancellation requested mid-run has no effect until the stage finishes on its own.

**Options considered** — (a) implement only the pre-flight check and document the mid-run gap
plainly (chosen); (b) poll `cancel_requested()` from a spawned thread and call the private
`Jail.cancel()` method (`packages/sandbox/jail.py:442`, which does exist) on the `Jail`
`run_baseline_stage` opens internally; (c) claim full cooperative cancellation support without
verifying it.

**Pros and cons** — (b) is technically reachable — `Jail.cancel()` is real — but
`run_baseline_stage(mission_id, source_dir, workspace_root, *, jail_policy=None)` neither
accepts a cancel token nor returns the `Jail` it opens, so reaching it from outside means
either monkeypatching `workers.baseline.run` internals from a different package (fragile,
and exactly the kind of "invent a new isolation approach" the assignment says not to do) or
editing that module's signature — which belongs to the compiler-toolchain-engineer seat, not
this task, and D-061 §3's obligations here are about *this* executor's idempotency, not about
extending someone else's already-tested module. (c) is the one genuinely unacceptable option:
the assignment is explicit that a real gap must be reported honestly, not faked, and `CLAUDE.
md`'s "no decorative fake" rule generalizes past UI metrics to this exact shape of claim.

**Cost implications** — closing this for real costs a small, separate follow-up PR against
`workers/baseline/run.py` (owned by compiler-toolchain-engineer): either accept a
`cancel_requested: CancelToken` parameter threaded into `run_variant`/`Jail`, or return the
open `Jail` so a caller can hold a reference and call `.cancel()` from its own heartbeat
thread. Not costed here since it is out of T1's scope.

**Security implications** — none; a `BASELINE` job that cannot be interrupted mid-run still
respects `packages.sandbox`'s own wall-clock/CPU/memory limits, so "cannot cancel" degrades to
"waits out the sandbox's own ceiling," not "runs unbounded."

**Scalability implications** — none at one worker, one mission (D-061's own framing). Matters
more once the worker deadline watchdog (T0, not yet built) is expected to guarantee prompt
cancellation for the overnight contract (architecture spec §3.3) — flagged as a real
follow-up need, not a blocker to T1 landing.

**Recommendation** — (a), as implemented, with the gap named in `workers/baseline/dispatch.
py`'s module docstring and in this record, and the follow-up (extend `run_baseline_stage`'s
signature) left for whoever owns that module next.

**Final approval authority** — CTO (technical) for accepting the gap as shipped; the follow-up
itself is compiler-toolchain-engineer's call once scheduled.

### 3. A real cross-package import gap, found by running the full suite: `apps/control-api` could not import `workers/`/`adapters`/`packages`, and fixing that collided with an existing namespace-package accident

**Decision** — `apps/control-api/config/settings/base.py` now puts `BASE_DIR` (`apps/
control-api`) at `sys.path[0]` and the repo root at the end of `sys.path`, both guarded by
`if ... not in sys.path`, on every settings import (covers `manage.py`, `wsgi`/`asgi`, and —
the path nothing previously covered — `pytest-django`, which imports this settings module
directly). `apps/control-api/tools/__init__.py` was added (previously absent — that directory
was an implicit PEP 420 namespace package) so it stops losing its own name to the unrelated
`tools/` package at the repo root.

**Why this needed deciding at all.** T0's `orchestrator/executors.py` docstring states
`ExecutorContext.source_dir` handling "mirror[s] `workers.baseline.run.run_baseline_stage`'s
existing signature" and D-061 T1's own scope is "wraps `workers/baseline/run_baseline_stage`"
— both assume that import already works from inside the Django project. It did not: nothing
before this branch ever ran `apps/control-api` code and top-level `workers`/`adapters`/
`packages` code in the same Python process, so the gap was invisible until this task tried to
do exactly that. D-026 moved `model-gateway`/`evidence-builder`/`telemetry` inside `apps/
control-api/`; `workers/`, `adapters/` and `packages/` were never part of that move and still
live as siblings of `apps/`, which is the layout T0/T1 inherited rather than chose.

**Options considered** — (a) leave `workers/`/`adapters`/`packages` unreachable from
`apps/control-api` and have T1's dispatch module do its own ad hoc `sys.path` surgery local to
itself; (b) fix it once, centrally, in `config/settings/base.py`, so every Django entrypoint
gets it for free; (c) physically move `workers/`/`adapters`/`packages` under `apps/
control-api/` to match D-026's stated end state.

**Pros and cons** — (a) is scoped to one file but means every future `JobKind` executor
(T2–T7, all of which wrap similar top-level stage packages per D-062's staffing plan) has to
rediscover and re-fix the same gap independently, or copy-paste the fix — the kind of
per-module inconsistency that produces exactly one working import path and six broken ones.
(b) fixes it once for every current and future consumer, at the cost of being a change to a
shared settings file rather than something scoped to `workers/baseline/`. (c) is what D-026
arguably implies should eventually happen, but is a real migration (import paths, `D-026`'s
own import-direction test, six workers' packages, CI paths) far outside a `BASELINE`
executor's scope — noted as a legitimate follow-up, not attempted here.

**The collision, found by running the suite, not by inspection.** `apps/control-api/tools/`
(holds `export_openapi.py`, consumed by `contracts/tests/test_openapi_dump.py`) has no
`__init__.py` — an implicit namespace package. The repo-root `tools/` (`fallback_demo.py`,
`verdict_report.py`) is a normal package with one, and shares the same bare name. Python's
import system lets a regular package found *anywhere* on `sys.path` take priority over a
namespace-package portion found earlier in path order — so simply appending the repo root
(planned as the safe, order-respecting fix) still let the *wrong* `tools` win, breaking
`contracts/tests/test_openapi_dump.py` with `ModuleNotFoundError: No module named
'tools.export_openapi'`. `apps/control-api/tools/__init__.py` (added, empty save for a
docstring) turns it into an ordinary regular package, which restores plain sys.path-order
precedence — and `BASE_DIR` sorts first — closing the collision without touching the
repo-root `tools/` package at all.

**Cost implications** — none; no new dependency, one new near-empty `__init__.py`, ~25 lines
in `base.py`.

**Security implications** — none; this only affects what is importable within the already-
trusted `control-api`/`worker` codebase, not any external input path.

**Scalability implications** — none.

**Recommendation** — (b), as implemented, with (c) flagged as a real but out-of-scope
follow-up for whoever next revisits D-026's layout (candidate: T0's author, since `run_worker`
will need this same reachability and may prefer to resolve it structurally rather than via
`sys.path`).

**Final approval authority** — CTO (technical); this is infrastructure shared by every
`JobKind` executor task (T2–T7), not something scoped to `BASELINE` alone, so flagging for
awareness beyond this task's own reviewer.

---


## D-069 — Wiring `MissionState.CANCELLING` into `orchestrator.queue.JOB_BACKED_STATES`, and keeping the synchronous teardown hook rather than removing it · 2026-08-17 · `backend-developer` seat

Posted while closing the gap PR #173's own engineering-manager review round found and
correctly blocked merge on (documented, not silently missed — see the PR's review thread):
`teardown_transition_policy` (D-068) was correct and fully tested, but unreachable, because
`orchestrator.queue.JOB_BACKED_STATES` — the only thing that decides which missions get a
`Job` enqueued (`ensure_jobs_enqueued`) or get their terminal job dispatched
(`dispatch_terminal_jobs`) — deliberately excluded `MissionState.CANCELLING`. A mission
entering `CANCELLING` therefore never got a `TEARDOWN` job, `dispatch_terminal_jobs` never had
one to route, and the pre-existing synchronous `_run_teardown_after_commit` hook (real, still
tested by `orchestrator/tests/test_teardown.py`, unchanged by #173) never calls
`transitions.transition()` — so the mission sat in `CANCELLING` forever. This is the literal
mechanism behind `.project/evidence/d7-gate-50-live-run-2026-08-17.md`'s repro.

**Decision 1 — add `MissionState.CANCELLING: JobKind.TEARDOWN` to `JOB_BACKED_STATES`.**
`CANCELLING` now behaves exactly like every other row in that map: `ensure_jobs_enqueued`
enqueues a `TEARDOWN` job on entry, `dispatch_terminal_jobs` reads its terminal result and asks
`teardown_transition_policy` (already built, already correct, untouched by this change) where
to go next. No change to `dispatch_terminal_jobs`, `ensure_jobs_enqueued`, or the policy itself
was needed — both already iterate `JOB_BACKED_STATES` generically; the map was the only thing
missing an entry.

**Options considered for the wiring point** — (a) add the map entry, as above; (b) teach
`_run_teardown_after_commit` itself to call `transitions.transition()` once
`teardown_started_compute` resolves, bypassing the job/dispatch machinery entirely for this one
state.

**Pros and cons** — (b) is fewer moving parts for this one case, but it violates
`orchestrator/queue.py`'s own stated invariant ("the only function in this codebase, outside
`authorization.service`'s own callers, that invokes `orchestrator.transitions.transition()`" —
i.e. `dispatch_terminal_jobs`), which exists precisely so there is one call site to audit for
the D-045/SEC-16 evidence-completeness guarantees `transition()` enforces under its row lock.
Calling `transition()` from a `transaction.on_commit` hook also runs it *outside* the
transaction that produced the teardown result, on a codepath with no existing precedent for
retry/failure handling if `transition()` itself raises (`_run_teardown_after_commit`'s return
value is currently discarded). (a) reuses the exact machinery T0 already built, tested
(`test_dispatch_terminal_jobs_actually_moves_a_zero_crash_mission_through_correlate` is the
reference shape), and reviewed for `FUZZ`/`CORRELATE`/etc — `CANCELLING` becomes one more
ordinary row instead of a special case.

**Recommendation / ruling** — (a). Matches the task brief's own instruction and the
engineering-manager review's first-listed option.

**Decision 2 — keep the synchronous `_run_teardown_after_commit` hook exactly as-is; do not
remove it or narrow `_requires_teardown` to stop firing on `CANCELLING`.** This means a
`CANCELLING` mission now genuinely runs `teardown.teardown_started_compute` twice: once
synchronously, inline, the moment the `CANCELLING` transition commits (existing #72 behaviour,
unchanged); once more, asynchronously, when the worker claims and runs the `TEARDOWN` job this
fix now enqueues.

**Options considered** — (a) keep both (this decision); (b) remove the `CANCELLING` case from
`_requires_teardown` (keep it firing only for genuinely terminal targets) so `CANCELLING`'s
resource release happens exactly once, through the job path, matching every other job-backed
stage's shape.

**Pros and cons** —
(b) is the architecturally "cleaner" end state — one authoritative path per event, matching how
`BASELINE`/`FUZZ`/etc already work, and it removes the double-invocation entirely rather than
relying on it being harmless. Against it: it changes tested, currently-passing behaviour owned
by #72 — `orchestrator/tests/test_teardown.py::test_transition_to_cancel_runs_teardown_after_
the_state_event` and `::test_terminal_states_are_teardown_boundaries` both assert, directly,
that entering `CANCELLING` runs the synchronous hook — and this task's authority does not
extend to silently rewriting another PR's tests to change what they assert (`Never silently
override or rewrite another role's prior work`, this seat's own operating rules). It would also
be a genuine behaviour regression for operator feedback: resource release currently happens
inline with the cancel HTTP call; removing it means an operator's "cancel" no longer visibly
tears anything down until the next orchestrator tick + a worker picks up the job (tick interval
+ claim latency, not instant) — worse UX for an action whose whole point is "stop this now",
days before a live judged demo.
(a) is not merely "acceptable because untested" — it was checked directly, not assumed:

- `orchestrator/teardown_executor.py`'s own module docstring already documents this exact
  design as deliberate ("Calling the same idempotent mechanism a second time ... is deliberate,
  not a bug to dedupe away"), written by the same PR (#173) this fix completes. This decision
  ratifies that stated intent now that the second call site actually exists and runs.
- Both real reapers are safe under genuine **concurrent** double-invocation, not merely safe
  when rerun sequentially. Traced directly: `DockerSandboxReaper.teardown_mission` ->
  `packages/sandbox/container.py::reap_orphans` calls `docker rm -f <id>` and never inspects
  the subprocess's exit code (`_run_cli` returns the `CompletedProcess` unchecked) — a second,
  concurrent `rm -f` against an id the first call already removed is a silent no-op, not an
  exception. `ModelHostReaper.teardown_mission` -> `orchestrator/model_host.py::
  stop_model_host_lease` shells out to `docker compose ... stop`, which Compose itself treats as
  idempotent (stopping an already-stopped service is not an error); the guard read
  (`_mission_started_lease`) is a read, not a claim/lock, so two readers both proceeding to
  `stop` is the worst case, and that case is itself safe.
- `teardown_started_compute`'s own "nothing left" branch (`DockerSandboxReaper`/
  `ModelHostReaper` both return `()` when there is nothing to release) means the *ordinary*
  case — sync hook wins the race, releases everything for real — leaves the async job's later
  run reporting a synthetic `no-started-compute`, `released=True` outcome: `result["total"] == 1
  > 0` and `failed_count == 0`, which is exactly what `teardown_transition_policy`'s
  `has_receipt` check requires to route `CANCELLING -> CANCELLED`. The redundant run is not
  just harmless, it is the mechanism that produces the receipt the R3 policy needs — there is
  no code path in which keeping the sync hook makes the async job's routing worse.
- Verified this by test, not just by reading: the new end-to-end test
  (`orchestrator/tests/test_cancelling_dispatch.py::
  test_cancelling_walks_all_the_way_to_cancelled_through_the_real_worker_path_with_both_
  teardown_paths_running`) asserts the fake reaper's `teardown_mission` is called exactly twice
  — once synchronously at the `CANCELLING` transition, once via the real executor dispatched
  through `queue.claim_job`/`queue.complete_job`/`queue.dispatch_terminal_jobs` — and that the
  mission still reaches `CANCELLED` cleanly. Ran it against real Postgres in this session (see
  PR test output); passes.

**Recommendation / ruling** — (a), keep both. The redundancy is real but proven safe under
concurrent (not just sequential) double execution against both actual reapers, it is the
documented intent of the PR that built the async path, and removing it would both regress
tested #72 behaviour outside this task's authority and slow down operator-visible cancel
feedback three days before the finale deadline for no correctness gain. Flagged below for
whoever owns `orchestrator/teardown.py`/`_run_teardown_after_commit` next: if a future reaper
is added for a resource that is *not* idempotent/concurrency-safe under double-invocation (e.g.
a billed cloud resource, a non-idempotent external API call), this decision must be revisited —
the safety argument here is specific to the two reapers `default_reapers()` returns today, not
a general license to keep stacking redundant release paths.

**Cost implications** — negligible; one extra `docker rm -f`/`docker compose stop` round-trip
per cancelled mission in the ordinary case (both already no-ops by the time the job runs), no
new infrastructure, no schema change.

**Security implications** — none beyond D-068's existing coverage. No new write path to
`Mission.state` (still exclusively `orchestrator.transitions.transition`, still enforced
structurally by SEC-16/`missions/lifecycle.py`); `dispatch_terminal_jobs` still the only
job-driven call site for `transition()`; job-to-mission scoping is still by `mission_id` FK,
never by anything in `Job.payload` — unchanged from cybersecurity's PR #173 review, which
already cleared the SEC-15-shaped id-confusion question for this exact dispatch path.

**Scalability implications** — none; single-mission-at-a-time throughout (D-062/D-065),
unchanged.

**Decision 3 — `_run_teardown_after_commit` now catches `teardown.TeardownFailedError` and
logs it instead of letting it propagate out of `transaction.on_commit`.** Found while writing
this fix's own end-to-end test (`orchestrator/tests/test_cancelling_dispatch.py::
test_cancelling_routes_to_failed_when_the_teardown_job_itself_reports_a_leak`), not assumed:
walking a mission `CANCELLING -> FAILED` through the real `dispatch_terminal_jobs` — the R3
"no receipt" branch — crashed, because `MissionState.FAILED` is itself teardown-triggering
(`is_terminal`), so the synchronous hook runs *again* on that second transition, and if the
same resource is still stuck (the realistic case — a resource that failed to release once is
likely to still be stuck moments later), `TeardownFailedError` propagates uncaught out of
`transaction.on_commit`, out of `transitions.transition()`, and — because `dispatch_terminal_
jobs`'s per-mission `try/except` only catches `ContractError` (a `RuntimeError` is not one) —
out of `dispatch_terminal_jobs` itself, crashing the tick's dispatch pass for every other
mission being processed in that same call, not just this one.

This was always a latent bug in `_run_teardown_after_commit` (any transition into a terminal
state with a synchronously-failing reaper would have hit it), but this fix is what makes it
newly *reachable*, for the first time, via `dispatch_terminal_jobs` — before this fix nothing
ever drove a mission from `CANCELLING` into `FAILED` at all, so this exact call sequence
(dispatch -> transition -> on_commit -> teardown -> raise) never fired.

**Options considered** — (a) catch `TeardownFailedError` in `_run_teardown_after_commit` and
log it, same shape as `queue.py`'s existing "one mission's failure must not stop the tick"
pattern; (b) leave it and instead broaden `dispatch_terminal_jobs`'s `except ContractError` to
also catch `TeardownFailedError`; (c) leave it unfixed and document it as a known risk for
whoever owns `orchestrator/transitions.py`/#72 next.

**Pros and cons** — (b) only protects the one call site this fix happens to exercise
(`dispatch_terminal_jobs`); the same crash is still reachable from any other direct caller of
`transition()` into a terminal state (`missions/service.py`'s `cancel_mission`/`pause_mission`
call it directly too, outside any tick loop's protection). (c) leaves a now-more-reachable crash
in place three days before a judged live demo, for a fix that is small and low-risk. (a) fixes
it at the one place the exception is actually produced, for every caller at once, and loses
nothing: `teardown_started_compute`'s own docstring already guarantees the failed outcome is
persisted as a `TEARDOWN_CONFIRMED` event *before* it raises, so logging-and-swallowing here
does not hide the failure from the event stream or from a future policy/operator reading it —
it only stops an already-committed state write from turning into an unhandled exception for
whichever caller happens to be on the stack. This also matches Django's own documented
`on_commit` contract more closely: a callback registered there runs after the transaction it
was attached to has already committed, with nothing left to roll back, so letting it raise
into an arbitrary caller is a correctness hazard independent of this fix.

**Recommendation / ruling** — (a). Proven by test, not just argued:
`test_a_synchronously_failing_teardown_does_not_crash_the_cancelling_transition` drives a real
`transitions.transition(..., CANCELLING, ...)` call with a reaper that always reports
`released=False`, and asserts both that `transition()` returns normally (no raise) and that the
failure is still recorded as a `TEARDOWN_CONFIRMED` event with `released=False` — nothing lost,
only the crash removed. Ran in this session against real Postgres; passes (see PR test output).

**Cost/security/scalability implications of Decision 3** — same as Decisions 1–2 above: no new
dependency, no new write path to `Mission.state`, no change to single-mission-at-a-time scope.
Slightly *reduces* an existing availability risk (an uncaught exception mid-tick previously
could have wedged `dispatch_terminal_jobs` for every mission in that pass).

**Open question flagged for CTO, not decided here** — whether `default_deadline_seconds`
should grow a `TEARDOWN`-specific budget (it currently falls through to the generic
`sandbox.max_seconds` default, 5400s/90min, same as every other kind without a dedicated
branch — `CORRELATE`/`PATCH_GENERATE`/`VERIFY`/`EXPORT` already share this gap, so it is not
new to this change and not this task's to fix unilaterally).

**Final approval authority** — CTO (technical), for the deadline-budget open question above;
the three implementation decisions themselves (map wiring, keep-both-teardown-paths, and the
`on_commit` exception-safety fix in Decision 3) are within backend-developer's scope per this
task's brief and D-061 §4's original delegation to T7/T0.

## D-070 — control-api/worker container boot regression (#168 T1, PR #174): `additional_contexts` for `workers/`, `packages/`, `adapters/`, mirroring D-032's `demo-repositories` pattern · 2026-08-17 · `devops-engineer` seat

**Trigger** — a backend-developer flagged, while merging `main` into an unrelated branch, that
PR #174 (#168 T1, already on `main`) changed `missions/apps.py`'s `ready()` to unconditionally
`from workers.baseline import dispatch`, which imports `packages.sandbox`. `ready()` runs on
every Django process start (`manage.py`, ASGI/WSGI, `pytest-django`), and
`control-api.Dockerfile`'s build context is `apps/control-api/` only —`workers/`, `packages/`,
`adapters/` are repo-root siblings of `apps/`, never copied or mounted into either image in
either compose profile. Verified real, not theoretical, by actually building and booting the
container against current `main` before touching anything:
`docker build -f infrastructure/compose/images/control-api.Dockerfile --target runtime
--build-context demo-repositories=./demo/repositories -t verify:runtime ./apps/control-api`
built clean (the build itself cannot fail on a missing Python import), but
`docker run ... verify:runtime python manage.py check` raised:

```
File "/app/missions/apps.py", line 26, in ready
    from workers.baseline import dispatch  # noqa: F401
ModuleNotFoundError: No module named 'workers'
```

— identically for both the `dev` and `runtime` Dockerfile targets. This is a **container-only**
regression: PR #174's own commit message and this repo's D-066 both claim a "cross-package
import fix" already covers this (`config/settings/base.py` appends `REPO_ROOT =
BASE_DIR.parent.parent` to `sys.path`). That fix is real and correct for the case it was
written for — a bare-metal checkout or CI runner, where `apps/control-api` sits two directories
below an on-disk repo root that actually contains `workers/`/`packages`/`adapters/` — but
inside either container image, `BASE_DIR` (`/app`) *is* the flattened build context (this
Dockerfile's own build context is `apps/control-api/` only, per its header), so
`BASE_DIR.parent.parent` resolves to the container filesystem root and the `sys.path.append`
silently matches nothing. Neither CI (runs `pytest` against a full bare-metal checkout, never
builds this image) nor `docker compose config` (validates YAML shape, never runs `docker
build`) could have caught this — confirmed by reading `.github/workflows/ci.yml` directly,
not assumed.

**Decision** — Apply the exact pattern PR #167/D-032 already established for
`demo/repositories` (a repo-root sibling of `apps/`, reached without widening
`control-api.Dockerfile`'s own build context): three more named Docker Compose
`additional_contexts` entries — `workers-source`, `packages-source`, `adapters-source` — added
to both `control-api` and `worker` services' `build:` blocks in `docker-compose.finale.yml`
(runtime target), `COPY --from=<name> --chown=app:app . /app/<name>` added to
`control-api.Dockerfile`'s `runtime` target, and equivalent plain bind mounts
(`../../workers:/app/workers`, `../../packages:/app/packages`, `../../adapters:/app/adapters`)
added to both services in `docker-compose.yml` (dev target copies nothing in at build time —
source arrives entirely by bind mount, same as `demo/repositories`'s existing dev-vs-finale
split). Landing at `/app/<name>` — plain subdirectories of `BASE_DIR`, already at
`sys.path[0]` — makes `import workers`/`packages`/`adapters` resolve with zero further
settings change; `REPO_ROOT`'s `sys.path.append` in `config/settings/base.py` is left alone as
dead-but-harmless code for the bare-metal/CI case it was actually written for, since fixing it
symmetrically (relative to a container's own root) is a bigger, riskier change to a file owned
by backend-developer, and this fix only needed to close the container-boot gap, not rewrite
someone else's already-tested settings logic.

**Options considered** — (a) the `additional_contexts`/bind-mount fix above; (b) widen
`control-api.Dockerfile`'s primary build context to the repo root, so a single `COPY . /app`
picks up everything; (c) physically move `workers/`/`packages/`/`adapters/` under
`apps/control-api/`, matching D-026's stated eventual end state (already flagged as a
legitimate follow-up in D-066 itself); (d) patch `config/settings/base.py`'s `REPO_ROOT`
computation to be container-aware (e.g. an env-var override).

**Pros and cons** — (b) is the smallest textual diff but breaks the Dockerfile's own explicit,
repeatedly-stated contract ("Build context is `apps/control-api/`... owned by the backend
developer... so that no infrastructure change ever touches a file inside the application
directory") and D-032's identical reasoning for `demo/repositories` — widening the primary
context also pulls in `.git/`, `docs/`, `services/`, `tests/`, everything else at repo root,
unless a much larger `.dockerignore` is grown to compensate, which is strictly more invasive
than three named contexts. (c) is a real repo-layout migration (import paths, D-026's own
import-direction test, six workers' packages, CI paths) — correctly out of scope for an urgent
regression fix, and already flagged as a candidate follow-up in D-066. (d) is tempting since it
would fix `tools/export_openapi.py`'s identical `REPO_ROOT` pattern too, but that script is
never invoked inside either container (checked directly: no CI step or Dockerfile RUN/CMD
references `export_openapi`) so fixing it here would be solving a problem this task doesn't
have, and would touch `config/settings/base.py`, a file this task's owning role does not own —
per this role's own standing instruction not to "fix" another role's code to make it deploy,
better flagged than silently patched. (a) is the only option that fixes the actual container
regression with no ownership boundary crossed and a precedent already reviewed and merged in
this exact codebase (PR #167).

**Cost implications** — none. No new dependency, no new service, no image-size concern worth
noting (`du -sh packages workers adapters` = 936K/148K/168K combined, checked directly).

**Security implications** — none beyond what `demo/repositories`'s identical mechanism already
carries: these are three more repo-root source directories reachable from a
build-time-only named context (`runtime`/finale) or a bind mount already scoped to the
already-`internal: true` `api`/`backend` networks (dev) — no new egress, no new secret, no
change to `read_only`/`cap_drop` posture on either service. Not marked `:ro` in the dev bind
mounts (unlike `demo/repositories`), a deliberate difference: these are live source
directories other roles actively edit locally, mirroring `apps/control-api`'s own writable
`/app` mount, not read-only fixture data — `packages`/`workers`/`adapters` never held
attacker-controlled bytes in the first place, so there is no new blast-radius question either
way.

**Scalability implications** — none; this only changes what is importable inside an
already-running process, not any runtime resource ceiling.

**Verification, stated plainly** — VERIFIED, not asserted: (1) `docker build --target runtime`
with the three new `--build-context` flags built clean and the resulting image's `manage.py
check` (finale settings, all required env vars supplied) reported `System check identified no
issues (0 silenced)`; (2) the `dev` target, run with the exact bind-mount layout added to
`docker-compose.yml`, likewise reported zero issues; (3) `docker compose -f docker-compose.yml
--env-file ../../.env up -d db redis control-api` — the real compose command, not a simulation
— brought `control-api` up clean (`docker ps` showed `Up`, no restart loop; logs showed a
normal uvicorn startup, no traceback), and `docker exec brahmadatta-control-api python
manage.py check` inside that live container reported zero issues; (4) both
`orchestrator.executors.EXECUTOR_REGISTRY` entries (`workers.baseline.dispatch`,
`orchestrator.teardown_executor`, the exact two modules `ready()` imports) register correctly
inside the running container, checked directly via `docker exec ... python -c "..."`, not
inferred; (5) `docker compose -f docker-compose.yml config --quiet` and
`docker compose -f docker-compose.finale.yml config --quiet` both validate clean with the same
env vars CI supplies; (6) the full host-side test suite — the same way CI itself runs it, since
containers have no network egress by design (C4) and cannot `pip install` — passes: `apps/
control-api`'s own suite (519 tests, matching CI's `Control API tests` step), root
`tests/` (74 tests, matching CI's `Architecture tests` step, including the compose-topology
tests that assert the finale profile has no source mounts into control-api — still true, this
fix does not touch that), and `packages/sandbox`/`packages/test-fixtures` (79 passed, 4 skipped
— all four skips pre-existing and platform/dependency-scoped, unrelated to this change:
Darwin's `RLIMIT_AS`/`/proc` sandbox-test gaps and a missing dev-only `jsonschema` install).

**Recommendation / ruling** — (a), implemented as described, pushed to
`fix/168-docker-build-context`.

**Final approval authority** — CTO (technical); this is an infrastructure fix restoring a
contract (dev/finale parity, `apps/control-api`'s stated build-context boundary) DevOps already
owns per its charter, not a new architectural call — flagged here at the same level of
formality as D-032/D-066 since it blocks/unblocks already-landed T0/T0b/T1 work and the
upcoming T5/T7 stages.

## D-071b — PR #187 (#168 T6, evidence-bundle export) security review: SEC-48 (CRITICAL) / SEC-49 (MEDIUM) filed, verdict BLOCKED · 2026-08-17 · `cybersecurity` seat

**Trigger** — assigned review of PR #187 (`feat/168-t6-export`), the `JobKind.EXPORT`
executor and evidence-bundle assembly, ahead of merge. Full findings posted as a PR
comment (`gh pr comment 187`); this entry records the binding severity call and the
reasoning per this seat's standing decision-record rule.

**Decision** — **BLOCKED (Critical).** SEC-48 (raw subprocess output, including
whatever secrets a verification subprocess's environment holds, reaches every one of
`report.md`/`report.json`/`gate-matrix.json` inside the tarball a judge downloads,
with zero redaction added at the export boundary) is a documented critical finding
and stands as this seat's veto until fixed. SEC-49 (write-side size-cap enforced too
late, and its own failure path orphans the oversized tarball on disk instead of
cleaning it up) is filed alongside as MEDIUM, non-blocking on its own.

**Why this is CRITICAL and not HIGH/MEDIUM** — the standing project rule this repo
already lives by (`GateResult.detail`'s own schema docstring: "User-safe summary.
Never raw target output, never secrets," `contracts/verdict.py:61-64`; and today's
earlier SEC-44/SEC-45 findings on PR #175, rated CRITICAL/HIGH for an *in-system*
exposure) already established that raw subprocess output reaching any consumer is
unacceptable. PR #187 takes that same still-open leak (SEC-44/SEC-45 are fixed only
on the unmerged `feat/168-t5-verify-executor` branch, commit `9ba17ec` — **not** in
`main`, and therefore not in this PR's own history) and, for the first time, routes
it to an external party outside the deployment entirely: a competition judge who
downloads the exported bundle. Widening a same-system leak into an
exfiltration-to-an-external-human channel is a strict severity increase, not a
lateral one — this seat's authority to set severity (per its charter) is exercised
here to hold the line at CRITICAL rather than let the T6 PR's own scope ("just
assembly, not the leak's root cause") argue it down.

**Proof, not argument** — three adversarial tests written and run against the PR's
own worktree (`brahmadatta-ai-worktrees/driver-t6` @ `9961250`), not committed to
the branch (scratch, deleted after the session): (1) confirmed `DATABASE_URL`
inheritance into a verification subprocess is still live on this PR's base; (2)
confirmed a fabricated `DATABASE_URL=...` line embedded in fake `cmake configure`
stdout still lands verbatim in `GateMatrix.compile.detail` via the real
`run_verification` code path; (3) confirmed that same poisoned `detail` string,
carried through a real `record_verification` → `assemble_evidence_bundle` →
`render_markdown`/`render_gate_matrix`/`EvidenceBundle.model_dump_json()`
round-trip, lands verbatim in all three exported files. All three passed (i.e.
reproduced the leak). SEC-49 proven the same way: forced
`EVIDENCE_BUNDLE_MAX_BYTES=10`, confirmed `UnreadableArchiveError` and a full-size
orphaned `.tar.gz` left in `EXPORT_WORKSPACE_ROOT` afterward. Full existing PR test
suite independently re-run and confirmed green (502 passed / 9 skipped control-api,
74 passed root, 19/19 T6-specific) — the leak is real precisely because none of the
PR's own tests construct a `GateResult` with a realistic `detail` value
(`orchestrator/tests/conftest.py::gate_matrix` only ever uses empty/literal
strings). `pip-audit -r requirements.txt`: no known vulnerabilities (this PR adds no
new dependency).

**Options considered** — (a) BLOCKED, full stop, until both PR #175 merges/rebases
under #187 *and* #187 adds its own redaction layer at the export boundary; (b)
BLOCKED only until #175 merges, treating T6's lack of independent redaction as a
non-blocking architectural note since the root cause is being fixed elsewhere; (c)
CLEARED with conditions, on the theory that T6's own code is a faithful "read what's
already there" assembly stage and the leak is entirely T5's to own.

**Pros and cons** — (c) is wrong on its own terms: T6 is the stage that turns an
in-system field into an artifact an external party receives, so it inherits the
exposure regardless of which stage generated the unsafe value — "I only read what
was already unsafe" does not change who ships it externally. (b) fixes the
immediate reproduced leak but leaves the export boundary with no independent check
against the *next* upstream stage (or gate, or future contributor) that violates
`GateResult.detail`'s own documented contract — given this is the last code that
runs before content leaves the system for a human outside it, trusting a docstring
alone here is the single point of failure this review exists to catch. (a) costs
one redaction pass at the export boundary, a small, contained change, in exchange
for closing that single point of failure permanently rather than only for the one
leak this session happened to find.

**Cost implications** — none beyond developer time for the two fixes; no new
dependency, no infrastructure change.

**Security implications** — this decision *is* the security implication; no further
downstream call to record.

**Scalability implications** — none; both findings are about correctness/leakage on
a fixed code path, not about load.

**Recommendation / ruling** — BLOCKED (Critical) stands. Findings route back through
`engineering-manager` to whichever developer owns #187 for the fix (sequencing onto
#175 plus an export-boundary redaction check for SEC-48; a `finally`-block fix for
SEC-49's orphaned tarball); re-review required before merge, per this project's own
review-chain rule that a critical finding is waived only by written CEO risk
acceptance recorded here — no such acceptance was sought or given.

**Final approval authority** — `cybersecurity` (severity rating, per this seat's own
charter); CTO may arbitrate a dispute over the severity call above but cannot waive
SEC-48 unilaterally; only a written CEO risk acceptance recorded in this file can
override the block.


---

## D-073 — Topology for FUZZ execution: no socket, no bare TLS-remote daemon either; a
kind-scoped `fuzz-worker` claims `FUZZ`/`MINIMIZE` off the host, everything else stays
containerized and egress-denied · 2026-08-17 · CTO

**Numbering/labelling note, read first.** The devops-engineer's D-072 §3 (open PR #192,
`feat/189-fuzzing-image`, not yet on `main`) and `packages/sandbox/container.py`'s own module
docstring both cite "**D-024**" as the ruling that forbids mounting the Docker socket. That is
a stale label surviving a renumbering collision this log's own notes already warn about (see
the numbering note appended to D-023/D-024 above). On `main` today, D-024 is
"Job queue is Postgres `SELECT … FOR UPDATE SKIP LOCKED`; no broker" — unrelated. **The actual
ruling forbidding a socket mount is D-036, "The container runtime socket is never mounted, and
a test says so"** (`FORBIDDEN_SOCKET_PATHS`, `tests/architecture/test_container_isolation.py`),
plus D-035's separate "worker container has no route off the host" invariant
(architecture-spec §4.1 L1). Both stand. This decision does not touch `container.py`'s
docstring or D-072's own text — those are other roles' or a prior session's work — but the
record here uses the correct numbers, and whoever next edits `container.py` should fix the
`D-024` references to `D-036` while there.

**Trigger** — D-072 §3 (devops-engineer, real verification: a genuine 2308-execution libFuzzer
campaign against `demo/repositories/pktcfg` found the seeded heap-buffer-overflow via
`ContainerJail`, run directly against the host's own Docker daemon, not through the compose
`worker` service). The finding: `ContainerJail.run` (`packages/sandbox/container.py::_run_cli`)
shells out to a `docker` binary via `subprocess.run`, which needs the binary on `PATH` and a
daemon reachable through whatever `DOCKER_HOST`/socket the process's environment resolves to.
The compose `worker` service is built from `control-api.Dockerfile` (Python/uvicorn, no
`docker` CLI, no socket mounted, by design), so the *containerized* `worker` cannot invoke
`ContainerJail` at all today — proven, not assumed, by D-072's own successful run happening
outside that container.

### 1. What I read before deciding

- `docs/09-company/06-architecture-spec.md` §1.1/§3/§4.1: `orchestrator` and `worker` are
  separate processes (D-024's own ruling); `worker` claims jobs generically off one `Job`
  table with `SKIP LOCKED` (`orchestrator/queue.py::claim_job`, checked directly — it filters
  on `state`/`run_after` only, **no `kind` filter exists today**); and Invariant A's L1
  ("the worker container has no route to the internet") is the mechanism that keeps the one
  process holding both repository content and the model-gateway HTTP client
  (`gateway/client.py`) from ever reaching a hosted inference API. The spec does not say
  *how* `worker` is meant to reach a container runtime for `FUZZ` specifically — this gap
  predates D-072; D-072 is the first task that actually exercised the path far enough to hit
  it.
- `packages/sandbox/container.py`: confirmed — CLI subprocess (`_run_cli`), no Docker SDK
  import anywhere in the file, no explicit `env=` override on the `subprocess.run` calls, so
  `DOCKER_HOST`/`DOCKER_TLS_VERIFY`/`DOCKER_CERT_PATH` in the calling process's environment
  would be honored by the `docker` CLI **with no code change to this module** — a remote
  context is mechanically available if `docker` is installed and reachable. This matters for
  option (b) below: it is not blocked by the code, only by D-035/D-036's network posture.
- `infrastructure/compose/docker-compose.yml` / `docker-compose.finale.yml`: `worker`'s
  network is `backend` only (`internal: true`, no gateway — same family as L1), and its
  `command` still defaults to `${CONTROL_API_WORKER_CMD:-python manage.py rqworker default}`
  — `django-rq` is not a dependency (confirmed absent from `requirements.txt`); this is dead
  scaffolding already flagged in D-061/D-062 (`.project/decisions.md` line ~2862) and not yet
  fixed on `main`. **No `orchestrator` service exists in either compose profile at all** — also
  already flagged in D-061/D-062, also not yet fixed. So the containerized deploy path for
  the real `run_orchestrator`/`run_worker` pair (built by T0/T0-series, `apps/control-api/
  missions/management/commands/run_worker.py`) has never been fully wired end to end;
  D-072's FUZZ-execution gap is one more item in that same unfinished list, not an isolated
  regression.
- Grepped this repo for "docker socket", "DinD", "docker-outside-of-docker", "remote docker",
  "DOCKER_HOST", "TLS" near "docker": nothing beyond D-035/D-036/D-072 §3 itself. This problem
  was not pre-anticipated with a named design; D-072 §3 is the first place it is written down.

### 2. The core judgment call: option (b) (remote `DOCKER_HOST` over TLS) is not actually
   safer than the socket mount D-036 forbids, and should not be adopted as the general answer

A client certificate authenticates *who* may connect to the Docker Engine API; it does not
scope *what* they may do once connected. The full Engine API — start a container with
`--privileged`, bind-mount `/` from the daemon's host, join the host PID/network namespace —
is reachable to anyone holding a valid client cert, exactly as D-036's own stated reasoning
about the socket describes ("a container with that socket can start a sibling with
`--privileged -v /:/host` and read or write anything"). Moving the same unrestricted API
across a TCP+TLS boundary changes *transport*, not *capability*. A compromised `worker`
process with `DOCKER_HOST=tcp://sandbox-executor:2376` and a valid client cert is exactly as
dangerous as a compromised `worker` with the socket bind-mounted — worse, in one respect: it
also requires opening `worker`'s network egress beyond L1's current "no route anywhere,"
undoing part of Invariant A's own enforcement for the same process that holds the model-gateway
client. **Option (b), as commonly implemented, is rejected as the general-purpose answer.** It
is not "cheaper D-036-lite"; it is D-036's exact threat model with a TLS handshake in front of
it, and it is scoped nowhere near narrowly enough to be worth that.

This is the finding that should have been in D-072 §3 as the reason (b) needs its own scrutiny,
not merely listed neutrally alongside (a) and (c) — flagged for the record now.

### 3. Recommended topology: split the worker fleet by `JobKind`, not by transport

**Decision** — `worker` stays exactly as architecture-spec §1.1/§4.1 describes: containerized,
`internal: true`, no egress, claiming every `JobKind` **except** `FUZZ`/`MINIMIZE`. A second,
purpose-built worker instance — `fuzz-worker` — claims only `FUZZ`/`MINIMIZE` jobs and is the
**only** process anywhere in this system ever given the ability to invoke a container runtime.
For the finale demo (§4 below) `fuzz-worker` runs directly on the host, outside any container
boundary at all — so D-036's "no container mounts the socket" rule is not merely obeyed, it is
inapplicable, because there is no container to mount anything into. For the post-competition
product, `fuzz-worker` is the seed of the "sandbox-executor" pattern named in the brief: a
single, narrow-purpose, network-egress-nothing process whose only job is "claim a `FUZZ`/
`MINIMIZE` job, run `ContainerJail`, report the result" — never given a model-gateway client,
never given repository-writing access beyond its own job's snapshot, so a compromise of it
cannot reach the inference API (it never has credentials or a code path to try) and a
compromise of the *general* `worker` cannot reach a container runtime (same reason, in
reverse).

**Options considered** — (a) a separate sandbox-executor host/service, `worker` talks to it
over a small internal API/queue, the executor is the only thing that ever touches the Docker
daemon — brief's own framing, adopted, but *scoped by `JobKind`-filtered claiming off the
existing `Job` table* rather than a new bespoke RPC surface, because the queue **already is**
that internal API: `Job` rows, `SKIP LOCKED`, a `lease_owner` — there is no need to invent a
second transport when the first one already generalizes to "more than one worker fleet claiming
different slices of the same table," which is exactly what a `kind`-filtered `claim_job` gives
for free. (b) remote `DOCKER_HOST` over mutual TLS — rejected in §2, not because TLS is weak,
but because the thing being protected by TLS (the raw Engine API) is too broad to protect this
way; adopting it would mean re-litigating D-036's own argument and losing. (c) relax D-036 and
mount the socket directly into the existing `worker` container — rejected outright, same as
D-072 §3 already concluded; not on the table without a CEO risk acceptance overriding a
documented Critical-adjacent binding decision, which nothing in this task justifies. (d) (mine,
not in the brief's three) split the worker fleet by `JobKind` rather than building a new
service — chosen, for the reasons in §4 below: it reuses `Job`/`claim_job` verbatim, needs one
small, additive filter, and does not touch `ContainerJail`, the compose network topology, or
any of D-035/D-036's already-tested assertions.

**Why (d)/kind-split over a literally-separate "sandbox-executor service" with its own API**:
the brief's (a) is architecturally right but is scoped as a new service with its own contract,
auth, and failure modes — real work, and more of it than this timeline affords cleanly (§4).
The queue already has everything a broker needs: a durable job table, lease/heartbeat fencing
proven correct under concurrent claimers (`orchestrator/tests/test_queue_claim_locking.py`),
and a `JobKind` dispatch table (`orchestrator/executors.py`) that already refuses to run a job
kind that never registered. Filtering `claim_job` by `kind` turns "which process may touch a
container runtime" into a property of *which jobs a given worker process claims*, enforced by
the same row-locking mechanism that already enforces "which process may touch `Mission.state`"
(D-045/SEC-16). No new network listener, no new credential, no new failure mode beyond "this
worker fleet is down," which the existing lease-reclaim reaper (architecture-spec §3.4) already
handles identically for every `JobKind`.

**Cost implications** — one more long-running process to supervise (the `fuzz-worker`), zero
new infrastructure (no new service, port, or credential) — a `--kinds` CLI flag and a `.filter
(kind__in=...)` clause. Compares favorably to (a)-as-a-literal-service, which would cost a
network listener, a schema or protocol for the RPC, and its own auth story.

**Security implications** — this *increases* the precision of D-035/D-036's existing
guarantees rather than trading one for the other: the general `worker` fleet (which holds the
model-gateway client) never gains container-runtime access, and the one process that gains
container-runtime access (`fuzz-worker`) never gains a model-gateway client or a route to
`model-host` — enforced structurally (no such import exists in `workers/fuzzing/`, checked
directly) rather than by discipline alone, matching D-026's own "the boundary that actually
carries the risk stays a process/container boundary" argument. Residual risk, stated plainly
in §5: for the finale demo `fuzz-worker` runs bare-metal, which forfeits L1's *network-level*
kill switch for that one process specifically (it is not `internal: true` the way the
containerized `worker` is) — mitigated by `fuzz-worker` never holding model-gateway code or
credentials at all, so there is nothing for that process to exfiltrate toward even with a
route out. Cybersecurity scrutiny required before this ships — see §6.

**Scalability implications** — none beyond D-024/D-062's existing single-mission-at-a-time
scope; a second worker fleet claiming a disjoint `kind` set is the same shape the architecture
spec already names as "DevOps decides: worker replica count (1 or 2)" (§1.1), just split by
capability instead of duplicated identically.

**Final approval authority** — CTO (technical) for the topology; `cybersecurity` holds the
review gate on the implementation per CLAUDE.md's standing rule for isolation-relevant changes,
and specifically on the bare-metal-for-finale exception in §4/§5.

### 4. Honest timeline read: the finale-demo shape is a same-day fix; the permanent
   sandbox-executor service is not

**Same-day, for 2026-08-20 (finale demo):** run `fuzz-worker` as a **bare-metal host process**
— `python manage.py run_worker --kinds FUZZ,MINIMIZE` — pointed at the same Postgres the
compose stack already runs (published on the host in dev; would need a published port or a
host-network escape hatch in the finale profile, see task 4 below), using the operator's own
already-verified Docker daemon exactly as D-072's own real campaign test already did. This is
not a new execution shape — it is the **exact path D-072 §3 already proved works**, generalized
from "a pytest process on the dev host" to "a supervised `run_worker` process on the finale
host," with only a `--kinds` filter as new code. There is direct precedent for running a piece
of this stack bare-metal rather than containerized: `infrastructure/scripts/build-fuzz-image.sh`
already does, and CI's own `cpp-adapter`/`packages/sandbox` test jobs run `pytest` directly on
the GitHub-hosted runner, not inside any of this repo's own images — "the process that touches
Docker runs on the box that has Docker" is already this project's tested, working pattern; this
decision extends it to `fuzz-worker` rather than inventing something new.

**Not a same-day fix, correctly deferred past 2026-08-20:** the permanent, containerized
"sandbox-executor" service — `fuzz-worker` itself running inside a narrowly-scoped container
with either its own isolated Docker-in-Docker daemon or a registry-fronted remote daemon on a
separate host, reachable over an authenticated channel, with a hardened API surface instead of
raw `Job`-table claiming. That is real infrastructure work (a new image, a new network segment,
a credential/cert lifecycle, and — because it is the one process in the whole system with
container-runtime power — the single highest-value cybersecurity review target this project
will have produced) and does not belong on a three-day clock next to T4 (`PATCH_GENERATE`,
still not started per D-061/D-062) and #189's own remaining MINIMIZE crash-artifact gap.
**Scope it down for the competition**: ship the bare-metal `fuzz-worker` exception now, flagged
explicitly as a documented, time-boxed deviation from "everything containerized," and open a
follow-up issue for the containerized sandbox-executor as the real post-competition fix.

### 5. What cybersecurity should specifically scrutinize once this is implemented

1. **`fuzz-worker`'s environment is not the general worker's environment.** It must have zero
   model-gateway configuration (`gateway/client.py` never imported, no API key/base-URL env
   var reachable) — the mitigating claim in §3's security-implications paragraph is only true
   if this is checked, not assumed. Recommend the same shape as L3's `test_single_inference_
   client.py`: an AST/import-set assertion that `workers/fuzzing/` (and whatever module
   `fuzz-worker`'s entrypoint pulls in) never imports `gateway.client` or an HTTP client.
2. **Bare-metal `fuzz-worker` really cannot reach `model-host`, not just "isn't configured
   to."** If it runs on the same physical/VM host as the rest of the compose stack and that
   host's own network allows it to reach `model-host`'s published/internal address, "no
   credentials" is a weaker claim than "no route." Verify with an actual connect attempt
   (same shape as `infrastructure/scripts/egress-test.sh`), not by code inspection alone.
3. **`--kinds` filtering is enforced at the query, not just the CLI flag.** A `fuzz-worker`
   invoked without `--kinds` (operator error, or a stale supervisor unit copied from the
   general worker's config) must not silently claim `PATCH_GENERATE`/`EXPORT`/etc — confirm
   the default, if `--kinds` is omitted, is either "refuse to start" or "claim nothing," never
   "claim everything," which would quietly reopen exactly what this decision closes.
4. **The finale host's own hardening.** A bare-metal process with real Docker daemon access is
   the single most privileged thing running on that machine for the day of the demo — confirm
   it is not also running as root, confirm the operator account it runs under is not also the
   account judges or anyone else touches, and confirm `docker` on that host is the same
   version/config this session's D-072 verification used (containerd store vs. overlay2
   changes the digest-pinning story per D-072 §2 — worth a pre-flight check the morning of).
5. **Whether the bare-metal exception needs its own written risk acceptance.** This decision
   treats it as a scoped, time-boxed, CTO-approved deviation, not a change to D-035/D-036
   themselves (those still bind the *containerized* `worker` fully). If cybersecurity judges
   that distinction insufficient, escalate for a CEO risk acceptance per this seat's own
   charter rather than treating my approval here as the final word — my authority covers the
   technical topology, not overriding a `cybersecurity` veto on an isolation-relevant change.

### 6. Task breakdown, sized against ~3 days

1. **`claim_job`/`run_worker` kind filter** (backend-developer, ~1-2 hrs). Add an optional
   `kinds: Iterable[JobKind] | None` parameter to `orchestrator.queue.claim_job`'s query
   (`.filter(kind__in=kinds)` when provided) and a `--kinds FUZZ,MINIMIZE`-style CLI argument
   to `run_worker.py`, threaded through `_claim_and_run`. Additive; does not change existing
   callers' behavior when the parameter is omitted.
2. **`fuzz-worker` bare-metal entrypoint + process supervision** (devops-engineer, ~half day).
   A documented `manage.py run_worker --kinds FUZZ,MINIMIZE` invocation against the finale
   Postgres (needs a reachable connection string from the host — check whether the finale
   profile already publishes Postgres's port or needs one added), a systemd unit or equivalent
   supervisor entry so it restarts like every other long-running process this project already
   documents supervision for (architecture-spec §3.4's "dead worker visible within 60s"
   already covers detection; this is only "start it and keep it started").
3. **Confirm `SANDBOX_FUZZ_IMAGE` and Docker reachability from the finale host directly**
   (devops-engineer, ~1 hr, mostly re-verification). D-072 already proved the image and
   `ContainerJail` work on the dev host; re-run the same real-campaign check
   (`BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN=1 pytest workers/fuzzing/tests/test_real_campaign.py`)
   on the actual finale host before the demo, not just once in this session, since D-072 §2
   already flagged that digest-pinning behavior differs by Docker storage driver.
4. **The import-boundary test from §5.1** (backend-developer or cybersecurity, ~1-2 hrs):
   assert `workers/fuzzing/` and `fuzz-worker`'s entrypoint module never import `gateway.client`
   or a raw HTTP client library, mirroring `tests/security/test_single_inference_client.py`'s
   existing AST-walk shape.
5. **Cybersecurity review of the whole shape** (cybersecurity, ~half day) — the five items in
   §5, run against the actual implementation, before this is treated as demo-ready. This is a
   gate, not a parallel task; nothing in 1-4 ships to the finale host without it signing off,
   per CLAUDE.md's standing rule for isolation-relevant changes.
6. **Fast-follow, explicitly not on this timeline**: file an issue for the permanent
   containerized sandbox-executor service (§4's "not a same-day fix" half) so the bare-metal
   exception has a tracked, dated expiry rather than quietly becoming the permanent answer by
   default.
7. **Unblocking prerequisite, not new scope**: the compose `worker` service's stale `rqworker`
   command and the missing `orchestrator` compose service (both already flagged in D-061/D-062,
   both still unfixed on `main` as of this session) should land before or alongside this, since
   they block the *general* `worker` fleet from running for real at all, independent of the
   FUZZ-specific gap this decision addresses.

**Final approval authority (whole record)** — CTO (technical) for the topology and staffing
shape; `cybersecurity` holds the implementation gate per §5/§6.5; CEO holds any risk-acceptance
escalation per §5.5 if cybersecurity judges the bare-metal exception needs one.


---

## D-075 — SEC-50 ruling: D-073 §3's "nothing to exfiltrate toward" mitigation does not hold;
`model-host` gets a bearer-token proxy and a loopback-only bind, not a CEO risk acceptance ·
2026-08-17 · CTO

**Numbering note.** `main` tops out at D-070 as of this session. `D-071`–`D-074` exist only on
open, unmerged branches (`feat/168-*` series, `feat/189-fuzz-worker-topology` / PR #197 which
this record responds to, `docs/d073-fuzz-topology` / PR #195) and disagree with each other
across branches — the exact collision this log's own D-023/D-024 note already warned about.
Checked directly against `origin` for every open PR branch, not assumed: the highest number in
use anywhere is D-074 (PR #197, PR #195). This record takes **D-075** so it does not collide
with any of them once they merge, regardless of merge order.

**Trigger** — cybersecurity's review of PR #197 (`feat/189-fuzz-worker-topology`, implementing
this seat's own D-073 design), filed as **SEC-50**, HIGH/CRITICAL for finale deployment
specifically, not blocking PR #197's merge (that PR's actual scope — kind-filtering,
import-boundary — is sound and cleared to merge as-is). Full finding:
https://github.com/Mahatav/brahmadatta-ai/pull/197#issuecomment-5315053710.

D-073 §3 accepted the residual risk of running `fuzz-worker` bare-metal (outside `internal:
true`, outside L1's network-level kill switch) on the argument that even a theoretical route
toward `model-host` had "nothing to exfiltrate toward... since there is nothing for that
process to exfiltrate toward even with a route out" — `fuzz-worker` structurally never holds a
model-gateway client or credentials (confirmed true, still true, enforced by
`tests/architecture/test_fuzz_worker_isolation.py`). Cybersecurity proved that mitigation
insufficient with real commands, not reasoning alone: Docker daemon access — the one privilege
`fuzz-worker` is irreducibly and deliberately given by D-073 itself — is *general-purpose
network access* to every network the daemon manages. `internal: true` stops a network's
existing members from routing to the internet; it does nothing to stop a new container,
created by anything holding daemon access, from joining that network directly (`docker run
--network backend ...`) and reaching every other member at L3/L4. Reproduced concretely: a
freshly created container on an `--internal` network reached another container on that same
network over plain TCP (`connect: refused`, not `timed out` — i.e. *reached*, just nothing
listening on that exact port), while the network's own designed egress-block still held for
requests leaving the network entirely. Combined with the separately-confirmed fact — I checked
this myself, independently, before writing this record, not just trusting the finding — that
`model-host` (`ollama/ollama`, both compose files, `OLLAMA_HOST: 0.0.0.0:11434`) has **no
authentication of any kind**: no token, no password, nothing in `.env.example` or either
compose file, and `services/model-gateway/gateway/client.py`'s `post_json`/`get_json` send no
`Authorization` header because there has never been anything to send. "No model-gateway client,
no credentials" was never actually the boundary — raw TCP reachability to `model-host:11434`
*is* sufficient to run inference against it, and Docker daemon access is a trivial, structural
way for `fuzz-worker` to get that reachability regardless of its own network namespace.

**What I verified myself, directly, before ruling** (not taken on the finding's word alone):

1. `infrastructure/compose/docker-compose.finale.yml` and `docker-compose.yml`, read in full.
   `model-host` is `profiles: ["model"]` (opt-in) in both, on the `backend` network only
   (`internal: true`, no published port, no gateway), `OLLAMA_HOST: 0.0.0.0:11434` — confirmed
   this binds every interface *inside that container's own network namespace*, which is exactly
   the interface every other member of `backend` sees it on. No `ports:` publish, no TLS, no
   auth env var anywhere in either compose file or `.env.example`/`apps/control-api/.env.example`.
2. `services/model-gateway/gateway/ollama.py` and `gateway/client.py`, read in full: the client
   that actually talks to `model-host` sends `Content-Type: application/json` and nothing else —
   no `Authorization`, no API key, no client cert. There is no code path today that could send a
   credential even if `model-host` demanded one.
3. `gateway/endpoint_policy.py`, read in full: the egress boundary this module enforces is
   *which hosts the gateway itself is allowed to dial* (loopback/RFC1918/declared service names,
   never a hosted provider). It says nothing about, and cannot say anything about, who else can
   reach `model-host` once something else has network access to `backend` — a different question
   than the one this module answers, and SEC-50 is precisely the gap between the two.
4. Whether Ollama has a cheap built-in auth option: it does not. Ollama's HTTP API accepts no
   credential of any kind server-side as of the version pinned here (`ollama/ollama@sha256:
   f478761c...`) — `OLLAMA_ORIGINS` exists but is a browser `Origin`-header CORS allowlist, not
   authentication, and is trivially bypassed by any non-browser client (exactly what `curl`/a
   Docker-daemon-created container is). There is no `--api-key`, no bearer-token mode, nothing
   to flip on. This rules out "the fastest possible fix" the task asked me to check for first —
   it does not exist upstream.

**Decision — fix now, not a CEO risk acceptance.** A concrete, cheap fix exists, fits well
inside the ~3 days remaining, does not touch D-073's approved topology (bare-metal
`fuzz-worker`, kind-scoped claiming — none of that changes), and closes the actual mechanism
SEC-50 demonstrated rather than a proxy for it:

1. **`model-host`: bind Ollama to loopback only inside its own network namespace.**
   `OLLAMA_HOST: 127.0.0.1:11434` instead of `0.0.0.0:11434`, in both compose files. This alone
   makes port 11434 unreachable from any *other* container on `backend`, however it got there —
   loopback inside a network namespace is not visible on that namespace's external interface,
   full stop, regardless of which bridge network the namespace's owning container is attached
   to. The existing healthcheck (`ollama list`, exec'd inside the same container/namespace)
   is unaffected — it still reaches loopback fine.
2. **A bearer-token-checking nginx sidecar, sharing `model-host`'s network namespace, is the
   only thing that can reach it.** New service `model-host-auth` (name TBD by whoever
   implements — devops-engineer's call), `network_mode: "service:model-host"` (not its own
   network membership — literally the same namespace, same IP as `model-host` on `backend`),
   `depends_on: model-host: condition: service_healthy`, reusing the already-pinned
   `nginxinc/nginx-unprivileged` digest already used for the ingress `nginx` service (no new
   image to vet). It listens on the shared namespace's externally-visible interface — e.g.
   `11434` itself, taking over the port number `model-host` no longer exposes there, so nothing
   else in the codebase needs its target port changed — checks `Authorization: Bearer
   <token>` against an env-supplied secret (`MODEL_HOST_BEARER_TOKEN`, `:?`-guarded in
   `docker-compose.finale.yml` the same way `POSTGRES_PASSWORD`/`REDIS_PASSWORD` already are;
   defaulted in dev's `.env.example` the same way `redis` has no password in dev today), and
   `proxy_pass`es a matching request to `http://127.0.0.1:11434`. Use nginx's own
   `docker-entrypoint.d` envsubst templating (`/etc/nginx/templates/*.template` →
   `/etc/nginx/conf.d/`, already ships in the `nginxinc/nginx-unprivileged` base image, no
   extra tooling) to interpolate the token into a static `if ($http_authorization != "Bearer
   ${MODEL_HOST_BEARER_TOKEN}") { return 401; }` block ahead of the `proxy_pass` — the same
   profile-switch-by-mounted-conf pattern this file already uses for `/admin` (D-019's own
   `admin-deny.conf`/`admin-allow.conf` split), so this is idiom-consistent with the rest of
   the compose file, not a new pattern.
3. **Thread the token through the one caller that is supposed to have it.** Add
   `MODEL_HOST_BEARER_TOKEN` to `gateway/settings.py`'s settings source and have
   `gateway/client.py`'s `_json_request`/`get_json` send `Authorization: Bearer <token>` when
   set (empty/unset in dev unless the operator opts in, matching how `MODEL_ENDPOINT`/
   `MODEL_SERVICE_NAMES` already default to permissive-but-explicit in that module).
   `control-api`/`worker` (the only processes ever given this token, via their normal
   `env_file`) can produce it; `fuzz-worker` never receives it — it already has no
   model-gateway configuration at all, per D-073 §5.1's own requirement, now independently
   confirmed by `test_fuzz_worker_isolation.py`.

**Why this actually closes the gap SEC-50 demonstrated, not just relocates it.** The attack
proven was "Docker daemon access ⇒ join `backend` ⇒ reach `model-host` directly," and it works
regardless of which network `model-host` sits on, because Docker daemon access lets an
adversary `docker network connect` into *any* network the daemon already manages, named or not
— so re-segmenting `model-host` onto a *different* internal network is not a durable fix on its
own; an adversary with full daemon access can join that network too, the same way they joined
`backend` in the PoC. What actually neutralizes this is that after this fix, joining `backend`
(or any network `model-host`'s namespace sits on) only gets an adversary as far as a listener
that demands a secret it structurally never holds — the same "enforced by what the process is
never given, not by network topology" logic D-073 §3 already relied on for the model-gateway
client, now applied to the one thing that logic missed: the *transport* itself needs a secret
too, not just the client code. This is deliberately **not** relying on network segmentation
alone, because SEC-50 already showed network segmentation alone doesn't survive Docker-daemon-
level access on the same host.

**Options considered:**

- **(a) The fix above — loopback bind + bearer-token nginx sidecar sharing `model-host`'s
  network namespace.** Chosen. Cheap (~half a day to a day: one compose service, one nginx
  conf template, one settings/client change, one new required env var), reuses an
  already-pinned image and an already-established compose idiom (D-019's profile-switch
  pattern), and closes the mechanism actually demonstrated rather than one that sounds similar.
- **(b) Network segmentation alone — move `model-host` off `backend` onto a new, narrower
  internal network `fuzz-worker` is never told the name of.** Rejected as insufficient by
  itself, for the reason stated above: Docker daemon access is not scoped by network names an
  attacker doesn't already know — `docker network ls` trivially enumerates every network the
  daemon manages, named or not, to anything holding daemon access. This is the same shape of
  argument D-073 §2 already made rejecting remote-TLS Docker access as "authenticates who, not
  what" — segmentation without an application-layer secret authenticates *which network*, not
  *whether the caller is allowed to be there*.
- **(c) Replace `fuzz-worker`'s raw Docker CLI access with a narrow, policy-enforcing wrapper
  service — cybersecurity's own second suggestion, and D-073 §4's already-deferred permanent
  "sandbox-executor" line item.** Correct as the eventual answer, explicitly not adopted here:
  this is real infrastructure work (a new service, its own auth/contract, a credential
  lifecycle) that D-073 §4 already scoped as "not a same-day fix, correctly deferred past
  2026-08-20" for the *general* Docker-access problem — SEC-50 does not change that math, and
  building it under a three-day clock to fix one specific unauthenticated downstream service is
  worse engineering than fixing that one service directly. Tracked as the same post-competition
  follow-up D-073 §4/§6.6 already named; SEC-50 does not enlarge its scope, it just adds one
  more concrete reason it is worth doing eventually.
- **(d) CEO risk acceptance instead of a fix.** Rejected as the primary path because a real fix
  is not expensive relative to the finding's severity — cybersecurity rated this HIGH/CRITICAL
  for the actual finale deployment, and (a) is a same-day, low-blast-radius change that does
  not touch D-073's approved topology, does not block PR #197 (separate PR/branch), and does
  not require re-opening any already-settled architectural question. Asking the CEO to accept a
  HIGH/CRITICAL-rated, structurally-demonstrated live-exploitability gap when a cheap structural
  fix exists is not a good use of that authority. Held in reserve as a **fallback only**, stated
  explicitly below, in case (a) cannot land in time.

**Cost implications** — one new compose service reusing an already-pinned image (no new image
to vet or pin), one nginx conf template (~15 lines), one new required env var per environment
(`MODEL_HOST_BEARER_TOKEN`, generated once per deployment, stored in `.env`, never committed —
same handling as `POSTGRES_PASSWORD`/`REDIS_PASSWORD` already receive), a small settings/header
change in `services/model-gateway`. No new infrastructure, no new network, no new credential
lifecycle beyond "one more secret in `.env`."

**Security implications** — closes SEC-50's demonstrated mechanism without depending on network
topology holding against an adversary who already has Docker daemon access (topology alone was
exactly what SEC-50 broke). Does not touch, weaken, or require re-litigating D-035/D-036 (socket
never mounted into any container), D-073's kind-split topology, or PR #197's import-boundary
work (SEC-49, tracked separately, unaffected by this). Residual risk after this fix, stated
plainly: `fuzz-worker` retains Docker daemon access (that is D-073's own accepted, approved
design, not something this record revisits) and could still use it to disrupt `backend` in
other ways (e.g. resource exhaustion, or attacking `db`/`redis` similarly if those are ever
found to have the same unauthenticated-transport gap — worth cybersecurity re-checking `redis`'s
dev-mode no-password posture and `db`'s posture under this same "Docker access = network access"
lens as a fast-follow, flagged here rather than silently assumed fine by analogy). This record
closes the specific SEC-50 finding (`model-host` reachable and usable with zero credential via
a Docker-daemon-granted network route); it does not claim to close every consequence of
`fuzz-worker` holding Docker daemon access, which remains D-073's own accepted, scoped residual
risk.

**Scalability implications** — none; one more small proxy process on a profile that is already
opt-in and already off by default in dev.

**Verification required before this is treated as closing SEC-50** (assigned in the task
breakdown below, not claimed done here — I have not implemented this myself in this session,
only designed and ruled on it): re-run cybersecurity's own PoC methodology from the SEC-50
finding — create an ad hoc container, join it to `backend` the way `fuzz-worker`'s Docker
access would, and confirm the request to `model-host`'s address now gets refused without the
token and succeeds with it. Code review alone is not sufficient for a finding that was proven
wrong by running real commands; the fix needs the same treatment.

**Fallback, only if (a) cannot land before 2026-08-20**: the CEO risk acceptance cybersecurity's
ruling requires as the alternative to a fix. Stated here so it is not punted if the timeline
slips — the risk statement the CEO would need to actually accept, in writing, in
`.project/decisions.md`:

> *If `infrastructure/scripts/run-fuzz-worker.sh` runs on the finale host with `model-host`
> live (`--profile model` up) on the same Docker daemon, before SEC-50 is fixed: a compromise of
> the `fuzz-worker` process — whether via a malicious/adversarial fuzz target under test, a
> supply-chain-compromised fuzzing dependency, or an operator running a crafted `Job.payload` —
> can use `fuzz-worker`'s own Docker daemon access (an irreducible, deliberately-granted
> privilege under D-073) to create a new container on the `backend` network and reach
> `model-host`'s inference API directly, with no credential required, regardless of
> `fuzz-worker` itself never holding model-gateway code or credentials. This could be used to
> run arbitrary inference requests against the local model host — plausible impact: resource
> exhaustion of the model host during the live demo, or (if the model is ever given anything
> resembling repository content or a system prompt worth reading, which it is not designed to
> be today, but nothing structurally prevents a future prompt-construction bug from doing so) a
> confidentiality exposure via inference responses. This is a real, demonstrated gap
> (cybersecurity's SEC-50), not a theoretical one, rated HIGH/CRITICAL for the finale deployment
> specifically.*

**Recommendation / ruling** — fix now: option (a). Sized at half a day to a day; does not block
PR #197's already-cleared merge; lands as its own small PR/branch before 2026-08-20, with the
verification step above run for real before being marked closed. CEO risk acceptance is the
documented fallback only, not the primary path, and should not be reached for unless (a)
genuinely cannot land in time.

**Task breakdown**

1. `docker-compose.yml` / `docker-compose.finale.yml`: `OLLAMA_HOST: 127.0.0.1:11434` on
   `model-host`; new `model-host-auth` service (`profiles: ["model"]`, `network_mode:
   "service:model-host"`, `depends_on: model-host: condition: service_healthy`, the pinned
   `nginxinc/nginx-unprivileged` digest, `read_only: true`, `cap_drop: ["ALL"]`, the standard
   `x-hardening` anchor); new required `MODEL_HOST_BEARER_TOKEN` env var (`:?`-guarded in
   finale, defaulted in dev) — devops-engineer, ~2-3 hrs.
2. `infrastructure/compose/nginx/model-host-auth.conf.template` (new file): the
   envsubst-templated bearer-check + `proxy_pass http://127.0.0.1:11434;` block, mirroring
   `nginx/profile/admin-deny.conf`'s existing pattern for a mounted, deliberate access-control
   conf — devops-engineer, ~1-2 hrs.
3. `services/model-gateway/gateway/settings.py` + `gateway/client.py`: read
   `MODEL_HOST_BEARER_TOKEN`, send `Authorization: Bearer <token>` when set — backend-developer,
   ~1 hr, plus updating `gateway/tests/test_ollama_backend.py`'s fixtures to cover the header.
4. Verification: the ad hoc-container PoC from cybersecurity's own SEC-50 methodology, re-run
   against the fixed stack, both with and without the token — devops-engineer or cybersecurity,
   ~1 hr.
5. Cybersecurity re-review of items 1-4 before this is marked as closing SEC-50, per this
   project's standing rule for isolation-relevant changes.
6. Fast-follow, not blocking SEC-50's closure: re-check whether `redis`'s dev-mode
   no-password posture and any other `backend`-network service share this same
   "Docker-access-is-network-access, and this service trusts the network" shape — flagged in
   the security-implications section above, owned by cybersecurity.

**Final approval authority** — CTO (technical) for this ruling and the fix design;
`cybersecurity` holds the implementation gate (task 5) before `run-fuzz-worker.sh` may run
against any environment where `model-host` is reachable, per its own SEC-50 ruling and
CLAUDE.md's standing rule for isolation-relevant changes; CEO holds the fallback risk-acceptance
authority stated above, only if invoked.


## D-071 — T3 (`JobKind.CORRELATE` executor + transition policy): the two-signal fallback while T2's `record_finding` has not landed, and why CORRELATE writes no new row · 2026-08-17 · `backend-developer` seat

Posted while implementing #168 T3 against D-061 §2/§4 and D-062's staffing plan.
`orchestrator/correlate_executor.py`, `orchestrator/tests/test_correlate_executor.py`,
`orchestrator/tests/test_correlate_routing.py`.

**Decision** — `CORRELATE`'s executor decides "is there anything worth a patch attempt" from
two signals, checked in priority order, with neither one invented: (1) real
`missions.models.Finding` rows for this mission, the authoritative signal since it's what
`orchestrator.candidates.record_patch_candidate`'s `finding_id` parameter actually needs; (2)
falling back to the terminal `FUZZ` job's raw `Job.result["crashes_found"]` — the same key
T0's own reference `_fuzz_transition_policy` already names as "the provisional FUZZ/CORRELATE
contract" — only when no `Finding` row exists yet. Neither present: `result["correlated"] =
False`, `source = "no_signal"`. The transition policy routes `correlated: True` results to
`MissionState.PATCH` and everything else (a `SUCCEEDED` job with `correlated: False`, or a job
whose result is missing the key entirely — e.g. `run_worker`'s own crash handler) to
`MissionState.HUMAN_REVIEW`, per D-061 §2's own instruction that "the 'nothing to bind' →
`HUMAN_REVIEW` decision belongs to the CORRELATE policy." `CANCELLED` defers (`None`, mirroring
T1's `_baseline_transition_policy`); `FAILED`/`TIMED_OUT` (never retried,
`MAX_ATTEMPTS_BY_KIND[CORRELATE] == 1`) route to `Mission.FAILED` — treated as the correlate
step itself never completing, not a legitimate "looked and found nothing" outcome (that always
reports `SUCCEEDED`).

**Options considered** — (a) read only `Finding` rows, leave the raw `FUZZ` result unread —
correct once T2 lands `record_finding`, but as of this task landing (checked directly: `git
diff main...feat/168-t2-fuzz-minimize` is empty except for pre-#168 libFuzzer-runner commits
already on `main`; no `FUZZ` executor or `record_finding` call exists on that branch yet) this
would make CORRELATE report "nothing to bind" for *every* mission that reaches it, regardless of
what FUZZ actually found, which defeats the point of testing this stage at all before T2 merges
and silently degrades every fuzz-positive mission to `HUMAN_REVIEW` in the interim. (b) read
only the raw `FUZZ` `Job.result`, ignore `Finding` rows entirely — simpler, but wrong the day
T2's producer lands, since a real `Finding` row is what T4 (`PATCH_GENERATE`) actually binds a
candidate to, and a raw crash count alone carries no `file_path`/fingerprint for T4 to work
from. (c) the two-signal priority order implemented: correct against the current state of the
repo (no `Finding` producer yet) *and* forward-compatible with T2's real producer landing later,
with zero code change required here when it does — the `Finding`-rows branch simply starts
being hit for real traffic and the raw-crash-count branch stops being exercised outside its own
tests. (d) have this task write `record_finding` itself, since D-061 §4 names it as "T2 (or T3)"
— rejected: T2 owns `FUZZ` end to end per D-062's staffing plan and is being built in parallel
on its own branch right now; writing a producer function into that same seam from a different
branch risks a merge conflict or two competing "who calls this" answers, for a function this
task does not need in order to make the CORRELATE routing decision correctly today.

**Pros and cons** — (c)'s cost is that a mission whose only signal is the raw crash count
reaches `PATCH` today with no bound `Finding` for T4 to work from yet — named explicitly in the
module's own docstring ("What is incomplete") rather than hidden, and closes itself the moment
T2's producer lands, with this module needing no change. (d) would close that gap sooner but
at the cost of two engineers' branches touching the same producer function mid-sprint under a
tight deadline, which this project's own schedule (Day 3 as an integration buffer, not new
feature work) argues against.

**Cost implications** — none; no new infrastructure, no new model. `CORRELATE` writes nothing
to the database — its "terminal artifact" is the immutable `Job.result` the queue already
protects (`orchestrator.queue.complete_job` only ever writes a `LEASED`/`RUNNING` job), so
D-061 §3 rule 2's pre-execution existence check is structurally satisfied rather than coded:
re-running this executor (crash-and-restart, a reclaimed lease) reads the same `Finding` rows
and the same terminal `FUZZ` job every time and reaches the same answer, the same "safe by
construction" shape `orchestrator/teardown_executor.py` documents for its own no-artifact case.

**Security implications** — the `Finding`-rows query is scoped `mission=ctx.mission`, matching
SEC-15's own discipline (`orchestrator/tests/test_cross_mission_evidence.py`'s precedent) — a
dedicated test (`test_does_not_leak_another_missions_finding_rows`) proves a second mission's
`Finding` row cannot make this mission's CORRELATE decision for it. No secret, no raw
repository content, in either signal read or in `Job.result` written (D-061 §3 rule 3).

**Scalability implications** — none; single-mission-at-a-time, one bounded query each for
`Finding` and the terminal `FUZZ` job, matching D-061/D-062's framing throughout #168.

**Recommendation / ruling** — (c), implemented as described, registered via
`missions/apps.py::ready()` alongside T1/T7's own modules. Full test suite:
`orchestrator/tests/test_correlate_executor.py` (6 tests — the two signals, the priority
between them, the cross-mission leak guard) and `orchestrator/tests/test_correlate_routing.py`
(13 tests — the direct policy unit tests, mirroring `test_stress_test_routing.py`'s own shape,
plus real end-to-end exercises through `orchestrator.queue.dispatch_terminal_jobs` for both the
"something to bind" and "nothing to bind" cases, including two that route the *real executor's*
own output through the real dispatcher rather than a hand-written `Job.result`). Full suite:
505 passed, 9 skipped (pre-existing Postgres-only tests, unrelated), 0 failed. `manage.py check`:
zero issues.

**Final approval authority** — CTO (technical) per D-061's own closing line that
implementation-level calls inside an already-approved task breakdown are within
backend-developer's scope. The `Finding`-model integration named as a fast-follow above ("What
is incomplete" in `orchestrator/correlate_executor.py`'s own docstring) needs no separate
sign-off — it activates automatically once T2 lands `record_finding`, and is flagged here so
that landing is not mistaken for a silent gap.


## D-072 — Pinned fuzzing-toolchain image (#189, P0): base toolchain, digest-pinning mechanism for a self-built image, and the FUZZ-execution-host gap it surfaced · 2026-08-17 · `devops-engineer` seat

**Decision** — Built `infrastructure/compose/images/fuzz-toolchain.Dockerfile`: `ubuntu:24.04`
(pinned by index digest) plus `clang` (resolves to clang-18 on noble), `cmake`, `make`, and
`libclang-rt-18-dev` (the compiler-rt package providing `libclang_rt.fuzzer-*.a` /
`.asan-*.a` / `.ubsan_standalone-*.a`), fixed uid/gid 10001 matching `ContainerJailPolicy`'s
own default. Added `infrastructure/scripts/build-fuzz-image.sh` to build it and resolve a
`name@sha256:<64 hex>` reference `adapters/cpp/toolchain.py::require_pinned` accepts. Added
`SANDBOX_FUZZ_IMAGE` to the root `.env.example` (empty by default — no safe default for
running untrusted code) and threaded it through both compose files' `worker` service, with an
explicit note that the compose `worker` service cannot currently act on it (§3 below). Added
`workers/fuzzing/tests/test_real_campaign.py`, a real (not mocked) end-to-end test: builds the
image for real, runs `run_fuzzing_stage` → `run_libfuzzer_campaign` → `ContainerJail` → a real
`docker run` with the full D-024 flag set, against `demo/repositories/pktcfg`'s real seeded
heap-buffer-overflow. Opt-in (`BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN=1`), mirroring
`finale-egress-evidence.sh`'s precedent for "real infra, real time" checks that do not belong
in default per-PR CI.

### 1. Toolchain: match CI's own Linux/Clang-18 signal, not a new pin

**Options considered** — (a) Ubuntu 24.04 + apt `clang`/`libclang-rt-18-dev` (what CI's
`ubuntu-24.04` runner family already is, one distro to reason about). (b) A pinned upstream
`llvm/llvm-project` release image. (c) Alpine + a musl Clang build (smaller image).

**Pros/cons** — (a): apt-installable in ~20s, same distro family CI's `cpp-adapter` job already
prints toolchain versions for, no new base-image trust decision. (b): more "canonical" LLVM but
a much larger pull and a second base-image pin to track for no correctness gain — pktcfg needs
nothing LLVM's own release doesn't also get from Ubuntu's build. (c): smaller image, but
libFuzzer-on-musl has known linking rough edges and no existing precedent anywhere in this
repository (every other image here is glibc-based) — a new toolchain-compatibility risk for a
size saving that doesn't matter at this project's scale (single demo target, not a fleet).

**Cost implications** — apt install adds ~15-20s to a cold build, cached thereafter; ~400 MB
image, comparable to control-api's Python base plus its dependency set.

**Security implications** — none beyond what every other apt-based Dockerfile in this repo
already carries (dependency provenance is Ubuntu's package signing, same trust boundary as
`gcc`/`libasan`/`libubsan` on the CI runner itself, which CI already trusts for the identical
ASan/UBSan runtime family). The image runs the untrusted fuzzer target, never the reverse —
D-024's container flags (`--network none`, `--cap-drop ALL`, fixed non-root uid) are supplied
by `ContainerJailPolicy` on every invocation regardless of what this image contains, so a
compromised toolchain package would still be network-isolated and non-root at worst.

**Scalability implications** — none; one image, rebuilt on Dockerfile change, cached otherwise.

**Recommendation** — (a), implemented.

**Final approval authority** — CTO (technical).

### 2. Pinning a self-built image by digest: local `RepoDigest` (no registry) vs. a push

**Decision** — `build-fuzz-image.sh` tries `docker inspect --format='{{index .RepoDigests 0}}'`
on the freshly built local tag first, and only falls back to pushing to an operator-supplied
`FUZZ_IMAGE_REGISTRY` if that is empty.

**Why this is a real decision and not a formality** — every other digest pin in this repository
(`postgres@sha256:...`, `nginxinc/nginx-unprivileged@sha256:...`, `python@sha256:...`) pins an
UPSTREAM image whose digest came from a registry round-trip that already happened (`docker
pull`). This is the first image built *by this repository* that Python code
(`ContainerJailPolicy.image` via `adapters/cpp/toolchain.py::require_pinned`) must reference
by digest — no prior Dockerfile here needed that. Whether a bare local build produces a usable
digest with NO push is a property of the daemon's image store, checked directly in this
session, not assumed: this machine's Docker Desktop uses the containerd image store
(`driver-type: io.containerd.snapshotter.v1`, confirmed via `docker info`), under which a local
build is content-addressed immediately — `docker inspect` returned a real `name@sha256:...`
`RepoDigest` with no push, and `docker run` against that exact string, with the full D-024 flag
set, worked. The classic overlay2 graphdriver (still the default on plain `apt install
docker.io`, and on GitHub-hosted `ubuntu-24.04` runners as of this writing) does NOT populate a
`RepoDigest` for a local-only image — that path needs an actual registry push, which is why the
script supports `FUZZ_IMAGE_REGISTRY` rather than assuming the free path always works.

**Options considered** — (a) local `RepoDigest`, registry-push fallback (chosen). (b) always
push to a registry, unconditionally. (c) relax `require_pinned` to also accept a bare image ID
(`sha256:<64 hex>` with no `name@` prefix) so no registry is ever needed.

**Pros/cons** — (a): zero infrastructure cost on a containerd-backed host (this session's), a
documented, actionable path (`FUZZ_IMAGE_REGISTRY`) on hosts that need it, and it never
silently guesses which case applies — always states which path it took, on stderr. (b): works
everywhere uniformly, but forces every operator (including this session's own containerd-store
host, which does not need it) to stand up or have credentials for a registry just to iterate on
this one image, for no correctness gain over (a). (c): weakens `require_pinned`'s own stated
purpose — a bare image ID pins locally but is not portable across hosts/registries the way a
`name@sha256:` reference is, and it is a change to a file this task's role does not own
(`adapters/cpp/toolchain.py`, compiler-toolchain-engineer's), so out of scope regardless of
merit.

**Cost implications** — (a) as chosen: $0 on a containerd-store host (this project's actual dev
host). A registry, if ever needed for a graphdriver-based deploy target, is a small additional
line item (`registry:3`, or an existing container registry) — not costed here because it is not
needed on the verified path.

**Security implications** — a self-built image referenced only by a local digest is not
independently reproducible from a fresh clone the way an upstream digest is (nobody else can
`docker pull` this exact digest without either the same build or a shared registry) — this is
the honest tradeoff of the free path, recorded rather than hidden: `require_pinned`'s guarantee
("the string in the config cannot be silently repointed") still holds; "anyone anywhere can
fetch these exact bytes" does not, until a registry is added. Flagged, not solved — matches
this repository's own established pattern for a limitation that belongs to a scope this task
does not own (compare `adapters/cpp/variants.py`'s `RLIMIT_AS` finding, flagged to
`packages/sandbox`'s owner rather than solved unilaterally there).

**Scalability implications** — none at this project's scale (one image, one demo target,
finale-day operation). A multi-host or CI-distributed deploy would need the registry path
regardless of what this decision picks, since a digest that only exists in one machine's local
containerd content store is not reachable from a second machine by construction.

**Recommendation** — (a), implemented.

**Final approval authority** — CTO (technical).

### 3. The `worker` compose service cannot execute FUZZ jobs today — flagged, not solved here

**Finding** — `packages/sandbox/container.py`'s own module docstring (D-024 condition 4) is
explicit: `/var/run/docker.sock` must never be bind-mounted, anywhere. `ContainerJail.run`
shells out to a `docker` binary against a reachable daemon (`_run_cli`, `subprocess.run([...,
"run", ...])`) — that requires either a docker CLI plus a locally reachable daemon (a socket
mount, forbidden) or a remote docker context. `docker-compose.yml`/`docker-compose.finale.yml`'s
`worker` service is built from `control-api.Dockerfile` (a Python/uvicorn image with no `docker`
CLI at all) and mounts no socket, by design. So even with a pinned `SANDBOX_FUZZ_IMAGE` now
threaded through both compose files' `worker` environment, that specific containerized service
cannot start a single `ContainerJail`-backed FUZZ job as built today — the gap #189 named
("no pinned fuzzing-toolchain image exists... a live #50 run will still die at the FUZZ step")
is only half closed by this task: the image now exists and is proven to work, but nothing in
the current compose topology can invoke it from inside the containerized worker process.

**Options considered, not chosen here (out of #189's scope — the image and its pinning, not
this service's deployment topology)** — (a) run the FUZZ-dispatching process directly on a
docker-capable host, not inside the `worker` compose container (the model this session's own
verification and `packages/sandbox/tests/test_container_jail.py` already use). (b) a dedicated
sandbox-executor host, reachable from `worker` via a TLS-secured remote `DOCKER_HOST`, with
`docker` CLI added to that image. (c) bind-mount `/var/run/docker.sock` into `worker` — rejected
outright, not merely deprioritized: this is the exact hole D-024 condition 4 and
`FORBIDDEN_SOCKET_PATHS`/`tests/architecture/test_container_isolation.py` exist to catch, full
host-root-equivalent access for anything that can reach the `worker` container.

**Recommendation** — flag to the software-architect / orchestrator owner as a real, structural
blocker on a live #50 FUZZ run, additional to and separate from #189's own "no image exists"
finding, which is now resolved. Do not choose (a) vs (b) unilaterally here — that is a
deployment-topology and, for (b), a security-posture (TLS-secured remote docker daemon) call
this task's scope does not cover, and (c) is not on the table at all under D-024.

**Cost/Security/Scalability implications** — deferred to whichever of (a)/(b) the architect
selects; not costed here since neither is implemented in this PR.

**Final approval authority** — CTO (technical) for the topology choice; cybersecurity review
required before either (a) or (b) ships, per CLAUDE.md's standing rule for isolation-relevant
changes.

### 4. `ContainerJail`'s cgroup `--memory` vs. `packages/sandbox/jail.py`'s `RLIMIT_AS`: independently checked, not assumed

Per T1/T5's and `adapters/cpp/variants.py`'s documented `RLIMIT_AS`-vs-ASan trap
(`MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS`, ~28 TiB measured on the subprocess-jail path): checked
directly on the container path in this session, not assumed either way. `docker run --memory
2048m` (a quarter of `ContainerJailPolicy`'s own 8192 MiB default) against this exact pinned
image ran pktcfg's real ASan+UBSan+libFuzzer build to a real heap-buffer-overflow crash with no
allocation failure (`peak_rss_mb: 36` in the libFuzzer output — nowhere near even the 2048 MiB
ceiling). This is a structural property, not a coincidence of this one input size: Docker's
`--memory` is enforced by the cgroup v2 memory controller against actual *resident* (charged)
pages, while `RLIMIT_AS` constrains *reserved virtual address space* regardless of whether it is
ever touched — ASan's ~28 TiB shadow-memory reservation is `mmap`'d `PROT_NONE`/lazily and is
never charged against cgroup memory accounting for the untouched majority of it. **No
`MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS`-equivalent override is needed on the `ContainerJail`
path.** This confirms PR #188's own claim (its description states the same conclusion for the
same reason) independently, from a different image and a different session.


## D-076 — T4 (`JobKind.PATCH_GENERATE` executor + transition policy): T4-lite scope, attempt-scoped idempotency, and the degradation ladder living outside the gateway package · 2026-08-17 · `backend-developer` seat

Implementing #168 T4 against D-061 §4's brief and D-062's T4-lite de-scoping. Four calls
made while doing that, none of them decided verbatim by D-061/D-062.

### 1. Confirmed and respected: T4-lite's boundary is the D-026 package move, nothing else

D-062 de-scoped exactly one thing — "wire `PATCH_GENERATE` against the CURRENT
`services/model-gateway` import path, NOT completing D-026's full package relocation." This
task does not move, rename, or edit any file under `services/model-gateway/`. Every
`gateway.*` symbol this task uses (`gateway.service.build_gateway`, `gateway.context.
build_context`/`request_patch`, `gateway.ollama.OllamaCodeLlamaBackend`, `gateway.errors.*`)
is consumed as-is, at its current path. The one genuinely new file this task adds inside
`services/model-gateway/` is none — confirmed by `git diff --stat` before pushing.

### 2. `sys.path`/import discipline: lazy, function-scoped, never at module top level

**The finding.** `missions.apps.MissionsConfig.ready()` — the mechanism T0/T1/T7 already use
to register a `JobKind` executor — runs on *every* process that touches `Job`/`Mission`,
**including the ASGI process** (that file's own docstring says so directly). D-028/C5
(`tests/architecture/test_import_direction.py::
test_importing_the_asgi_app_does_not_load_the_gateway`) requires `gateway.*` never load
inside the ASGI process. A `from gateway.service import ModelGateway` at the top of a module
`ready()` imports would have broken that invariant the moment this task's own registration
line landed — the exact "modules, not services" boundary decay that test's own docstring
warns about, self-inflicted by a normal-looking import.

**Decision** — `orchestrator/patch_generate_executor.py` (`missions/apps.py`'s new
registration line) imports nothing from `gateway.*` at module scope. `sys.path` insertion
(`_ensure_gateway_importable`) and every `from gateway...` import live inside function
bodies that only `run_worker`'s claim loop ever reaches. Proven, not just argued:
`tests/architecture/test_import_direction.py`'s full 8-test suite (including the runtime
`config.asgi` import check) passes with this module registered.

**Options considered** — (a) top-level `gateway.*` imports, relying on review discipline to
catch any accidental ASGI reachability; (b) function-scoped imports, so the failure mode is
structurally absent rather than reviewed-against.

**Pros and cons** — (a) is what the module would look like if written the "obvious" way
(mirroring `workers.baseline.dispatch`'s own top-level `from workers.baseline.run import
run_baseline_stage`) and is exactly wrong here because `workers.baseline.run` is not the one
package D-028 singles out for this restriction — `gateway` is. (b) costs one extra
indirection per gateway call and is what `orchestrator/model_host.py`/`orchestrator/
transitions.py` already do for a different reason (compose subprocess calls, not a security
boundary) — here it is load-bearing, not tidiness.

**Security implications** — this is the content of the decision; see above.

**Final approval authority** — CTO (technical), since it touches D-028's boundary directly;
flagging for confirmation rather than treating it as self-evidently correct.

### 3. Attempt-scoped idempotency: keyed on `PatchCandidate.objects.filter(mission=...).count()`, not `Job.attempt`

D-061 §3 names `PATCH_GENERATE` as the one exception to "check your stage's terminal artifact
before doing real work," phrased as "using the job's attempt field." Read literally against
code that did not exist yet when D-061 was written, that cannot mean the `Job.attempt` ORM
column: `orchestrator/queue.py::ensure_jobs_enqueued` (T0, merged after D-061) states
`PATCH_GENERATE`/`VERIFY` are "one job each with fan-out *inside* them," and
`MAX_ATTEMPTS_BY_KIND[JobKind.PATCH_GENERATE]` is `1` — so `Job.attempt` never advances past
`1` for this kind; a lease timeout goes straight to `FAILED` (`reap_expired_leases`), never
back to `QUEUED`. There is no code path today that re-enters this executor for the same
`Job` row.

**Decision** — idempotency is keyed on the *internal* generation-attempt index, read from
`PatchCandidate.objects.filter(mission=mission).count()` at the top of the executor: it
resumes from `already + 1` rather than fanning out from `1` again. This is the property a
hypothetical future re-entry (or a test exercising the function twice) needs, and it is what
`test_executor_resumes_from_already_recorded_candidates_not_from_zero`/
`test_executor_short_circuits_when_the_target_is_already_met`
(`orchestrator/tests/test_patch_generate_executor.py`) prove directly, with a call-counting
fake backend rather than just asserting a row count.

**Options considered** — (a) treat D-061 §3's "the job's attempt field" as literally
`Job.attempt` and key resumption on it (would always resume from `0` — vacuous, since
`Job.attempt` never changes for this kind); (b) key on the count of `PatchCandidate` rows
already recorded for the mission, per the reasoning above.

**Recommendation / ruling** — (b). Flagged as a real deviation from D-061 §3's literal text,
not a silent reinterpretation — the text predates the "one job, fan-out inside" design T0
later ratified, and (a) is not implementable against the code as it actually landed.

**Final approval authority** — CTO (technical), since it revises a named clause of D-061 §3.

### 4. The degradation ladder (architecture spec §6.4) lives in the executor, not the gateway

`services/model-gateway/gateway/client.py` has no transport retry of its own (checked
directly), and `gateway/errors.py`'s own module docstring states the design intent plainly:
"Degradation is the orchestrator's job... It is not the gateway's, because the gateway
cannot tell the difference between 'the operator wants a fallback' and 'the operator wants
the truth'." Building the retry/context-reduction ladder into `gateway.*` would have been
both out of T4-lite's scope (touching a package D-062 says to leave alone) and against that
package's own stated design.

**Decision** — `_generate_with_ladder` (`orchestrator/patch_generate_executor.py`) implements
all three rungs of §6.4 per fan-out attempt: the call as configured, one same-context
transport retry, one reduced-context retry (`_reduced_code_slice` — the spec's "±40-line
slice instead of ±120" approximated as the middle third of `Finding.code_slice`'s lines,
since T3/CORRELATE — not yet merged to this branch — is what would define an exact
line-window convention). `gateway.errors.LiveBackendUnavailableError` (no backend configured
at all) skips the ladder outright rather than wasting two rungs on a fact that cannot change
mid-ladder.

**Cost implications** — none; no new runtime dependency, three iterations per attempt at
worst, bounded by `OllamaCodeLlamaBackend`'s own per-call timeout (300s default).

**Scalability implications** — none; single-mission-at-a-time, matching D-061/D-062.

**Recommendation** — as implemented; `orchestrator/queue.py::default_deadline_seconds`
gained one new branch (`JobKind.PATCH_GENERATE`, `attempts_target * 360s`, floor 1800s) so
the job's own `deadline_at` has headroom for the worst case (up to three HTTP calls per
attempt) without assuming it on every attempt — this is the "starting points... for T1/T3/
T4/.../T7 to override at their own enqueue call" invitation that function's own docstring
already names, not an unscoped change to shared infrastructure.

**Also added, and flagged rather than silently folded in:**

- `MissionPolicy.patch_generation_attempts` (`contracts/schemas/missions.py`), default `10`
  — the fan-out width, matching the D6 kill criterion's supporting threshold ("at least 3 of
  10 attempts," `docs/09-company/01-vision-and-p0-cut.md`). Not present in D-061/D-062's own
  text; a minor API-contract addition within backend-developer's own scope of authority,
  documented here per that role's own brief ("document every addition back into the contract
  doc"). `packages/schemas/openapi.json` regenerated (`tools/export_openapi.py`) and
  `contracts/tests/test_openapi_dump.py` re-passes against the new field.
- `MODEL_ENDPOINT` env var (`.env.example`, `apps/control-api/.env.example`) — the gateway's
  own settings module (`gateway/settings.py::from_environment`) reads `MODEL_ENDPOINT`; the
  control API's pre-existing convention is `SMALL_MODEL_BASE_URL`
  (`config/settings/base.py::MODEL_ENDPOINTS`). Nothing before this task wired the two
  together. `_build_gateway_settings` falls back to `SMALL_MODEL_BASE_URL` when
  `MODEL_ENDPOINT` is unset, so a deployment that only set the control API's own variable
  still works — flagged for ml-infra-engineer to reconcile into one name, not decided
  unilaterally here (same shape as D-052's own "flagged, not blocking" pattern).

**Final approval authority (this whole record)** — CTO (technical), per D-061's own closing
line for calls within a task's implementation; item 2's ASGI-import discipline and item 3's
idempotency-key reinterpretation are flagged above for explicit confirmation since they
revise or extend named clauses of D-061/D-028 rather than merely filling in unscoped detail.

## D-067 — T5 (`JobKind.VERIFY` executor + transition policy): fan-out-aware idempotency and
routing, and an unsandboxed-execution risk flagged for cybersecurity · 2026-08-16 ·
`backend-developer`

Implements the T5 slice of D-061/D-062 against `orchestrator/executors.py`'s interface
contract (T0, already merged on this branch) and the two already-built, already-tested
functions D-061 §4 named: `orchestrator/verification.py::run_verification` and
`orchestrator/candidates.py::record_verification`. New code:
`apps/control-api/orchestrator/verify_dispatch.py`,
`apps/control-api/orchestrator/tests/test_verify_dispatch.py`, one `ready()` hook added to
`apps/control-api/missions/apps.py`.

### 1. Idempotency key is the candidate (`job.payload["patch_id"]`), not the mission and not `job.attempt`

**Decision** — Key the pre-execution existence check on `VerificationRecord.objects.filter
(patch_id=...)`, not on "does this mission have any verification record" and not on
`job.attempt`.

**Options considered** — (a) mission-scoped, mirroring `BASELINE`'s check against D-061 §3
rule 1 as literally stated; (b) attempt-scoped, mirroring `PATCH_GENERATE`, the one named
exception in that same rule; (c) candidate-scoped, keyed on `job.payload["patch_id"]`.

**Pros and cons** — (a) is wrong by construction once `VERIFY` fans out one job per
policy-accepted `PatchCandidate` (architecture spec §2.3, decision (b), confirmed live by
`orchestrator/tests/test_fan_out.py`): the first candidate's `VerificationRecord` existing
would make the check skip verifying every sibling candidate, silently dropping them from the
mission's evidence bundle. (b) is wrong for a different reason — `MAX_ATTEMPTS_BY_KIND
[JobKind.VERIFY]` is 1 (`missions/models.py`, asserted by
`missions/tests/test_models.py::test_verify_jobs_are_not_retryable`), so `job.attempt` is
always `1` and carries no information to key on; two different candidates verified by two
different jobs would both read as "attempt 1" and be indistinguishable. (c) matches the real
per-unit uniqueness constraint already in the schema: `VerificationRecord.patch` is a
`OneToOneField` (`missions/models.py`), the same shape `BaselineReport`'s per-mission
constraint has, just scoped one level narrower. A worker that died after
`record_verification` committed but before its `Job` row reached `SUCCEEDED` reports the
existing record instead of retrying into `IntegrityError`.

**Cost implications** — none; one indexed filter, no schema change.

**Security implications** — none. Does not change authorization, mission-binding, or the
D-046 candidate-set freeze — all three are still enforced by `record_verification` itself.

**Scalability implications** — none at one mission at a time.

**Recommendation / ruling** — (c), implemented. D-061 §3 rule 1 should be read as naming the
general principle ("check for your stage's own terminal artifact before re-running") with two
worked examples (mission-scoped, attempt-scoped), not an exhaustive enumeration — `VERIFY` is
a third shape. Flagging so whoever writes T1-T4/T6/T7's own idempotency checks does not treat
the rule as a closed set of two options.

**Final approval authority** — CTO (technical), since this is a reading of D-061 rather than a
new rule; no objection expected but recorded per this role's decision-record obligation.

### 2. Transition policy waits for the full candidate set before leaving `VERIFY`, and never returns `HUMAN_REVIEW` directly

**Decision** — `_verify_transition_policy` compares
`PatchCandidate.objects.filter(mission_id=..., policy_status=ACCEPTED).count()` against
`VerificationRecord.objects.filter(mission_id=...).count()` on every terminal `SUCCEEDED`
`VERIFY` job, and returns `MissionState.EXPORTING` only once they are equal — `None`
otherwise. It never returns `MissionState.HUMAN_REVIEW`, even though
`contracts.state_machine.TRANSITIONS[MissionState.VERIFY]` legally allows it.

**Options considered** — (a) route every terminal `SUCCEEDED` `VERIFY` job straight to
`EXPORTING`, once per job; (b) wait for the full candidate set, as implemented; (c) route a
job whose own verdict is `HUMAN_REVIEW_REQUIRED` (a required gate `NOT_RUN`/`ERROR`,
`contracts.verdict.derive_verdict`) straight to `MissionState.HUMAN_REVIEW`.

**Pros and cons** — (a) is what `test_fan_out.py`'s own committed shape rules out: two
candidates each finishing their own `VERIFY` job would each attempt `VERIFY -> EXPORTING`,
and the second attempt 409s (`InvalidStateTransitionError`, since `EXPORTING` is not a legal
target from `EXPORTING`) — survivable per the orchestrator's own "log and retry next tick"
behavior (`orchestrator/executors.py` module docstring), but the same docstring calls a
policy that regularly returns an illegal target "a bug in the policy, not a safety net to
lean on." (c) is the `VERIFY`-shaped mirror of the trap D-061 §2 names for `FUZZ`/
`STRESS_TEST`: the mission's terminal verdict is `derive_mission_outcome` over the *whole*
candidate set (architecture spec §2.3), evaluated only on transitions *out of* `EXPORTING`
(`contracts.state_machine.assert_verdict_is_evidenced`); deciding `HUMAN_REVIEW` from one
job's own inconclusive gates — especially when it is the mission's only candidate so far, the
strongest pull toward doing so — pre-empts that reduction and is exactly the kind of
shortcut D-046 exists to close, on the losing side instead of the winning one. (b) is the only
option consistent with both `test_fan_out.py`'s existing shape and D-061 §2's reasoning.

**Cost implications** — two indexed count queries per terminal job; negligible at this scale.

**Security implications** — closes a route to a "generate until pass"-adjacent shortcut
symmetric with D-046 (see options analysis above), rather than opening one.

**Scalability implications** — none at one mission at a time; the two counts are cheap even
at the ten-candidate ceiling D6 exercises.

**Recommendation / ruling** — (b), implemented and tested
(`test_succeeded_job_waits_for_sibling_candidates_before_routing_onward`,
`test_transition_policy_never_returns_human_review_directly`). Any non-`SUCCEEDED` terminal
`VERIFY` job (`FAILED`/`TIMED_OUT`) routes to `MissionState.FAILED` — per D-061 §2's own
example, a legitimate gate failure is always a `SUCCEEDED` job with a failing `GateResult`
inside it, so a job that reaches `FAILED`/`TIMED_OUT` at all means the gates never ran to
completion, an infrastructure fault the mission must not be left waiting on forever (`MAX_
ATTEMPTS_BY_KIND[VERIFY]` is 1 — no retry is coming). `CANCELLED` returns `None` deliberately,
deferring to the mission-level cancel path rather than racing it.

**Final approval authority** — CTO (technical), same basis as D-061 §2's original ruling on
the `FUZZ`/`STRESS_TEST` case this mirrors.

### 3. Flagged, not decided: `VERIFY` executes a patched binary unsandboxed on the worker host

**Decision** — Not made here. `_verify_executor` calls `run_verification` with its shipped
default (a real `subprocess` runner, no isolation) rather than wrapping it in
`packages.sandbox.Jail`.

**Why this needed a decision and didn't get one from me** — `Jail` is built and tested for
exactly this shape of work (`packages/sandbox/jail.py`'s own docstring: "build and test the
demo target," confirmed working against this same repository by
`packages/sandbox/tests/test_baseline_in_jail.py`). But `Jail.run()` has no `stdin`
parameter, and `run_verification`'s `git apply --whitespace=nowarn -` step depends on piping
the candidate diff over stdin — wiring the two together means changing how
`orchestrator/verification.py` invokes `git apply` (write the diff to a file and pass it as
an argument instead), which is a change to code D-061 §4 named as "already-built,
already-tested" and assigned to no one to modify as part of T5. Rewriting another task's
signed-off module under this task's own deadline pressure, to make a security property true
that nothing in this task's brief asked for by name, is exactly the kind of unilateral call
this role's own operating rules say not to make.

**Options considered** — (a) ship as-is (`verification.py`'s existing subprocess runner,
unsandboxed) and flag the gap; (b) modify `orchestrator/verification.py` to write the diff to
a file instead of stdin, so a `Jail`-backed `CommandRunner` adapter becomes possible, and wire
it in this task; (c) extend `packages.sandbox.Jail.run()` to accept `stdin`, then wire it.

**Pros and cons** — (a) ships something real and correctly attributes the gap rather than
hiding it; the risk is real (a patched binary — potentially model-generated — is compiled and
executed on the worker host with no isolation) but is not new: it is `verification.py`'s
existing, already-reviewed shape, not something T5 introduced. (b) and (c) both close the gap
but touch modules this task does not own (`verification.py` is D-061 §4's "already-tested,
wire it in, don't rebuild it" instruction; `packages/sandbox/jail.py` carries its own
extensive security-review history — SEC-35, SEC-38 — that a same-day, unreviewed `stdin`
addition should not bypass).

**Cost implications** — (a) costs nothing now, a real security review and a `verification.py`
change later. (b)/(c) cost review time this task's scope does not budget for.

**Security implications** — HIGH, flagged as a risk in this task's handoff, not silently
shipped. `VERIFY` is the one stage in the whole pipeline that compiles and runs code from a
diff whose provenance may be `MODEL_GENERATED` — the same trust boundary `packages/sandbox`
exists to enforce for `FUZZ` (`#28`, gated on `#15`'s rootless-container isolation per that
module's own docstring) is currently unenforced for `VERIFY`.

**Scalability implications** — none either way.

**Recommendation** — cybersecurity and software-architect decide whether `VERIFY` needs the
same isolation posture `FUZZ` is gated on before this ships past a demo, and if so, whether
the fix is `verification.py`'s `git apply` invocation, `Jail.run()`'s `stdin` support, or a
different adapter — not decided here.

**Final approval authority** — cybersecurity (security posture) and software-architect /
CTO (whether this blocks release), per this role's own stated boundaries.

### 4. Wiring: registration lives in `missions/apps.py::MissionsConfig.ready()`, not a hand-picked import list

**Decision** — Added one import line (`from orchestrator import verify_dispatch`) to
`MissionsConfig.ready()` rather than leaving the wiring as a note for T0's
`run_worker`/`run_orchestrator` to pick up later.

**Options considered** — (a) leave a comment noting where the import should go once
`run_worker`/`run_orchestrator` exist (matching the letter of this task's own instructions,
"note the follow-up wiring needed"); (b) add the import to `missions/apps.py`'s `ready()`
hook, which Django's app registry guarantees runs for *every* entry point that loads it —
management commands (including the two not yet built), ASGI/WSGI boot, `manage.py check`, and
the test suite.

**Pros and cons** — (a) does the minimum the task asked for but leaves a real gap open until
T0's commands exist and someone remembers to add the import. (b) closes the gap now, for
every current and future entry point, at the cost of one import line and a precedent other
`JobKind` tasks (T1-T4, T6, T7) should follow rather than each inventing a separate mechanism.
Verified directly: `manage.py check` and a fresh `django.setup()` both populate
`EXECUTOR_REGISTRY[JobKind.VERIFY]` / `TRANSITION_POLICY_REGISTRY[JobKind.VERIFY]` with the
real functions, with no `run_worker` in existence yet.

**Cost implications** — none.
**Recommendation / ruling** — (b), implemented. Left an explicit note in
`missions/apps.py::ready()` asking T1-T4/T6/T7 to add their own dispatch module's import
alongside this one (or for T0 to consolidate all seven into one list) rather than leaving six
more ad hoc wiring mechanisms to reconcile later.

**Final approval authority** — engineering-manager / CTO, since this sets a convention other
tasks are asked to follow rather than being purely local to T5.


### 5. Fixing cybersecurity's PR #175 review — SEC-44/SEC-45/SEC-47 all closed; a separate, more urgent Docker-packaging gap found along the way and flagged, not fixed here

Follow-up to §3 above, which flagged the unsandboxed-execution risk without deciding it.
Cybersecurity's review (PR #175 comment) confirmed it as **SEC-44 (CRITICAL)** — no `env=`
on any of `run_verification`'s five `subprocess.run` calls, so a patch under verification
(including an operator-authored one per D-008) inherits the worker's full environment,
`DATABASE_URL` included — plus **SEC-45 (HIGH)**, `GateResult.detail`'s "never raw target
output, never secrets" contract already violated by embedding raw stdout/stderr, and
**SEC-47 (HIGH)** — no `packages.sandbox.Jail` isolation on `run_verification`'s
build/run/ctest steps. All three are fixed on this branch. This entry was drafted once
already, concluding SEC-47 was genuinely blocked (not merely deferred) by an import-boundary
gap — that conclusion turned out to be **stale by the time of writing**, not wrong when
written: merging `origin/main` mid-task (this branch had fallen behind #168 T1's and T7's
already-merged PRs) pulled in T1's own fix for the exact gap that was blocking SEC-47.
Recorded here in full, including the reversal, rather than quietly rewritten as if SEC-47
had been straightforward from the start.

**Decision (SEC-44)** — Explicit env allowlist (`_ENV_ALLOWLIST`), imported directly from
`packages.sandbox.policy.DEFAULT_ENV_ALLOWLIST`, passed via `env=` to every subprocess this
module spawns. First implemented as a **locally duplicated** tuple (see the superseded
reasoning below); switched to a direct import once SEC-47's work resolved the same import
boundary that made duplication necessary in the first place.

**Options considered (as originally decided, before the import boundary was resolved)** —
(a) `from packages.sandbox.policy import DEFAULT_ENV_ALLOWLIST` (the review's stated
preference: "reuse... rather than inventing a second list"); (b) duplicate the tuple locally
with a comment cross-referencing the source of truth.

**What actually happened** — (b) was implemented first. Verified directly, twice, at that
point: (1) `python -c "import packages.sandbox"` from `apps/control-api` with only that
directory on `sys.path` raised `ModuleNotFoundError`; (2) a throwaway pytest test doing the
same import, collected and run the way CI actually invokes this suite (`cd apps/control-api
&& pytest`, no `PYTHONPATH` override), failed to collect with the same error. Root cause at
the time: `infrastructure/compose/images/control-api.Dockerfile`'s build context is
`apps/control-api/` only, and `apps/control-api/config/settings/base.py` put nothing but
`BASE_DIR` itself on `sys.path`. Both were true when checked. What was **not** accounted for:
`origin/main` had, by that point, already merged #168 T1's PR (`e937933`), which added exactly
the missing piece — `config/settings/base.py` now appends the repository root to `sys.path`
on every Django entrypoint including `pytest-django` (D-066 §3, this same document, filed the
day before this one) — and this branch had not yet merged that commit. Merging `origin/main`
into this branch and re-running the same probe test (`import packages.sandbox` from
`apps/control-api`) now **passes**. (a) was then implemented for real: `_ENV_ALLOWLIST` is now
`DEFAULT_ENV_ALLOWLIST` imported directly, no duplication.

**The lesson, stated plainly rather than only fixed** — this branch (`feat/168-t5-verify-executor`)
was opened before T1/T7 merged and was not rebased before this fix session started. A security
finding's "is X importable from this runtime path" answer is a property of the *merged* tree
at fix time, not of the branch's point of divergence — verifying against a stale base and
reporting the answer as current is exactly the kind of thing that reads as diligence
(re-verified directly, twice!) while still being wrong. Re-verified a third time, against
`origin/main` merged in, before writing this revision.

**Cost implications** — none now; the branch is merged current, the import works, no
duplicated allowlist to drift.

**Security implications** — closes SEC-44. `Jail.run()` (see SEC-47 below) also scrubs to this
same allowlist independently, so the property now holds twice over on the default runner path.

**Scalability implications** — none.

**Recommendation / ruling** — (a), implemented for real once the blocker was actually gone.

**Final approval authority** — CTO (technical).

**Decision (SEC-45)** — Unchanged from the first pass, and not affected by the SEC-47
reversal. `GateResult.detail` is built from only known-safe values: the tool name, the exit
code, a fixed hand-written prefix, and — for the regression gate's failure case — two bare
integers ("N of M tests failed") extracted by a regex capture group that can only ever contain
digits. `result.stdout`/`result.stderr` are read nowhere in `_summarize`. No new "sensitive
log" persistence channel was added; `verification.py` still has no evidence/artifact store
wired into it as a pure function, and inventing one under deadline pressure risked recreating
the exact leak this fix closes, just moved to a new field. Options considered, cost/security/
scalability reasoning, and ruling are exactly as in the superseded draft of this entry — see
the PR discussion on #175 for the full text; not repeated here since nothing about it changed.

**Decision (SEC-47)** — Wrapped `run_verification`'s `git apply`/`cmake` configure/`cmake`
build/`ctest` steps in exactly one `packages.sandbox.Jail` per call, mirroring
`workers/baseline/run.py`'s pattern for BASELINE. Concretely: `run_verification` now opens
`Jail.create(JailPolicy(wall_clock_seconds=float(baseline.timeout_seconds)))` for the whole
call; `_copy_source_tree`'s destination moved from a bare `tempfile.TemporaryDirectory` to
`jail.root / source.name`, so `jail.resolve()`'s containment check is checking something real;
the candidate diff is written to a file inside the jail (`jail.root / ".brahmadatta-candidate.patch"`)
and applied via `git apply --whitespace=nowarn <path>` instead of piping it over stdin, since
`Jail.run()` hardcodes `stdin=subprocess.DEVNULL`; a new `_jail_command_runner(jail)` adapts
`Jail.run()` to this module's existing `CommandRunner` shape and is the default runner when a
caller does not inject one — `_subprocess_runner` (SEC-44's env-scrubbed bare `subprocess.run`)
remains available and tested as an explicit, non-jailed alternative, not deleted.

**Options considered** — (a) leave SEC-47 open as a follow-up once the import-boundary gap
resolved itself (i.e., merge `origin/main` for SEC-44's sake only, and stop); (b) implement the
`Jail`-wrap now, using the exact pattern the review named and the exact one `workers/baseline/run.py`
already established; (c) extend `packages.sandbox.Jail.run()` to accept `stdin` directly instead
of working around the gap in `verification.py`.

**Pros and cons** — (a) would have been the honest, defensible choice if the import blocker
had genuinely still been open (see the immediately-preceding, now-superseded SEC-47 decision
in this same section's edit history) — but leaving a HIGH finding open once the reviewer's own
"a few hours" estimate turned out to be accurate, on a task that explicitly asked "if you get
it done cleanly, great," would have been under-delivering against the actual, current state of
the repo, not a defensible stop. (c) modifies a module (`packages/sandbox/jail.py`) with its
own extensive, independent security-review history (SEC-33 through SEC-41) for a workaround
`git apply`'s own CLI already supports natively (a path argument) — no reason to touch
already-reviewed isolation code for that. (b) is what the review itself recommended and what
BASELINE already proved out.

**Cost implications** — none beyond the implementation time already spent; no new runtime
dependency (`packages.sandbox` was already a dependency of this Django project via T1's merge).

**Security implications** — `run_verification`'s build/run/ctest steps now run under real,
measured CPU/address-space/process-count/wall-clock ceilings, closing the resource-exhaustion/
blast-radius gap SEC-44 alone does not touch (per the review's own words, "`Jail` alone would
not [stop credential exfiltration]" — the inverse is also true: SEC-44 alone does not bound
resource exhaustion). `Jail`'s own docstring caveat still applies verbatim: it "does not
constrain what the command does once running" beyond those ceilings, and has no network
namespace — this pairs with, does not replace, SEC-44's env allowlist.

**Scalability implications** — none; one `Jail` per `VERIFY` job, matching the existing
one-mission-at-a-time design.

**Recommendation / ruling** — (b), implemented and tested: `test_run_verification_opens_exactly_one_jail_sized_from_the_baseline_timeout`
(spies on the real `Jail.create`, asserts exactly one call, sized from
`VerificationBaseline.timeout_seconds`), `test_run_verification_default_runner_actually_invokes_jail_run`
(spies on the real `Jail.run`, against a real trivial CMake target, asserts every command —
`git`, `cmake` configure, `cmake --build`, `ctest` — actually routes through it; regression-
checked to fail when the default runner is reverted to `_subprocess_runner`), and
`test_real_wall_clock_limit_stops_a_hung_build` (a real build whose step sleeps 300s completes
in seconds against a real, unmodified `run_verification` call — labelled honestly in its own
docstring as evidence of "does not hang forever," not exclusively of `Jail`, since a bare
`subprocess.run(timeout=...)` would also have passed it; the `Jail.run`-spy test is the one
that actually discriminates).

**Final approval authority** — cybersecurity (to confirm the fix matches what SEC-47 asked
for) / CTO (technical).

**A separate, more urgent finding surfaced while investigating this: `main` may not currently boot in either Docker profile.** Not decided here — flagged for immediate DevOps/CTO attention, filed as its own item because it is broader than SEC-47 and predates this PR.

While tracing exactly why `packages.sandbox` became importable, I checked whether the *deployed
container* — not just the local/CI pytest invocation — actually has `packages/` available.
It does not, and the gap is live on `main` today, independent of anything in this PR:
`infrastructure/compose/images/control-api.Dockerfile`'s build context is still
`apps/control-api/` only (`COPY --chown=app:app . /app` copies nothing outside it), and neither
`docker-compose.yml` nor `docker-compose.finale.yml` mounts or bakes `packages/`, `workers/`, or
`adapters/` into the `control-api` or `worker` image — confirmed by diffing those three infra
files between this branch's fork point and current `origin/main`: zero changes. Meanwhile,
`origin/main`'s `missions/apps.py::MissionsConfig.ready()` (T1's merge, `e937933`) now
unconditionally runs `from workers.baseline import dispatch` at Django app-startup — not
guarded by `try/except ModuleNotFoundError` the way `orchestrator/teardown.py`'s pre-existing,
narrower use of the same import is — and `workers/baseline/dispatch.py` → `workers/baseline/run.py`
→ `from packages.sandbox import ISOLATION_MODE, Jail, JailPolicy` is a hard, module-level import
chain. `ready()` runs on every Django entrypoint, including the actual container `CMD` in both
`control-api.Dockerfile` targets (`dev` and `runtime`). If `packages/` genuinely is not on that
container's filesystem, this reads as: **the control-api and worker containers, in both compose
profiles, would fail to start** (`ModuleNotFoundError` inside `ready()`, which Django does not
tolerate) — a live regression, not a hypothetical one, that predates this PR (introduced by T1's
merge) and that this PR's own SEC-47 fix adds a second, identical dependency onto rather than
introducing fresh. Not independently reproduced by actually building and running the container
in this session (out of this task's scope and time budget) — reported as "reads as" from reading
the Dockerfile/compose diff directly, not as a confirmed incident, and should be verified by
running `docker compose up control-api` against current `main` before being treated as certain.
If confirmed, this is a CRITICAL-shaped operational gap (the product does not run at all) that
needs a DevOps/CTO-owned fix — bring `packages/`, `workers/`, `adapters/` into the `control-api`/
`worker` build context (mirroring `docker-compose.finale.yml`'s existing `additional_contexts:
demo-repositories` pattern is the most direct precedent already in the repo) — before the next
deploy of either profile, independent of and likely more urgent than this PR's own merge.

### 6. Fixing engineering-manager's functional re-review (commit `8ffdccd`) — `Jail.memory_bytes` not sized for VERIFY's own default sanitizer build, silently zeroing out `VERIFIED` on real Linux · 2026-08-17 · `backend-developer`

Follow-up to §5's SEC-47 fix. Engineering-manager's functional re-review of `8ffdccd`
(PR #175 comment) found that §5's `Jail` construction —
`JailPolicy(wall_clock_seconds=float(baseline.timeout_seconds))` — overrides only the wall
clock. `memory_bytes` stays at `JailPolicy`'s generic 2 GiB `RLIMIT_AS` default, but
`VerificationBaseline.configure_args` defaults to `-DPKTCFG_SANITIZE=ON`, and
`adapters/cpp/variants.py`'s module docstring already documents — with a measured Linux
repro — that AddressSanitizer's shadow-memory reservation needs on the order of tens of
TiB regardless of actual usage, which is exactly why every sanitizer `VariantSpec` there
sets `min_jail_memory_bytes = MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS` and why
`workers/replay/run.py` builds its own `Jail` from that value
(`JailPolicy(memory_bytes=spec.min_jail_memory_bytes)`). §5's rewrite drives
`cmake`/`ctest` directly against `VerificationBaseline.configure_args` rather than through
`adapters.cpp.pipeline.run_variant`/`VariantSpec`, and missed carrying this sizing rule
over. The failure mode is silent, not loud: `Jail.run()` returns an ordinary
`JailResult` with a nonzero exit code (no exception), which `_fail`/`derive_verdict` turns
into a completely normal-looking `REJECTED` — on real Linux (`RLIMIT_AS` is unenforced on
Darwin, which is why this passed locally in §5 without being caught), VERIFY could not
produce a `VERIFIED` verdict for any candidate, correct or not.

**Decision** — Added `orchestrator/verification.py::_sanitizers_enabled(configure_args)`,
which inspects `VerificationBaseline.configure_args` for either a raw `-fsanitize=...`
compiler flag or a CMake `-D<...SANITIZE...>=<truthy>` cache entry (pktcfg's own
`-DPKTCFG_SANITIZE=ON` is the second case). `run_verification` now builds its `JailPolicy`
with `memory_bytes=MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS` (imported from
`adapters.cpp.variants`, not a second constant) whenever that check is true, leaving every
other `JailPolicy` field — including `memory_bytes` itself when no sanitizer is on — at
its generic default.

**Options considered** — (a) detect sanitizers from `configure_args` (the raw strings
`run_verification` actually builds with, since it does not route through `VariantSpec`);
(b) route `run_verification` through `adapters.cpp.pipeline.run_variant`/`VariantSpec`
instead, so `Variant.ASAN_UBSAN.min_jail_memory_bytes` is available directly, no detection
needed; (c) always size the `Jail` at `MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS`, unconditionally,
regardless of whether sanitizers are actually on for a given call.

**Pros and cons** — (b) is the more structurally "correct" long-term shape (one source of
truth for a variant's whole configuration, matching how BASELINE and the replay stage both
work) but is a materially larger change: `run_verification` builds its own configure/build
argv directly against `VerificationBaseline.configure_args`, applies its own
`ignored_names`/worktree-copy logic, and returns `GateMatrix`/`GateResult` shapes distinct
from `BuildResult`/`ReproducerResult` — swapping the whole execution model under a
same-day fix risks a second silent regression, and the engineering-manager's own review
explicitly asked to reuse the constant, not restructure the pipeline. (c) is simpler code
but wrong on the merits: `MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS`'s own docstring is explicit
that "this is not a memory budget," and paying a 64 TiB `RLIMIT_AS` unconditionally —
including for the (currently hypothetical, since `VerificationBaseline`'s only shipped
default has sanitizers on) case of a caller passing `configure_args` with no sanitizer —
would silently mask a future regression in the *other* direction: a caller relying on
`RLIMIT_AS` actually bounding a non-sanitized build's address space would get no such
bound and no signal that it was gone. (a) is scoped to the actual regression, keeps the
fix inside the file the review pointed at, and is directly testable without a real
toolchain (see below).

**Cost implications** — none; no new runtime dependency (`adapters.cpp.variants` was
already importable from this runtime path, confirmed directly — see §5's D-066 §3
cross-reference).

**Security implications** — none negative; this closes a functional gap in SEC-47's own
fix, not a new attack surface. `_sanitizers_enabled` only ever widens `RLIMIT_AS`, never
narrows the env allowlist (SEC-44) or `GateResult.detail`'s no-raw-output guarantee
(SEC-45), both untouched by this change.

**Scalability implications** — none; one `Jail` per `VERIFY` call, unchanged shape.

**Recommendation / ruling** — (a), implemented and verified on real Linux, not just
inferred from the docstring or macOS-passing tests (macOS does not enforce `RLIMIT_AS` at
all, which is exactly how this shipped in §5 without being caught):

1. **Reproduced the original bug directly**, in a bare `ubuntu:24.04` container (no
   Django/pytest involved — the same reproduction shape the review itself used): built
   real pktcfg with `-DPKTCFG_SANITIZE=ON`, ran its real `ctest` suite under
   `ulimit -v 2097152` (2048 MiB, `JailPolicy`'s exact unpatched default). Output matched
   the review's report exactly: `AddressSanitizer failed to allocate 0x200001000
   (8589938688) bytes ... ReserveShadowMemoryRange failed ... 0% tests passed, 8 tests
   failed out of 8`.
2. **Confirmed the fix on the same real Linux container**, via a full `pytest` run of
   `apps/control-api` (Python 3.12.3, real `cmake`/`ctest`/`git`, real venv from this
   repo's own `requirements.txt`): `orchestrator/tests/test_verification.py` —
   33 passed, 0 skipped (the two new Linux-only tests below ran for real, not skipped, on
   this platform); full `apps/control-api` suite — 527 passed, 9 skipped (pre-existing
   SQLite-vs-Postgres skips), 0 failed; `adapters/cpp packages/sandbox workers/baseline
   tests/architecture` (unchanged by this fix, run for regression coverage) — 180 passed,
   18 skipped, 0 failed; `manage.py check` — `System check identified no issues
   (0 silenced)`.
3. New tests in `orchestrator/tests/test_verification.py`: `test_sanitizers_enabled_detects_pktcfgs_default_configure_args`,
   `test_sanitizers_enabled_is_false_when_no_sanitizer_is_turned_on` (5 cases),
   `test_sanitizers_enabled_recognises_every_documented_spelling` (6 cases) — unit-level,
   no toolchain needed, run everywhere including macOS;
   `test_run_verification_sizes_jail_memory_for_the_default_sanitizer_configure_args` and
   `test_run_verification_leaves_jail_memory_at_the_generic_default_without_sanitizers` —
   spy on the real `Jail.create`, assert the exact `memory_bytes` `run_verification`
   builds, both directions; `test_real_verify_achieves_verified_under_sanitizers_on_linux`
   (Linux-only, `skipif(sys.platform == "darwin")` mirroring
   `adapters/cpp/tests/test_sanitizer.py`'s existing convention) — the real,
   unmodified `run_verification`, real toolchain, real pktcfg, reaches `VERIFIED`;
   `test_real_verify_without_sanitizer_memory_sizing_fails_every_gate_on_linux`
   (same Linux-only guard) — monkeypatches `_sanitizers_enabled` to always report `False`
   (simulating the exact pre-fix behaviour) against the same real pipeline and asserts
   every gate FAILs while `derive_verdict` still reads as an ordinary `REJECTED` —
   pinning the silent-failure shape the review specifically warned about, not just the
   allocation error itself.

Also fixed, same commit: `orchestrator/verify_dispatch.py`'s module docstring ("## What
this module deliberately does not do") still described the pre-§5 state (no `Jail` at
all) — stale since §5 moved the wrap inside `verification.py`, flagged non-blocking by
cybersecurity's re-review of `8ffdccd` with an explicit "please fix before merge."
Updated to describe the current, sized state accurately.

**Left alone, per the functional review's own instruction** — neither `_subprocess_runner`
nor `_jail_command_runner` sets `ASAN_OPTIONS`/`UBSAN_OPTIONS` the way
`adapters/cpp/variants.py`'s `VariantSpec.runtime_env` does for BASELINE/replay. The review
named this explicitly as a separate, pre-existing, non-blocking gap ("neither the old nor
new runner sets ASAN_OPTIONS/UBSAN_OPTIONS... that gap predates this PR and isn't new")
and asked that it not be bundled into this fix. Not touched here; worth its own follow-up
so sanitizer exit-code/halt behaviour is pinned for `VERIFY` the way it already is for
BASELINE and replay.

**Final approval authority** — engineering-manager (to confirm this closes the specific
finding raised) / CTO (technical).

---

## D-077 — Implementing D-073: kind-scoped `claim_job`, `run_worker --kinds`, the
fuzz-worker bare-metal entrypoint, and the loopback Postgres port this needed to actually
work · 2026-08-17 · `backend-developer`/`devops-engineer` seat

**Decision** — Implemented D-073's task-breakdown items 1, 2 and 4 (the CTO's own sizing:
backend-developer ~1-2 hrs for the kind filter, devops-engineer ~half day for the
bare-metal entrypoint, backend-developer/cybersecurity ~1-2 hrs for the import-boundary
test) in one PR, against issue #189, on `feat/189-fuzz-worker-topology`:

1. `orchestrator.queue.claim_job` takes an optional `kinds: Iterable[JobKind] | None`
   parameter, applied as `.filter(kind__in=...)` inside the existing `SELECT ... FOR
   UPDATE SKIP LOCKED` query — the filter is in the same locking query, not a
   post-hoc check, so there is no window where an unfiltered claim could race a
   filtered one. Two new module constants: `FUZZ_ONLY_KINDS = {FUZZ, MINIMIZE}` and
   `DEFAULT_WORKER_KINDS = frozenset(JobKind) - FUZZ_ONLY_KINDS`.
2. `manage.py run_worker` gained `--kinds KIND[,KIND...]`, parsed by a new
   `parse_kinds()` function: `None` (flag omitted) resolves to `DEFAULT_WORKER_KINDS`;
   an explicit value resolves to that exact set or raises `CommandError` on anything
   empty or unrecognized. The resolved set is computed once in `handle()` and passed
   explicitly to `queue.claim_job` on every claim — `claim_job`'s own `kinds=None`
   default (kept for backward compatibility with any other caller) is never reached
   from this command, by construction.
3. `infrastructure/scripts/run-fuzz-worker.sh` — the bare-metal entrypoint, preflight-
   checking Docker reachability, the control-api venv/interpreter, and `DATABASE_URL`,
   then `exec`ing `python manage.py run_worker --kinds FUZZ,MINIMIZE "$@"`.
4. `tests/architecture/test_fuzz_worker_isolation.py` — the import-boundary gate D-073
   §5 item 1 asks for: a static AST scan of `workers/fuzzing/` for `gateway`/HTTP-
   client imports, plus a runtime subprocess check that `django.setup()` + loading
   `WORKER_EXECUTOR_MODULES` (exactly what starting `fuzz-worker` does before its
   claim loop begins) never puts `gateway` into `sys.modules`.
5. Both compose files' `worker` service gained a comment block stating the FUZZ/
   MINIMIZE exclusion is deliberate (D-036/D-073), so it is not "fixed" later as a
   bug — task item 5.
6. **Not in D-073's original four-item list, but required to make item 3 actually
   runnable**: `docker-compose.yml`'s dev-profile `db` service now also publishes on
   `127.0.0.1:${POSTGRES_PORT:-5432}` — see the "Postgres reachability" sub-decision
   below.

### The default-exclusion vs. default-inclusion call (task item 1)

D-073's own task breakdown left this as a two-line filter without specifying its
shape; the assignment asked for a documented choice. **Chose default-EXCLUSION**
(`DEFAULT_WORKER_KINDS = frozenset(JobKind) - FUZZ_ONLY_KINDS`) over a hand-maintained
default-INCLUSION list of every other kind named explicitly.

**Options considered** — (a) default-inclusion: `DEFAULT_WORKER_KINDS = frozenset({
BASELINE, SANITIZER_BUILD, CORRELATE, PATCH_GENERATE, VERIFY, EXPORT, TEARDOWN})`,
named by hand; (b) default-exclusion, as implemented.

**Pros and cons.** (a) reads slightly more explicitly at the call site — the exact
set the general worker claims is spelled out in one place — but has the opposite
failure mode from what this task exists to prevent: a `JobKind` added later (a T8, or
a split of `PATCH_GENERATE`, say) is claimable by *nothing* until someone remembers to
add it to this hand-written list, and the failure is silent — the job sits `QUEUED`
forever, no error, no log line, discovered only when a mission visibly stalls. (b)'s
failure mode is the opposite and much louder: a new kind is claimable by the general
worker automatically unless someone deliberately adds it to the two-member
`FUZZ_ONLY_KINDS`, and getting that wrong (a new kind that genuinely needs a container
runtime, not added to `FUZZ_ONLY_KINDS`) fails exactly the way an unregistered
executor already fails today — `orchestrator/executors.py`'s stub raises
`NotImplementedError`, which `run_worker._run_executor` catches and reports as a
visible `FAILED` job with a message naming the missing owner, not a silent stall. (b)
also reduces "can the containerized worker ever claim FUZZ/MINIMIZE" to one fact to
audit (`FUZZ_ONLY_KINDS`'s contents, checked directly against `packages.sandbox`'s own
dependency) instead of two facts that must independently agree (an inclusion list
that omits both, checked against an exclusion fact stated nowhere else).

**Cost implications** — none; both are two lines.

**Security implications** — favors (b), which is the actual reason for the choice:
D-073's own required property is "fails closed, not open" for the two kinds that need
a container runtime specifically, not "fails closed for every kind" — a stalled
`PATCH_GENERATE` job from a forgotten inclusion-list entry is a availability bug, not a
container-runtime-access leak, but it is exactly the kind of quiet failure a
seven-day-old test suite would not catch before the finale. (b) converts that
specific failure mode into a loud one.

**Scalability implications** — none.

**Final approval authority** — backend-developer's own call per D-073 task item 1's
explicit "your call, document reasoning" instruction; CTO retains override.

### Postgres reachability for the bare-metal entrypoint — dev profile fixed now,
finale profile left as an open, unreviewed decision (task item 4, D-073 §6 task 2)

**Trigger.** D-073 §6 task 2 named this directly: "needs a reachable connection
string from the host — check whether the finale profile already publishes Postgres's
port or needs one added." Checked directly: **neither** `docker-compose.yml` nor
`docker-compose.finale.yml` publishes any port for `db`, in either profile, as of this
session. `apps/control-api/.env.example`'s own `DATABASE_URL` default
(`...@localhost:5432/...`) already assumed a bare-metal Django process could reach
Postgres at `localhost` — that assumption predates this task and was already false for
the dev profile; this closes a pre-existing gap rather than opening a new one there.
`infrastructure/scripts/gen-postgres-cert.sh`'s TLS certificate already carries
`localhost`/`127.0.0.1` in its `subjectAltName`, alongside `db` — independent evidence
that a host-loopback Postgres connection was anticipated by whoever wrote that script,
even though nothing wired it up.

**Decision, split by profile:**

- **`docker-compose.yml` (dev): fixed.** `db` now publishes
  `127.0.0.1:${POSTGRES_PORT:-5432}:5432` — loopback only, same pattern nginx already
  uses for its own published ports in this exact file family, and gated by nothing
  the dev profile did not already expose (any process on the operator's own laptop
  could already reach the API through nginx's own loopback publish). This is what
  `infrastructure/scripts/run-fuzz-worker.sh` and `apps/control-api/.env.example`'s
  documentation now assume for local testing/rehearsal of the fuzz-worker mechanism.
- **`docker-compose.finale.yml`: deliberately NOT changed.** That file states, as an
  explicit, load-bearing invariant in its own header comment, "no port is published
  except through nginx" (item 6 of its documented differences from the dev profile).
  Breaking that invariant for the finale host — the machine actually used on stage —
  is a real security-posture change, not a documentation fix, and this seat's charter
  explicitly excludes security posture sign-off (`cybersecurity` owns that). Left as
  an open question, with `run-fuzz-worker.sh`'s own preflight refusing to guess at a
  `DATABASE_URL` and explaining why, rather than silently defaulting to something
  that was never decided.

**Options considered for the finale profile specifically** (not decided here — listed
for whoever picks this up): (a) publish `db` on `127.0.0.1` in the finale profile too,
mirroring the dev fix exactly — cheapest, matches an already-anticipated TLS SAN, but
is the first exception to a stated invariant on the one machine judges are in the room
for; (b) run `fuzz-worker` itself with `docker network connect backend <container>`-
style access to the compose network from the host's own network namespace — avoids
publishing a port at all, but blurs D-073's own "bare-metal, not containerized" framing
and has not been tried; (c) an SSH/socat loopback tunnel set up by the operator by hand
on the finale host, published nowhere in compose at all — smallest blast radius,
costs an extra manual step in an already-tight finale runbook, and is easy to forget
under stage pressure; (d) leave it broken and accept that `fuzz-worker` cannot reach
the finale database at all, i.e., D-073's whole mechanism does not actually run on the
finale host — clearly wrong, listed only for completeness.

**Cost implications** — the dev fix: none. The finale question: unresolved, so unknown
until decided.

**Security implications** — the dev fix is judged low-risk (loopback-only, dev
machine, mirrors an existing pattern in the same file) but is still a network-topology
change and is called out here rather than folded silently into "documentation," so
`cybersecurity` can review it on the same PR as everything else in this change. The
finale question is explicitly unresolved and is the single most important open item
in this whole change — see Open Questions in the PR description.

**Scalability implications** — none.

**Recommendation** — ship the dev fix now; escalate the finale question to
CTO/devops-engineer for a decision and to `cybersecurity` for review before
`infrastructure/scripts/run-fuzz-worker.sh` is ever run against the finale host's own
compose stack. Recommend option (a) above as the same-day answer if a decision is
needed before 2026-08-20 — it is the smallest diff and the TLS material already
anticipates it — but that recommendation is not a decision.

**Final approval authority** — devops-engineer/CTO for the finale-profile compose
change itself; `cybersecurity` holds the review gate on it per CLAUDE.md's standing
rule for isolation-relevant changes, same as the rest of D-073's implementation.

### What is still open after this PR

1. The finale-profile Postgres reachability question above — unresolved by design.
2. D-073 §5 item 2 (bare-metal `fuzz-worker` genuinely has no route to `model-host`,
   not just "isn't configured to") needs a live connectivity check on the actual
   finale host, in the shape `infrastructure/scripts/egress-test.sh` already
   establishes for the containerized services — not attempted here; there is no
   bare-metal-host equivalent of that script yet.
3. D-073 §5 item 4 (the finale host's own hardening — not running as root, a
   dedicated operator account, `docker` version/storage-driver parity with D-072's own
   verification) is an operational checklist item for whoever runs the finale
   rehearsal, not something a PR can close.
4. The stale `D-024` citations in `packages/sandbox/container.py`'s own module
   docstring (D-073's numbering note already flagged this) are untouched here —
   that file is owned by the sandbox/container-jail work, not this PR, per this
   seat's standing instruction not to edit another role's code opportunistically.
   `apps/control-api/.env.example`'s own near-identical stale citation, immediately
   adjacent to the `SANDBOX_RUNTIME` documentation this PR was already touching, was
   corrected in passing (D-036, not D-024) since it is this seat's own file.
5. `docker-compose.finale.yml`'s/`docker-compose.yml`'s stale `CONTROL_API_WORKER_CMD`
   default (`python manage.py rqworker default`, no `django_rq` installed — D-070's
   own note) is unrelated to this change and left as-is; it does not block
   `run_worker --kinds`, since the compose `command:` line for the containerized
   `worker` service is not what this PR changes.

**Final approval authority (whole record)** — CTO (technical) for the topology
implementation, following D-073's own ruling; `cybersecurity` holds the review gate
required before any of this runs against the finale host, per D-073 §5/§6.5 and
CLAUDE.md's standing rule for isolation-relevant changes. Not yet reviewed as of this
entry — PR opened as draft for that reason.

---

## D-078 — implementing D-075 (SEC-50 fix): three real corrections found by actually
bringing the stack up, and where `MODEL_HOST_BEARER_TOKEN` is (and is not) declared · 2026-08-17
· devops-engineer

**Numbering note.** This branch (`fix/189-model-host-auth`) is cut from `main`, which tops out
at D-070 — neither D-071–D-074 nor **D-075** (the CTO ruling this record implements, PR #200,
branch `docs/d075-sec-50-model-host-auth-ruling`, not yet merged) exist in this file on this
branch. Checked directly against every open branch and PR before numbering this record, the
same way D-075's own numbering note did: the highest `## D-` heading anywhere is D-075, so this
record takes **D-078** to avoid colliding with it once both land, regardless of merge order.
D-075's own text is not reproduced here — see PR #200 or `git show
docs/d075-sec-50-model-host-auth-ruling:.project/decisions.md` for the full ruling this record
implements. This is the implementation record D-075's own task breakdown asked for (items 1, 2,
3 partial, 4), not a re-litigation of the ruling itself.

**Trigger** — implementing D-075's task breakdown (`infrastructure/scripts/run-fuzz-worker.sh`
gate: bind Ollama to loopback, front it with a bearer-token nginx sidecar sharing its network
namespace, thread the token through `services/model-gateway`). Three things D-075's design did
not anticipate — because they only surface when the stack actually runs, not on inspection —
required a real decision during implementation, all verified by actually bringing
`docker compose --profile model up` up on both `docker-compose.yml` and
`docker-compose.finale.yml` and probing it with real HTTP requests (recorded on the PR, not
just asserted here).

**1. Ollama's own internal port had to move from 11434 to 11435.**

D-075's design assumed the sidecar takes over port 11434 on the shared namespace's external
interface "so nothing else in the codebase needs its target port changed." True for every
*external* caller (`model-host:11434` is unchanged for anything on `backend`), but the sidecar
still needs `proxy_pass` to reach Ollama somewhere inside the shared namespace — and
`OLLAMA_HOST=127.0.0.1:11434` plus nginx `listen 11434;` (wildcard, `0.0.0.0`) in the SAME
network namespace do not coexist: a wildcard bind on a port collides with an already-bound
exact address on that same port at the kernel level (`EADDRINUSE`, confirmed live —
`brahmadatta-model-host-auth` failed to start with exactly this error the first time this was
brought up). Two options: give nginx a specific non-wildcard bind (requires a static IP
assignment for `model-host` on `backend`, which does not have a pinned subnet today, unlike
`api`), or move Ollama's *internal* port. Moved Ollama's internal port to 11435 — it is not
part of any external contract (nothing outside this container/namespace has dialed it directly
since before this fix existed), so changing it is invisible to every other service, while
pinning a static IP for `model-host` would have been a second, unrelated network-topology
change to a file that does not need one. `OLLAMA_HOST: 127.0.0.1:11435` in both compose files;
`proxy_pass http://127.0.0.1:11435;` in the template.

**2. The sidecar's `proxy_pass` had to rewrite the `Host` header to `127.0.0.1`.**

With the port fixed, the very next real request came back `403` from Ollama itself — not the
sidecar's own `401`. Ollama enforces its own Host-header allowlist (distinct from
`OLLAMA_ORIGINS`, which is a browser `Origin`-header CORS check, not this) and refuses anything
other than `localhost`/`127.0.0.1`/`0.0.0.0`, regardless of whether the caller is otherwise
authenticated — confirmed live by sending a request through with the caller's real Host header
(`model-host:11434`, the compose service name a normal `backend` caller uses) and watching
Ollama itself reject it with `403` even after the sidecar had already accepted the correct
bearer token. Fixed: `proxy_set_header Host 127.0.0.1;` in the template, so Ollama sees exactly
the Host it already trusts regardless of what the original caller addressed it as. This is a
genuine finding about Ollama's own behaviour, not a workaround for anything this fix introduced
— it would have bitten *any* reverse proxy in front of Ollama, D-075-shaped or not.

**3. `/etc/nginx/conf.d` needed an explicit `mode=1777` on its tmpfs mount.**

The sidecar's `read_only: true` + tmpfs pattern mirrors the ingress `nginx` service exactly,
but the ingress service never actually needs to *write* into `/var/cache/nginx`/`/var/run` at
startup — this sidecar does, because `NGINX_ENVSUBST_OUTPUT_DIR` (`/etc/nginx/conf.d` by
default) is where the image's own `20-envsubst-on-templates.sh` entrypoint step writes the
rendered `model-host-auth.conf` before nginx starts. A bare `tmpfs: [/etc/nginx/conf.d]` entry
comes back `root:root 0775` — confirmed live (`ls -ld` inside the running container) — which
uid 101 (this image's `nginx` user) cannot write into; the image's own baked-in
`/etc/nginx/conf.d` is `nginx:root 0775` and only writable there because uid 101 *owns* it, an
ownership a plain tmpfs mount does not preserve. First attempt failed with `20-envsubst-on-
templates.sh: ERROR: /etc/nginx/templates exists, but /etc/nginx/conf.d is not writable`. Fixed
with `- /etc/nginx/conf.d:mode=1777` (matches `/tmp`'s own default mode, which is why `/tmp`
needed no such override).

**4. `MODEL_HOST_BEARER_TOKEN` is declared ONLY in the repository-root `.env.example`
(compose-only), deliberately never in `apps/control-api/.env.example`.**

D-075 named `apps/control-api/.env.example` as a candidate location by analogy with
`MODEL_HOST_LIFECYCLE_*` (declared in both root and `apps/control-api/.env.example` today) but
did not resolve which file(s) the new token belongs in. Checked directly: D-073's bare-metal
`fuzz-worker` process (`infrastructure/scripts/run-fuzz-worker.sh`, PR #197, not yet merged —
read via `gh pr diff 197`) sources `apps/control-api/.env` **wholesale**
(`set -a; source "${CONTROL_API}/.env"; set +a`) whenever `DATABASE_URL` is not already set in
the calling shell, to get Postgres reachability outside the compose network. Declaring
`MODEL_HOST_BEARER_TOKEN` in that file would place it in `fuzz-worker`'s process environment
the moment an operator's real `apps/control-api/.env` contains both — an ambient exposure that
holds regardless of whether `fuzz-worker`'s own code ever imports `gateway` or reads the
variable, which is exactly the class of leak this entire fix exists to close. `fuzz-worker` is
not a compose service at all (D-073), so `control-api`/`worker`'s normal `env_file: ../../.env`
already delivers the token to the only processes that are ever supposed to have it, with no
`apps/control-api/.env.example` declaration required. `apps/control-api/.env.example` instead
gets a comment explaining the omission, so a future edit does not "helpfully" add it back
without re-reading this reasoning. `tests/architecture/test_compose_topology.py::
test_model_host_bearer_token_is_declared_only_in_the_compose_env_example` guards this.

**Options considered (for item 4 specifically, the only one with more than one defensible
answer):**

- **(a) Root `.env.example` only.** Chosen. Matches every compose-only secret's existing
  pattern in that file (`POSTGRES_PASSWORD`, `REDIS_PASSWORD`) and is the one placement that
  cannot reach `fuzz-worker`'s environment through `run-fuzz-worker.sh`'s own `source` line.
- **(b) Both files, mirroring `MODEL_HOST_LIFECYCLE_*`.** Rejected: `MODEL_HOST_LIFECYCLE_*`
  are non-secret configuration (compose file paths, profile names, timeouts) with no
  confidentiality property to protect if `fuzz-worker` happens to see them; a bearer token is
  exactly the kind of value D-075 exists to keep away from that process. The analogy does not
  hold for a secret.
- **(c) `apps/control-api/.env.example` only, since that is where the eventual T4 (`feat/168-
  t4-patch-generate`, not on this branch) wiring will presumably read it from `MODEL_ENDPOINT`-
  style.** Rejected outright for the ambient-exposure reason above — this is the option D-075's
  own phrasing could be read to suggest, and checking `run-fuzz-worker.sh` directly is what
  ruled it out.

**Cost implications** — zero beyond D-075's own estimate; these are corrections found while
implementing the same half-day-to-a-day fix, not new scope. No new service, no new secret
beyond the one D-075 already named.

**Security implications** — items 1–3 are availability/correctness fixes (the sidecar would not
start, or would forward 403s, without them) with no security regression either way. Item 4 is
itself a security decision: it closes an ambient-secret-exposure path to `fuzz-worker` that
D-075's text did not explicitly rule on, using the same "fuzz-worker must never receive this
token" requirement D-075 already stated as its goal for the *code-import* path
(`tests/architecture/test_fuzz_worker_isolation.py`, not present on this branch — lives on PR
#197) and extending it to the *environment-variable* path, which that test does not and cannot
cover (it asserts imports, not `os.environ` contents).

**Scalability implications** — none.

**Recommendation / ruling** — implemented as described; see this PR's own verification section
for the live proof (`docker compose --profile model up`, real `curl` probes with/without the
token from a container freshly joined to `backend` — the exact SEC-50 PoC shape — and the
production `gateway.tools.model_prep doctor` command run against the real sidecar+Ollama pair
through a container attached only to `backend`, confirming `401` without the token and a real
Ollama response with it). Cybersecurity re-review is still required before this is marked as
closing SEC-50, per D-075's own task breakdown item 5 and this project's standing rule for
isolation-relevant changes — not claimed done here.

**Final approval authority** — CTO (technical), per D-075's own final-approval line, which this
record implements without revisiting; items 1–3 are implementation corrections within that
already-approved design, not new architectural calls. Item 4 is flagged at the same formality
as the rest of this record because it is a real judgment call about where a secret is
declared, even though it follows directly from D-073/D-075's own stated intent.

---

## D-079 — SEC-51 ruling: what D-075/D-078 actually closed, what it did not, and why no bigger
fix lands before 2026-08-20 · 2026-08-17 · CTO

**Context.** Cybersecurity's PR #201 re-review (re-attacking the live, fixed stack, not a diff
read) confirms SEC-50 as literally scoped — a container joining `backend` and reaching
`model-host` directly, unauthenticated — is closed and re-verified with real requests: refused
connect on the raw port, `401` with no/garbage token, `200` with the real token, a full port
scan of the shared namespace showing nothing else answers. That verdict is not being revisited
here. The same review surfaced a new, more fundamental finding, **SEC-51 (HIGH)**: Docker
daemon access — the one privilege `fuzz-worker` is irreducibly and deliberately granted under
D-073, precisely so it can run `ContainerJail` for fuzzing campaigns — defeats D-075/D-078's
fix without touching the network path at all. `docker inspect brahmadatta-model-host-auth`
returns `MODEL_HOST_BEARER_TOKEN` in plaintext (proven live by cybersecurity's own command
output, not asserted); `docker exec` into `model-host` reaches Ollama over its own loopback
directly. This record rules on SEC-51.

**Verification performed before ruling (this session, not re-litigating cybersecurity's own
live PoC, which already produced real command output).** Read `infrastructure/compose/
docker-compose.yml` on this branch directly: `model-host-auth`'s `MODEL_HOST_BEARER_TOKEN` is
supplied via a plain `environment:` entry (compose's standard mechanism), which Docker always
stores as part of the container's config and returns verbatim from `docker inspect
--format '{{json .Config.Env}}'` — this is not this repo's bug, it is how every container
runtime built on the Docker/OCI config model works; there is no compose-level mechanism (short
of Swarm/Compose secrets bind-mounted as files, discussed and rejected below) that keeps an
`environment:`-declared value out of `docker inspect`. Confirmed `model-host` has no bind mount
or network boundary that would stop `docker exec` from any process holding daemon access —
`docker exec` operates through the daemon socket directly and is not mediated by the container's
own network namespace or listeners at all. Cybersecurity's technical claim is accurate; the
options below are evaluated on that basis.

**Options considered.**

- **(a) Run `model-host` on a genuinely separate Docker daemon/host that `fuzz-worker`'s own
  daemon has no reach to.** The only mechanism that actually survives "attacker has Docker
  daemon access" as a threat model, because it removes the shared daemon rather than trying to
  further restrict what a process with full daemon access can do to containers on it — nothing
  short of that removal is durable, for the same reason D-075 itself already rejected network
  segmentation alone (`docker network ls`/`connect` enumerate and join anything the daemon
  manages; the equivalent argument here is `docker inspect`/`exec` reach anything the daemon
  manages). Concretely this means: a second host (or a nested/remote Docker daemon with its own
  independent auth — TLS client certs, which is exactly the "authenticates who, not what"
  mechanism D-073 §2 already evaluated and found insufficient on its own for the *general*
  fuzz-worker-access problem, though it would be sufficient *here* since the question is "can
  this specific daemon reach that daemon at all," not "what can an authenticated caller do"),
  finale-up.sh and `run-fuzz-worker.sh` re-plumbed to talk to it, a new network path opened and
  secured between the two hosts, and a full rehearsal of that new topology. This is real
  infrastructure work — new provisioning, new deployment code, new failure modes — not a
  same-day change, and it is not close to one: D-075/D-078's own fix, by comparison, was
  correctly sized at half a day to a day specifically because it stayed inside one daemon, one
  compose file, one process's namespace. Rejected as required-before-2026-08-20, for reasons
  stated under Recommendation below.
- **(b) Accept SEC-50's fix as real, worthwhile defense-in-depth; document SEC-51 explicitly as
  a residual risk within D-073's own already-accepted envelope; no further fix before
  2026-08-20.** This is cybersecurity's own recommendation in the PR #201 review ("costs a
  paragraph, not a rebuild") and this record adopts it. Chosen — see Recommendation.
- **(c) Replace `fuzz-worker`'s raw Docker CLI access with a narrow, policy-enforcing wrapper
  service.** The eventual correct answer for the *general* problem SEC-51 is one more instance
  of — already D-073 §4/§6.6's named, deferred "sandbox-executor" follow-up, and already
  correctly scoped there as post-2026-08-20 work, for the same reason D-075 gave when it
  declined to build this under a three-day clock to fix one downstream service: this is real
  infrastructure (a new service, its own auth/contract, a credential lifecycle) that does not
  get smaller by being motivated by SEC-51 instead of SEC-50. SEC-51 does not enlarge this
  item's scope; it adds one more concrete reason it is worth doing eventually. Not adopted here,
  unchanged from D-073.

**Recommendation / ruling — option (b). SEC-51 is a documented, accepted residual risk. It is
not required to be fixed before 2026-08-20.**

Reasoning, stated plainly rather than deferred to "cybersecurity said so":

1. **The precondition is significant and was already accepted, at CTO authority, under D-073.**
   SEC-51 requires `fuzz-worker` to already be compromised — a live adversary with code
   execution inside the one process D-073 deliberately gave Docker daemon access to, for
   fuzzing to work at all. D-073 already accepted that privilege as irreducible for this
   project's timeline, and D-075's own residual-risk paragraph already stated in writing that
   "`fuzz-worker` retains Docker daemon access ... could still use it to disrupt `backend` in
   other ways." SEC-51 does not open a new door; it proves, with a real command, exactly how far
   through the already-acknowledged door an attacker who is already inside gets. That is
   materially different from a finding that introduces new exposure the project had not already
   priced in.
2. **The finale's actual threat model does not feature the adversary SEC-51 requires.** This is
   a single-host demo, run by a single trusted operator, fuzzing a known, non-adversarial target
   (`pktcfg`) chosen for this exercise — not a hosted, multi-tenant, or internet-facing service
   where an external party has both motive and opportunity to compromise the fuzz worker
   specifically to pivot toward inference credentials. The gap is real and the reasoning behind
   it is sound engineering; the probability-weighted risk against this specific, time-boxed
   demo is low. This is exactly the class of finding CLAUDE.md's proportionality principle
   exists for — not "ignore it," but "size the response to who is actually plausible as an
   attacker within scope, on this timeline."
3. **Cybersecurity itself did not rate this CRITICAL.** The standing rule ("a critical security
   finding is waived only by written CEO risk acceptance") is written against CRITICAL, and
   cybersecurity's own review is explicit: "I'm not rating it CRITICAL." Combined with point 1
   — that the underlying risk boundary was already CTO-approved under D-073, and this finding
   sharpens rather than expands it — SEC-51 does not cross the bar that requires a fresh,
   written CEO risk acceptance. It stays at CTO final-approval authority, the same authority
   that already accepted D-073's design. I am ruling on it here rather than escalating it, and
   recording the reasoning so the call is auditable, not asserted.
4. **The bigger fix is not a good use of the three days remaining.** Per `.project/state.md`,
   the actual gate blocking the finale demo from existing at all is `#50` — seven of eleven
   mission-lifecycle HTTP routes are still unwired stubs, discovered by an end-to-end audit that
   the per-module test suites did not catch. That is the critical path. Spending a meaningful
   fraction of the three days remaining before 2026-08-20 standing up a second Docker daemon,
   re-plumbing two deployment scripts, and rehearsing a new topology — to close a gap whose
   precondition is "the fuzz worker is already compromised," in a threat model where that
   precondition is implausible — would trade a small, already-priced-in residual risk for a real
   chance of not having a working mission API to demo at all. That is the wrong trade under this
   timeline, independent of SEC-51's technical merits.

**What is explicitly NOT true, and must not be read into "SEC-50 closed" from here forward —
this is the addendum cybersecurity's review asked for:**

> D-075/D-078's fix is real and worth having: it closes the literal, demonstrated SEC-50 attack
> (a container joining `backend` and reaching `model-host` with zero credential), and it raises
> the bar against any adversary whose capability tops out at "network route to `backend`" —
> which matters against some threat classes even though it is not the one SEC-51 is about. **It
> does not mean, and must not be read to mean, that `fuzz-worker` is now safe to run near a live
> `model-host`.** The actual safety property the finale depends on when both are up together has
> never rested on this network/auth boundary — it rests entirely on `fuzz-worker` itself never
> being compromised in the first place. That property is carried by `fuzz-worker`'s own
> isolation — `ContainerJail`'s hardening and the fuzz target's own containment (D-053, D-073) —
> not by this PR. If `fuzz-worker`'s own containment is ever weakened, extended, or reused for a
> less-trusted fuzz target than `pktcfg`, this residual risk gets re-evaluated from scratch; it
> is not a one-time acceptance that travels forward unexamined.

**Cost implications** — zero new engineering cost before 2026-08-20 (this record itself is the
only deliverable). Option (a)'s cost, if ever picked up post-competition alongside D-073 §4/
§6.6's sandbox-executor line: a second host or isolated remote daemon, new deployment plumbing,
new rehearsal cycle — materially larger than D-075/D-078's half-day-to-a-day fix.

**Security implications** — SEC-50 (network-route, zero-credential access) stays closed. SEC-51
(Docker-daemon-access defeats the token) is recorded as an accepted residual risk, scoped to the
precondition "`fuzz-worker` is already compromised," which is itself D-073's own accepted,
irreducible design tradeoff. No new exposure is introduced by this ruling; it makes an existing,
already-accepted boundary explicit rather than leaving it implicit in D-075's residual-risk
paragraph. Fast-follow, unchanged from D-075 task 6: cybersecurity's own recommendation to
re-check `redis`'s dev-mode no-password posture and any other `backend`-network service for the
same "Docker access is a strictly broader capability than network access" shape remains open and
owned by cybersecurity, not superseded by this record.

**Scalability implications** — none.

**Recommendation** — PR #201 is clear to merge (cybersecurity's own verdict: "PASS WITH
CONDITIONS ... not a blocker on this PR's merge"); this record satisfies the stated condition.
No further code change is required before 2026-08-20 to close SEC-51. `#50` (mission API
routing) is the correct next claim on the three days remaining, not this.

**Final approval authority** — CTO (technical), consistent with D-073/D-075's own final-approval
lines, which this record extends rather than reopens. No CEO risk acceptance is required per
point 3 above; this is noted for CEO/PM visibility in the handoff, not routed as a required
sign-off.
