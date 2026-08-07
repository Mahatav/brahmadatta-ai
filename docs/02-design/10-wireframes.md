# Wireframes

## 1. Mission Setup

```text
┌ BRAHMADATTA AI ─ CREATE MISSION ─────────────────────────────────────────────┐
│ Repository [Upload / Approved URL]     Snapshot [pending]                    │
│ Authorization [✓]                                                          │
│ Adapter [C/C++] Build [cmake ...] Tests [ctest ...]                         │
│ Network [Denied] CPU [8] RAM [16 GB] Time [90m]                             │
│ Lightweight GPU [30m] Heavy escalation [Enabled, max 20m]                   │
│ [Run Preflight]                                            [Start Mission]   │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 2. Live Brahmadatta Command Center

```text
┌ Identity / status / mission time / active repo / threat / UTC ──────────────┐
├ Repository & static ───┬──────────── BRAHMADATTA CORE ─────────┬ Queue ─────┤
│ baseline               │       INGEST • ANALYZE • CORRELATE     │ findings   │
│ findings               │       STRESS TEST • PATCH • VERIFY     │ fuzzing    │
│ dependencies           │       central state and progress       │ patches    │
├ Git bisect ────────────┼ Alerts ──────────┬ Rented GPU health ──┼ Tests ─────┤
│ commit timeline        │ operator actions │ lease / VRAM / util  │ pass/fail  │
├ secure session / command palette / logs / artifact vault / safe cancel ─────┤
└──────────────────────────────────────────────────────────────────────────────┘
```

## 3. Finding Drawer

```text
CVE/Rule • Severity • Confirmed by • Source location
Reproducer | Sanitizer trace | Code context | Git origin
Routing: Tier 2 because localized in one function
[Open Patch Attempt] [Export Finding]
```

## 4. Patch and Verification

```text
Unified Diff                  Verification Matrix
+ bounds check                Compile       PASS
+ length validation           Reproducer    PASS: no crash
Changed lines: 8              Regression    PASS
Restricted files: none        Static delta  PASS
Model tier: Lightweight       Renewed fuzz  PASS
                              FINAL: VERIFIED
```

## 5. Presentation Mode

```text
[Large Brahmadatta Core]
Current phase • confirmed evidence • first bad commit • patch • final verdict
Resource efficiency: CPU stages / GPU escalation / lease teardown
```

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
