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

import sys
from pathlib import Path

from config import env

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# D-026 collapsed `model-gateway`/`evidence-builder`/`telemetry` into modules inside
# this Django project, but `workers/`, `adapters/` and `packages/` (the stage code the
# `JobKind` executors wire into — #168 T1/T2/...) were never moved in; they still live
# one level up, as siblings of `apps/`. Nothing before this line put that directory on
# `sys.path`, so `from workers.baseline.run import run_baseline_stage` (or any sibling
# import) raised `ModuleNotFoundError` from every Django entrypoint (`manage.py`,
# `wsgi`/`asgi`, and — critically — `pytest-django`, which imports this settings module
# directly rather than going through `manage.py`).
#
# There IS a real name collision: `apps/control-api/tools/` (import contract:
# `tools.export_openapi`, used by `contracts/tests/test_openapi_dump.py`) and
# repo-root `tools/` (`fallback_demo.py`, `verdict_report.py`) are two different
# packages sharing the bare name `tools`. Whichever one Python resolves first for
# `import tools` wins that name for the rest of the process — the two can never both
# be `tools` at once. `BASE_DIR` is therefore inserted at `sys.path[0]` *before*
# `REPO_ROOT` is appended, deterministically, rather than relying on whatever already
# put `BASE_DIR` on `sys.path` by the time this module runs (`manage.py`/`wsgi`/`asgi`
# do, in their own `main()`/module scope — but nothing does under `pytest-django`,
# which imports this settings module directly and never calls `manage.py`). Getting
# this backwards is silent and order-dependent: it manifested as `contracts/tests/
# test_openapi_dump.py` raising `ModuleNotFoundError: No module named
# 'tools.export_openapi'` the first time this file appended without first inserting —
# found by running the full suite, not by inspection. `apps/control-api`'s own
# top-level packages (`api`, `authorization`, `config`, `contracts`, `missions`,
# `orchestrator`, and now `tools`) have no other collision against repo root's
# (`adapters`, `demo`, `docs`, `infrastructure`, `packages`, `services`, `tests`,
# `workers` — checked directly), but the insert-before-append order is what makes
# that true even if one is added later, not the absence of a name today.
REPO_ROOT = BASE_DIR.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

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

# SEC-05 (#96): the OpenAPI dump and the docs page are on by default — useful while the
# contract is being built out — and forced off in the finale profile the same way
# ADMIN_ENABLED is: a hard override in finale.py, not env-driven. The committed dump at
# packages/schemas/openapi.json is generated by tools/export_openapi.py, not by this live
# route, so nothing in the build depends on the endpoint existing.
API_DOCS_ENABLED = env.get_bool("CONTROL_API_DOCS_ENABLED", True)

# --- Server-sent events (#13) ---------------------------------------------------

# CTO-C1: a hard per-mission concurrent-stream cap. A handful of tabs/reconnects is
# ordinary; unbounded readers is a resource leak with no operator-visible cause. One
# supervised ASGI process per D-019/D-024 (no Redis, no multi-worker fan-out for the
# control API), so a process-local counter in api.sse is the whole store.
SSE_MAX_STREAMS_PER_MISSION = env.get_int("SSE_MAX_STREAMS_PER_MISSION", 4)

# How often the stream polls MissionEvent for rows past the client's cursor. No
# broker (D-019/D-024 again) — this is a plain SELECT, sync_to_async per call.
SSE_POLL_INTERVAL_SECONDS = env.get_float("SSE_POLL_INTERVAL_SECONDS", 0.5)

# `: heartbeat\n\n` comment cadence during an idle stream. sse.conf's
# `proxy_read_timeout 3600s` covers the upstream-idle gap; this is what lets a client
# (and a human watching curl) tell a quiet mission from a dead connection well before
# that fires. infrastructure/compose/nginx/includes/sse.conf recommends 15s.
SSE_HEARTBEAT_INTERVAL_SECONDS = env.get_float("SSE_HEARTBEAT_INTERVAL_SECONDS", 15.0)

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
MODEL_SERVICE_NAMES = frozenset(
    name.strip().lower()
    for name in env.get_str("MODEL_SERVICE_NAMES").replace(";", ",").split(",")
    if name.strip()
)

MODEL_HOST_LIFECYCLE = {
    "enabled": env.get_bool("MODEL_HOST_LIFECYCLE_ENABLED", False),
    "runtime": env.get_str("MODEL_HOST_RUNTIME", "docker"),
    "compose_file": env.get_str(
        "MODEL_HOST_COMPOSE_FILE",
        str(BASE_DIR.parent.parent / "infrastructure" / "compose" / "docker-compose.yml"),
    ),
    "profile": env.get_str("MODEL_HOST_COMPOSE_PROFILE", "model"),
    "service": env.get_str("MODEL_HOST_COMPOSE_SERVICE", "model-host"),
    "resource_id": env.get_str("MODEL_HOST_RESOURCE_ID", "model-host"),
    "lease_seconds": env.get_int("MODEL_HOST_LEASE_SECONDS", 1800),
    "command_timeout_seconds": env.get_int("MODEL_HOST_COMMAND_TIMEOUT_SECONDS", 60),
}

