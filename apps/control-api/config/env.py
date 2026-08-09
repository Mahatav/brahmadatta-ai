"""Environment reading helpers.

Every deployment-varying value in the control API comes from the environment.
Nothing in this module carries a usable default for a secret: a missing secret
is an error, never a silently-weak fallback.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

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


def get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be a number, got {raw!r}") from exc


def get_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default) or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def _sqlite_name(parsed) -> str:
    """Resolve a SQLite DSN to a Django `NAME`.

    The spellings, and what each means — this is the standard SQLAlchemy /
    `dj-database-url` reading, and the repository's own `ci.yml` and `.env.example`
    both use the relative form:

        sqlite://                    in-memory
        sqlite://:memory:            in-memory
        sqlite:///:memory:           in-memory
        sqlite:///relative.db        relative to the working directory
        sqlite:////absolute/path.db  absolute

    Previously `sqlite:///ci.sqlite3` produced `NAME=/ci.sqlite3` — an absolute path at
    the filesystem root, which is unwritable on a CI runner. Nothing noticed because
    nothing in the suite touched the database (QA, BUG-010). The models in this change
    are what make it bite, so it is fixed here rather than filed.
    """
    netloc = parsed.netloc or ""
    path = parsed.path or ""

    if netloc in {"", ":memory:"} and path in {"", "/:memory:", ":memory:"}:
        return ":memory:"
    if netloc == ":memory:" or path == "/:memory:":
        return ":memory:"

    if path.startswith("//"):
        # sqlite:////absolute/path -> path == "//absolute/path"
        return path[1:]
    if path.startswith("/"):
        # sqlite:///relative.db -> path == "/relative.db", meaning "relative.db"
        return path[1:]
    return path or ":memory:"


#: DSN query parameters this system understands and forwards to libpq. Everything on
#: this list is TLS configuration, which is the only category of DSN parameter the
#: deployment actually needs and the only one whose silent loss is a security event.
LIBPQ_TLS_PARAMETERS: frozenset[str] = frozenset(
    {"sslmode", "sslrootcert", "sslcert", "sslkey", "sslcrl"}
)

#: `sslmode` values that actually authenticate the server. `require` encrypts but does
#: not verify the certificate; it is the weakest value the finale check will accept, on
#: the grounds that the finale topology puts postgres on a private network — see the
#: system check in `contracts/checks.py`.
SSLMODE_VALUES: frozenset[str] = frozenset(
    {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
)


def _libpq_options(query: str) -> dict[str, str]:
    """Map DSN query parameters into Django's `OPTIONS`, or refuse to boot.

    Before this existed, `database_from_url` never read `parsed.query`. All four of

        ?sslmode=verify-full&sslrootcert=/etc/ssl/ca.pem
        ?sslmode=require
        ?sslmode=disable
        (no query string at all)

    produced byte-identical database configuration: the operator's strongest possible
    TLS statement and their explicit opt-out were the same string to this system. libpq
    then applied its own default, `prefer` — attempt TLS, **fall back to plaintext
    without error if the server declines, and never validate the certificate either
    way**. Someone who wrote `verify-full` specifically to defeat an active
    man-in-the-middle got `prefer`.

    **Fail closed, not best-effort.** An unrecognised parameter raises rather than being
    dropped, because the mechanism that caused this was silence, not the particular
    parameter. A control that accepts a security-relevant setting and discards it is
    worse than one that rejects it outright: the operator now believes something false
    and there is nothing to observe. This is the same posture `brahmadatta.E001` takes
    on a hosted inference endpoint — refuse to boot rather than degrade quietly.
    """
    if not query:
        return {}

    options: dict[str, str] = {}
    for key, values in parse_qs(query, keep_blank_values=True).items():
        if key not in LIBPQ_TLS_PARAMETERS:
            raise ImproperlyConfigured(
                f"DATABASE_URL carries the query parameter {key!r}, which this system "
                f"does not understand. It is refused rather than ignored: a dropped "
                f"connection parameter is a setting the operator believes is in effect "
                f"and is not. Supported: {sorted(LIBPQ_TLS_PARAMETERS)}."
            )
        if len(values) > 1:
            raise ImproperlyConfigured(
                f"DATABASE_URL sets {key!r} more than once; which one wins would be an "
                f"accident of parsing."
            )
        value = values[0]
        if key == "sslmode" and value not in SSLMODE_VALUES:
            raise ImproperlyConfigured(
                f"DATABASE_URL sets sslmode={value!r}, which libpq does not define. "
                f"Valid: {sorted(SSLMODE_VALUES)}."
            )
        options[key] = value

    return options


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
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": _sqlite_name(parsed)}

    if parsed.scheme not in {"postgres", "postgresql", "psql"}:
        raise ImproperlyConfigured(
            f"Unsupported DATABASE_URL scheme {parsed.scheme!r}; "
            f"expected postgresql:// (or sqlite:// for local tests)."
        )

    if not parsed.hostname:
        raise ImproperlyConfigured("DATABASE_URL is missing a host.")

    options: dict[str, object] = {"connect_timeout": 5}
    options.update(_libpq_options(parsed.query))

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")) or "brahmadatta",
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(parsed.port or 5432),
        "CONN_MAX_AGE": 60,
        "OPTIONS": options,
    }
