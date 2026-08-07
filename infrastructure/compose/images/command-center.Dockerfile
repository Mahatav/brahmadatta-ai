# syntax=docker/dockerfile:1.7
#
# Command Center image — the Astro build, served as static files by nginx.
#
# Build context is apps/command-center/ (owned by the frontend developer). As of D1 that
# directory does not exist yet, so this file is a CONTRACT and is marked unverified in the
# D1 handoff: it has not been built. It states exactly what the frontend must provide.
#
# Contract with apps/command-center/:
#   - package.json + package-lock.json at the context root
#   - `npm run build` writes a static site to ./dist
#   - Node 22
#
# The DEV profile does not use this file at all. docker-compose.yml runs the Astro dev
# server straight from the pinned node image with the source bind-mounted, because a dev
# server that needs an image rebuild on every dependency change is a dev server nobody
# uses.
#
# Targets:
#   build  — produces /app/dist
#   static — an nginx image with dist/ baked in. Used only if the finale ever needs a
#            self-contained frontend image; docker-compose.finale.yml instead mounts the
#            build output into the shared ingress, which keeps one nginx in the stack.

# node:22.20-alpine, pinned by multi-arch index digest.
FROM node@sha256:dbcedd8aeab47fbc0f4dd4bffa55b7c3c729a707875968d467aaaea42d6225af AS build

WORKDIR /app

# npm ci, not npm install: it fails loudly when package-lock.json disagrees with
# package.json instead of silently resolving a different tree than the one that was tested.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# The node image already ships a `node` user (uid 1000). Nothing here runs as root.
USER node


# ---------------------------------------------------------------------------
FROM nginxinc/nginx-unprivileged@sha256:0c79d56aee561a1d81c63f00eee5fb5fe29279560cdc55e91425133104c7fbe6 AS static

COPY --from=build /app/dist /usr/share/nginx/html
USER 101:101
EXPOSE 8080
