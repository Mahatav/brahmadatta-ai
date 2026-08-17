#!/usr/bin/env bash
# Generate a self-signed TLS certificate for the finale profile's Postgres image.
#
# Required by brahmadatta.E005: APP_ENV=finale refuses to start unless DATABASE_URL is
# encrypted (sslmode=require or better). See infrastructure/compose/images/postgres-tls.Dockerfile
# for why this is baked into the image at build time rather than bind-mounted — Postgres
# refuses to start if server.key is not owned by the postgres user at mode 600, and a real
# Linux bind mount (unlike macOS Docker Desktop, which hides this) delivers the *host's*
# ownership into the container, not the image's declared user. Baking it in at build time
# with COPY --chown sidesteps the problem instead of working around it.
#
# Output lands in infrastructure/compose/postgres/certs/, gitignored twice over exactly
# like infrastructure/compose/nginx/certs/. Nothing this script writes may ever be committed.
#
# Development/finale-rehearsal only. A real finale deployment on a rented box writes its own
# operational TLS material by hand, same as .env — see docs/06-operations/71-ingress-and-proxy-contract.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CERT_DIR="${REPO_ROOT}/infrastructure/compose/postgres/certs"
DAYS="${DEV_CERT_DAYS:-365}"

mkdir -p "${CERT_DIR}"

if [[ -f "${CERT_DIR}/server.crt" && -f "${CERT_DIR}/server.key" && "${1:-}" != "--force" ]]; then
  echo "certs already present in ${CERT_DIR} (pass --force to regenerate)"
  openssl x509 -in "${CERT_DIR}/server.crt" -noout -subject -enddate
  exit 0
fi

cat > "${CERT_DIR}/openssl.cnf" <<'EOF'
[req]
distinguished_name = dn
x509_extensions    = v3_req
prompt             = no

[dn]
CN = db
O  = Brahmadatta AI (finale rehearsal only)

[v3_req]
basicConstraints = CA:FALSE
keyUsage         = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName   = @alt_names

[alt_names]
DNS.1 = db
DNS.2 = localhost
IP.1  = 127.0.0.1
EOF

openssl req -x509 -nodes \
  -newkey rsa:2048 \
  -days "${DAYS}" \
  -keyout "${CERT_DIR}/server.key" \
  -out    "${CERT_DIR}/server.crt" \
  -config "${CERT_DIR}/openssl.cnf" >/dev/null 2>&1

# 600, not 644. Unlike nginx's cert, nothing bind-mounts this one — the Dockerfile COPYs it
# into the image at build time with --chown=postgres:postgres and its own chmod 600, so the
# host-side file only ever needs to be readable by whoever runs `docker compose build`.
# Locking it down here is free and matches the general rule (world-readable is a documented,
# deliberate exception on the nginx cert specifically, not a default to reach for).
chmod 600 "${CERT_DIR}/server.key"
chmod 644 "${CERT_DIR}/server.crt"
rm -f "${CERT_DIR}/openssl.cnf"

echo "wrote ${CERT_DIR}/server.crt and server.key"
openssl x509 -in "${CERT_DIR}/server.crt" -noout -subject -enddate -ext subjectAltName
