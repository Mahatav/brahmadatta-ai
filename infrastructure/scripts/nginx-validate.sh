#!/usr/bin/env bash
# Validate the committed nginx configuration with `nginx -t`, without needing the rest of
# the stack up. Run for both profiles:
#
#   infrastructure/scripts/nginx-validate.sh dev
#   infrastructure/scripts/nginx-validate.sh finale
#   infrastructure/scripts/nginx-validate.sh            # both
#
# Two things this script has to fake, and why:
#
#  1. --add-host. nginx resolves `server control-api:8000;` inside an upstream block at
#     config-parse time and hard-fails with "host not found in upstream" if the name does
#     not resolve. Under compose those names come from Docker's DNS. Standalone they do
#     not, so they are pointed at 127.0.0.1 purely to let the parser finish. This does not
#     weaken the check — every directive is still parsed and validated.
#
#  2. Certificates. `nginx -t` opens and parses ssl_certificate. Self-signed dev material
#     is generated first if it is missing.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NGINX_DIR="${REPO_ROOT}/infrastructure/compose/nginx"

# Pinned by digest — see the same pin in infrastructure/compose/docker-compose.yml.
NGINX_IMAGE="nginxinc/nginx-unprivileged@sha256:0c79d56aee561a1d81c63f00eee5fb5fe29279560cdc55e91425133104c7fbe6"

if [[ ! -f "${NGINX_DIR}/certs/server.crt" ]]; then
  "${REPO_ROOT}/infrastructure/scripts/gen-dev-certs.sh"
fi

validate_profile() {
  local profile="$1" admin_include
  case "${profile}" in
    dev)    admin_include="admin-allow.conf" ;;
    finale) admin_include="admin-deny.conf"  ;;
    *) echo "unknown profile: ${profile}" >&2; return 2 ;;
  esac

  echo "=== nginx -t · profile: ${profile} ==="
  # D-088 (T0): conf.d.${profile}/ became templates.${profile}/ — a *.template file, not
  # a ready-to-parse conf file, since the ingress now injects CONTROL_API_OPERATOR_TOKEN
  # via the image's own envsubst entrypoint step. Mounted at /etc/nginx/templates (the
  # entrypoint's default template dir), NOT /etc/nginx/conf.d — `nginx -t` still runs the
  # entrypoint.d scripts before parsing (docker-entrypoint.sh only skips them when the
  # command is not `nginx`/`nginx-debug`, and it is here), so the template renders into
  # the image's own writable /etc/nginx/conf.d before `nginx -t` ever reads it. A fake,
  # obviously-non-production token is enough to prove the substitution and the resulting
  # config both parse; the real value is never used by this script.
  docker run --rm \
    --add-host control-api:127.0.0.1 \
    --add-host command-center:127.0.0.1 \
    -e CONTROL_API_OPERATOR_TOKEN="nginx-validate-not-a-real-token-0123456789ab" \
    -e NGINX_ENVSUBST_FILTER="^CONTROL_API_OPERATOR_TOKEN$" \
    -v "${NGINX_DIR}/nginx.conf:/etc/nginx/nginx.conf:ro" \
    -v "${NGINX_DIR}/includes:/etc/nginx/includes:ro" \
    -v "${NGINX_DIR}/profile/${admin_include}:/etc/nginx/profile/admin.conf:ro" \
    -v "${NGINX_DIR}/templates.${profile}:/etc/nginx/templates:ro" \
    -v "${NGINX_DIR}/certs:/etc/nginx/certs:ro" \
    "${NGINX_IMAGE}" nginx -t
}

if [[ $# -eq 0 ]]; then
  validate_profile dev
  validate_profile finale
else
  validate_profile "$1"
fi
