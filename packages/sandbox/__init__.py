"""Sandbox isolation for jailed command execution.

Two backends, both built:

* **subprocess jail** (`jail.py`, #81) - working-directory jail, resource limits, hard
  timeout. Enough for a build and a test run. NOT enough for untrusted code.
* **rootful-daemon container, `--network none`** (`container.py`, #15) - D-024's
  isolation for untrusted target code and the fuzzer. `container_runner.py`
  (#181/SEC-57) adapts it to `Jail`'s own call surface so `adapters/cpp/*` and
  `orchestrator/verification.py` can drive either backend through the same call
  sites — see that module's docstring for BASELINE/VERIFY's own wiring.

`jail.py`/`container.py` each open with what their own isolation guarantees are and are
not. Read the one you are about to use before using it for anything.
"""

from packages.sandbox.container import ContainerJail, ContainerJailPolicy, ContainerJailResult
from packages.sandbox.container_runner import ContainerJailRunner
from packages.sandbox.errors import (
    CancelledError,
    ContainerUnavailableError,
    CpuExceededError,
    FileSizeExceededError,
    JailError,
    JailUnavailableError,
    LimitExceededError,
    LimitKind,
    MemoryExceededError,
    PathEscapeError,
    WallClockExceededError,
)
from packages.sandbox.jail import ISOLATION_MODE, Jail, JailResult, probe_limits
from packages.sandbox.policy import JailPolicy

__all__ = [
    "ISOLATION_MODE",
    "CancelledError",
    "ContainerJail",
    "ContainerJailPolicy",
    "ContainerJailResult",
    "ContainerJailRunner",
    "ContainerUnavailableError",
    "CpuExceededError",
    "FileSizeExceededError",
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
