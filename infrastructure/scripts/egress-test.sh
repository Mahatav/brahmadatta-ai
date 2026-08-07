#!/usr/bin/env bash
# C4 assertion: nothing except nginx can reach anything off this host.
#
#   infrastructure/scripts/egress-test.sh
#
# Why this test exists, in one paragraph. The product's hardest invariant is that
# repository content never reaches an external inference API. That was being enforced over
# *configuration* — a base URL validated at startup — and configuration is not a boundary.
# `http://169.254.169.254/` passes a "must be a private range" validator, and on a rented
# VM it is the cloud metadata endpoint that hands out instance credentials. Meanwhile the
# container that holds the repository snapshot and assembles the prompt had no egress
# restriction at all; only the sandbox did, and the sandbox holds no inference client.
# So the boundary moved to the network: every container except nginx is on
# `internal: true` networks and has no route out at any layer.
#
# This is the acceptance criterion for #11 and #15.
#
# Two layers of assertion, because they fail differently:
#
#   TOPOLOGY — read each service's network attachments out of `docker compose config` and
#              require that only nginx (plus the documented dev-only npm installer) touches
#              `external`. Catches the regression where someone adds `- external` to a
#              service to make something work. Needs nothing running, so it cannot be
#              skipped for being inconvenient.
#
#   LIVE     — put a probe container on exactly the networks control-api and worker use and
#              actually try to connect out. Catches the case where the topology reads right
#              and Docker did something else. It also probes nginx, which MUST reach out —
#              so a wall of "denied" results cannot come from a broken probe.
#
# This is the network-level assertion. The in-container assertion — exec into the RUNNING
# control-api of the finale profile and try to reach a hosted inference API — is
# infrastructure/scripts/finale-egress-evidence.sh, and it is the one the security reviewer
# re-runs. Both exist because they fail differently: this one runs with nothing built and
# catches a compose-file regression; that one proves the running container, which is what
# the Critical was actually about.
#
# It runs against the network definitions, not against running application containers, so
# it works on a tree where apps/ does not exist yet and needs no application image.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infrastructure/compose/docker-compose.yml"
PYTHON_IMAGE="python@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2"
PROJECT="brahmadatta"

rc=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; rc=1; }

CREATED_NETS=()
PROBE="egress-probe-$$"
# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
  docker rm -f "${PROBE}" >/dev/null 2>&1 || true
  for n in ${CREATED_NETS[@]+"${CREATED_NETS[@]}"}; do
    docker network rm "${n}" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT

# `--profile worker` so the profile-gated worker service is present in the config; leaving
# it out would silently exempt exactly the service this test most needs to check.
config_json="$(docker compose -f "${COMPOSE_FILE}" --profile worker config --format json)"

svc_networks() {
  printf '%s' "${config_json}" | python3 -c "
import json,sys
cfg = json.load(sys.stdin)
svc = cfg.get('services', {}).get('$1')
print(' '.join(sorted((svc.get('networks') or {}).keys())) if svc else 'MISSING')
"
}

# ---------------------------------------------------------------------------
echo "== topology: only nginx may touch the network that has a gateway"

on_external="$(printf '%s' "${config_json}" | python3 -c '
import json,sys
cfg = json.load(sys.stdin)
for name, svc in sorted(cfg.get("services", {}).items()):
    if "external" in (svc.get("networks") or {}):
        print(name)
')"

echo "  services attached to \`external\`:"
printf '%s\n' "${on_external}" | sed 's/^/    /'

# command-center-deps is the one documented exception, and only in the DEVELOPMENT stack:
# `npm ci` needs the registry. It is a short-lived installer that exits before the dev
# server starts, holds no repository content and runs no inference client. The finale stack
# has no npm step and therefore no exception at all. Anything else on this list is a bug.
allowed="nginx command-center-deps"
for svc in ${on_external}; do
  case " ${allowed} " in
    *" ${svc} "*) ;;
    *) fail "service '${svc}' is attached to \`external\` and must not be" ;;
  esac
