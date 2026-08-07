# UI State and Motion Specification

## Mission states

| State | Core behavior | Primary color | Operator meaning |
|---|---|---|---|
| Idle | Slow static ring | Blue | Ready for a mission |
| Validating | Inward scan pulse | Cyan | Checking configuration |
| Analyzing | Rotating segmented ring | Cyan | Deterministic tools running |
| Stress testing | Rapid outer waveform | Amber | Sandboxed fuzzing active |
| Patching | Focused inner pulse | Blue-white | Patch candidate being produced |
| Verifying | Alternating before/after arcs | Cyan/green | Required gates executing |
| Verified | Stable shield lock | Green | All gates passed |
| Rejected | Broken patch arc | Red | Candidate failed evidence gates |
| Human review | Paused amber halo | Amber | Policy requires a person |
| Failed | Static red alert ring | Red | Mission cannot continue safely |

## Motion rules

- Default transitions: 150–300 ms.
- Long-running phase motion should be slow and non-distracting.
- No flashing above safe accessibility thresholds.
- Reduced-motion mode replaces rotation and pulses with progress bars and state text.
- A severity change may animate once, then become static.
- Critical alerts may use a single border pulse, never continuous flashing.

## Sound

Sound is off by default. Optional competition mode may use a subtle completion tone and critical alert tone; neither is required for operation.

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
