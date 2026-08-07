# UI Design Direction

| Field | Value |
|---|---|
| Product | Brahmadatta AI |
| Interface | Brahmadatta Command Center |
| Visual direction | Futuristic armored-assistant mission control |
| Primary viewport | Desktop, 1440 × 900 and above |
| Last updated | 2026-08-06 |

## Design goal

Create a dashboard that feels like an advanced armored operating system: visually impressive, information-dense, and immediately useful during a live cyber-reasoning run. The interface may evoke the general feeling of cinematic suit-control systems, but it must use original geometry, icons, wording, and branding.

## Core visual language

- Near-black and deep navy background.
- Cyan, ice-blue, and white as primary information colors.
- Green for verified or operational states.
- Amber for warnings, escalation, and medium severity.
- Red only for critical findings, failed gates, or unsafe conditions.
- Thin luminous borders, nested glass panels, subtle grids, precise typography, and restrained glow.
- Circular instrumentation at the center; rectangular evidence panels around it.
- Charts, counters, and animations must display real system telemetry. Decorative fake metrics are prohibited.

## Information architecture

### Top command bar

- Brahmadatta AI identity and release label.
- System state: idle, operational, degraded, paused, or failed.
- Mission elapsed time.
- Active repository and branch/snapshot.
- Current threat level derived from confirmed findings.
- AI confidence shown only beside its source and never as a verification result.
- UTC clock and operator identity.

### Left analysis rail

- Repository status and immutable snapshot hash.
- Baseline build and regression status.
- Static-analysis findings by severity.
- Dependency and compiler health.
- Coverage and risky-change summaries.

### Central Brahmadatta Core

The central radial component shows the active mission phase:

1. **Ingest**
2. **Analyze**
3. **Correlate**
4. **Stress Test**
5. **Remediate**
6. **Verify**

The center displays the final mission state: protected, investigating, vulnerability confirmed, patching, verified, rejected, human review, or failed.

### Right remediation rail

- Prioritized vulnerability queue.
- Live fuzzing executions, crashes, unique findings, and coverage.
- Patch-generation attempts and their state.
- Model routing: deterministic, lightweight model, or heavy model.
- Verification gate summary.

### Lower evidence deck

- Git bisect timeline.
- System alerts and operator-required actions.
- Rented GPU utilization, memory, active lease time, and teardown state.
- Regression-test results.
- Evidence-bundle readiness and export control.

### Footer control strip

- Secure-session status.
- Operator and mission ID.
- Command palette.
- Log-stream rate.
- Artifact-vault state.
- Safe pause, cancel, and emergency teardown controls.

## Complexity rules

- Use progressive disclosure: summary first, evidence drawer second, raw logs third.
- Keep no more than one dominant visual focal point.
- Do not show a metric unless the operator can act on it or use it as evidence.
- Critical controls require labels, confirmation, and visible consequences.
- Use motion to communicate state changes, not to decorate idle screens.

## Responsive scope

The competition MVP is desktop-first. At widths below 1280 px, collapse side rails into tabbed drawers and preserve the central mission core. Mobile is read-only and out of scope.

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
