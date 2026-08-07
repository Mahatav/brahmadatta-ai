"""Finale profile: the settings the competition run uses.

Django admin is not merely defaulted off here — it is *forced* off and removed from
INSTALLED_APPS, so `CONTROL_API_ADMIN_ENABLED=true` in a stray environment cannot
re-enable it. nginx blocks the path as a second layer (issue #10). See D-013.
"""

from __future__ import annotations

from config import env
from config.settings.base import *  # noqa: F401,F403
from config.settings.base import INSTALLED_APPS

DEBUG = False

# Persistent database connections are thread-local, and under ASGI a held SSE stream
# would pin one idle for the life of the connection. The finale runs one operator and
# one mission; connection setup cost is irrelevant beside leaking the pool (CTO C2).
DATABASES = {**DATABASES, "default": {**DATABASES["default"], "CONN_MAX_AGE": 0}}  # noqa: F405

# Not env-driven. Deliberately.
ADMIN_ENABLED = False
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "django.contrib.admin"]

ALLOWED_HOSTS = env.get_list("DJANGO_ALLOWED_HOSTS") or ["localhost"]

# TLS terminates at nginx; Django trusts its forwarded scheme header only.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.get_int("DJANGO_HSTS_SECONDS", 0)
