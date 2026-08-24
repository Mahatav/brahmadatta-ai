#!/usr/bin/env bash
# Bring up the development stack, after checking the things that otherwise fail in
# confusing ways.
#
#   infrastructure/scripts/dev-up.sh              # everything
#   infrastructure/scripts/dev-up.sh db redis     # a subset
#   DEV_UP_WORKER=1 infrastructure/scripts/dev-up.sh   # include the queue worker
#
# Why a script instead of a bare `docker compose up`:
#
#   1. A bind mount whose host path does not exist is CREATED BY DOCKER, owned by root.
#      apps/command-center/ does not exist yet, so a plain `up` would leave a root-owned
#      directory in the repository that the frontend developer then cannot write to. This
#      script refuses instead.
#   2. nginx will not start without TLS material; it is generated here if missing.
#   3. `--env-file` has to point at the repository root .env, because compose otherwise
#      looks for one next to the compose file.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infrastructure/compose/docker-compose.yml"

fail() { printf '\033[31mblocked:\033[0m %s\n' "$1" >&2; exit 1; }
note() { printf '  %s\n' "$1"; }

# docker-compose.yml pins `name: brahmadatta`, so two concurrent checkouts
# bringing this stack up independently silently share the same containers,
# networks, and named volumes — one session's rebuild/teardown yanks resources
# out from under the other. Found colliding for real between two concurrent
# agent worktrees, D-098/D-099, 2026-08-19. A linked worktree's git-dir differs
# from the repo's git-common-dir; the primary checkout's does not, so this only
# renames the project for a worktree, leaving the primary checkout's existing
# `brahmadatta-*` container/volume names (and everything that already assumes
# them) unchanged.
#
# #230: COMPOSE_PROJECT_NAME alone does not isolate everything docker-compose.yml pins
# outside Compose's own project-prefixed naming — every `container_name:`, nginx's two
# published host ports, and the `api` network's subnet. See that file's own header
# comment for why each one collided. All three are derived below from the SAME worktree
# hash as COMPOSE_PROJECT_NAME, so a given worktree gets stable values across repeated
# dev-up.sh runs, and each is exported only if not already set — an operator's own
# override always wins, same convention COMPOSE_PROJECT_NAME itself already uses.
if [[ -z "${COMPOSE_PROJECT_NAME:-}" ]]; then
  git_dir="$(git -C "${REPO_ROOT}" rev-parse --git-dir)"
  common_dir="$(git -C "${REPO_ROOT}" rev-parse --git-common-dir)"
  if [[ "${git_dir}" != "${common_dir}" ]]; then
    worktree_hash="$(printf '%s' "${REPO_ROOT}" | shasum | cut -c1-8)"
    export COMPOSE_PROJECT_NAME="brahmadatta-${worktree_hash}"
    note "linked worktree detected — isolated compose project: ${COMPOSE_PROJECT_NAME}"

    # Decimal form of the same 8 hex chars, for deriving a port/subnet offset. Ranges are
    # chosen clear of the primary checkout's own defaults (8080/8443, 172.28.90.0/24) and
    # of this host's other known Docker networks (172.17-25.0.0/16) — collision between
    # two worktrees is possible in principle (a hash collision, or an unlucky modulo) but
    # was judged acceptable for a handful of concurrent checkouts rather than worth an
    # allocate-and-retry loop; a collision fails loudly at `docker compose up` (port/subnet
    # already in use), it does not silently share resources the way the pre-#230 bug did.
    worktree_hash_dec="$((16#${worktree_hash}))"
    if [[ -z "${NGINX_HTTP_PORT:-}" ]]; then
      export NGINX_HTTP_PORT=$(( 20000 + (worktree_hash_dec % 10000) ))
    fi
    if [[ -z "${NGINX_HTTPS_PORT:-}" ]]; then
      export NGINX_HTTPS_PORT=$(( 30000 + (worktree_hash_dec % 10000) ))
    fi
    if [[ -z "${UVICORN_DEV_FORWARDED_ALLOW_IPS:-}" ]]; then
      export UVICORN_DEV_FORWARDED_ALLOW_IPS="10.90.$(( (worktree_hash_dec % 250) + 1 )).0/24"
    fi

    # #235: docker-compose.yml's control-api service interpolates
    # `${DJANGO_CSRF_TRUSTED_ORIGINS:-https://localhost:8443,http://localhost:8080}` — a
    # static literal that matches the PRIMARY checkout's nginx ports but not a linked
    # worktree's derived ones (NGINX_HTTP_PORT/NGINX_HTTPS_PORT above). Django's CSRF
    # middleware only ever narrows trust, never widens it (safe to fail this way), but a
    # browser POST/PUT through the worktree's own nginx port was rejected until the
    # operator manually overrode this var.
    #
    # Unlike UVICORN_FORWARDED_ALLOW_IPS just above, this does NOT need a differently-named
    # source variable: .env.example's DJANGO_CSRF_TRUSTED_ORIGINS is already the correct
    # PRIMARY-checkout dev value (no stale cross-profile value to accidentally inherit —
    # contrast UVICORN_FORWARDED_ALLOW_IPS, which .env.example defines for the FINALE
    # subnet, so reusing that name here would have silently picked up the wrong stack's
    # value). Exporting the SAME name Django/compose already read is enough, and Compose's
    # shell-environment interpolation outranks the value it would otherwise read from
    # `--env-file .env` (verified empirically for this fix, since the precedence is easy to
    # get backwards from docs alone: an unset shell var falls through to the `.env` file's
    # literal value, a set one wins over it — same "operator's own override always wins"
    # convention as COMPOSE_PROJECT_NAME/NGINX_HTTP_PORT above).
    if [[ -z "${DJANGO_CSRF_TRUSTED_ORIGINS:-}" ]]; then
      export DJANGO_CSRF_TRUSTED_ORIGINS="https://localhost:${NGINX_HTTPS_PORT},http://localhost:${NGINX_HTTP_PORT}"
    fi

    note "isolated nginx ports: ${NGINX_HTTP_PORT} / ${NGINX_HTTPS_PORT}"
    note "isolated api network subnet: ${UVICORN_DEV_FORWARDED_ALLOW_IPS}"
    note "isolated CSRF trusted origins: ${DJANGO_CSRF_TRUSTED_ORIGINS}"
  fi
