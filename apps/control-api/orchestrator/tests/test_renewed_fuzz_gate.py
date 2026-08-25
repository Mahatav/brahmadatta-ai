"""#40 — the RENEWED_FUZZING optional gate ("how do you know the patch isn't just
overfit to one input").

Unit-level, mirroring `test_verification.py`'s own style: a `ScriptedRunner` drives the
compile/reproducer/regression side (unchanged by this feature) and an injected
`campaign_runner` drives the renewed-fuzz side, so every case here runs with no real
Docker daemon and no network. `orchestrator/tests/test_renewed_fuzz_gate_real_e2e.py`
is the companion opt-in test that drives a real libFuzzer campaign against a real
patched build, for both a genuinely correct patch and a deliberately overfit one.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from adapters.cpp.errors import BuildStep, StepFailure
from adapters.cpp.fuzzing import (
    FuzzFailure,
    FuzzToolchainRecord,
    LibFuzzerMetrics,
    LibFuzzerRunResult,
)
from contracts.enums import EvidenceSource, GateStatus, Verdict
from contracts.verdict import derive_verdict
from orchestrator.tests.conftest import CANDIDATE_A
from orchestrator.tests.test_verification import CRASH, DEMO_REPOSITORY, ScriptedRunner
from orchestrator.verification import (
    RenewedFuzzConfig,
    VerificationBaseline,
    run_verification,
)
from packages.sandbox.container import ContainerJailPolicy
from packages.sandbox.errors import ContainerUnavailableError

BASELINE = VerificationBaseline(expected_regression_tests=8)
_POLICY = ContainerJailPolicy(image="fuzz-toolchain@sha256:" + "0" * 64)


class _ScriptedCampaign:
    """Injectable stand-in for `adapters.cpp.fuzzing.run_libfuzzer_campaign`.

    Records every call's `source_dir`/kwargs so tests can assert the gate is driven
    against the *patched* worktree (never the caller's own `DEMO_REPOSITORY`), and can
    either return a scripted `LibFuzzerRunResult` or raise a scripted exception —
    covering both of `_run_renewed_fuzz`'s outcome shapes.
    """

    def __init__(self, *, result: LibFuzzerRunResult | None = None, raises: Exception | None = None) -> None:
        self._result = result
        self._raises = raises
        self.calls: list[dict[str, object]] = []

    def __call__(self, source_dir, policy, **kwargs) -> LibFuzzerRunResult:
        self.calls.append({"source_dir": Path(source_dir), "policy": policy, **kwargs})
        if self._raises is not None:
            raise self._raises
        assert self._result is not None
        return self._result


def _run_result(*, unique_crashes: int = 0, executions: int = 1000, failure=None) -> LibFuzzerRunResult:
    return LibFuzzerRunResult(
        harness="pktcfg_fuzz",
        engine="libFuzzer",
        runtime_seconds=12.5,
        metrics=LibFuzzerMetrics(
            executions=executions,
            crashes_found=unique_crashes,
            unique_crashes=unique_crashes,
            coverage=123,
            corpus_size=8,
        ),
        toolchain=FuzzToolchainRecord(
            image=_POLICY.image, isolation_mode="CONTAINER_NO_NETWORK", tools=()
        ),
        failure=failure,
    )


# --------------------------------------------------------------------------------
# Not configured — disclosed as NOT_RUN, never silently omitted, never blocks VERIFIED.
# --------------------------------------------------------------------------------


def test_renewed_fuzz_defaults_to_not_run_when_no_config_is_given():
    gates = run_verification(
        DEMO_REPOSITORY, CANDIDATE_A.read_text(), CRASH, BASELINE, runner=ScriptedRunner()
    )

    assert gates.renewed_fuzzing.status is GateStatus.NOT_RUN
    assert gates.renewed_fuzzing.evidence_source is EvidenceSource.REPLAYED_ARTIFACT
    assert "not requested" in gates.renewed_fuzzing.detail
    assert derive_verdict(gates) is Verdict.VERIFIED


def test_renewed_fuzz_is_not_run_when_no_sandbox_image_is_configured():
    config = RenewedFuzzConfig(container_policy=None)

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=ScriptedRunner(),
        renewed_fuzz=config,
    )

    assert gates.renewed_fuzzing.status is GateStatus.NOT_RUN
    assert "SANDBOX_FUZZ_IMAGE" in gates.renewed_fuzzing.detail
    assert derive_verdict(gates) is Verdict.VERIFIED


def _apply_always_fails(argv, cwd, stdin, timeout):
    from orchestrator.verification import CommandResult

    argv = tuple(argv)
    if argv[:2] == ("git", "apply"):
        return CommandResult(argv=argv, returncode=1, stderr="patch does not apply")
    raise AssertionError(f"unexpected command reached the runner: {argv}")


def test_renewed_fuzz_is_not_run_when_the_diff_never_applied():
    """Compile-gate early-return paths must say something specific, not the stale
    GateMatrix field default ("cut from the seven-day build") #40 made inaccurate."""
    campaign = _ScriptedCampaign(result=_run_result())
    config = RenewedFuzzConfig(container_policy=_POLICY, campaign_runner=campaign)

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=_apply_always_fails,
        renewed_fuzz=config,
    )

    assert gates.compile.status is GateStatus.FAIL
    assert gates.renewed_fuzzing.status is GateStatus.NOT_RUN
    assert "did not apply" in gates.renewed_fuzzing.detail
    assert campaign.calls == [], "the campaign must never run against an unapplied diff"


