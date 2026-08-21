#!/usr/bin/env bash
# Bring up the FINALE stack.
#
#   infrastructure/scripts/finale-up.sh
#
# UNVERIFIED as of D1: this has never been run end to end, because apps/command-center/
# does not exist and therefore neither does its build output. The compose file validates
# and its nginx profile is tested; nothing else is.
#
# The finale profile differs from development in ways that are all security-relevant, and
# the preflight below checks each one rather than trusting that the right file got mounted.
# Full list in docs/06-operations/71-ingress-and-proxy-contract.md §5.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infrastructure/compose/docker-compose.finale.yml"

fail() { printf '\033[31mblocked:\033[0m %s\n' "$1" >&2; exit 1; }
note() { printf '  %s\n' "$1"; }

# See dev-up.sh's matching comment: docker-compose.finale.yml pins
# `name: brahmadatta-finale`, so a worktree checkout bringing this up
# independently of the primary checkout would silently share containers,
# networks, and named volumes with it. Same fix, same reasoning.
#
# #230: same fast-follow as dev-up.sh — COMPOSE_PROJECT_NAME alone does not isolate
# every `container_name:`, nginx's published host port, or the `api` network's subnet in
# docker-compose.finale.yml either. See that file's header comment for the full reasoning.
if [[ -z "${COMPOSE_PROJECT_NAME:-}" ]]; then
  git_dir="$(git -C "${REPO_ROOT}" rev-parse --git-dir)"
  common_dir="$(git -C "${REPO_ROOT}" rev-parse --git-common-dir)"
  if [[ "${git_dir}" != "${common_dir}" ]]; then
    worktree_hash="$(printf '%s' "${REPO_ROOT}" | shasum | cut -c1-8)"
    export COMPOSE_PROJECT_NAME="brahmadatta-finale-${worktree_hash}"
    note "linked worktree detected — isolated compose project: ${COMPOSE_PROJECT_NAME}"

    # Same derivation as dev-up.sh, different offset ranges so a worktree running BOTH
    # stacks at once (dev-up.sh and finale-up.sh from the same checkout) does not have its
    # own dev and finale ports/subnets collide with each other.
    worktree_hash_dec="$((16#${worktree_hash}))"
    if [[ -z "${NGINX_FINALE_HTTP_PORT:-}" ]]; then
      export NGINX_FINALE_HTTP_PORT=$(( 40000 + (worktree_hash_dec % 10000) ))
    fi
    if [[ -z "${UVICORN_FORWARDED_ALLOW_IPS:-}" ]]; then
      export UVICORN_FORWARDED_ALLOW_IPS="10.91.$(( (worktree_hash_dec % 250) + 1 )).0/24"
    fi
    note "isolated nginx port: ${NGINX_FINALE_HTTP_PORT}"
    note "isolated api network subnet: ${UVICORN_FORWARDED_ALLOW_IPS}"
  fi
fi

echo "== finale preflight"

docker info >/dev/null 2>&1 || fail "the docker daemon is not running"

[[ -f "${REPO_ROOT}/.env" ]] || fail ".env is missing. Write it on this host by hand, mode 0600 — never copy one from a laptop."

if grep -q 'REPLACE_ME' "${REPO_ROOT}/.env"; then
  fail ".env still contains REPLACE_ME placeholders. The finale stack will not start with defaults."
fi
note ".env present and has no placeholders"

perms="$(stat -f '%Lp' "${REPO_ROOT}/.env" 2>/dev/null || stat -c '%a' "${REPO_ROOT}/.env")"
if [[ "${perms}" != "600" ]]; then
  echo "  warning: .env is mode ${perms}; it should be 600" >&2
fi

[[ -d "${REPO_ROOT}/apps/command-center/dist" ]] \
  || fail "apps/command-center/dist is missing. Run 'npm ci && npm run build' in apps/command-center first — the finale profile serves a built site, not a dev server."
note "Astro build output present"

note "stage origin is http://localhost:${NGINX_FINALE_HTTP_PORT:-8080} — no TLS certificate is required"

echo
echo "== validating the finale configuration before anything starts"
docker compose --env-file "${REPO_ROOT}/.env" -f "${COMPOSE_FILE}" config --quiet
note "compose config valid"
"${REPO_ROOT}/infrastructure/scripts/nginx-validate.sh" finale >/dev/null
note "nginx -t (finale profile) passed"

echo
echo "== confirming every image this run needs is already in the local Docker image store"
# The finale host has NO internet access at demo time (competition constraint) — every
# image below (pinned upstream pulls AND this repo's own `build:` images: control-api,
# worker, db) must already have been pulled/built on THIS SAME Docker daemon while it was
# still online. `docker compose up` resolves an already-cached digest/tag from the local
# store with no registry round-trip, and will not silently rebuild an image that already
# exists — but if any image below is genuinely absent, `up` fails with a raw network error
# mid-attempt instead of a clear preflight message, which is worse to discover on stage
# than here. This check does not build or pull anything itself.
missing_images=0
while IFS= read -r image_ref; do
  [[ -z "${image_ref}" ]] && continue
  if ! docker image inspect "${image_ref}" >/dev/null 2>&1; then
    printf '  \033[31mmissing locally:\033[0m %s\n' "${image_ref}" >&2
    missing_images=1
  fi
done < <(docker compose --env-file "${REPO_ROOT}/.env" -f "${COMPOSE_FILE}" config --images "$@")
if [[ "${missing_images}" -eq 1 ]]; then
  fail "one or more images above are not in the local Docker image store. Pull/build them all WHILE ONLINE, before this host goes offline: 'docker compose --env-file .env -f ${COMPOSE_FILE} build' for this repo's own images (control-api/worker/db), plus a normal 'docker compose ... up -d' once (or 'docker compose ... pull') for the pinned upstream images (nginx, redis, ollama). This check only looks; it never pulls or builds."
fi
note "every image this run needs is already present locally"

echo
echo "== docker compose up"
docker compose --env-file "${REPO_ROOT}/.env" -f "${COMPOSE_FILE}" up -d --remove-orphans "$@"

echo
docker compose --env-file "${REPO_ROOT}/.env" -f "${COMPOSE_FILE}" ps

echo
echo "== post-start assertions"
sleep 5
# #230: the finale host port is parameterized (NGINX_FINALE_HTTP_PORT, default 8080 —
# see docker-compose.finale.yml's nginx `ports:` block), so these assertions probe
# whichever port this run actually published, not always literal 8080.
finale_http_port="${NGINX_FINALE_HTTP_PORT:-8080}"
admin_code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${finale_http_port}/admin/" || echo 000)"
if [[ "${admin_code}" != "404" ]]; then
  printf '  \033[31mFAIL\033[0m /admin/ returned %s, expected 404.\n' "${admin_code}" >&2
  echo "  The finale admin block is not in effect. Do not run the demo until it is." >&2
  exit 1
fi
note "/admin/ returns 404 — finale admin block is in effect"

hsts="$(curl -sI "http://127.0.0.1:${finale_http_port}/" | grep -ci 'strict-transport-security' || true)"
[[ "${hsts}" -eq 0 ]] || fail "HSTS header is present on localhost; the finale must not trigger browser TLS pinning"
note "HSTS absent — localhost will not be forced back to HTTPS"

health_code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${finale_http_port}/healthz" || echo 000)"
[[ "${health_code}" == "200" ]] || fail "/healthz returned ${health_code}, expected 200"
note "http://localhost:${finale_http_port}/healthz is reachable"

echo
echo "  Rollback:  docs/06-operations/71-ingress-and-proxy-contract.md §7"
