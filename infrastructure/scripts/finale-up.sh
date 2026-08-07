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

[[ -f "${REPO_ROOT}/infrastructure/compose/nginx/certs/server.crt" ]] \
  || fail "no TLS certificate at infrastructure/compose/nginx/certs/server.crt"
note "TLS material present"
openssl x509 -in "${REPO_ROOT}/infrastructure/compose/nginx/certs/server.crt" -noout -subject -enddate | sed 's/^/  /'

echo
echo "== validating the finale configuration before anything starts"
docker compose --env-file "${REPO_ROOT}/.env" -f "${COMPOSE_FILE}" config --quiet
note "compose config valid"
"${REPO_ROOT}/infrastructure/scripts/nginx-validate.sh" finale >/dev/null
note "nginx -t (finale profile) passed"

echo
echo "== docker compose up"
docker compose --env-file "${REPO_ROOT}/.env" -f "${COMPOSE_FILE}" up -d --remove-orphans "$@"

echo
docker compose --env-file "${REPO_ROOT}/.env" -f "${COMPOSE_FILE}" ps

echo
echo "== post-start assertions"
sleep 5
admin_code="$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8443/admin/ || echo 000)"
if [[ "${admin_code}" != "404" ]]; then
  printf '  \033[31mFAIL\033[0m /admin/ returned %s, expected 404.\n' "${admin_code}" >&2
  echo "  The finale admin block is not in effect. Do not run the demo until it is." >&2
  exit 1
fi
note "/admin/ returns 404 — finale admin block is in effect"

hsts="$(curl -skI https://127.0.0.1:8443/ | grep -ci 'strict-transport-security' || true)"
[[ "${hsts}" -ge 1 ]] || fail "HSTS header is missing; the dev nginx profile may be mounted"
note "HSTS present — finale nginx profile is mounted"

echo
echo "  Rollback:  docs/06-operations/71-ingress-and-proxy-contract.md §7"
