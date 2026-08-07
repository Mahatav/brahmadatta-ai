"""Deployment profiles: the admin must be closable for the finale.

D-013 introduced the Django admin as a build-time convenience and, with it, the
obligation to be able to shut it. This asserts the finale profile does so in the
settings themselves, independently of nginx also blocking the path (issue #10).
"""

from __future__ import annotations

import importlib
import os
from contextlib import contextmanager

import pytest
from django.test import override_settings

from contracts.checks import (
    ADMIN_CHECK_ID,
    check_admin_disabled_in_finale,
    check_debug_off_in_finale,
)


@contextmanager
def environment(**values: str):
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def load_profile(module_name: str):
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def test_finale_profile_disables_the_admin_even_when_the_env_asks_for_it():
    with environment(
        APP_ENV="finale",
        CONTROL_API_ADMIN_ENABLED="true",
        DJANGO_SECRET_KEY="finale-profile-import-test-key-000000000000",
        DATABASE_URL="sqlite://:memory:",
    ):
        finale = load_profile("config.settings.finale")

    assert finale.ADMIN_ENABLED is False
    assert "django.contrib.admin" not in finale.INSTALLED_APPS
    assert finale.DEBUG is False
    assert finale.SESSION_COOKIE_SECURE is True


def test_development_profile_offers_the_admin():
    with environment(
        APP_ENV="development",
        DJANGO_SECRET_KEY="development-profile-import-test-key-0000000",
        DATABASE_URL="sqlite://:memory:",
    ):
        development = load_profile("config.settings.development")

    assert development.ADMIN_ENABLED is True
    assert "django.contrib.admin" in development.INSTALLED_APPS


@override_settings(
    APP_ENV="finale",
    ADMIN_ENABLED=True,
    INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.admin"],
)
def test_startup_check_catches_an_admin_left_on_in_the_finale():
    messages = check_admin_disabled_in_finale(None)
    assert [message.id for message in messages] == [ADMIN_CHECK_ID]
    assert messages[0].is_serious()


@override_settings(APP_ENV="finale", DEBUG=True)
def test_startup_check_catches_debug_left_on_in_the_finale():
    assert check_debug_off_in_finale(None)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pw@localhost:5432/brahmadatta",
        "postgres://user:pw@db:5432/brahmadatta",
    ],
)
def test_database_url_parses_postgres(url: str):
    from config.env import database_from_url

    parsed = database_from_url(url)
    assert parsed["ENGINE"] == "django.db.backends.postgresql"
    assert parsed["NAME"] == "brahmadatta"


def test_database_url_is_required():
    from config.env import ImproperlyConfigured, database_from_url

    with pytest.raises(ImproperlyConfigured):
        database_from_url("")


def test_unsupported_database_scheme_is_refused():
    from config.env import ImproperlyConfigured, database_from_url

    with pytest.raises(ImproperlyConfigured):
        database_from_url("mysql://user:pw@localhost/brahmadatta")
