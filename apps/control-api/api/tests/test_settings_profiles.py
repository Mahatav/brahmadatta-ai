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


# --- BUG-010: the SQLite DSN spellings, now that migrations exist -----------------


@pytest.mark.parametrize(
    ("dsn", "expected"),
    [
        ("sqlite://", ":memory:"),
        ("sqlite://:memory:", ":memory:"),
        ("sqlite:///:memory:", ":memory:"),
        ("sqlite:///ci.sqlite3", "ci.sqlite3"),
        ("sqlite:///qa.sqlite3", "qa.sqlite3"),
        ("sqlite:////tmp/abs.sqlite3", "/tmp/abs.sqlite3"),
    ],
)
def test_sqlite_dsn_spellings(dsn: str, expected: str):
    """`sqlite:///relative.db` is the standard SQLAlchemy / dj-database-url spelling for
    a *relative* path, and it is what this repository's own `ci.yml` uses. It used to
    resolve to `/relative.db` — an absolute path at the filesystem root, unwritable on a
    CI runner. Harmless while nothing touched the database; a broken CI job the moment
    migrations landed, which is this change.
    """
    from config.env import database_from_url

    assert database_from_url(dsn)["NAME"] == expected


# --- SEC-18: the DSN stops silently discarding its own security configuration ------


@pytest.mark.parametrize(
    ("dsn", "expected_sslmode"),
    [
        ("postgresql://u:p@db:5432/brahmadatta?sslmode=require", "require"),
        ("postgresql://u:p@db:5432/brahmadatta?sslmode=verify-full", "verify-full"),
        ("postgresql://u:p@db:5432/brahmadatta?sslmode=disable", "disable"),
    ],
)
def test_sslmode_reaches_the_driver(dsn: str, expected_sslmode: str):
    """All four DSN spellings — including no query string at all — used to produce
    byte-identical configuration. The operator's strongest possible TLS statement and
    their explicit opt-out were the same string to this system, and libpq then applied
    its own default of `prefer`: attempt TLS, fall back to plaintext without error, and
    never validate the certificate either way.
    """
    from config.env import database_from_url

    assert database_from_url(dsn)["OPTIONS"]["sslmode"] == expected_sslmode


def test_the_tls_material_reaches_the_driver_too():
    """A `verify-full` with no CA path is not verify-anything."""
    from config.env import database_from_url

    options = database_from_url(
        "postgresql://u:p@db:5432/brahmadatta"
        "?sslmode=verify-full&sslrootcert=/etc/ssl/ca.pem"
    )["OPTIONS"]
    assert options["sslmode"] == "verify-full"
    assert options["sslrootcert"] == "/etc/ssl/ca.pem"


def test_a_dsn_with_no_query_string_still_works():
    """The fix must not make the ordinary case ceremony."""
    from config.env import database_from_url

    options = database_from_url("postgresql://u:p@db:5432/brahmadatta")["OPTIONS"]
    assert options == {"connect_timeout": 5}


def test_an_unknown_dsn_parameter_refuses_to_boot():
    """Fail closed, not best-effort.

    Mapping the parameters we know and dropping the rest fixes today's symptom and
    preserves the mechanism that caused it: the next security-relevant parameter is
    dropped just as silently. A control that accepts a setting and discards it is worse
    than one that rejects it, because the operator now believes something false and
    there is nothing to observe.
    """
    from config.env import ImproperlyConfigured, database_from_url

    with pytest.raises(ImproperlyConfigured) as excinfo:
        database_from_url(
            "postgresql://u:p@db:5432/brahmadatta?sslmode=require&application_name=x"
        )
    assert "application_name" in str(excinfo.value)


def test_an_undefined_sslmode_value_refuses_to_boot():
    """`sslmode=verify` is not a libpq value. Accepting it would read as verification
    while doing none."""
    from config.env import ImproperlyConfigured, database_from_url

    with pytest.raises(ImproperlyConfigured):
        database_from_url("postgresql://u:p@db:5432/brahmadatta?sslmode=verify")


def test_the_dsn_error_never_echoes_the_password():
    """The DSN carries a credential; its error messages must not."""
    from config.env import ImproperlyConfigured, database_from_url

    with pytest.raises(ImproperlyConfigured) as excinfo:
        database_from_url("postgresql://u:sup3rsecret@db:5432/b?unknown=1")
    assert "sup3rsecret" not in str(excinfo.value)


def test_the_finale_refuses_to_start_without_database_tls():
    """SEC-18 part 3. Forwarding `sslmode` closes the silence; it does not make anyone
    set the parameter. libpq's default is `prefer`, which falls back to plaintext."""
    from django.core.checks import Error

    from contracts.checks import check_database_tls_in_finale

    postgres = {
        "ENGINE": "django.db.backends.postgresql",
        "OPTIONS": {"connect_timeout": 5},
    }

    with override_settings(APP_ENV="finale", DATABASES={"default": postgres}):
        messages = check_database_tls_in_finale(None)
    assert len(messages) == 1
    assert isinstance(messages[0], Error)
    assert "prefer" in messages[0].msg

    verified = {
        "ENGINE": "django.db.backends.postgresql",
        "OPTIONS": {"connect_timeout": 5, "sslmode": "verify-full"},
    }
    with override_settings(APP_ENV="finale", DATABASES={"default": verified}):
        assert check_database_tls_in_finale(None) == []


def test_the_database_tls_check_is_scoped_to_the_finale():
    """Development and the test suite run on SQLite without ceremony."""
    from contracts.checks import check_database_tls_in_finale

    with override_settings(APP_ENV="development"):
        assert check_database_tls_in_finale(None) == []