# --------------------------------------------------------------------------------
# The acceptance criteria, directly: PASS when clean, FAIL (and verdict flip) on a new
# crash, and the gate runs regardless of the CommandRunner's own compile/regression path.
# --------------------------------------------------------------------------------


def test_renewed_fuzz_passes_when_the_campaign_finds_no_new_crash():
    campaign = _ScriptedCampaign(result=_run_result(unique_crashes=0, executions=50_000))
    config = RenewedFuzzConfig(container_policy=_POLICY, budget_seconds=90, campaign_runner=campaign)

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=ScriptedRunner(),
        renewed_fuzz=config,
    )

    assert gates.renewed_fuzzing.status is GateStatus.PASS
    assert gates.renewed_fuzzing.evidence_source is EvidenceSource.TOOL_EXECUTION
    assert gates.renewed_fuzzing.tool == "libFuzzer"
    assert "no new crash" in gates.renewed_fuzzing.detail
    assert derive_verdict(gates) is Verdict.VERIFIED

    assert len(campaign.calls) == 1
    call = campaign.calls[0]
    assert call["budget_seconds"] == 90
    # The gate is driven against the patched *copy*, never the fixture's own tree.
    assert call["source_dir"] != DEMO_REPOSITORY
    assert DEMO_REPOSITORY not in call["source_dir"].parents


def test_renewed_fuzz_fail_on_a_new_crash_flips_the_verdict_away_from_verified():
    """The literal acceptance criterion: every required gate PASSes, and the mission
    would be VERIFIED without this gate — a new crash the renewed campaign finds is
    what turns that into REJECTED."""
    campaign = _ScriptedCampaign(result=_run_result(unique_crashes=1, executions=4_200))
    config = RenewedFuzzConfig(container_policy=_POLICY, campaign_runner=campaign)

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=ScriptedRunner(),
        renewed_fuzz=config,
    )

    assert gates.compile.status is GateStatus.PASS
    assert gates.reproducer_eliminated.status is GateStatus.PASS
    assert gates.regression_preserved.status is GateStatus.PASS
    assert gates.renewed_fuzzing.status is GateStatus.FAIL
    assert "1 new crash" in gates.renewed_fuzzing.detail
    assert derive_verdict(gates) is Verdict.REJECTED


def test_renewed_fuzz_runs_even_when_regression_already_failed():
    """Disclosure, not gated on the other gates' outcome (see `_run_renewed_fuzz`'s own
    docstring): the campaign still runs and is still reported, even though the mission
    is already REJECTED on the regression gate alone."""
    from orchestrator.tests.test_verification import CommandResult

    runner = ScriptedRunner(
        regression=CommandResult(
            argv=("ctest",),
            returncode=8,
            stdout="88% tests passed, 1 tests failed out of 8\n",
        )
    )
    campaign = _ScriptedCampaign(result=_run_result(unique_crashes=0))
    config = RenewedFuzzConfig(container_policy=_POLICY, campaign_runner=campaign)

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=runner,
        renewed_fuzz=config,
    )

    assert gates.regression_preserved.status is GateStatus.FAIL
    assert gates.renewed_fuzzing.status is GateStatus.PASS
    assert len(campaign.calls) == 1
    assert derive_verdict(gates) is Verdict.REJECTED


