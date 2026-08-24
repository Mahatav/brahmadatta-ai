#!/usr/bin/env bash
# Prove, from INSIDE the running control-api container of the FINALE profile, that a
# hosted inference API is unreachable.
#
#   infrastructure/scripts/finale-egress-evidence.sh
#
# This is the evidence the security review asked for and re-runs before #78 closes. It is
# deliberately not the same test as infrastructure/scripts/egress-test.sh:
#
#   egress-test.sh          reads the compose topology and probes the networks. Runs with
#                           nothing built. Catches a compose-file regression.
#   this script             execs into the real, running, finale-profile control-api and
#                           tries to open a socket. Catches everything else — a stray
#                           `docker network connect`, a host-level route, an image that
#                           ships a proxy, a difference between what compose says and what
#                           Docker did.
#
# The Critical was found by connecting to api.openai.com from inside the container and
# getting an answer. The only refutation of that is the same action, from the same place,
# failing. Not an inspection of configuration.
#
# It leaves the stack down afterwards, and it prints the raw container output before it
# prints a verdict, so the verdict can be checked against the evidence rather than trusted.
#
# #234: container names below are `${COMPOSE_PROJECT_NAME:-brahmadatta-finale}-<service>`,
# never a bare literal — PR #219/#233 (D-098/D-099/#230) established that a linked worktree
# isolates its own finale stack under `brahmadatta-finale-<worktree-hash>`, and a script that
# still `docker inspect`s the literal `brahmadatta-finale-control-api` against an isolated
# worktree's stack does not fail, it silently finds nothing — `docker inspect` on a
# nonexistent name errors, but this script never checked that error, so the SEC-R3 evidence
# it produces would be no evidence at all. Same worktree-detection block as finale-up.sh
# (and dev-up.sh's own matching copy), duplicated here rather than pulled into a shared file
# — see finale-up.sh's header comment for why duplication was already chosen over a new
# shared mechanism for this exact block.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infrastructure/compose/docker-compose.finale.yml"

if [[ -z "${COMPOSE_PROJECT_NAME:-}" ]]; then
  git_dir="$(git -C "${REPO_ROOT}" rev-parse --git-dir)"
  common_dir="$(git -C "${REPO_ROOT}" rev-parse --git-common-dir)"
  if [[ "${git_dir}" != "${common_dir}" ]]; then
    worktree_hash="$(printf '%s' "${REPO_ROOT}" | shasum | cut -c1-8)"
    export COMPOSE_PROJECT_NAME="brahmadatta-finale-${worktree_hash}"
    echo "  linked worktree detected — isolated compose project: ${COMPOSE_PROJECT_NAME}"
    worktree_hash_dec="$((16#${worktree_hash}))"
    if [[ -z "${NGINX_FINALE_HTTP_PORT:-}" ]]; then
      export NGINX_FINALE_HTTP_PORT=$(( 40000 + (worktree_hash_dec % 10000) ))
    fi
    if [[ -z "${UVICORN_FORWARDED_ALLOW_IPS:-}" ]]; then
      export UVICORN_FORWARDED_ALLOW_IPS="10.91.$(( (worktree_hash_dec % 250) + 1 )).0/24"
    fi
  fi
fi

# The one name every container below is derived from — matches
# docker-compose.finale.yml's own `container_name: ${COMPOSE_PROJECT_NAME:-brahmadatta-finale}-<service>`
# on every service exactly, not a separately-maintained copy of the same default.
CONTROL_API_CONTAINER="${COMPOSE_PROJECT_NAME:-brahmadatta-finale}-control-api"

COMPOSE=(docker compose --env-file "${REPO_ROOT}/.env" -f "${COMPOSE_FILE}")

rc=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; rc=1; }

# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
  echo
  echo "== tearing the finale stack down"
  "${COMPOSE[@]}" down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [ ! -d "${REPO_ROOT}/apps/control-api" ]; then
  echo "blocked: apps/control-api does not exist in this tree, so there is no container to" >&2
  echo "         exec into. Run this from a tree that has the control API." >&2
  exit 2
