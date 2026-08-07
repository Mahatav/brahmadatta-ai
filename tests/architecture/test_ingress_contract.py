"""The half of the ingress contract that lives in Django settings.

`infrastructure/compose/nginx/includes/proxy-headers.conf` sets `X-Forwarded-Proto` and
`X-Forwarded-Host` on every proxied request. Those headers do nothing until Django is told
to trust them. Two settings, and without them every absolute URL Django builds behind the
proxy comes out as `http://` on the wrong port: `request.is_secure()` is False, secure
cookies are not set, `build_absolute_uri()` is wrong, and the generated OpenAPI `servers`
entry points somewhere the browser cannot reach.

This test exists because that contract was documented in a config comment and implemented
nowhere. Across a twelve-hour timezone gap, a half-documented contract is worse than
neither half — the reader believes the other side is handled. So it is asserted instead.

**If this test is failing, the fix is two lines** in `apps/control-api/config/settings/base.py`:

    USE_X_FORWARDED_HOST = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

Owner: backend developer (`apps/control-api/` is theirs; this test is not).

The check is static — it reads the settings sources rather than importing Django — so it
runs with no dependencies installed and no environment set up, and it cannot be made to
pass by a `DEBUG`-only branch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_API = REPO_ROOT / "apps" / "control-api"
SETTINGS_DIR = CONTROL_API / "config" / "settings"

pytestmark = pytest.mark.skipif(
    not SETTINGS_DIR.is_dir(),
    reason="apps/control-api/config/settings does not exist yet",
)

FIX_HINT = (
    "\n\nAdd to apps/control-api/config/settings/base.py:\n"
    "    USE_X_FORWARDED_HOST = True\n"
    '    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")\n\n'
    "Context: docs/06-operations/71-ingress-and-proxy-contract.md §3. nginx overwrites "
    "both headers on every request, so they cannot be spoofed by a client."
)


def _settings_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(SETTINGS_DIR.glob("*.py")))


def test_use_x_forwarded_host_is_enabled() -> None:
    source = _settings_source()
    assert "USE_X_FORWARDED_HOST" in source, (
        "USE_X_FORWARDED_HOST is not set anywhere in config/settings/. Django will build "
        "absolute URLs from its own Host header rather than the browser's, so every "
        "redirect behind nginx points at the wrong host and port." + FIX_HINT
    )
    assert "USE_X_FORWARDED_HOST = True" in source, (
        "USE_X_FORWARDED_HOST is mentioned but not set to True." + FIX_HINT
    )


def test_finale_closes_database_connections_after_each_request() -> None:
    """CONN_MAX_AGE must be 0 in the finale profile.

    Django's persistent database connections are thread-local. Under ASGI a held SSE stream
    occupies a thread for the life of the connection, so with CONN_MAX_AGE > 0 an idle
    Postgres connection is pinned alongside every open Command Center tab, for the whole
    mission. The finale runs on one box with one Postgres; wasting slots on connections
    doing nothing is not a trade worth making for the handshake it saves.
    """
    finale = SETTINGS_DIR / "finale.py"
    if not finale.is_file():
        pytest.skip("config/settings/finale.py not present")
    source = finale.read_text(encoding="utf-8")
    assert "CONN_MAX_AGE" in source, (
        "CONN_MAX_AGE is not set in the finale settings. Under ASGI it must be 0 — see the "
        "docstring above, and docs/06-operations/71-ingress-and-proxy-contract.md §3."
    )
    assert '"CONN_MAX_AGE": 0' in source or "CONN_MAX_AGE = 0" in source, (
        "CONN_MAX_AGE is set in the finale settings but not to 0."
    )


def test_secure_proxy_ssl_header_is_set() -> None:
    source = _settings_source()
    assert "SECURE_PROXY_SSL_HEADER" in source, (
        "SECURE_PROXY_SSL_HEADER is not set. request.is_secure() will be False for every "
        "request behind the proxy, so Django emits http:// URLs and will not set secure "
        "cookies even though the browser connected over TLS." + FIX_HINT
    )
    assert "HTTP_X_FORWARDED_PROTO" in source, (
        "SECURE_PROXY_SSL_HEADER does not reference HTTP_X_FORWARDED_PROTO, which is the "
        "header nginx actually sets." + FIX_HINT
    )
