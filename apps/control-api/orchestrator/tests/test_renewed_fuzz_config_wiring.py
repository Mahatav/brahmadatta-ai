"""#40 — `orchestrator.verify_dispatch._renewed_fuzz_config_for` and its wiring into
`_verify_executor`'s call to `run_verification`.

`orchestrator/tests/test_renewed_fuzz_gate.py` covers the gate logic itself
(`orchestrator/verification.py`); this file covers the one thing that lives in
`verify_dispatch.py`: building a real `RenewedFuzzConfig` from Django settings and the
mission's own `MissionPolicy`, the same way `workers/fuzzing/dispatch.py::
_container_policy` does for the original discovery campaign.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from contracts.enums import MissionState
from missions.models import Mission
from orchestrator import transitions
from orchestrator.tests.conftest import CANDIDATE_A, NOW, TRACE, gate_matrix, walk_to
from orchestrator.verification import RenewedFuzzConfig
from orchestrator.verify_dispatch import _renewed_fuzz_config_for, _verify_executor
from orchestrator.tests.test_verify_dispatch import (
    _accepted_candidate,
    _ctx,
    _extend_authorization,
    _job,
)

pytestmark = pytest.mark.django_db(transaction=True)


def test_no_sandbox_image_configured_yields_a_disabled_config(mission: Mission):
    with override_settings(SANDBOX_FUZZ_IMAGE=""):
        config = _renewed_fuzz_config_for(mission)

    assert config.container_policy is None


def test_renewed_fuzz_seconds_zero_disables_even_with_an_image_configured(mission: Mission):
    mission.policy = {**mission.policy, "renewed_fuzz_seconds": 0}
    mission.save(update_fields=["policy"])

    with override_settings(SANDBOX_FUZZ_IMAGE="fuzz-toolchain@sha256:" + "1" * 64):
        config = _renewed_fuzz_config_for(mission)

    assert config.container_policy is None
    assert config.budget_seconds == 0


def test_a_configured_image_and_nonzero_budget_produces_a_real_container_policy(mission: Mission):
    mission.policy = {**mission.policy, "renewed_fuzz_seconds": 45}
    mission.save(update_fields=["policy"])
    image = "fuzz-toolchain@sha256:" + "2" * 64

    with override_settings(SANDBOX_FUZZ_IMAGE=image):
        config = _renewed_fuzz_config_for(mission)

    assert config.container_policy is not None
    assert config.container_policy.image == image
    assert config.budget_seconds == 45
    # Sized generously above the fuzz budget itself, same reasoning as
    # workers/fuzzing/dispatch.py's own wall-clock buffer.
    assert config.container_policy.wall_clock_seconds > 45
    assert str(mission.id) in config.mission_ref


def test_renewed_fuzz_seconds_defaults_to_120_when_unset_in_policy(mission: Mission):
    """`MissionPolicy.renewed_fuzz_seconds`'s own schema default — proven end to end
    through a mission whose stored policy dict never mentions the field at all (the
    real shape every mission created before #40 has)."""
    assert "renewed_fuzz_seconds" not in mission.policy

    with override_settings(SANDBOX_FUZZ_IMAGE="fuzz-toolchain@sha256:" + "3" * 64):
        config = _renewed_fuzz_config_for(mission)

    assert config.budget_seconds == 120


def test_verify_executor_forwards_a_renewed_fuzz_config_to_run_verification(
    mission, finding, tmp_path, monkeypatch
):
    """The one integration point: `_verify_executor` must actually pass the built
    `RenewedFuzzConfig` through to `run_verification`, not merely be capable of one."""
    walk_to(mission, MissionState.PATCH)
    candidate = _accepted_candidate(mission, finding, CANDIDATE_A.read_text())
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    _extend_authorization(mission)

    seen = {}

    def _capture(worktree, diff, reproducer, baseline, **kwargs):
        seen["renewed_fuzz"] = kwargs.get("renewed_fuzz")
        return gate_matrix()

    monkeypatch.setattr("orchestrator.verify_dispatch.run_verification", _capture)

    with override_settings(SANDBOX_FUZZ_IMAGE="fuzz-toolchain@sha256:" + "4" * 64):
        job = _job(mission, patch_id=candidate.id)
        result = _verify_executor(_ctx(job, mission, tmp_path))

    from orchestrator.executors import JobOutcome

    assert result.outcome is JobOutcome.SUCCEEDED, result.detail
    assert isinstance(seen["renewed_fuzz"], RenewedFuzzConfig)
    assert seen["renewed_fuzz"].container_policy is not None
