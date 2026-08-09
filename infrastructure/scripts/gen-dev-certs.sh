#!/usr/bin/env bash
# Generate a self-signed TLS certificate for local development.
#
# Development only. The finale TLS path is described in
# docs/06-operations/71-ingress-and-proxy-contract.md.
#
# Output lands in infrastructure/compose/nginx/certs/, which is gitignored twice over.
# Nothing this script writes may ever be committed.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CERT_DIR="${REPO_ROOT}/infrastructure/compose/nginx/certs"
DAYS="${DEV_CERT_DAYS:-365}"

mkdir -p "${CERT_DIR}"

if [[ -f "${CERT_DIR}/server.crt" && -f "${CERT_DIR}/server.key" && "${1:-}" != "--force" ]]; then
  echo "certs already present in ${CERT_DIR} (pass --force to regenerate)"
  # Re-normalize permissions even on the early-exit path: a key generated before the
  # world-readable fix below (chmod 600) would otherwise sit there forever, since nothing
  # else ever revisits it. See the chmod comment below for why 644 is correct here.
  chmod 644 "${CERT_DIR}/server.key" "${CERT_DIR}/server.crt"
  openssl x509 -in "${CERT_DIR}/server.crt" -noout -subject -enddate
  exit 0
fi

cat > "${CERT_DIR}/openssl.cnf" <<'EOF'
[req]
distinguished_name = dn
x509_extensions    = v3_req
prompt             = no

[dn]
CN = localhost
O  = Brahmadatta AI (development only)

[v3_req]
basicConstraints = CA:FALSE
keyUsage         = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName   = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = brahmadatta.localhost
DNS.3 = nginx
IP.1  = 127.0.0.1
IP.2  = ::1
EOF

openssl req -x509 -nodes \
  -newkey rsa:2048 \
  -days "${DAYS}" \
  -keyout "${CERT_DIR}/server.key" \
  -out    "${CERT_DIR}/server.crt" \
  -config "${CERT_DIR}/openssl.cnf" >/dev/null 2>&1

# Not 600. This key is bind-mounted read-only into nginxinc/nginx-unprivileged, which
# runs nginx as uid 101 (the `nginx` user), not as whoever generated this file — the CI
# runner's user locally, and the same is true for any developer running docker-compose.yml
# directly on Linux (macOS's Docker Desktop bind-mount layer maps ownership per-accessing-
# process and hides this; a real Linux bind mount does not — the container sees the host's
# actual UID/GID and honours the host's actual permission bits). 600 leaves the key
# readable only by the host user that ran this script, so `nginx -t` and every real
# container boot fails: "cannot load certificate key ... Permission denied". World-readable
# is fine here specifically because this key secures nothing: self-signed, CN=localhost,
# regenerated on every run, gitignored twice over, explicitly out of the production TLS
# path (docs/06-operations/71-ingress-and-proxy-contract.md), and never leaves local disk
# or an ephemeral CI runner.
chmod 644 "${CERT_DIR}/server.key"
chmod 644 "${CERT_DIR}/server.crt"
rm -f "${CERT_DIR}/openssl.cnf"

echo "wrote ${CERT_DIR}/server.crt and server.key"
openssl x509 -in "${CERT_DIR}/server.crt" -noout -subject -enddate -ext subjectAltName
