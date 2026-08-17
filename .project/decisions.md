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
