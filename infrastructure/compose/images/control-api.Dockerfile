# syntax=docker/dockerfile:1.7
#
# Control API image — Django + django-ninja served over ASGI by uvicorn.
#
# Build context is apps/control-api/ (owned by the backend developer). This Dockerfile
# lives in infrastructure/ because packaging and runtime posture are DevOps-owned, and so
# that no infrastructure change ever touches a file inside the application directory.
# The ignore list is the sibling file control-api.Dockerfile.dockerignore.
#
# Contract with apps/control-api/ — if any of these change, this file must change too:
#   - requirements.txt at the context root
#   - ASGI callable at config.asgi:application
#   - manage.py at the context root
#   - Python 3.12
#
# Targets:
#   dev     — dependencies only. Source arrives by bind mount so edits reload.
#   runtime — dependencies plus a copy of the source. Nothing is mounted at run time.

# python:3.12-slim-bookworm, pinned by multi-arch index digest. Never `latest`, never a
# bare tag: a tag can be repointed under us between a green CI run and the finale.
FROM python@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:${PATH}"

# A fixed high uid/gid, so a bind-mounted source tree has predictable ownership and so the
# id cannot collide with a real account on the host.
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin app

WORKDIR /app

RUN python -m venv /opt/venv

# psycopg is installed as psycopg[binary], so no libpq-dev / build-essential is needed and
# the image stays slim. If the backend ever switches to source psycopg, that changes.
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt \
 && chown -R app:app /opt/venv


# ---------------------------------------------------------------------------
# dev — source is bind-mounted by docker-compose.yml; nothing is copied in.
# ---------------------------------------------------------------------------
FROM base AS dev

ENV DJANGO_SETTINGS_MODULE=config.settings.development

USER app:app
EXPOSE 8000

# --host 0.0.0.0 is required INSIDE a container. The docstring in config/asgi.py shows
# 127.0.0.1, which is right for a bare-metal run and wrong here: a loopback-bound listener
# is unreachable from nginx in another container. It is still not exposed to the host —
# docker-compose.yml publishes no port for this service, so the only route in is nginx.
#
# SEC-14 (#98): --forwarded-allow-ips was "*" here — any client that could reach the
# container, not just nginx, could set X-Forwarded-Proto and X-Forwarded-For and have
# uvicorn believe it. The correct pattern already existed eight lines below in the
# runtime target: ${UVICORN_FORWARDED_ALLOW_IPS:-...}, an env var docker-compose.yml
# controls. Same shape here, using sh -c for the same reason the runtime target does —
# CMD's exec form does not expand shell variables, so a hardcoded "*" was the only value
# a JSON-array CMD could ever produce. Default 127.0.0.1 is deliberately wrong-safe: with
# no override, the dev server trusts nothing, which fails loudly (uvicorn logs the real
# peer IP as untrusted) rather than silently defaulting back to "*".
#
# Verification status, stated plainly (see the PR for #98's acceptance criteria):
#   VERIFIED  the compose wiring: `docker compose up` with this change resolves the
#             container's UVICORN_FORWARDED_ALLOW_IPS to the pinned api-network subnet
#             (172.28.90.0/24), a real request reached /api/v1/system/health through
#             nginx over TLS (200 OK), and the shell substitution `${VAR:-default}` was
#             checked in isolation for both the set and unset cases.
#   VERIFIED  end-to-end with THIS Dockerfile's CMD actually running, in a later session.
#             The earlier hang (`resolve image config for
#             docker-image://docker.io/docker/dockerfile:1.7`) was this machine's Docker
#             Desktop credential helper (`docker-credential-desktop`) stalling on every
#             invocation — confirmed by reproducing the identical hang on a bare
#             `docker pull docker/dockerfile:1.7` with no Dockerfile involved at all, and
#             by getting a clean pull immediately after pointing `DOCKER_CONFIG` at a
#             config with no `credsStore`. Environmental, not a property of this
#             repository's config, and not something anything under version control can
#             fix. `docker buildx build --target dev` completed
#             (`brahmadatta-control-api-test:dev`), and running that image's actual CMD
#             confirmed both branches of the substitution: unset resolves to the
#             wrong-safe `--forwarded-allow-ips 127.0.0.1` default, and
#             `UVICORN_FORWARDED_ALLOW_IPS=172.28.90.0/24` (the value docker-compose.yml
#             supplies) resolves to `--forwarded-allow-ips 172.28.90.0/24` — read back
#             from `/proc/1/cmdline` inside the running container, not asserted from the
#             Dockerfile text. `docker compose -f docker-compose.yml config` also
#             validates clean with this change in place.
CMD ["sh", "-c", "exec uvicorn config.asgi:application \
     --host 0.0.0.0 --port 8000 \
     --reload --reload-dir /app \
     --proxy-headers --forwarded-allow-ips \"${UVICORN_FORWARDED_ALLOW_IPS:-127.0.0.1}\" \
     --log-level info"]