done
case "${on_external}" in
  *nginx*) pass "nginx is on \`external\`" ;;
  *)       fail "nginx is NOT on \`external\`; the ingress cannot serve anything" ;;
esac

for svc in control-api worker db redis command-center; do
  nets="$(svc_networks "${svc}")"
  case "${nets}" in
    *external*) fail "${svc} is on \`external\` (networks: ${nets})" ;;
    MISSING)    fail "${svc} is not defined in the compose file" ;;
    *)          pass "${svc} has no gateway network (networks: ${nets})" ;;
  esac
done

# ---------------------------------------------------------------------------
echo
echo "== live: attempt outbound from the application networks"

# Create any declared network that does not exist yet, with the same `internal` flag the
# compose file declares. The probe then runs on the real thing rather than on an
# approximation of it.
ensure_network() {
  local short="$1" full="${PROJECT}_$1" is_internal
  if docker network inspect "${full}" >/dev/null 2>&1; then
    return
  fi
  is_internal="$(printf '%s' "${config_json}" | python3 -c "
import json,sys
cfg = json.load(sys.stdin)
print(bool((cfg.get('networks') or {}).get('${short}', {}).get('internal')))
")"
  if [ "${is_internal}" = "True" ]; then
    docker network create --internal "${full}" >/dev/null
  else
    docker network create "${full}" >/dev/null
  fi
  CREATED_NETS+=("${full}")
}

for n in external api edge backend; do ensure_network "${n}"; done

probe_on() {
  local label="$1" expect="$2"; shift 2
  local first="$1"; shift

  docker rm -f "${PROBE}" >/dev/null 2>&1 || true
  docker create --name "${PROBE}" \
    --network "${PROJECT}_${first}" \
    --user 65534:65534 \
    -v "${REPO_ROOT}/infrastructure/scripts/testing/egress-probe.py:/srv/egress-probe.py:ro" \
    "${PYTHON_IMAGE}" python3 /srv/egress-probe.py 3 >/dev/null
  for n in "$@"; do
    docker network connect "${PROJECT}_${n}" "${PROBE}" >/dev/null
  done

  echo
  echo "  --- ${label} (networks: ${first} $*) — expecting egress ${expect}"
  local out reached
  out="$(docker start -a "${PROBE}" 2>&1 || true)"
  docker rm -f "${PROBE}" >/dev/null 2>&1 || true
  printf '%s\n' "${out}" | sed 's/^/    /'

  reached="$(printf '%s' "${out}" | python3 -c '
import json,sys
try:
    d = json.loads(sys.stdin.read())
except Exception:
    print("PARSE_ERROR"); raise SystemExit
print(",".join(sorted(k for k, v in d.items() if v.get("reached"))) or "none")
')"

  if [ "${expect}" = "denied" ]; then
    if [ "${reached}" = "none" ]; then
      pass "${label}: no target reachable"
    else
      fail "${label}: REACHED ${reached}"
    fi
  else
    if [ "${reached}" = "none" ] || [ "${reached}" = "PARSE_ERROR" ]; then
      fail "${label}: reached nothing — the probe itself is broken, so every 'denied' result above proves nothing"
    else
      pass "${label}: reached ${reached} (required — this is the control)"
    fi
  fi
}

# Attachments mirrored from the compose file. Keep in step with it.
probe_on "control-api networks"    denied  api backend
probe_on "worker networks"         denied  backend
probe_on "command-center networks" denied  edge
# The control. nginx MUST have egress; without this, every "denied" above is unfalsifiable.
probe_on "nginx networks"          allowed external api edge

echo
if [ "${rc}" -eq 0 ]; then
  echo "egress test: PASS — only nginx can reach off-host"
else
  echo "egress test: FAIL"
fi
exit "${rc}"
