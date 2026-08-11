"""#38 — clean-worktree deterministic verification."""

from __future__ import annotations

from pathlib import Path
import inspect
import typing

from contracts.enums import GateStatus, PatchProvenance, Verdict
from contracts.verdict import GateMatrix, derive_verdict
from orchestrator.tests.conftest import CANDIDATE_A, CANDIDATE_B
from orchestrator.verification import (
    CommandResult,
    VerificationBaseline,
    run_verification,
)


DEMO_REPOSITORY = CANDIDATE_A.parents[1]
CRASH = DEMO_REPOSITORY / "crash" / "crash-literal-tab.bin"
BASELINE = VerificationBaseline(expected_regression_tests=8)


def test_run_verification_signature_is_provenance_blind():
    signature = inspect.signature(run_verification)

    assert list(signature.parameters) == [
        "worktree",
        "candidate_diff",
        "reproducer",
        "baseline",
        "runner",
    ]
    hints = typing.get_type_hints(run_verification)
    assert hints["return"] is GateMatrix

    forbidden = {"patch", "candidate", "provenance", "model", "confidence", "rationale"}
    for name, parameter in signature.parameters.items():
        if name == "candidate_diff":
            continue
        assert not any(token in name.lower() for token in forbidden)
        assert not any(token in str(parameter.annotation).lower() for token in forbidden)


def test_verifier_is_provenance_blind():
    """The same diff gets the same gates regardless of how evidence labels it."""

    # These are deliberately not passed to run_verification; the verifier has no slot
    # for them.
    model_recorded_as = PatchProvenance.MODEL_GENERATED
    operator_recorded_as = PatchProvenance.OPERATOR_SUPPLIED
    assert model_recorded_as is not operator_recorded_as

    model_run = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=ScriptedRunner(),
    )
    operator_run = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=ScriptedRunner(),
    )

    assert model_run.model_dump(mode="json") == operator_run.model_dump(mode="json")
    assert derive_verdict(model_run) is Verdict.VERIFIED


def test_verified_path_runs_in_a_fresh_worktree():
    runner = ScriptedRunner()

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=runner,
    )

    assert derive_verdict(gates) is Verdict.VERIFIED
    assert gates.compile.status is GateStatus.PASS
    assert gates.reproducer_eliminated.status is GateStatus.PASS
    assert gates.regression_preserved.status is GateStatus.PASS
    assert runner.cwd_seen
    assert all(cwd != DEMO_REPOSITORY for cwd in runner.cwd_seen)
    assert all(DEMO_REPOSITORY not in cwd.parents for cwd in runner.cwd_seen)
    assert runner.applied_diffs == [CANDIDATE_A.read_text()]


def test_reproducer_eliminated_but_regression_failed_is_rejected():
    runner = ScriptedRunner(
        regression=CommandResult(
            argv=("ctest",),
            returncode=8,
            stdout="88% tests passed, 1 tests failed out of 8\n"
            "The following tests FAILED:\n"
            "4 - test_tab_expansion (Failed)\n",
        )
    )

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_B.read_text(),
        CRASH,
        BASELINE,
        runner=runner,
    )

    assert gates.reproducer_eliminated.status is GateStatus.PASS
    assert gates.regression_preserved.status is GateStatus.FAIL
    assert "Regression suite failed" in gates.regression_preserved.detail
    assert derive_verdict(gates) is Verdict.REJECTED


def test_regression_coverage_drop_is_not_a_pass():
    runner = ScriptedRunner(
        regression=CommandResult(
            argv=("ctest",),
            returncode=0,
            stdout="100% tests passed, 0 tests failed out of 5\n",
        )
    )

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=runner,
    )

    assert gates.reproducer_eliminated.status is GateStatus.PASS
    assert gates.regression_preserved.status is GateStatus.FAIL
    assert "Regression coverage dropped" in gates.regression_preserved.detail
    assert derive_verdict(gates) is Verdict.REJECTED


def test_failed_compile_discloses_gates_that_did_not_run():
    runner = ScriptedRunner(build=CommandResult(argv=("cmake", "--build"), returncode=2))

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=runner,
    )

    assert gates.compile.status is GateStatus.FAIL
    assert gates.reproducer_eliminated.status is GateStatus.NOT_RUN
    assert gates.regression_preserved.status is GateStatus.NOT_RUN
    assert "build failed" in gates.reproducer_eliminated.detail
    assert derive_verdict(gates) is Verdict.REJECTED


class ScriptedRunner:
    def __init__(
        self,
        *,
        configure: CommandResult | None = None,
        build: CommandResult | None = None,
        replay: CommandResult | None = None,
        regression: CommandResult | None = None,
    ) -> None:
        self.configure = configure or CommandResult(argv=("cmake",), returncode=0)
        self.build = build or CommandResult(argv=("cmake", "--build"), returncode=0)
        self.replay = replay or CommandResult(argv=("pktcfg_replay",), returncode=0)
        self.regression = regression or CommandResult(
            argv=("ctest",),
            returncode=0,
            stdout="100% tests passed, 0 tests failed out of 8\n",
        )
        self.cwd_seen: list[Path] = []
        self.applied_diffs: list[str] = []

    def __call__(
        self,
        argv,
        cwd: Path,
        stdin: str | None,
        timeout: int,
    ) -> CommandResult:
        del timeout
        argv = tuple(argv)
        self.cwd_seen.append(cwd)

        if argv[:3] == ("git", "apply", "--whitespace=nowarn"):
            self.applied_diffs.append(stdin or "")
            return CommandResult(argv=argv, returncode=0)

        if argv[:4] == ("cmake", "-S", ".", "-B"):
            return _with_argv(self.configure, argv)

        if argv[:2] == ("cmake", "--build"):
            result = _with_argv(self.build, argv)
            if result.ok:
                build_dir = cwd / argv[2]
                build_dir.mkdir(parents=True, exist_ok=True)
                replay_binary = build_dir / "pktcfg_replay"
                replay_binary.write_text("#!/bin/sh\nexit 0\n")
                replay_binary.chmod(0o755)
            return result

        if Path(argv[0]).name == "pktcfg_replay":
            return _with_argv(self.replay, argv)

        if argv[0] == "ctest":
            return _with_argv(self.regression, argv)

        raise AssertionError(f"unexpected command: {argv}")


def _with_argv(result: CommandResult, argv: tuple[str, ...]) -> CommandResult:
    return CommandResult(
        argv=argv,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
