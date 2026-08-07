# Competition Finale Environment Guide

This document replaces a commercial production guide. It defines the environment used for the judged MVP demonstration.

## Required environments

1. **Local developer environment** — feature work and unit tests.
2. **Rehearsal environment** — mirrors the finale topology with smaller model capacity.
3. **Finale environment** — frozen, tagged, monitored, and limited to demo targets.

## Finale topology

- One frontend/API control node.
- One database/queue service.
- One or more CPU analysis workers.
- Disposable target sandbox worker.
- Lightweight model GPU.
- Heavy model cluster only when the approved demo path requires it.
- Encrypted artifact volume.

## Freeze policy

- Freeze major features 48 hours before travel or final submission.
- Freeze model weights, prompts, and schemas after the final full rehearsal.
- Permit only blocker fixes with two-person review.
- Keep a known-good release tag and offline deployment bundle.

## Demo data

Use authorized controlled repositories with known defects. Never depend on live access to a public target or an untested third-party repository during judging.

## Fallbacks

- Pre-built container image cache.
- Local copies of tool packages and model manifests.
- Smaller fallback model.
- Known-good static/fuzzing evidence bundle.
- Short pre-recorded end-to-end run for infrastructure failure only; clearly label it as recorded.

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
