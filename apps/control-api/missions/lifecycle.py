"""The mission lifecycle write gate (SEC-16).

## What this closes, and why a convention was not enough

`orchestrator.transitions.transition` is the only place that may move a mission's
lifecycle fields, because it is the only place that takes `SELECT … FOR UPDATE` on the
mission row and loads the mission's **complete** verification set before deciding. That
completeness is what closes BUG-004(c), and it is not checkable from inside the guard —
see `contracts/state_machine.py`'s module docstring.

Until this module existed, "only the orchestrator writes `Mission.state`" was a
convention defended by two structural tests over `transition`'s own signature and
loader. The security review defeated it in four lines without touching either:

    assert_transition(..., verifications=[the VERIFIED one only])   # guard says yes
    mission.state = "VERIFIED"; mission.save()                      # nothing objects

and separately:

    Mission.objects.filter(pk=...).update(state="VERIFIED")         # CREATED -> VERIFIED

Both now raise. The gate is deliberately narrow: it covers the four fields that carry
rulings, and only those. Everything else on `Mission` — `name`, `policy`,
`repository_ref` — is ordinary data and writes normally, so this does not become the
kind of blanket guard people learn to route around.

## Why a context flag rather than call-stack inspection

Inspecting the caller's stack would be cheaper to write and would break the moment the
orchestrator grows a helper. The flag is set by `transition` itself, under the row lock,
for the duration of one transaction — so the permission is scoped to the operation that
earned it rather than to a module name.

It is per-thread. A second thread entering `transition` gets its own flag, and a thread
that never entered it cannot write lifecycle fields no matter what another thread is
doing.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

#: The mission fields the orchestrator owns. A write to any of these outside
#: `orchestrator.transitions.transition` (or, for the freeze column,
#: `orchestrator.candidates.record_verification`) is refused.
LIFECYCLE_FIELDS: frozenset[str] = frozenset(
    {"state", "paused_from", "verdict", "verification_started_at"}
)

_local = threading.local()


def lifecycle_write_permitted() -> bool:
    return getattr(_local, "permitted", 0) > 0


@contextmanager
def lifecycle_write() -> Iterator[None]:
    """Permit lifecycle writes on this thread for the duration of the block.

    Re-entrant by counter, because `record_verification` sets the freeze column inside
    its own transaction and `transition` may later be extended to do the same.
    """
    _local.permitted = getattr(_local, "permitted", 0) + 1
    try:
        yield
    finally:
        _local.permitted -= 1
