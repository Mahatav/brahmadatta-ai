"""Test profile: no PostgreSQL, no real secrets, admin off.

The contract tests exercise schemas, the state machine and the HTTP surface. None of
them touch the database, so an in-memory SQLite handle keeps the suite runnable on a
machine with no PostgreSQL — including CI before infrastructure lands (issue #11).
"""

from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-a-real-secret-key-000000")
os.environ.setdefault("DATABASE_URL", "sqlite://:memory:")
os.environ.setdefault(
    "CONTROL_API_OPERATOR_TOKEN", "test-operator-token-0123456789abcdef0123"
)
os.environ.setdefault(
    "CONTROL_API_REVIEWER_TOKEN", "test-reviewer-token-0123456789abcdef0123"
)
os.environ.setdefault(
    "CONTROL_API_ADMIN_TOKEN", "test-administrator-token-0123456789abcdef"
)

from config.settings.base import *  # noqa: E402,F401,F403

DEBUG = False
ADMIN_ENABLED = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
