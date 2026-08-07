"""Django system checks.

These run on `manage.py check`, `manage.py runserver` and ASGI startup. An `Error`
(as opposed to a `Warning`) stops the process, which is the point: two of these
guard product rules that must not be violable by a stray environment variable.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, Warning, register

from contracts.errors import ExternalInferenceBlockedError
from contracts.model_policy import assert_local_inference_endpoint

MODEL_ENDPOINT_CHECK_ID = "brahmadatta.E001"
ADMIN_CHECK_ID = "brahmadatta.E002"
TOKEN_CHECK_ID = "brahmadatta.W003"
DEBUG_CHECK_ID = "brahmadatta.E004"


@register()
def check_model_endpoints(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """No configured inference endpoint may be a hosted third party."""
    messages: list[CheckMessage] = []
    for name, url in getattr(settings, "MODEL_ENDPOINTS", {}).items():
        if not url:
            continue
        try:
            assert_local_inference_endpoint(name, url)
        except ExternalInferenceBlockedError as exc:
            messages.append(
                Error(
                    str(exc),
                    hint=(
                        "Set this to a loopback, private-range, or *.internal host "
                        "serving the model yourself. See CLAUDE.md, 'Repository "
                        "content is never sent to an external inference API'."
                    ),
                    id=MODEL_ENDPOINT_CHECK_ID,
                )
            )
    return messages


@register()
def check_admin_disabled_in_finale(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """The finale profile must not expose the Django admin."""
    if getattr(settings, "APP_ENV", "") != "finale":
        return []
    if getattr(settings, "ADMIN_ENABLED", False) or "django.contrib.admin" in settings.INSTALLED_APPS:
        return [
            Error(
                "Django admin is enabled while APP_ENV=finale.",
                hint="Run the finale with DJANGO_SETTINGS_MODULE=config.settings.finale.",
                id=ADMIN_CHECK_ID,
            )
        ]
    return []


@register()
def check_operator_tokens(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """Tokens must be absent (API fails closed) or long enough to be worth having."""
    messages: list[CheckMessage] = []
    minimum = getattr(settings, "CONTROL_API_MIN_TOKEN_LENGTH", 32)
    for role, token in getattr(settings, "CONTROL_API_TOKENS", {}).items():
        if len(token) < minimum:
            messages.append(
                Warning(
                    f"Bearer token for role {role!r} is shorter than {minimum} "
                    f"characters.",
                    hint="Generate one with `python -c \"import secrets;"
                    "print(secrets.token_urlsafe(48))\"`.",
                    id=TOKEN_CHECK_ID,
                )
            )
    if not getattr(settings, "CONTROL_API_TOKENS", {}):
        messages.append(
            Warning(
                "No control API bearer tokens are configured; every authenticated "
                "endpoint will reject every request.",
                hint="Set CONTROL_API_OPERATOR_TOKEN. See .env.example.",
                id=TOKEN_CHECK_ID,
            )
        )
    return messages


@register()
def check_debug_off_in_finale(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    if getattr(settings, "APP_ENV", "") == "finale" and settings.DEBUG:
        return [
            Error(
                "DEBUG is on while APP_ENV=finale.",
                hint="Tracebacks would be served to the browser during the demo.",
                id=DEBUG_CHECK_ID,
            )
        ]
    return []
