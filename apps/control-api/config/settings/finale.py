"""Finale profile: the settings the competition run uses.

Django admin is not merely defaulted off here — it is *forced* off and removed from
INSTALLED_APPS, so `CONTROL_API_ADMIN_ENABLED=true` in a stray environment cannot
re-enable it. nginx blocks the path as a second layer (issue #10). See D-013.
"""

from __future__ import annotations

from config import env
from config.settings.base import *  # noqa: F401,F403
from config.settings.base import INSTALLED_APPS

# Not env-driven. Deliberately — same argument as ADMIN_ENABLED below. base.py reads
# APP_ENV from the environment so the test and development profiles can each say who they
# are; docker-compose.finale.yml's env_file supplies APP_ENV=development (SEC-03), which
# means the two APP_ENV-gated system checks (contracts.checks.check_admin_disabled_in_finale,
# check_debug_off_in_finale) silently never fired in the one profile they exist to guard.
# A stray environment variable must not be able to turn this profile into "development" by
# accident.
APP_ENV = "finale"

DEBUG = False

# Persistent database connections are thread-local, and under ASGI a held SSE stream
# would pin one idle for the life of the connection. The finale runs one operator and
# one mission; connection setup cost is irrelevant beside leaking the pool (CTO C2).
DATABASES = {**DATABASES, "default": {**DATABASES["default"], "CONN_MAX_AGE": 0}}  # noqa: F405

# Not env-driven. Deliberately.
ADMIN_ENABLED = False
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "django.contrib.admin"]

# SEC-05 (#96): not env-driven, deliberately — same argument as ADMIN_ENABLED above. The
# OpenAPI dump and docs page are free reconnaissance of the whole API surface to anyone on
# the venue network, and the docs page fetches Swagger UI from a third-party CDN, which is
# a live outbound request from the browser on a stack whose headline claim is that it
# doesn't talk to anyone. nginx also closes both paths (conf.d.finale/brahmadatta.conf) —
# belt and braces, so neither layer being wrong alone is sufficient.
API_DOCS_ENABLED = False

ALLOWED_HOSTS = env.get_list("DJANGO_ALLOWED_HOSTS") or ["localhost"]

# TLS terminates at nginx; Django trusts its forwarded scheme header only.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.get_int("DJANGO_HSTS_SECONDS", 0)