fi

echo "== preflight"

command -v docker >/dev/null || fail "docker is not installed"
docker compose version >/dev/null 2>&1 || fail "docker compose v2 is not available"
docker info >/dev/null 2>&1 || fail "the docker daemon is not running"
note "docker $(docker version --format '{{.Server.Version}}') / compose $(docker compose version --short)"

if [[ ! -f "${REPO_ROOT}/.env" ]]; then
  fail ".env is missing. Run: cp .env.example .env   (then fill in the REPLACE_ME values)"
fi
note ".env present"

if grep -q 'REPLACE_ME' "${REPO_ROOT}/.env"; then
  echo "  warning: .env still contains REPLACE_ME placeholders" >&2
fi

if [[ ! -f "${REPO_ROOT}/infrastructure/compose/nginx/certs/server.crt" ]]; then
  note "generating self-signed development certificates"
  "${REPO_ROOT}/infrastructure/scripts/gen-dev-certs.sh" >/dev/null
fi
note "TLS material present"

missing=()
for d in apps/control-api apps/command-center; do
  [[ -d "${REPO_ROOT}/${d}" ]] || missing+=("${d}")
done
if (( ${#missing[@]} > 0 )); then
  cat >&2 <<EOF

blocked: these bind-mount sources do not exist yet:
$(printf '  - %s\n' "${missing[@]}")

Docker would create them as root-owned empty directories, which then breaks the developer
who owns them. Either wait for that work to land, or start a subset:

  infrastructure/scripts/dev-up.sh db redis nginx

EOF
  # Only hard-fail when the caller asked for everything.
  if [[ $# -eq 0 ]]; then exit 1; fi
fi

profiles=()
if [[ "${DEV_UP_WORKER:-0}" == "1" ]]; then
  profiles+=(--profile worker)
fi

echo
echo "== docker compose up"
set -x
docker compose \
  --env-file "${REPO_ROOT}/.env" \
  -f "${COMPOSE_FILE}" \
  ${profiles[@]+"${profiles[@]}"} \
  up -d --remove-orphans "$@"
set +x

echo
docker compose --env-file "${REPO_ROOT}/.env" -f "${COMPOSE_FILE}" ps

# #230: these were a literal heredoc; now interpolated, because a linked worktree's ports
# are not 8080/8443 any more. `${VAR:-default}` matches the primary checkout unchanged.
http_port="${NGINX_HTTP_PORT:-8080}"
https_port="${NGINX_HTTPS_PORT:-8443}"
cat <<EOF

  Command Center   https://localhost:${https_port}/          (self-signed: accept the warning once)
  API              https://localhost:${https_port}/api/v1/
  Event stream     https://localhost:${https_port}/api/v1/missions/<id>/events
  Django admin     https://localhost:${https_port}/admin/    (dev only; 404 in the finale profile)
  nginx liveness   http://localhost:${http_port}/healthz

  Test SSE THROUGH nginx, never against the API directly:
      infrastructure/scripts/smoke-sse.sh

  Logs:  docker compose -f infrastructure/compose/docker-compose.yml logs -f nginx
  Down:  docker compose -f infrastructure/compose/docker-compose.yml down
  Down + wipe data:  ... down -v
EOF
