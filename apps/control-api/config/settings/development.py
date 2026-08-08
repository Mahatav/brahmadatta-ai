"""Development profile: Django admin available, verbose errors, local hosts.

Never use this profile for the finale run — see `config.settings.finale`.
"""

from __future__ import annotations

from config import env
from config.settings.base import *  # noqa: F401,F403
from config.settings.base import INSTALLED_APPS

# Not env-driven. Deliberately — mirrors config.settings.finale (SEC-03). This profile
# must never present itself as APP_ENV=finale, which would suppress every finale-only
# system check for a stack that is not actually the finale.
APP_ENV = "development"

DEBUG = env.get_bool("DJANGO_DEBUG", True)

# Admin defaults ON here — it is the reason Django was chosen over FastAPI (D-013):
# inspecting evidence records mid-build. It can still be switched off explicitly.
ADMIN_ENABLED = env.get_bool("CONTROL_API_ADMIN_ENABLED", True)

if ADMIN_ENABLED and "django.contrib.admin" not in INSTALLED_APPS:
    INSTALLED_APPS = [*INSTALLED_APPS, "django.contrib.admin"]

ALLOWED_HOSTS = env.get_list(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0,control-api"
)
