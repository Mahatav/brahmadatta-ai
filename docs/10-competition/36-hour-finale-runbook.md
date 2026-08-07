# 36-Hour Finale Runbook

**Every stage below has a fallback, a trigger that fires the switch, and a sentence that goes
with each mode. They live in [`../09-company/10-fallback-ladder.md`](../09-company/10-fallback-ladder.md)
(#84). Read it before the clock starts, not when a stage stalls.**

## Before the clock starts

- Verify the frozen release, container images, tool cache, model artifacts, demo repositories, and fallback recording.
- Work the fallback-ladder pre-flight (§7): isolation egress smoke check, fuzz build, one #82 transcript resolved by hash, SSE through the finale stack, and the #49 capture played offline. Isolation mode is set here and does not change after hour 3.
- Confirm the command-center presentation mode.
- Confirm that GPU teardown can be triggered from both UI and command line.

## 0–3 hours — Environment and target validation

- Deploy control plane and lightweight model.
- Validate repository authorization, build, tests, policy, and adapter.
- Confirm live event streaming to the Brahmadatta Core.

## 3–10 hours — Tier 1

- Establish baseline.
- Run static analysis, dependency inventory, and Git analysis.
- Confirm dashboard findings and timeline panels.

## 10–18 hours — Tier 2

- Build sanitizer target.
- Run fuzzing, reproduce, deduplicate, and minimize.
- Convert the failure into a stable verification target.

## 18–25 hours — Patching

- Attempt lightweight patch first.
- Use one justified heavy-model escalation only when the localized route fails and capacity permits.
- Apply patch policy before any verification run.

## 25–31 hours — Independent verification

- Rebuild from a clean worktree.
- Run original reproducer, regression suite, static delta, and renewed fuzzing.
- Produce both a verified case and a rejected bad-patch case.

## 31–34 hours — Evidence and UI polish

- Freeze functional changes.
- Generate Markdown/JSON evidence.
- Confirm all dashboard panels show real run data.
- Switch to presentation mode and rehearse the narrative.

## 34–36 hours — Submission and teardown

- Finalize five slides and demonstration order.
- Tag the release and preserve logs.
- Terminate unneeded GPU leases and confirm teardown in the UI.

## Hard rules

- Stop major features after hour 24.
- Never claim physical air-gapping from rented cloud infrastructure.
- Never accept a patch without all required gates.
- Never narrate a fallback mode with the primary mode's claim. The wording for each mode is fixed in the fallback ladder §1; do not improvise one on stage.
- Never scan an unauthorized or public target.
- Prefer a stable, fully evidenced demonstration over adding another feature.

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
