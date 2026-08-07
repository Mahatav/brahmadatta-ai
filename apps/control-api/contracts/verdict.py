"""Verdict derivation.

Product rule, repeated in every document in the pack: *a patch is never accepted on
model confidence alone*. This module makes that structurally true rather than a
comment someone has to remember:

* `derive_verdict` takes exactly one argument — a `GateMatrix`. There is no parameter
  a confidence value could be passed as.
* `GateResult` and `GateMatrix` forbid extra fields, so a caller cannot smuggle
  `confidence=0.98` through `**payload` and have it ride along in the record.
* A gate's outcome is a four-valued enum (`PASS`/`FAIL`/`NOT_RUN`/`ERROR`). There is
  no numeric field anywhere on the path from evidence to verdict, so there is nothing
  for a threshold to be compared against.
* `contracts.schemas.evidence.VerificationRecord` re-derives the verdict in a
  validator and refuses to serialize if the stored verdict disagrees with the gates.
  A record asserting `VERIFIED` over a failed regression gate cannot be constructed,
  let alone returned to the browser.

Model confidence still exists — it is recorded on `ModelProvenance` and displayed in
the patch panel, because hiding it would be its own kind of dishonesty. It simply has
no path into this function.
"""

from __future__ import annotations

from typing import Iterator, Sequence

from ninja import Schema
from pydantic import BaseModel, ConfigDict, Field

from contracts.enums import GateName, GateStatus, Verdict


class GateResult(Schema):
    """One deterministic gate's outcome, with the tool that produced it."""

    model_config = ConfigDict(extra="forbid")

    name: GateName
    status: GateStatus
    tool: str = Field(
        default="",
        max_length=120,
        description="Tool that produced this result, e.g. 'ctest 3.28.3'. Empty when NOT_RUN.",
    )
    detail: str = Field(
        default="",
        max_length=2000,
        description="User-safe summary. Never raw target output, never secrets.",
    )
    evidence_ref: str | None = Field(
        default=None,
        max_length=500,
        description="Opaque artifact pointer (artifact://...). Resolved through a "
        "signed short-lived link, never returned inline.",
    )

    @classmethod
    def not_run(cls, name: GateName, reason: str) -> "GateResult":
        return cls(name=name, status=GateStatus.NOT_RUN, detail=reason)


#: Gates that must PASS for a `VERIFIED` verdict. Non-negotiable set (P0-11).
REQUIRED_GATES: tuple[GateName, ...] = (
    GateName.COMPILE,
    GateName.REPRODUCER_ELIMINATED,
    GateName.REGRESSION_PRESERVED,
)

#: Gates that strengthen the verdict when they run and cannot be the sole basis for
#: one. Both are CUT for the seven-day build (P1-2, P1-3); they are declared so the
#: gate matrix in the evidence bundle discloses what did *not* run rather than hiding
#: it.
OPTIONAL_GATES: tuple[GateName, ...] = (
    GateName.STATIC_DELTA,
    GateName.RENEWED_FUZZING,
)

_CUT_REASON = "Not run: cut from the seven-day build (see docs/09-company/03-seven-day-plan.md)."


class GateMatrix(Schema):
    """The complete evidence basis for a verdict. Nothing else is consulted."""

    model_config = ConfigDict(extra="forbid")

    compile: GateResult
    reproducer_eliminated: GateResult
    regression_preserved: GateResult
    static_delta: GateResult = Field(
        default_factory=lambda: GateResult.not_run(GateName.STATIC_DELTA, _CUT_REASON)
    )
    renewed_fuzzing: GateResult = Field(
        default_factory=lambda: GateResult.not_run(GateName.RENEWED_FUZZING, _CUT_REASON)
    )

    def results(self) -> Iterator[GateResult]:
        yield self.compile
        yield self.reproducer_eliminated
        yield self.regression_preserved
        yield self.static_delta
        yield self.renewed_fuzzing

    def by_name(self, name: GateName) -> GateResult:
        for result in self.results():
            if result.name == name:
                return result
        raise KeyError(f"Gate {name} is not present in the matrix")


