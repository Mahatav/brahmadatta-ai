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
#
# #239: this script brings up `orchestrator` and (as of this fix) `worker`, both compose
# services. It does NOT start `fuzz-worker` — D-073's bare-metal-only FUZZ/MINIMIZE worker,
# deliberately not a compose service at all (no `docker` CLI in any container, D-036) — and
# it is not this script's job to. See the reminder printed at the end of this run, and
# infrastructure/scripts/run-fuzz-worker.sh's own header for the full reasoning and for
# `fuzz-worker`'s still-open Postgres-reachability question on a real finale host.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infrastructure/compose/docker-compose.finale.yml"

fail() { printf '\033[31mblocked:\033[0m %s\n' "$1" >&2; exit 1; }
note() { printf '  %s\n' "$1"; }

# #239: `worker` claims every job-backed mission stage EXCEPT FUZZ/MINIMIZE (see
# docker-compose.finale.yml's own `worker` service comment for the D-073 reasoning). It is
# `profiles: ["worker"]`-gated in the compose file, same idiom as dev-up.sh's DEV_UP_WORKER
# — but unlike dev (D-031: opt-in there because no queue framework existed yet), the finale
# profile's whole point is a real, unattended, timed rehearsal (#57): a demo host that comes
# up with `orchestrator` advancing missions past VALIDATING but no `worker` to claim the job
# behind that stage is not a smaller version of a working demo, it is a stalled one — this
# is exactly the D-122 gap #239 filed. So the default here is inverted from dev-up.sh's:
# worker is ON unless explicitly opted out, not off unless explicitly opted in.
# `FINALE_UP_WORKER=0` is the escape hatch for the rare case an operator wants nginx/API up
# without a worker (e.g. isolating a control-api-only issue) — not for routine use.
finale_profiles=(--profile worker)
if [[ "${FINALE_UP_WORKER:-1}" == "0" ]]; then
  finale_profiles=()
  echo "  FINALE_UP_WORKER=0 — worker profile intentionally excluded. Missions will stall" >&2
  echo "  past VALIDATING with nothing claiming job-backed stages. Debugging use only." >&2
fi

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
# `--profile` is a top-level `docker compose` flag (see `docker compose --help`), not a
# subcommand option — it MUST precede `config`/`up`/`ps`, not follow them. Confirmed live:
# `docker compose ... config --images --profile worker` fails "unknown flag: --profile";
# `docker compose --profile worker ... config --images` works. Every invocation below
# places `${finale_profiles[@]}` accordingly, same placement dev-up.sh already uses for
# its own `${profiles[@]}` ahead of `up`.
docker compose --env-file "${REPO_ROOT}/.env" -f "${COMPOSE_FILE}" \
  ${finale_profiles[@]+"${finale_profiles[@]}"} config --quiet
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
done < <(docker compose --env-file "${REPO_ROOT}/.env" -f "${COMPOSE_FILE}" \
  ${finale_profiles[@]+"${finale_profiles[@]}"} config --images "$@")
if [[ "${missing_images}" -eq 1 ]]; then
  fail "one or more images above are not in the local Docker image store. Pull/build them all WHILE ONLINE, before this host goes offline: 'docker compose --env-file .env -f ${COMPOSE_FILE} build' for this repo's own images (control-api/worker/db), plus a normal 'docker compose ... up -d' once (or 'docker compose ... pull') for the pinned upstream images (nginx, redis, ollama). This check only looks; it never pulls or builds."
fi
note "every image this run needs is already present locally"

echo
echo "== docker compose up"
docker compose --env-file "${REPO_ROOT}/.env" -f "${COMPOSE_FILE}" \
  ${finale_profiles[@]+"${finale_profiles[@]}"} up -d --remove-orphans "$@"

echo
docker compose --env-file "${REPO_ROOT}/.env" -f "${COMPOSE_FILE}" \
  ${finale_profiles[@]+"${finale_profiles[@]}"} ps

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

# #239: fuzz-worker (D-073) is bare-metal, not a compose service — nothing docker-compose-
# side ever starts it, and this script cannot reliably supervise a process outside its own
# tree, so this is a soft, informational check only, never a `fail`. `pgrep` is present on
# both the macOS and Linux hosts this repo targets; if it is missing for some other reason,
# skip the check rather than block the whole run over it.
if command -v pgrep >/dev/null 2>&1; then
  if pgrep -f 'manage\.py run_worker --kinds FUZZ' >/dev/null 2>&1; then
    note "fuzz-worker (bare-metal, D-073) appears to be running"
  else
    echo "  note: fuzz-worker (bare-metal, D-073) does not appear to be running." >&2
    echo "        FUZZ/MINIMIZE jobs will never be claimed without it. Start it separately:" >&2
    echo "        FUZZ_WORKER_PROFILE=finale infrastructure/scripts/run-fuzz-worker.sh" >&2
    echo "        (see that script's own header for its still-open Postgres-reachability" >&2
    echo "        question on a real finale host, tracked in .project/decisions.md's D-073" >&2
    echo "        follow-up entry — not resolved by this script.)" >&2
  fi
fi

# #298: same soft/informational shape as the fuzz-worker note above. `model-host` is
# `profiles: ["model"]`-gated — this script's own `${finale_profiles[@]}` never
# includes it, and per this script's own `--profile` placement constraint (see the
# "validating the finale configuration" comment above: `--profile` must precede the
# subcommand, so `"$@"` — appended AFTER `config`/`up` throughout this script — could
# not carry `--profile model` even if an operator tried), the only way `model-host`
# is running here is a separate, independent `docker compose --profile model up -d`
# against this same project. Checked directly by container name (not `docker compose
# ps`, which is scoped to the CURRENT invocation's active profiles and would not see
# a service started under a different one) so this note still fires either way.
model_host_container="${COMPOSE_PROJECT_NAME:-brahmadatta-finale}-model-host"
if docker ps --filter "name=^${model_host_container}$" --filter "status=running" --format '{{.Names}}' 2>/dev/null | grep -qx "${model_host_container}"; then
  echo "  note: ${model_host_container} is up. Before a mission depends on it, run the" >&2
  echo "        #298 memory pre-flight explicitly — this is NOT part of this script or" >&2
  echo "        model-host's own healthcheck (see docker-compose.finale.yml's model-host" >&2
  echo "        comment for why: ollama list proves the server answers, not that the" >&2
  echo "        model fits in MODEL_HOST_MEM_LIMIT):" >&2
  echo "        python -m gateway.tools.model_prep doctor --check-memory \\" >&2
  echo "          --endpoint http://model-host:11434/api --bearer-token \"\${MODEL_HOST_BEARER_TOKEN}\"" >&2
  echo "        A clear 'insufficient-memory' result here is a capacity decision for" >&2
  echo "        whoever owns this hardware (model choice / MODEL_HOST_MEM_LIMIT / host" >&2
  echo "        RAM, tracked in .project/decisions.md — not resolved by this script) —" >&2
  echo "        not something to discover live during a mission." >&2
fi

echo
echo "  Rollback:  docs/06-operations/71-ingress-and-proxy-contract.md §7"
