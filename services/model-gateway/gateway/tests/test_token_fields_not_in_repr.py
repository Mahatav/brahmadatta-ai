"""#224: `GatewaySettings.model_host_bearer_token` and
`OllamaCodeLlamaBackend.bearer_token` are frozen dataclass fields carrying a live
bearer token. Neither is exercised by a real `repr()`/`str()`/log call path today (a
prior security review confirmed that, see the issue), but with no `field(repr=False)`
guard a future stray debug log or exception handler that stringifies either object
would print the token in cleartext with nothing stopping it.

These tests assert the guard is actually in place: the token string must not appear
in `repr()`/`str()` of either object, while another, non-secret field on the same
object must still appear -- so a passing test proves the token field specifically is
hidden, not that `repr()` is broken/empty for the whole object.
"""

from __future__ import annotations

from gateway.ollama import OllamaCodeLlamaBackend
from gateway.settings import GatewayMode, GatewaySettings

REALISTIC_TOKEN = "sk-live-9f3a1c7e4b2d4f6a8c0e2b4d6f8a0c2e"  # noqa: S105 -- test fixture, not a real credential


def test_gateway_settings_repr_hides_bearer_token_but_shows_other_fields() -> None:
    settings = GatewaySettings(
        mode=GatewayMode.LIVE,
        endpoint="http://model-host:11434",
        model_host_bearer_token=REALISTIC_TOKEN,
    )

    rendered_repr = repr(settings)
    rendered_str = str(settings)

    assert REALISTIC_TOKEN not in rendered_repr
    assert REALISTIC_TOKEN not in rendered_str
    # The field is hidden, not the whole object: other fields must still render.
    assert "http://model-host:11434" in rendered_repr
    assert GatewayMode.LIVE.value in rendered_repr or "LIVE" in rendered_repr


def test_ollama_backend_repr_hides_bearer_token_but_shows_other_fields() -> None:
    backend = OllamaCodeLlamaBackend(
        endpoint="http://model-host:11434/api",
        bearer_token=REALISTIC_TOKEN,
    )

    rendered_repr = repr(backend)
    rendered_str = str(backend)

    assert REALISTIC_TOKEN not in rendered_repr
    assert REALISTIC_TOKEN not in rendered_str
    # The field is hidden, not the whole object: other fields must still render.
    assert "http://model-host:11434/api" in rendered_repr
    assert backend.model_name in rendered_repr
