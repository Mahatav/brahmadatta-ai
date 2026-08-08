"""Base settings shared by every deployment profile.

Profiles live beside this file:

* `config.settings.development` — admin on, DEBUG on, permissive hosts.
* `config.settings.finale`      — admin off, DEBUG off, strict hosts. The profile
                                  the competition run uses.
* `config.settings.test`        — in-memory SQLite, deterministic secrets.

Nothing here reads a secret with a working default. Missing configuration fails
loudly at startup rather than degrading into an insecure state.
"""

from __future__ import annotations

from pathlib import Path

from config import env

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env.load_env_file(BASE_DIR)

# --- Identity -----------------------------------------------------------------

APP_NAME = "brahmadatta-control-api"
APP_VERSION = "0.1.0"
APP_ENV = env.get_str("APP_ENV", "development")

# --- Core Django --------------------------------------------------------------

SECRET_KEY = env.get_str("DJANGO_SECRET_KEY", required=True)
DEBUG = False
ALLOWED_HOSTS = env.get_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env.get_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# The Django admin is a build-time convenience for inspecting evidence records.
# It is disabled by default and must stay disabled in the finale profile, where
# nginx also blocks the path (issue #10). See D-013.
ADMIN_ENABLED = env.get_bool("CONTROL_API_ADMIN_ENABLED", False)

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "contracts",
    "missions",
]

MIDDLEWARE = [
    "api.trace.TraceIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {"default": env.database_from_url(env.get_str("DATABASE_URL"))}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "/django-static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- API surface --------------------------------------------------------------

API_PREFIX = "api/v1/"

# --- Operator authentication ---------------------------------------------------
#
# Bearer tokens, one per role, supplied by the environment. Absent tokens mean the
# role cannot authenticate at all — the API fails closed rather than open.
# Tokens are never logged and never returned in a response body.

CONTROL_API_TOKENS: dict[str, str] = {
    role: token
    for role, token in (
        ("operator", env.get_str("CONTROL_API_OPERATOR_TOKEN")),
        ("reviewer", env.get_str("CONTROL_API_REVIEWER_TOKEN")),
        ("administrator", env.get_str("CONTROL_API_ADMIN_TOKEN")),
    )
    if token
}
CONTROL_API_MIN_TOKEN_LENGTH = 32

# --- Model routing -------------------------------------------------------------
#
# Hard product rule: repository content never reaches an external inference API.
# These endpoints are validated by `contracts.checks.check_model_endpoints`, which
# runs as a Django system check — a hosted provider URL here fails `manage.py check`
# and therefore fails startup, rather than being caught in review.
# Tier 3 / rented GPU is CUT by D-015; the variable is validated if it is set at all.

MODEL_ENDPOINTS: dict[str, str] = {
    "SMALL_MODEL_BASE_URL": env.get_str("SMALL_MODEL_BASE_URL"),
    "TIER3_BASE_URL": env.get_str("TIER3_BASE_URL"),
}

# --- Sandbox policy defaults ---------------------------------------------------
#
# Consumed by the orchestrator (D2, issue #12). Declared here so the control API can
# echo the effective policy back to the Command Center without inventing values.

SANDBOX_POLICY = {
    "runtime": env.get_str("SANDBOX_RUNTIME", "podman"),
    "network": env.get_str("SANDBOX_NETWORK", "deny"),
    "cpu_limit": env.get_int("SANDBOX_CPU_LIMIT", 4),
    "memory_mb": env.get_int("SANDBOX_MEMORY_MB", 8192),
    "max_seconds": env.get_int("SANDBOX_MAX_SECONDS", 5400),
}

# --- Snapshot ingestion (#18) ---------------------------------------------------
#
# Content-addressed artifact store: ARTIFACT_ROOT/<sha256[0:2]>/<sha256>, mode 0600,
# directory 0700 (architecture spec §5.2). SNAPSHOT_SOURCE_ROOT bounds which local
# directories a mission's own repository_ref may resolve to when the snapshot is built
# from a directory rather than an uploaded archive — a repository_ref that resolves
# outside this root is refused (authorization.errors.RepositoryOutOfScopeError), never
# read. SNAPSHOT_STAGING_ROOT bounds an uploaded archive's archive_ref the same way.
ARTIFACT_ROOT = Path(env.get_str("ARTIFACT_ROOT", str(BASE_DIR / "var" / "artifacts")))
SNAPSHOT_SOURCE_ROOT = Path(
    env.get_str(
        "SNAPSHOT_SOURCE_ROOT", str(BASE_DIR.parent.parent / "demo" / "repositories")
    )
)
SNAPSHOT_STAGING_ROOT = Path(
    env.get_str("SNAPSHOT_STAGING_ROOT", str(BASE_DIR / "var" / "uploads"))
)
#: 512 MiB. The demo targets are single-digit megabytes; this is a DoS ceiling, not a
#: realistic size, and ingestion refuses (does not truncate) the instant it is crossed.
SNAPSHOT_MAX_BYTES = env.get_int("SNAPSHOT_MAX_BYTES", 536_870_912)

# --- Security headers ----------------------------------------------------------

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# --- Logging -------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": env.get_str("LOG_LEVEL", "INFO")},
}

# The Django half of the ingress contract. nginx overwrites both headers on every request
# in both profiles (infrastructure/compose/nginx/includes/proxy-headers.conf), so trusting
# them is safe and NOT trusting them is the bug: without these, Django builds http:// URLs
# and the wrong host behind a TLS-terminating proxy.
#
# In base.py rather than finale.py deliberately. The development profile runs behind the
# same nginx and had the same defect — the security review flagged it, and
# tests/architecture/test_ingress_contract.py fails if either is absent.
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
