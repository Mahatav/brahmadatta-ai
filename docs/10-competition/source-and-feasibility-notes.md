# Source and Feasibility Notes

## Requirements established by the supplied competition material

- Build a Cyber-Reasoning System that combines an LLM with fuzzing, static analysis, dynamic analysis, and a regression-test harness.
- The system must autonomously find a vulnerability, generate a patch, and prove that the fix holds.
- The initial submission is a maximum five-slide presentation covering the idea, methodology, technology/architecture, novelty, and final deliverables.
- Shortlisting emphasizes resource utilization, novelty, and a lightweight solution.
- The grand finale is a 36-hour in-person build and refinement period.
- Final evaluation emphasizes performance, speed, precision, functionality, and scalability in a simulated defence environment.

## Feasibility position

Brahmadatta AI should not attempt to solve all repository-security problems in the MVP. The credible competition target is one repeatable C/C++ pipeline with controlled defects and strong evidence.

The architecture reduces risk by:

- Running deterministic CPU tools before models.
- Requiring a concrete reproducer before patching where possible.
- Limiting the lightweight model to localized repairs.
- Treating the heavy self-hosted model as a bounded escalation path rather than a default dependency.
- Keeping verification independent of both models.
- Providing a smaller-model fallback if the heavy rented GPU topology is unavailable.

## Claims that require measurement before submission

- Percentage of cases resolved without heavy escalation.
- Time from repository intake to confirmed reproducer.
- Patch success rate.
- False-positive reduction.
- GPU startup, inference, and teardown timing.
- Maximum repository size and context package supported.

## Required technical spike

Before the architecture is presented as final, run one end-to-end heavy-model spike on the intended rented GPU topology. Record startup time, model memory, inference latency, context limits, stability, and teardown behavior. If the heavy model cannot meet the demonstration envelope, retain the three-tier design but use the validated smaller self-hosted model for the MVP.

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
