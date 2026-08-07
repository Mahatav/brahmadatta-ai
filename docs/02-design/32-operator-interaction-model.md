# Operator Interaction Model

## Operating principle

Brahmadatta AI is autonomous inside a fixed policy, while the human operator controls authorization, resource ceilings, escalation permission, cancellation, and final review.

## Main interaction path

```text
Create Mission
  → Validate Authorization and Repository
  → Confirm Resource Policy
  → Start Mission
  → Observe Brahmadatta Core
  → Inspect Confirmed Finding
  → Observe Patch and Verification
  → Export Evidence
  → Mark for Human Review
```

## Command palette

Open with `Ctrl/Cmd + K`. Suggested commands:

- Open mission setup.
- Focus current stage.
- Open vulnerability queue.
- Show Git bisect.
- Show verification matrix.
- Pause after current stage.
- Cancel mission safely.
- Tear down idle rented GPUs.
- Export evidence.

Destructive commands always require confirmation and display the cleanup steps that will occur.

## Panel behavior

- Single click: select and summarize.
- Double click or Enter: open detail drawer.
- Escape: close drawer without changing mission state.
- Pin: keep a panel visible during phase transitions.
- Compare: place before/after evidence side by side.

## System feedback

- Every operator action receives an immediate acknowledgement.
- Long tasks expose stage, elapsed time, latest heartbeat, and cancel behavior.
- Failure messages state what failed, what remains safe, and the next recovery action.
- Model confidence is visually distinct from verified evidence.
- A successful patch displays **Verified** only after all required gates pass.

## Presentation mode

A competition presentation toggle hides setup complexity and enlarges:
- The central mission core.
- Current stage and elapsed time.
- Confirmed evidence.
- Git root cause.
- Patch diff.
- Verification result.
- GPU/resource-efficiency summary.

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
