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
    service_names = getattr(settings, "MODEL_SERVICE_NAMES", ())
    for name, url in getattr(settings, "MODEL_ENDPOINTS", {}).items():
        if not url:
            continue
        try:
            assert_local_inference_endpoint(name, url, service_names=service_names)
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


DATABASE_TLS_CHECK_ID = "brahmadatta.E005"

#: `sslmode` values that give an active man-in-the-middle nothing to work with. `require`
#: encrypts but does not authenticate the server; it is accepted as the floor because the
#: finale topology puts PostgreSQL on an `internal: true` network with no published port,
#: so reaching the MITM position already means being inside the boundary. `prefer` — the
#: libpq default — is NOT accepted: it falls back to plaintext without error.
_ACCEPTABLE_FINALE_SSLMODES: frozenset[str] = frozenset(
    {"require", "verify-ca", "verify-full"}
)


@register()
def check_database_tls_in_finale(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """The finale must not start on an unverified database connection.

    `config.env` now forwards `sslmode` to libpq and refuses to boot on a DSN parameter
    it does not understand. That closes the *silence*; it does not make anyone set the
    parameter. Without this check the finale still starts happily on a DSN with no
    `sslmode`, and libpq's default is `prefer` — attempt TLS, fall back to plaintext
    without error, never validate the certificate.

    An `Error` rather than a `Warning`, for the same reason `E001` is: the process
    stopping is the point. Scoped to `APP_ENV=finale` so development and the test suite
    run on SQLite and on a local PostgreSQL without ceremony.
    """
    if getattr(settings, "APP_ENV", "") != "finale":
        return []

    default = getattr(settings, "DATABASES", {}).get("default", {})
    engine = str(default.get("ENGINE", ""))
    if "postgresql" not in engine:
        return [
            Error(
                f"APP_ENV=finale is configured against {engine or 'no database'}; the "
                f"competition run uses PostgreSQL.",
                hint="Set DATABASE_URL to a postgresql:// DSN.",
                id=DATABASE_TLS_CHECK_ID,
            )
        ]

    sslmode = str(default.get("OPTIONS", {}).get("sslmode", ""))
    if sslmode not in _ACCEPTABLE_FINALE_SSLMODES:
        return [
            Error(
                f"APP_ENV=finale with database sslmode="
                f"{sslmode or 'unset (libpq defaults to prefer)'}. `prefer` silently "
                f"falls back to plaintext when the server declines TLS, so the "
                f"authorization statements and verification records this system exists "
                f"to protect would cross the wire unencrypted with nothing to observe.",
                hint="Append ?sslmode=verify-full&sslrootcert=... to DATABASE_URL, or "
                "?sslmode=require at minimum.",
                id=DATABASE_TLS_CHECK_ID,
            )
        ]
    return []
