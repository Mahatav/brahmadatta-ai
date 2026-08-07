"""The frozen contract.

This package is the seam between the Command Center (Astro) and the pipeline. It
contains no I/O, no Django models and no business logic that can drift: enums, the
event envelope, request/response schemas, the mission state machine, the
authorization gate and the verdict derivation.

Three product rules are enforced here structurally rather than by convention:

1. `contracts.model_policy` — no inference endpoint may be a hosted third party.
2. `contracts.verdict`      — a verdict is derivable only from deterministic gates.
                              Model confidence is recordable and displayable and
                              cannot reach the derivation.
3. `contracts.state_machine`— no mission stage runs without an active authorization
                              record.
"""

default_app_config = "contracts.apps.ContractsConfig"
