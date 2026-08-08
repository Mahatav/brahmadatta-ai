"""The explicit, pre-I/O authorization check.

`orchestrator.transitions.transition` already refuses a transition into a state that
needs authorization it does not have. But by the time `transition` runs at the end of
`authorization.service.create_mission_snapshot`, the request has already resolved a
path, opened a file and hashed its contents. Calling `require_active_authorization`
first — before any of that — means an unauthorized attempt is refused before the
mission's target is touched at all, not merely before the database row commits.

This is the second of the two sanctioned places this gate is enforced. The first is
`orchestrator.transitions.transition`, called at the end of the same request under the
same mission-row lock — belt and braces, and the two cannot disagree because they read
the same row through the same `orchestrator.repository` functions.
"""

from __future__ import annotations

from datetime import datetime

from contracts.enums import MissionStage
from contracts.state_machine import assert_stage_can_run
from missions.models import Mission
from orchestrator import repository


def require_active_authorization(
    mission: Mission, stage: MissionStage, now: datetime
) -> None:
    """Raise `contracts.errors.AuthorizationRequiredError` unless `stage` may run now.

    Caller must already hold the mission row lock (`select_for_update`), so the
    authorization and snapshot-binding state read here cannot change out from under
    the decision before the rest of the request runs in the same transaction.
    """
    authorization = repository.load_active_authorization(mission, now)
    snapshot_sha256 = repository.latest_snapshot_sha256(mission)
    assert_stage_can_run(stage, authorization, now, snapshot_sha256)