# --------------------------------------------------------------------------------
# Infrastructure faults degrade to a disclosed NOT_RUN, never to a silent PASS and
# never to a REJECT on their own (GateStatus.ERROR has no producer in this module).
# --------------------------------------------------------------------------------


def test_renewed_fuzz_harness_build_failure_is_not_run_not_failed():
    failure = FuzzFailure(
        step=BuildStep.CONFIGURE.value,
        command=("cmake",),
        exit_code=1,
        first_error="CMake Error: unknown option -DPKTCFG_FUZZ",
    )
    campaign = _ScriptedCampaign(result=_run_result(failure=failure))
    config = RenewedFuzzConfig(container_policy=_POLICY, campaign_runner=campaign)

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=ScriptedRunner(),
        renewed_fuzz=config,
    )

    assert gates.renewed_fuzzing.status is GateStatus.NOT_RUN
    assert "failed to build or run" in gates.renewed_fuzzing.detail
    assert derive_verdict(gates) is Verdict.VERIFIED


def test_renewed_fuzz_toolchain_step_failure_exception_is_not_run():
    exc = StepFailure(
        step=BuildStep.PROBE_TOOLCHAIN,
        target="libFuzzer",
        command=("clang", "--version"),
        exit_code=127,
        first_error="clang: command not found",
    )
    campaign = _ScriptedCampaign(raises=exc)
    config = RenewedFuzzConfig(container_policy=_POLICY, campaign_runner=campaign)

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=ScriptedRunner(),
        renewed_fuzz=config,
    )

    assert gates.renewed_fuzzing.status is GateStatus.NOT_RUN
    assert "could not be built or run" in gates.renewed_fuzzing.detail
    assert derive_verdict(gates) is Verdict.VERIFIED


def test_renewed_fuzz_sandbox_unavailable_is_not_run():
    campaign = _ScriptedCampaign(raises=ContainerUnavailableError("docker daemon unreachable"))
    config = RenewedFuzzConfig(container_policy=_POLICY, campaign_runner=campaign)

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=ScriptedRunner(),
        renewed_fuzz=config,
    )

    assert gates.renewed_fuzzing.status is GateStatus.NOT_RUN
    assert "sandbox was unavailable" in gates.renewed_fuzzing.detail
    assert derive_verdict(gates) is Verdict.VERIFIED


def test_renewed_fuzzing_never_produces_gate_status_error():
    """This module's own local convention (stated in its docstring): every gate here
    degrades to NOT_RUN, never ERROR. Exercised across every failure shape above."""
    scenarios = [
        RenewedFuzzConfig(container_policy=None),
        RenewedFuzzConfig(container_policy=_POLICY, campaign_runner=_ScriptedCampaign(raises=StepFailure(
            step=BuildStep.BUILD, target="pktcfg_fuzz", command=("cmake", "--build"),
            exit_code=2, first_error="undefined reference",
        ))),
        RenewedFuzzConfig(container_policy=_POLICY, campaign_runner=_ScriptedCampaign(
            raises=ContainerUnavailableError("no daemon")
        )),
    ]
    for config in scenarios:
        gates = run_verification(
            DEMO_REPOSITORY,
            CANDIDATE_A.read_text(),
            CRASH,
            BASELINE,
            runner=ScriptedRunner(),
            renewed_fuzz=config,
        )
        assert gates.renewed_fuzzing.status is not GateStatus.ERROR


# --------------------------------------------------------------------------------
# The parameter itself is provenance-blind, same as everything else in this module.
# --------------------------------------------------------------------------------


def test_renewed_fuzz_parameter_carries_no_confidence_or_provenance_field():
    forbidden = {"patch", "candidate", "provenance", "model", "confidence", "rationale"}
    fields = {f.name for f in RenewedFuzzConfig.__dataclass_fields__.values()}
    for name in fields:
        assert not any(token in name.lower() for token in forbidden), name


def test_run_verification_signature_includes_renewed_fuzz_keyword_only():
    signature = inspect.signature(run_verification)
    assert "renewed_fuzz" in signature.parameters
    assert signature.parameters["renewed_fuzz"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["renewed_fuzz"].default is None
