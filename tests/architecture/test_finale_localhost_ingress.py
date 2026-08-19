"""Issue #92: finale runs on localhost without a browser TLS warning."""

from __future__ import annotations

from pathlib import Path

# D-088 (T0): conf.d.finale/brahmadatta.conf became a template, rendered by the nginx
# image's own envsubst entrypoint step at container start (see
# templates.finale/brahmadatta.conf.template's header comment) — the properties this
# test asserts on are unaffected, since the ${CONTROL_API_OPERATOR_TOKEN} substitution
# never touches any of the text these assertions check for.
CONF = (
    Path(__file__).resolve().parents[2]
    / "infrastructure"
    / "compose"
    / "nginx"
    / "templates.finale"
    / "brahmadatta.conf.template"
)


def _source() -> str:
    return CONF.read_text(encoding="utf-8")


def test_finale_nginx_serves_plain_localhost_http() -> None:
    source = _source()

    assert "listen      8080;" in source
    assert "listen      8443 ssl" not in source
    assert "return 301 https://" not in source
    assert "include /etc/nginx/includes/tls.conf" not in source


def test_finale_nginx_does_not_send_hsts_on_localhost() -> None:
    source = _source()

    assert "include /etc/nginx/includes/hsts.conf" not in source
    assert "Strict-Transport-Security" not in source
