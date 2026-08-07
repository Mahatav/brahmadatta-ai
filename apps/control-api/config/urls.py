"""URL configuration.

The Django admin is mounted only when the active profile enables it. The finale
profile removes it from `INSTALLED_APPS` entirely and nginx blocks the path as a
second layer (D-013, issue #10).
"""

from __future__ import annotations

from django.conf import settings
from django.urls import path

from api.api import api

urlpatterns = [
    path(settings.API_PREFIX, api.urls),
]

if getattr(settings, "ADMIN_ENABLED", False) and "django.contrib.admin" in settings.INSTALLED_APPS:
    from django.contrib import admin

    admin.site.site_header = "Brahmadatta AI — evidence inspection"
    admin.site.site_title = "Brahmadatta AI"
    admin.site.index_title = "Development only"
    urlpatterns += [path("django-admin/", admin.site.urls)]
