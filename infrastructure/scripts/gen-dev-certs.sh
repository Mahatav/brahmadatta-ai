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

chmod 600 "${CERT_DIR}/server.key"
chmod 644 "${CERT_DIR}/server.crt"
rm -f "${CERT_DIR}/openssl.cnf"

echo "wrote ${CERT_DIR}/server.crt and server.key"
openssl x509 -in "${CERT_DIR}/server.crt" -noout -subject -enddate -ext subjectAltName
