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
