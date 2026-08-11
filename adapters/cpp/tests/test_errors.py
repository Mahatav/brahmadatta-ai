from __future__ import annotations

import pytest

from adapters.cpp.errors import BuildStep, StepFailure, first_error_line


def test_step_failure_requires_a_command() -> None:
    """Injected violation: construct a StepFailure with an empty command tuple — the
    dataclass must refuse it rather than let 'which command' silently be unanswerable."""
    with pytest.raises(ValueError, match="command"):
        StepFailure(
            step=BuildStep.BUILD,
            target="x",
            command=(),
            exit_code=1,
            first_error="boom",
        )


def test_step_failure_str_contains_every_acceptance_criterion_field() -> None:
    failure = StepFailure(
        step=BuildStep.CONFIGURE,
        target="pktcfg",
        command=("cmake", "-S", ".", "-B", "build"),
        exit_code=1,
        first_error="CMake Error at CMakeLists.txt:1: bad syntax",
        log_path="/tmp/configure.log",
    )
    text = str(failure)
    assert "CONFIGURE" in text
    assert "pktcfg" in text
    assert "cmake -S . -B build" in text
    assert "exit 1" in text
    assert "CMake Error" in text
    assert "/tmp/configure.log" in text


def test_step_failure_as_dict_is_structural_not_a_blob() -> None:
    failure = StepFailure(
        step=BuildStep.BUILD,
        target="pktcfg",
        command=("make",),
        exit_code=2,
        first_error="undefined reference to `foo'",
    )
    data = failure.as_dict()
    assert data["step"] == "BUILD"
    assert data["target"] == "pktcfg"
    assert data["command"] == ["make"]
    assert data["exit_code"] == 2
    assert data["first_error"] == "undefined reference to `foo'"


def test_first_error_line_finds_a_marker_not_just_the_last_line() -> None:
    stderr = "compiling foo.c\ncompiling bar.c\nfoo.c:12:5: error: use of undeclared identifier 'x'\nmake: *** [foo.o] Error 1"
    assert "error: use of undeclared identifier" in first_error_line(stderr)


def test_first_error_line_falls_back_to_last_nonempty_line() -> None:
    stderr = "some normal output\nwith no recognisable marker\n"
    assert first_error_line(stderr) == "with no recognisable marker"


def test_first_error_line_of_empty_streams_is_empty() -> None:
    assert first_error_line("", "") == ""


def test_first_error_line_checks_stderr_before_stdout() -> None:
    stdout = "note: informational, not the real problem"
    stderr = "error: the actual problem"
    assert first_error_line(stderr, stdout) == "error: the actual problem"
