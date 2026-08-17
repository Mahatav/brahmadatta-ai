#!/usr/bin/env bash
# Start `fuzz-worker` — the D-073 bare-metal deployment for FUZZ/MINIMIZE jobs.
#
#   infrastructure/scripts/run-fuzz-worker.sh                 # dev profile (default)
#   FUZZ_WORKER_PROFILE=finale infrastructure/scripts/run-fuzz-worker.sh
#   infrastructure/scripts/run-fuzz-worker.sh --once           # claim/run one job, exit
#
# WHY THIS IS A SEPARATE, BARE-METAL PROCESS, NOT A COMPOSE SERVICE (D-073)
#
# The containerized `worker` service has no `docker` CLI, and D-036 forbids ever
# mounting the host's Docker socket into it — so it structurally cannot run
# `packages.sandbox.container.ContainerJail`, which every FUZZ/MINIMIZE job needs.
# D-073's ruling: split the worker FLEET by JobKind, not by transport. This script
# starts the second fleet member — `fuzz-worker` — as
#
#     python manage.py run_worker --kinds FUZZ,MINIMIZE
#
# directly on this host, exactly as `infrastructure/scripts/build-fuzz-image.sh` and
# CI's own `packages/sandbox`/`cpp-adapter` jobs already run bare-metal — this is not a
# new execution shape for this repository. It is the ONLY process anywhere in this
# system ever given container-runtime access, and it is deliberately given NO
# model-gateway configuration and NO route to `model-host` (see the checks below and
# `tests/architecture/test_fuzz_worker_isolation.py`, which asserts the import half of
# that structurally). The fully-containerized "sandbox-executor" replacement for this
# script is an explicit post-deadline fast-follow, not attempted here — see D-073 §4.
#
# WHAT THIS SCRIPT DOES NOT DO
#
# It does not decide whether `fuzz-worker`'s Postgres connection string is safe to
# publish on the finale host — docker-compose.finale.yml still states "no port is
# published except through nginx" as an explicit invariant, and this script refuses to
# guess at overriding it. See the preflight below and the D-073 follow-up entry in
# .project/decisions.md for the open decision this hands to CTO/devops-engineer, with
# cybersecurity review required before it ships.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTROL_API="${REPO_ROOT}/apps/control-api"
PROFILE="${FUZZ_WORKER_PROFILE:-dev}"

fail() { printf '\033[31mblocked:\033[0m %s\n' "$1" >&2; exit 1; }
note() { printf '  %s\n' "$1"; }
warn() { printf '  \033[33mwarning:\033[0m %s\n' "$1" >&2; }

echo "== fuzz-worker preflight (profile: ${PROFILE})"

# --- 1. This is the one process anywhere in this system that needs Docker -----------
command -v docker >/dev/null || fail "docker is not installed — fuzz-worker cannot run ContainerJail without it"
docker info >/dev/null 2>&1 || fail "the docker daemon is not reachable from this host/user"
note "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '(version unknown)') reachable"

# --- 2. The control-api Django project must be importable from here -----------------
[[ -d "${CONTROL_API}" ]] || fail "apps/control-api is missing"
[[ -f "${CONTROL_API}/manage.py" ]] || fail "apps/control-api/manage.py is missing"

if [[ -x "${CONTROL_API}/.venv/bin/python" ]]; then
  PYTHON="${CONTROL_API}/.venv/bin/python"
elif command -v python3 >/dev/null; then
  PYTHON="$(command -v python3)"
  warn "no apps/control-api/.venv found; using $(command -v python3) from PATH — its packages must already satisfy apps/control-api/requirements.txt"
else
  fail "no Python interpreter found (checked apps/control-api/.venv/bin/python and PATH)"
fi
note "python: ${PYTHON}"

# --- 3. Environment ------------------------------------------------------------------
# Deliberately NOT `config.settings.development`/`config.settings.finale`'s usual
# compose env_file — fuzz-worker is not a compose service. It reads .env the same way
# a bare-metal `apps/control-api/.env` would (see apps/control-api/.env.example), or
# whatever DJANGO_SETTINGS_MODULE/DATABASE_URL the caller has already exported.
if [[ -z "${DJANGO_SETTINGS_MODULE:-}" ]]; then
  case "${PROFILE}" in
    finale) export DJANGO_SETTINGS_MODULE="config.settings.finale" ;;
    *)      export DJANGO_SETTINGS_MODULE="config.settings.development" ;;
  esac
fi
note "DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  if [[ -f "${CONTROL_API}/.env" ]]; then
    # shellcheck disable=SC1090
    set -a; source "${CONTROL_API}/.env"; set +a
  fi
fi
if [[ -z "${DATABASE_URL:-}" ]]; then
  fail "DATABASE_URL is not set and apps/control-api/.env does not set it either. fuzz-worker runs OUTSIDE the compose network — it needs Postgres reachable from THIS host (e.g. postgresql://brahmadatta:...@127.0.0.1:5432/brahmadatta with the compose dev profile's loopback-published db port; see infrastructure/compose/docker-compose.yml's db service). The finale profile does not publish this port today — that is an open, undecided question, not a default this script will choose for you."
fi
note "DATABASE_URL is set (value not printed)"

# --- 4. The property D-073 exists to protect: no model-gateway, no route to model-host
#
# Cheap, real, LOCAL signals only — not a substitute for the network-level LIVE check
# infrastructure/scripts/egress-test.sh runs for the containerized services, which has
# no bare-metal-host equivalent yet. D-073 §5 item 2 names that as a cybersecurity
# review item before this ships to the finale host.
if [[ -n "${SMALL_MODEL_BASE_URL:-}" || -n "${TIER3_BASE_URL:-}" ]]; then
  warn "SMALL_MODEL_BASE_URL/TIER3_BASE_URL are set in this shell's environment. fuzz-worker never reads them (it has no model-gateway client — see tests/architecture/test_fuzz_worker_isolation.py) but their presence here is worth a second look before this runs on the finale host."
fi

echo
echo "== starting fuzz-worker"
echo "    python manage.py run_worker --kinds FUZZ,MINIMIZE $*"
echo
cd "${CONTROL_API}"
exec "${PYTHON}" manage.py run_worker --kinds FUZZ,MINIMIZE "$@"