def derive_verdict(gates: GateMatrix) -> Verdict:
    """Deterministic gates in, verdict out. The only accepted argument is the matrix.

    * any required gate FAIL                 -> REJECTED
    * any required gate NOT_RUN or ERROR     -> HUMAN_REVIEW_REQUIRED
    * an optional gate that ran and FAILED   -> REJECTED
    * an optional gate that ERRORED          -> HUMAN_REVIEW_REQUIRED
    * otherwise                              -> VERIFIED
    """
    required = [gates.by_name(name) for name in REQUIRED_GATES]

    if any(result.status is GateStatus.FAIL for result in required):
        return Verdict.REJECTED
    if any(
        result.status in (GateStatus.NOT_RUN, GateStatus.ERROR) for result in required
    ):
        return Verdict.HUMAN_REVIEW_REQUIRED

    optional = [gates.by_name(name) for name in OPTIONAL_GATES]
    if any(result.status is GateStatus.FAIL for result in optional):
        return Verdict.REJECTED
    if any(result.status is GateStatus.ERROR for result in optional):
        return Verdict.HUMAN_REVIEW_REQUIRED

    return Verdict.VERIFIED


def derive_mission_verdict(verdicts: Sequence[Verdict]) -> Verdict:
    """Reduce a mission's per-candidate verdicts to the mission verdict.

    The demo runs **two** candidates through the identical pipeline and shows the
    results side by side — one `Verified`, one `Rejected`. That is the differentiator
    (P0 cut §3 steps 6 and 7, D6 gate), so the mission's terminal state is a function
    of the whole *set* of verification runs, not of whichever one finished last.

    The rule, stated explicitly so it cannot be assumed:

    * no verifications at all      -> `HUMAN_REVIEW_REQUIRED`. Nothing was proven.
    * any `HUMAN_REVIEW_REQUIRED`  -> `HUMAN_REVIEW_REQUIRED`. A gate that errored or
      did not run outranks a success elsewhere; a person looks before we claim anything.
    * at least one `VERIFIED`      -> `VERIFIED`. The mission's question is "does a
      repair that holds exist", and one that passed every deterministic gate answers it.
    * otherwise (all `REJECTED`)   -> `REJECTED`.

    A `VERIFIED` mission verdict therefore never means "every candidate passed", and
    the rejected candidates are not hidden by it: `MissionVerdictSummary` carries the
    per-candidate breakdown, and the evidence bundle carries every record in full.
    """
    verdicts = list(verdicts)
    if not verdicts:
        return Verdict.HUMAN_REVIEW_REQUIRED
    if any(verdict is Verdict.HUMAN_REVIEW_REQUIRED for verdict in verdicts):
        return Verdict.HUMAN_REVIEW_REQUIRED
    if any(verdict is Verdict.VERIFIED for verdict in verdicts):
        return Verdict.VERIFIED
    return Verdict.REJECTED


def iter_nested_field_names(model: type[BaseModel], _seen: set[type] | None = None) -> Iterator[str]:
    """Yield every field name reachable from `model`, recursively.

    Used by `contracts.tests.test_verdict` to assert that no field named after a
    confidence score exists anywhere on the verdict path.
    """
    seen = _seen if _seen is not None else set()
    if model in seen:
        return
    seen.add(model)

    for field_name, field in model.model_fields.items():
        yield field_name
        annotation = field.annotation
        for candidate in _unwrap(annotation):
            if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                yield from iter_nested_field_names(candidate, seen)


def _unwrap(annotation: object) -> Iterator[object]:
    """Yield the concrete types inside an annotation (Optional, list, union, ...)."""
    yield annotation
    for arg in getattr(annotation, "__args__", ()) or ():
        yield from _unwrap(arg)
