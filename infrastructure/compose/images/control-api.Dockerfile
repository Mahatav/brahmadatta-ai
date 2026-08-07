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
CMD ["uvicorn", "config.asgi:application", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "/app", \
     "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--log-level", "info"]


# ---------------------------------------------------------------------------
# runtime — finale posture. Immutable source, no reloader, no dev settings.
# ---------------------------------------------------------------------------
FROM base AS runtime

ENV DJANGO_SETTINGS_MODULE=config.settings.finale

COPY --chown=app:app . /app

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