# ---------------------------------------------------------------------------
# runtime — finale posture. Immutable source, no reloader, no dev settings.
# ---------------------------------------------------------------------------
FROM base AS runtime

ENV DJANGO_SETTINGS_MODULE=config.settings.finale

COPY --chown=app:app . /app

# `config.settings.base.SNAPSHOT_SOURCE_ROOT` defaults to `/demo/repositories`
# (`BASE_DIR.parent.parent / "demo" / "repositories"`, resolving to `/demo/repositories`
# when BASE_DIR is `/app`) — the only way to hand the container a local demo target
# (e.g. `pktcfg`) for `source="git"` snapshot ingestion without a real git remote.
#
# D-032: the finale compose file may not bind-mount host paths into control-api — the
# finale image is the artifact, and a source mount makes what runs on stage different
# from what was tested (tests/architecture/test_compose_topology.py::
# test_the_finale_profile_has_no_source_mounts_into_control_api enforces this). So this
# is baked in at build time instead, the same pattern as `COPY --chown=app:app . /app`
# two lines up and as images/postgres-tls.Dockerfile's baked-in TLS certs. `demo/` lives
# outside this Dockerfile's build context (apps/control-api/, owned by the backend
# developer — see the file header) by design, so it arrives via a named additional
# build context rather than a path inside `.`: `demo-repositories`, pointed at
# `../../demo/repositories` by both the `control-api` and `worker` services' `build:`
# blocks in docker-compose.finale.yml. `docker compose build` resolves it automatically;
# a bare `docker build` needs `--build-context demo-repositories=../../demo/repositories`.
COPY --from=demo-repositories --chown=app:app . /demo/repositories

# `docker-compose.finale.yml` mounts named volumes at these two paths for the
# content-addressed artifact store (ARTIFACT_ROOT) and the exported evidence bundle
# store. A fresh named volume is created empty and root-owned; Docker seeds it from
# whatever already exists at the mount point in the image at first mount, ownership
# included — so creating these here, owned by `app`, is what lets the non-root
# `runtime` process (USER app:app below, and `read_only: true` + `cap_drop: ["ALL"]`
# in the finale compose file — no CHOWN capability at runtime to fix this after the
# fact) actually write into them. Without this, both paths 500 on first write with
# `PermissionError: [Errno 13] Permission denied`. Found running the #50 live
# rehearsal, 2026-08-17 — `evidence/` had never been reached by any prior partial
# verification, and `artifacts/` had never existed as a writable path in any profile.
RUN mkdir -p /var/lib/brahmadatta/artifacts /var/lib/brahmadatta/evidence \
 && chown -R app:app /var/lib/brahmadatta

USER app:app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import socket,sys; s=socket.create_connection(('127.0.0.1',8000),3); s.close()"]

# --forwarded-allow-ips is scoped to the compose edge network in the finale compose file
# via UVICORN_FORWARDED_ALLOW_IPS. Trusting "*" here would let anything that can reach the
# container spoof X-Forwarded-Proto.
CMD ["sh", "-c", "exec uvicorn config.asgi:application \
     --host 0.0.0.0 --port 8000 \
     --proxy-headers --forwarded-allow-ips \"${UVICORN_FORWARDED_ALLOW_IPS:-127.0.0.1}\" \
     --log-level info"]
