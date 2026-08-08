"""Sandbox isolation for jailed command execution.

Two backends are planned. This package currently ships one:

* **subprocess jail** (#81, here) - working-directory jail, resource limits, hard
  timeout. Enough for a build and a test run. NOT enough for untrusted code.
* **rootless container** (#15, not built) - required before fuzzing (#28) runs on D4.

`jail.py` opens with what that distinction means in practice. Read it before using this
for anything.
"""

from services.sandbox.errors import (
    CancelledError,
    CpuExceededError,
    JailError,
    JailUnavailableError,
    LimitExceededError,
    LimitKind,
    MemoryExceededError,
    PathEscapeError,
    WallClockExceededError,
)
from services.sandbox.jail import ISOLATION_MODE, Jail, JailResult, probe_limits
from services.sandbox.policy import JailPolicy

__all__ = [
    "ISOLATION_MODE",
    "CancelledError",
    "CpuExceededError",
    "Jail",
    "JailError",
    "JailPolicy",
    "JailResult",
    "JailUnavailableError",
    "LimitExceededError",
    "LimitKind",
    "MemoryExceededError",
    "PathEscapeError",
    "WallClockExceededError",
    "probe_limits",
]
