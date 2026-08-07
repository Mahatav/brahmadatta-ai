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

cat <<'EOF'

  Command Center   https://localhost:8443/          (self-signed: accept the warning once)
  API              https://localhost:8443/api/v1/
  Event stream     https://localhost:8443/api/v1/missions/<id>/events
  Django admin     https://localhost:8443/admin/    (dev only; 404 in the finale profile)
  nginx liveness   http://localhost:8080/healthz

  Test SSE THROUGH nginx, never against the API directly:
      infrastructure/scripts/smoke-sse.sh

  Logs:  docker compose -f infrastructure/compose/docker-compose.yml logs -f nginx
  Down:  docker compose -f infrastructure/compose/docker-compose.yml down
  Down + wipe data:  ... down -v
EOF
