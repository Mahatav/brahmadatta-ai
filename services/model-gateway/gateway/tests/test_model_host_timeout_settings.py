"""D-123 (.project/decisions.md): `MODEL_HOST_TIMEOUT_SECONDS` is the one source of
truth `gateway.settings.GatewaySettings.model_host_timeout_seconds` and
`infrastructure/compose/nginx/model-host-auth/templates/model-host-auth.conf.template`'s
`proxy_read_timeout`/`proxy_send_timeout` both derive from, replacing two
independently hardcoded `300s` literals that only matched by coincidence. These tests
cover the Python side of that fix: `from_environment()`'s parsing of the env var, and
the default it falls back to when the var is unset.

The nginx side (the template actually rendering the same value) is verified against
the real container's rendered config, not by a unit test — see this task's handoff
for the live verification steps.
"""

from __future__ import annotations

import pytest

from gateway.errors import GatewayConfigurationError
from gateway.settings import (
    DEFAULT_MODEL_HOST_TIMEOUT_SECONDS,
    GatewayMode,
    from_environment,
)


def test_unset_model_host_timeout_seconds_defaults_to_300() -> None:
    """Unchanged behavior: before this fix the hardcoded value was 300s in both the
    client and the nginx proxy, so an operator who has not touched `.env` yet must
    still get exactly 300."""
    settings = from_environment({"MODEL_GATEWAY_MODE": "replay"})

    assert settings.model_host_timeout_seconds == DEFAULT_MODEL_HOST_TIMEOUT_SECONDS
    assert DEFAULT_MODEL_HOST_TIMEOUT_SECONDS == 300.0


def test_blank_model_host_timeout_seconds_also_defaults_to_300() -> None:
    """A `.env` line present but empty (`MODEL_HOST_TIMEOUT_SECONDS=`) must behave
    the same as the variable being absent entirely, matching every other blank-means-
    default variable this settings module already parses (e.g. `MODEL_ENDPOINT`)."""
    settings = from_environment(
        {"MODEL_GATEWAY_MODE": "replay", "MODEL_HOST_TIMEOUT_SECONDS": "   "}
    )

    assert settings.model_host_timeout_seconds == 300.0


def test_model_host_timeout_seconds_is_read_from_the_environment() -> None:
    """The actual fix: an operator who raises this one variable changes the value
    `_build_live_backend` will pass to `OllamaCodeLlamaBackend(timeout_sec=...)` --
    the numeric value itself is deliberately not changed by this task (D-123), only
    the mechanism, so this asserts the plumbing works for an arbitrary value rather
    than asserting anything about what the "real" number should be."""
    settings = from_environment(
        {"MODEL_GATEWAY_MODE": "replay", "MODEL_HOST_TIMEOUT_SECONDS": "900"}
    )

    assert settings.model_host_timeout_seconds == 900.0


def test_non_numeric_model_host_timeout_seconds_is_a_configuration_error() -> None:
    with pytest.raises(GatewayConfigurationError, match="MODEL_HOST_TIMEOUT_SECONDS"):
        from_environment(
            {"MODEL_GATEWAY_MODE": "replay", "MODEL_HOST_TIMEOUT_SECONDS": "forever"}
        )


@pytest.mark.parametrize("bad_value", ["0", "-1", "-300"])
def test_non_positive_model_host_timeout_seconds_is_a_configuration_error(
    bad_value: str,
) -> None:
    """A non-positive timeout is not "no override", it is a nonsensical one -- this
    must fail loudly rather than silently produce a client that times out instantly
    or never."""
    with pytest.raises(GatewayConfigurationError, match="greater than zero"):
        from_environment(
            {"MODEL_GATEWAY_MODE": "replay", "MODEL_HOST_TIMEOUT_SECONDS": bad_value}
        )


def test_live_mode_also_picks_up_the_timeout_override() -> None:
    settings = from_environment(
        {
            "MODEL_GATEWAY_MODE": "live",
            "MODEL_ENDPOINT": "http://127.0.0.1:11434/api",
            "MODEL_RESOLVE_ENDPOINT": "false",
            "MODEL_HOST_TIMEOUT_SECONDS": "600",
        }
    )

    assert settings.mode is GatewayMode.LIVE
    assert settings.model_host_timeout_seconds == 600.0
