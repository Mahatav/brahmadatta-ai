"""Failure types for the C/C++ adapter.

Craft rule 5 from `.claude/agents/compiler-toolchain-engineer.md`: *"Fail loudly and
specifically. 'Build failed' is useless. Which target, which step, which command, which
exit code, which first error line."*

That sentence is the entire reason this module exists as a type rather than a string. A
`str` message can be assembled without the caller ever having the exit code to hand;
`StepFailure` cannot be constructed without one. The five fields in #16's acceptance
criterion are five required constructor arguments, so an incomplete failure report is a
`TypeError` at the raise site rather than a vague line in a log at 2am.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "AdapterError",
    "BuildStep",
    "StepFailure",
    "ToolchainError",
    "UnpinnedToolchain",
    "first_error_line",
]


class BuildStep(StrEnum):
    """The pipeline stage a failure came out of. Named, not free text, so a downstream
    consumer can branch on it without matching English."""

    DETECT = "DETECT"
    PROBE_TOOLCHAIN = "PROBE_TOOLCHAIN"
    CONFIGURE = "CONFIGURE"
    BUILD = "BUILD"
    TEST_ENUMERATE = "TEST_ENUMERATE"
    TEST_RUN = "TEST_RUN"
    TEST_PARSE = "TEST_PARSE"


class AdapterError(Exception):
    """Base for everything this package raises deliberately."""


class ToolchainError(AdapterError):
    """A required tool is missing, or its version could not be established."""


class UnpinnedToolchain(AdapterError):
    """A container image was named by a mutable tag rather than a digest.

    Hard rule from the role file: *"Never pin to a floating tag (`latest`, `main`) where a
    digest or version will do."* Enforced in `adapters/cpp/toolchain.py`, demonstrated by
    `test_toolchain.py::test_a_floating_tag_is_rejected`.
    """


@dataclass(frozen=True, slots=True)
class StepFailure(AdapterError):
    """A specific, reportable failure of one pipeline step.

    Every field named in #16's fourth acceptance criterion is required:

    ==================  ============================================================
    acceptance wording  field
    ==================  ============================================================
    which target        :attr:`target`
    which step          :attr:`step`
    which command       :attr:`command`
    which exit code     :attr:`exit_code`
    the first error line :attr:`first_error`
    ==================  ============================================================

    :attr:`log_path` is not in the criterion but is carried anyway, because a report
    nobody can drill into is a report nobody trusts.
    """

    step: BuildStep
    target: str
    command: tuple[str, ...]
    exit_code: int
    first_error: str
    log_path: str | None = None
    timed_out: bool = False
    detail: str = ""
    #: Set when the step died on the jail's wall-clock timeout rather than its own exit.
    limits_applied: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.command:
            raise ValueError("StepFailure.command must name the command that was run")

    def __str__(self) -> str:
        shown = " ".join(self.command)
        reason = "timed out" if self.timed_out else f"exit {self.exit_code}"
        lines = [
            f"{self.step.value} failed for target '{self.target}' ({reason})",
            f"  command: {shown}",
            f"  first error: {self.first_error or '<no error line found in output>'}",
        ]
        if self.log_path:
            lines.append(f"  log: {self.log_path}")
        if self.detail:
            lines.append(f"  detail: {self.detail}")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, object]:
        """Structured form for the evidence record. No log blob."""
        return {
            "step": self.step.value,
            "target": self.target,
            "command": list(self.command),
            "exit_code": self.exit_code,
            "first_error": self.first_error,
            "log_path": self.log_path,
            "timed_out": self.timed_out,
            "detail": self.detail,
        }


#: Tokens that mark a line as the compiler/linker/CMake actually complaining, in rough
#: order of how specific they are. Deliberately conservative: a false negative gives an
#: empty `first_error` and the operator opens the log, while a false positive puts a
#: misleading sentence in an evidence report.
_ERROR_MARKERS: tuple[str, ...] = (
    "error:",
    "fatal error:",
    "CMake Error",
    "undefined reference",
    "Undefined symbols",
    "ld: symbol(s) not found",
    "No such file or directory",
    "Error 1",
    "Permission denied",
    "command not found",
)


def first_error_line(*streams: str, limit: int = 400) -> str:
    """The first line across ``streams`` that looks like a real error.

    Scans stderr-then-stdout in the order given. Falls back to the last non-empty line of
    the first stream that has one, because a build system that dies without an
    `error:` marker still leaves its complaint at the bottom of the log.
    """
    for stream in streams:
        for raw in stream.splitlines():
            line = raw.strip()
            if line and any(marker in line for marker in _ERROR_MARKERS):
                return line[:limit]
    for stream in streams:
        tail = [raw.strip() for raw in stream.splitlines() if raw.strip()]
        if tail:
            return tail[-1][:limit]
    return ""
