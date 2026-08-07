"""Environment reading helpers.

Every deployment-varying value in the control API comes from the environment.
Nothing in this module carries a usable default for a secret: a missing secret
is an error, never a silently-weak fallback.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv


class ImproperlyConfigured(Exception):
    """Raised when the environment cannot produce a usable configuration."""


def load_env_file(base_dir: Path) -> None:
    """Load `apps/control-api/.env` if present.

    `.env` is gitignored. `.env.example` documents the required keys and is the
    only env file that is ever committed.
    """
    env_path = base_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


def get_str(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(
            f"Required environment variable {name} is unset. "
            f"See apps/control-api/.env.example."
        )
    return value or ""


def get_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer, got {raw!r}") from exc


def get_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default) or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def database_from_url(url: str) -> dict[str, object]:
    """Translate a `postgresql://` DSN into a Django DATABASES entry.

    Only PostgreSQL and SQLite are accepted; the persistence choice is fixed by
    the stack table in CLAUDE.md and is not a per-environment decision.
    """
    if not url:
        raise ImproperlyConfigured(
            "DATABASE_URL is unset. See apps/control-api/.env.example."
        )

    parsed = urlparse(url)

    if parsed.scheme in {"sqlite", "sqlite3"}:
        name = parsed.path or ":memory:"
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": name}

    if parsed.scheme not in {"postgres", "postgresql", "psql"}:
        raise ImproperlyConfigured(
            f"Unsupported DATABASE_URL scheme {parsed.scheme!r}; "
            f"expected postgresql:// (or sqlite:// for local tests)."
        )

    if not parsed.hostname:
        raise ImproperlyConfigured("DATABASE_URL is missing a host.")

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")) or "brahmadatta",
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(parsed.port or 5432),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 5},
    }
