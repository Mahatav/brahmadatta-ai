# Project Vision

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Version | 0.2 Competition MVP |
| Status | Working draft |
| Owner | TBD |
| Last updated | 2026-08-06 |

## Vision

Brahmadatta AI will demonstrate that autonomous vulnerability repair becomes more trustworthy and resource-efficient when deterministic evidence is gathered first, lightweight AI handles localized repairs, and heavy reasoning is reserved for confirmed complex cases.

## North-star demonstration

An authorized operator starts a mission from the Brahmadatta Command Center and receives a defensible evidence bundle containing:

- An immutable repository snapshot.
- A confirmed vulnerability or regression.
- A stable minimized reproducer.
- Relevant Git history and the suspected introducing commit.
- A minimal patch candidate.
- Before/after regression, static-analysis, and fuzzing results.
- Tool, model, prompt-schema, and resource-usage records.
- A final verdict of **Verified**, **Rejected**, or **Human Review Required**.

## Product principles

1. Evidence before intelligence.
2. Minimum necessary compute.
3. Fail closed when evidence is incomplete.
4. Prefer minimal diffs to broad refactors.
5. Verification is determined by tools, not model confidence.
6. Keep repository data inside team-controlled infrastructure.
7. Make every dashboard element operationally useful.
8. Preserve a credible path to future sovereign, air-gapped deployment.

## Competition promise

The system will not claim to find every vulnerability. It will prove one complete autonomous loop extremely well: discover, reproduce, locate, patch, and independently verify.

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
