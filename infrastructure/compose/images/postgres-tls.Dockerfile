# Postgres with TLS enabled, for the finale profile's brahmadatta.E005 check
# (APP_ENV=finale requires DATABASE_URL to carry sslmode=require or verify-full — a
# plaintext connection to the store holding authorization statements and verification
# records is exactly what that check exists to catch).
#
# Baked in at build time, not bind-mounted at runtime: postgres refuses to start if
# server.key is not owned by the postgres user at mode 0600, and a bind mount from a
# macOS host cannot reliably deliver that ownership into the container's user namespace.
# Copying the cert in as this Dockerfile's own COPY + chown/chmod, as `postgres`, sidesteps
# the bind-mount ownership problem entirely — the same reasoning as control-api.Dockerfile's
# baked-in-not-mounted source for the finale target.
ARG POSTGRES_DIGEST=postgres@sha256:ef257d85f76e48da1c64832459b59fcaba1a4dac97bf5d7450c77753542eee94
FROM ${POSTGRES_DIGEST}

# Paths are relative to the build context (infrastructure/compose/, set by the `db`
# service's `build:` block in docker-compose.finale.yml). Run
# infrastructure/scripts/gen-postgres-cert.sh before building — it writes exactly here.
COPY --chown=postgres:postgres postgres/certs/server.crt /etc/postgresql/server.crt
COPY --chown=postgres:postgres postgres/certs/server.key /etc/postgresql/server.key
RUN chmod 600 /etc/postgresql/server.key && chmod 644 /etc/postgresql/server.crt

CMD ["postgres", "-c", "ssl=on", "-c", "ssl_cert_file=/etc/postgresql/server.crt", "-c", "ssl_key_file=/etc/postgresql/server.key"]
