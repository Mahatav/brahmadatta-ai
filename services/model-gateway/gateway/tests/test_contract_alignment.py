"""The gateway's provenance and the control API's `ModelProvenance` must stay aligned.

They are not shared by import and must not become so:
`tests/architecture/test_import_direction.py` (C5) bans the ASGI process from importing
`gateway`, and the reason is good — an inference client inside the request path is an
inference client in the process holding operator credentials and repository snapshots.

The cost of that boundary is two definitions of the same three fields, which is a drift
risk. This module is what pays for it: the gateway's `to_contract_dict()` is fed to the
control API's real `ModelProvenance` and has to validate. If the contract agent renames a
field or tightens a pattern, this fails here rather than at the seam on D6.

**Reading the contract is the coordination mechanism.** Nothing in this package writes to
`apps/control-api/`.

Skips cleanly when the control API or its dependencies are absent, and `-rs` in CI prints
the reason, so a silently-skipping test is visible in the log rather than passing as a dot.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway.provenance import ResponseProvenance, ResponseSource

REPO_ROOT = Path(__file__).resolve().parents[4]
CONTROL_API = REPO_ROOT / "apps" / "control-api"


def _model_provenance():
    """Import the control API's `ModelProvenance` without booting a Django project.

    `contracts.schemas.evidence` pulls in django-ninja, which reads Django settings at
    import time. A minimal `settings.configure()` is enough — no database, no apps, no
    `manage.py` — and it keeps this test runnable from `services/model-gateway/` on its
    own, which is where it belongs.
    """
    if not (CONTROL_API / "contracts" / "schemas" / "evidence.py").is_file():
        pytest.skip("apps/control-api is not present")
    if str(CONTROL_API) not in sys.path:
        sys.path.insert(0, str(CONTROL_API))

    try:
        from django.conf import settings as django_settings

        if not django_settings.configured:
            django_settings.configure(
                DEBUG=False,
                SECRET_KEY="gateway-contract-alignment-test-not-a-real-secret",  # noqa: S106
                INSTALLED_APPS=[],
                DATABASES={},
                USE_TZ=True,
            )
    except Exception as exc:
        pytest.skip(f"Django is not importable here: {exc}")

    try:
        from contracts.schemas.evidence import ModelProvenance
    except Exception as exc:
        pytest.skip(f"cannot import the control API contract here: {exc}")
    return ModelProvenance


REPLAYED = ResponseProvenance(
    source=ResponseSource.RECORDED_TRANSCRIPT,
    model_name="qwen2.5-coder-1.5b-instruct-q4_k_m",
    model_revision="q4_k_m",
    model_artifact_sha256="b" * 64,
    served_from="http://127.0.0.1:8080/v1",
    prompt_sha256="a" * 64,
    context_bytes=4096,
    confidence=0.61,
    generated_at=datetime(2026, 8, 13, tzinfo=UTC),
    replayed_from_transcript=f"{'d' * 64}.json",
    captured_at=datetime(2026, 8, 6, 21, 45, tzinfo=UTC),
    transcript_sha256="d" * 64,
)

LIVE = ResponseProvenance(
    source=ResponseSource.LIVE_INFERENCE,
    model_name="qwen2.5-coder-1.5b-instruct-q4_k_m",
    served_from="http://127.0.0.1:8080/v1",
    prompt_sha256="a" * 64,
    generated_at=datetime(2026, 8, 13, tzinfo=UTC),
)


@pytest.mark.parametrize("provenance", [LIVE, REPLAYED], ids=["live", "replayed"])
def test_the_gateway_record_validates_against_the_real_contract(
    provenance: ResponseProvenance,
) -> None:
    ModelProvenance = _model_provenance()
    contract = ModelProvenance.model_validate(provenance.to_contract_dict())

    assert contract.replayed_from_transcript == provenance.replayed_from_transcript
    assert contract.transcript_sha256 == provenance.transcript_sha256
    assert contract.is_replayed is provenance.is_replayed


def test_the_contract_still_carries_the_three_replay_fields() -> None:
    """D-020's schema addition. If these move, the gateway's mapping is wrong."""
    ModelProvenance = _model_provenance()
    fields = set(ModelProvenance.model_fields)
    assert {"replayed_from_transcript", "captured_at", "transcript_sha256"} <= fields


def test_the_contract_rejects_a_half_declared_replay() -> None:
    """The gateway's validator and the contract's must agree on what is inadmissible.

    A record that is partly a replay is the shape that lets a replayed response be read as
    a live one, and both sides refuse it.
    """
    ModelProvenance = _model_provenance()
    half = REPLAYED.to_contract_dict() | {"captured_at": None}
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
        ModelProvenance.model_validate(half)


def test_a_gateway_record_never_relies_on_the_contract_default() -> None:
    """BUG-007 mitigation, asserted against the real contract.

    `ModelProvenance`'s replay fields default to the *stronger* claim (D-049 Part 1, open
    on #6). A gateway record states all three explicitly, so what the contract defaults to
    cannot change what a gateway-produced record says. This does not fix BUG-007 for
    records built anywhere else, and it is not claimed to.
    """
    ModelProvenance = _model_provenance()
    payload = LIVE.to_contract_dict()
    assert set(payload) >= {"replayed_from_transcript", "captured_at", "transcript_sha256"}

    contract = ModelProvenance.model_validate(payload)
    assert contract.is_replayed is False
    assert contract.replayed_from_transcript is None
