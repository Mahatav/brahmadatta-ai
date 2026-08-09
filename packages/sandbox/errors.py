"""Failures a jailed run can produce.

Each one maps to an `ErrorCode` the contract already has, so the orchestrator can turn a
jail failure into a mission event without inventing vocabulary. The mapping is explicit
rather than derived, because a wrong guess here shows up in the operator's face as the
wrong reason for a dead mission.
"""

from __future__ import annotations

from enum import StrEnum


class LimitKind(StrEnum):
    """Which limit stopped the run. `NONE` means it finished on its own terms."""

    NONE = "NONE"
    CPU = "CPU"
    MEMORY = "MEMORY"
    WALL_CLOCK = "WALL_CLOCK"
    FILE_SIZE = "FILE_SIZE"
    OUTPUT = "OUTPUT"


class JailError(Exception):
    """Base for everything this package raises."""

    #: `contracts.enums.ErrorCode` member name. Kept as a string so this package does not
    #: import the Django app.
    error_code: str = "INTERNAL_ERROR"


class PathEscapeError(JailError):
    """A path argument pointed outside the jail root.

    Raised before the command runs. This is a refusal to *construct* an escaping
    command; it is not a claim that a running process cannot read outside the jail. It
    absolutely can. See the README.
    """

    error_code = "SANDBOX_POLICY_VIOLATION"


class JailUnavailableError(JailError):
    """The jail could not be created or its root disappeared under it."""

    error_code = "SANDBOX_UNAVAILABLE"


class ContainerUnavailableError(JailError):
    """`packages.sandbox.container`: the container runtime is missing, the daemon did
    not respond, a container failed to start, or the caller tried to use a sandbox
    that was already closed or cancelled."""

    error_code = "SANDBOX_UNAVAILABLE"


class LimitExceededError(JailError):
    """A resource limit stopped the command. Always carries which one."""

    error_code = "JOB_TIMED_OUT"

    def __init__(self, kind: LimitKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class WallClockExceededError(LimitExceededError):
    error_code = "JOB_TIMED_OUT"

    def __init__(self, seconds: float) -> None:
        super().__init__(
            LimitKind.WALL_CLOCK,
            f"command exceeded its {seconds:g}s wall-clock budget and its process group "
            f"was killed",
        )


class CpuExceededError(LimitExceededError):
    error_code = "JOB_TIMED_OUT"

    def __init__(self, seconds: int) -> None:
        super().__init__(
            LimitKind.CPU,
            f"command exceeded its {seconds}s CPU budget (RLIMIT_CPU, SIGXCPU)",
        )


class MemoryExceededError(LimitExceededError):
    error_code = "SANDBOX_POLICY_VIOLATION"

    def __init__(self, limit_bytes: int, detail: str) -> None:
        super().__init__(
            LimitKind.MEMORY,
            f"command hit its {limit_bytes // (1024 * 1024)} MiB address-space limit: "
            f"{detail}",
        )


class FileSizeExceededError(LimitExceededError):
    """A single file the command wrote grew past `RLIMIT_FSIZE` (SEC-35).

    Bounds one file, not the jail's aggregate disk usage — several files that each stay
    under the limit are not caught by this, or by anything else here. See
    `JailPolicy.max_file_bytes` and `packages/sandbox/README.md`.
    """

    error_code = "SANDBOX_POLICY_VIOLATION"

    def __init__(self, limit_bytes: int) -> None:
        super().__init__(
            LimitKind.FILE_SIZE,
            f"command tried to write a file past its {limit_bytes // (1024 * 1024)} "
            f"MiB per-file limit (RLIMIT_FSIZE, SIGXFSZ)",
        )


class CancelledError(JailError):
    """`Jail.cancel()` was called, or the context exited while a command was running."""

    error_code = "SAFE_CANCELLATION_IN_PROGRESS"