# --- Orchestrator / worker (#168, T0) -------------------------------------------
#
# `manage.py run_orchestrator` and `manage.py run_worker` (orchestrator/queue.py).
# Architecture spec §3.5: "Backend developer (#12) decides: ... lease duration (60s
# suggested); heartbeat interval (10s suggested); backoff shape" and "polling interval
# (recommend 1s — this is one mission on one machine)". Every value here is that kind
# of developer-scoped default, not a Fixed contract value — safe to retune without a
# CTO call.
ORCHESTRATOR_TICK_INTERVAL_SECONDS = env.get_float("ORCHESTRATOR_TICK_INTERVAL_SECONDS", 1.0)
WORKER_JOB_LEASE_SECONDS = env.get_int("WORKER_JOB_LEASE_SECONDS", 60)
WORKER_HEARTBEAT_INTERVAL_SECONDS = env.get_int("WORKER_HEARTBEAT_INTERVAL_SECONDS", 10)
WORKER_POLL_INTERVAL_SECONDS = env.get_float("WORKER_POLL_INTERVAL_SECONDS", 1.0)

# --- Sandbox policy defaults ---------------------------------------------------
#
# Consumed by the orchestrator (D2, issue #12) and by
# packages.sandbox.container.ContainerJailPolicy.from_settings (#15). Declared here
# so the control API can echo the effective policy back to the Command Center
# without inventing values.
#
# `runtime` defaults to "docker", not "podman": D-024
# (docs/09-company/08-security-review.md §6.4) accepted a standard rootful-daemon
# container with `--network none` as the substitute for rootless Podman, on the
# grounds that Podman was not installed on the build host at all (SEC-11) and that
# `--network none` answers the threats that actually matter here more completely
# than a rootless-but-networked container would. `network` stays "deny" — the API
# has no vocabulary for anything else, and `ContainerJailPolicy` hardcodes the
# enforcement independently of this setting regardless.

SANDBOX_POLICY = {
    "runtime": env.get_str("SANDBOX_RUNTIME", "docker"),
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
    env.get_str("SNAPSHOT_SOURCE_ROOT", str(BASE_DIR.parent.parent / "demo" / "repositories"))
)
SNAPSHOT_STAGING_ROOT = Path(
    env.get_str("SNAPSHOT_STAGING_ROOT", str(BASE_DIR / "var" / "uploads"))
)
#: 512 MiB. The demo targets are single-digit megabytes; this is a DoS ceiling, not a
#: realistic size, and ingestion refuses (does not truncate) the instant it is crossed.
#:
#: Shared, deliberately, with the *extraction* side of the same round-trip
#: (`orchestrator.snapshot.materialize_snapshot` passes this same value to
#: `authorization.archive.extract_archive`'s `max_bytes`) rather than each end
#: choosing its own number. Round-4 security review, HIGH-1: an ingested archive can
#: pass this ceiling on its own (compressed) size while still decompressing to
#: hundreds of GB on disk — a gzip bomb of highly-compressible content compresses at
#: up to ~1000:1 — so the ceiling has to be enforced again, independently, against the
#: bytes extraction actually writes, not just assumed to still hold from ingest time.
SNAPSHOT_MAX_BYTES = env.get_int("SNAPSHOT_MAX_BYTES", 536_870_912)
#: Where `orchestrator.snapshot.materialize_snapshot` (#168, T0b) extracts a mission's
#: stored snapshot archive back to disk, one fresh `<root>/<mission_id>/<uuid4>`
#: directory per call. Kept a sibling of ARTIFACT_ROOT rather than nested inside it —
#: extracted, writable working trees have a different lifecycle (created and torn down
#: per stage run) than the content-addressed store (immutable, keyed by digest), and
#: keeping them apart means a bulk cleanup of one can never touch the other.
SNAPSHOT_WORKSPACE_ROOT = Path(
    env.get_str("SNAPSHOT_WORKSPACE_ROOT", str(BASE_DIR / "var" / "workspaces"))
)

#: Where `orchestrator.evidence_export.export_mission` (#168, T6) assembles the
#: `report.md`/`report.json`/`manifest.json`/`gate-matrix.json`/`tool-versions.json`
#: directory and its `.tar.gz` before the tarball is ingested into `ARTIFACT_ROOT`
#: (content-addressed, durable) and the scratch directory is discarded. A sibling of
#: `SNAPSHOT_WORKSPACE_ROOT` for the same reason that root is kept apart from
#: `ARTIFACT_ROOT`: a different lifecycle (created and torn down per export) from the
#: content-addressed store it feeds.
EXPORT_WORKSPACE_ROOT = Path(
    env.get_str("EXPORT_WORKSPACE_ROOT", str(BASE_DIR / "var" / "exports"))
)
#: Byte ceiling for one evidence bundle tarball. The bundle never contains the
#: target's source archive (architecture spec §5.3, "never in"), so this is far
#: smaller than `SNAPSHOT_MAX_BYTES` — 64 MiB is generous for diffs, logs and JSON.
EVIDENCE_BUNDLE_MAX_BYTES = env.get_int("EVIDENCE_BUNDLE_MAX_BYTES", 67_108_864)

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