fi
if [ ! -f "${REPO_ROOT}/.env" ]; then
  echo "blocked: .env is missing." >&2
  exit 2
fi

echo "== starting the FINALE profile"
"${COMPOSE[@]}" up -d --build control-api db redis 2>&1 | tail -5

echo
echo "== container identity and network attachments (from Docker, not from the compose file)"
docker inspect "${CONTROL_API_CONTAINER}" \
  --format '  networks: {{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}'
docker inspect "${CONTROL_API_CONTAINER}" \
  --format '  user: {{.Config.User}}  read_only: {{.HostConfig.ReadonlyRootfs}}  privileged: {{.HostConfig.Privileged}}'
echo "  gateway per network:"
docker inspect "${CONTROL_API_CONTAINER}" \
  --format '{{range $k, $v := .NetworkSettings.Networks}}    {{$k}}: gateway="{{$v.Gateway}}"{{"\n"}}{{end}}'
echo "  routing table inside the container:"
"${COMPOSE[@]}" exec -T control-api sh -c 'cat /proc/net/route' 2>/dev/null | sed 's/^/    /' || true

echo
echo "== attempting outbound FROM INSIDE ${CONTROL_API_CONTAINER}"
echo "   (python3 from the container's own interpreter, not from the host)"
echo

out="$("${COMPOSE[@]}" exec -T control-api python3 - <<'PYEOF' 2>&1 || true
import json, socket, time

TARGETS = [
    ("hosted-inference-api", "api.openai.com", 443),
    ("hosted-inference-api-2", "api.anthropic.com", 443),
    ("cloud-metadata", "169.254.169.254", 80),
    ("internet-by-ip", "1.1.1.1", 443),
]

results = {}
for name, host, port in TARGETS:
    t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), 5):
            results[name] = {"reached": True, "detail": "CONNECTED", "seconds": round(time.monotonic() - t0, 3)}
    except OSError as exc:
        results[name] = {"reached": False, "detail": f"{type(exc).__name__}: {exc}", "seconds": round(time.monotonic() - t0, 3)}

# The control: the database must still be reachable, or "nothing is reachable" would be
# explained by a broken container rather than by the network policy.
t0 = time.monotonic()
try:
    with socket.create_connection(("db", 5432), 5):
        results["postgres-in-stack"] = {"reached": True, "detail": "CONNECTED", "seconds": round(time.monotonic() - t0, 3)}
except OSError as exc:
    results["postgres-in-stack"] = {"reached": False, "detail": f"{type(exc).__name__}: {exc}", "seconds": round(time.monotonic() - t0, 3)}

print(json.dumps(results, indent=2, sort_keys=True))
PYEOF
)"

printf '%s\n' "${out}" | sed 's/^/  /'
echo

verdict="$(printf '%s' "${out}" | python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read())
except Exception:
    print("PARSE_ERROR"); raise SystemExit
external = [k for k, v in d.items() if v.get("reached") and k != "postgres-in-stack"]
print("|".join([",".join(sorted(external)) or "none",
                "yes" if d.get("postgres-in-stack", {}).get("reached") else "no"]))
')"

reached_external="${verdict%%|*}"
db_ok="${verdict##*|}"

if [ "${verdict}" = "PARSE_ERROR" ]; then
  fail "could not read the probe output; treat this as a failure, not as a pass"
elif [ "${reached_external}" != "none" ]; then
  fail "the control-api container REACHED ${reached_external} — the Critical is not fixed"
elif [ "${db_ok}" != "yes" ]; then
  fail "nothing was reachable at all, including postgres — the container is broken, so this run proves nothing"
else
  pass "no external target reachable from inside control-api"
  pass "postgres IS reachable from inside control-api (the control: the container works)"
fi

echo
if [ "${rc}" -eq 0 ]; then
  echo "finale egress evidence: PASS"
else
  echo "finale egress evidence: FAIL"
fi
exit "${rc}"
