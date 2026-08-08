"""Limits a jailed command runs under.

`SANDBOX_POLICY` in `apps/control-api/config/settings/base.py` already carries the same
shape for both halves of the isolation story, so `JailPolicy.from_settings` maps it
rather than inventing a second vocabulary. The `runtime` and `network` keys are the
container half (#15) and are deliberately not consumed here — see `errors.py` and the
README for why a subprocess jail cannot honour a network policy at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MIB = 1024 * 1024

#: Environment variables a jailed command inherits. Everything else is dropped, so a
#: credential in the orchestrator's environment cannot reach a build script by accident.
#: `PATH` is here because a build needs a compiler; that is also the single biggest hole
#: in this design, and the README says so.
DEFAULT_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TERM",
    "CC",
    "CXX",
    "CMAKE_BUILD_PARALLEL_LEVEL",
    "MAKEFLAGS",
)


@dataclass(frozen=True)
class JailPolicy:
    """What a single jailed command is allowed to consume.

    Defaults are sized for the demo target's build and test run, not for a fuzzing
    campaign. `docs/09-company/03-seven-day-plan.md` budgets the D3 baseline in minutes;
    900 wall-clock seconds is generous against a run measured at roughly three.
    """

    cpu_seconds: int = 300
    """RLIMIT_CPU, in CPU-seconds. Per process, not per process group — see README."""

    memory_bytes: int = 2048 * MIB
    """RLIMIT_AS, the address-space ceiling. Per process. Enforcement is
    platform-dependent; `jail.probe_limits()` reports what this kernel actually does."""

    wall_clock_seconds: float = 900.0
    """Hard timeout. Enforced by the parent, not the kernel, and it is the only limit
    here that applies to the whole process group."""

    max_output_bytes: int = 4 * MIB
    """How much stdout/stderr is kept. Output beyond this is dropped, not buffered."""

    max_file_bytes: int = 512 * MIB
    """RLIMIT_FSIZE. Bounds the size any *single* file the command writes may grow to —
    a runaway log or one pathological build product. Sized to leave a normal build's
    object files well clear.

    SEC-36: this is not aggregate disk protection. Twenty files at 400 MiB each would
    all individually stay under this limit and still fill a disk this jail leaves
    entirely unguarded against; nothing here sums file sizes across a run. See
    `packages/sandbox/README.md` and
    `test_file_size_limit_bounds_one_file_not_aggregate_usage`.
    """

    max_processes: int = 512
    """RLIMIT_NPROC. A brake on fork bombs, not a defence against one — the limit is
    per-user on most kernels, so it is shared with everything else the operator runs."""

    kill_grace_seconds: float = 5.0
    """Between SIGTERM and SIGKILL to the process group."""

    env_allowlist: tuple[str, ...] = DEFAULT_ENV_ALLOWLIST

    def __post_init__(self) -> None:
        if self.cpu_seconds < 1:
            raise ValueError("cpu_seconds must be at least 1")
        if self.memory_bytes < 16 * MIB:
            raise ValueError("memory_bytes below 16 MiB cannot start a compiler")
        if self.wall_clock_seconds <= 0:
            raise ValueError("wall_clock_seconds must be positive")
        if self.max_output_bytes < 1024:
            raise ValueError("max_output_bytes must be at least 1 KiB")
        if self.kill_grace_seconds < 0:
            raise ValueError("kill_grace_seconds cannot be negative")

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any], **overrides: Any) -> JailPolicy:
        """Build from Django's `SANDBOX_POLICY`.

        `runtime` and `network` are ignored on purpose. A subprocess jail has no network
        namespace, so consuming `network: deny` here would silently claim an isolation
        property that is not delivered.
        """
        values: dict[str, Any] = {}
        if "cpu_limit" in settings:
            # SANDBOX_CPU_LIMIT is a core count in the container half. As a CPU-seconds
            # budget that is meaningless, so it scales the wall clock instead.
            values["cpu_seconds"] = max(
                1, int(settings["cpu_limit"]) * int(settings.get("max_seconds", 900))
            )
        if "memory_mb" in settings:
            values["memory_bytes"] = int(settings["memory_mb"]) * MIB
        if "max_seconds" in settings:
            values["wall_clock_seconds"] = float(settings["max_seconds"])
        values.update(overrides)
        return cls(**values)
