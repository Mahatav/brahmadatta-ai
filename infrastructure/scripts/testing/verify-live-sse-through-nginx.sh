#!/usr/bin/env bash
# Prove #13's SSE endpoint — the REAL Django view, not the stub `smoke-sse.sh` uses —
# survives the nginx ingress: incremental delivery, Last-Event-ID reconnect replay, and
# an idle stream that outlives its own heartbeat interval without being dropped.
#
# smoke-sse.sh (issue #114) proves the nginx CONFIG is correct against a synthetic
# upstream and runs in CI on every PR. This script proves the same property against the
# actual control-api container running the actual `api.routers.missions.stream_events`
# view, backed by a real (SQLite, for this script's purposes) MissionEvent table. It is
# not wired into CI — it needs a built control-api image and takes tens of seconds —
# and is run by hand for the #13 PR, with its output pasted there.
#
#   infrastructure/scripts/testing/verify-live-sse-through-nginx.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
NGINX_DIR="${REPO_ROOT}/infrastructure/compose/nginx"
CONTROL_API_DIR="${REPO_ROOT}/apps/control-api"

NGINX_IMAGE="nginxinc/nginx-unprivileged@sha256:0c79d56aee561a1d81c63f00eee5fb5fe29279560cdc55e91425133104c7fbe6"
NET="brahmadatta-sse-live"
API="brahmadatta-sse-live-api"
PROXY="brahmadatta-sse-live-proxy"
HOST_PORT="${SSE_LIVE_SMOKE_PORT:-18444}"
TMPDIR_LOCAL="$(mktemp -d)"
IMAGE_TAG="brahmadatta-control-api:sse-live-verify"

cleanup() {
  docker rm -f "${PROXY}" "${API}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
  rm -rf "${TMPDIR_LOCAL}"
}
trap cleanup EXIT

if [[ ! -f "${NGINX_DIR}/certs/server.crt" ]]; then
  "${REPO_ROOT}/infrastructure/scripts/gen-dev-certs.sh"
fi

echo "=== building the real control-api image (runtime target) ==="
docker build --target runtime -t "${IMAGE_TAG}" \
  -f "${REPO_ROOT}/infrastructure/compose/images/control-api.Dockerfile" \
  "${CONTROL_API_DIR}" >/dev/null

docker network create "${NET}" >/dev/null

echo "=== starting control-api ==="
# No --rm: case 5 below stops and restarts THIS SAME container to prove the events
# table survives a process restart. It is removed explicitly in cleanup() instead.
docker run -d --name "${API}" \
  --network "${NET}" --network-alias control-api \
  --user 10001:10001 \
  -e DJANGO_SETTINGS_MODULE=config.settings.development \
  -e DJANGO_SECRET_KEY="sse-live-verify-not-a-real-secret-000000000000" \
  -e DJANGO_DEBUG=false \
  -e DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1,control-api" \
  -e DATABASE_URL="sqlite:////home/app/sse-live-verify.sqlite3" \
  -e CONTROL_API_OPERATOR_TOKEN="sse-live-verify-operator-token-0123456789ab" \
  -e CONTROL_API_ADMIN_ENABLED=false \
  -e CONTROL_API_DOCS_ENABLED=false \
  -e SSE_HEARTBEAT_INTERVAL_SECONDS=2 \
  -e SSE_POLL_INTERVAL_SECONDS=0.2 \
  "${IMAGE_TAG}" \
  sh -c "python manage.py migrate --noinput && exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --log-level info" \
  >/dev/null

echo "=== waiting for control-api to become healthy ==="
for _ in $(seq 1 60); do
  if docker exec "${API}" python -c "import socket; socket.create_connection(('127.0.0.1',8000),1).close()" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

echo "=== starting nginx (committed dev config, unmodified) ==="
# D-088 (T0): conf.d.dev/ became templates.dev/ — mounted at /etc/nginx/templates so the
# image's own envsubst entrypoint step renders it into /etc/nginx/conf.d before nginx
# starts. The token below matches control-api's CONTROL_API_OPERATOR_TOKEN exactly above,
# so nginx's injected Authorization header (which OVERWRITES whatever curl sends with
# -H "${AUTH}" further down) authenticates for real, the same way the browser will.
docker run -d --rm --name "${PROXY}" \
  --network "${NET}" \
  -p "127.0.0.1:${HOST_PORT}:8443" \
  -e CONTROL_API_OPERATOR_TOKEN="sse-live-verify-operator-token-0123456789ab" \
  -e NGINX_ENVSUBST_FILTER="^CONTROL_API_OPERATOR_TOKEN$" \
  -v "${NGINX_DIR}/nginx.conf:/etc/nginx/nginx.conf:ro" \
  -v "${NGINX_DIR}/includes:/etc/nginx/includes:ro" \
  -v "${NGINX_DIR}/profile/admin-allow.conf:/etc/nginx/profile/admin.conf:ro" \
  -v "${NGINX_DIR}/templates.dev:/etc/nginx/templates:ro" \
  -v "${NGINX_DIR}/certs:/etc/nginx/certs:ro" \
  "${NGINX_IMAGE}" >/dev/null

for _ in $(seq 1 40); do
  if docker exec "${PROXY}" nginx -T >/dev/null 2>&1; then break; fi
  sleep 0.25
done
sleep 0.5

BASE="https://127.0.0.1:${HOST_PORT}"
AUTH="Authorization: Bearer sse-live-verify-operator-token-0123456789ab"

echo
echo "=== health check through nginx ==="
curl -sk --http1.1 "${BASE}/api/v1/system/health" -H "${AUTH}"
echo

echo
echo "=== creating a mission and three events directly in the container's DB ==="
MISSION_ID=$(docker exec "${API}" python manage.py shell -c "
import uuid
from missions.models import Mission, MissionEvent
from contracts.enums import LanguageAdapter, EventType, MissionStage, MissionState, EventStatus, Severity
from django.utils import timezone

m = Mission.objects.create(
    name='sse-live-verify',
    repository_ref='file:///demo/repositories/pktcfg',
    adapter=LanguageAdapter.C_CMAKE_CTEST.value,
    policy={},
)
for seq in (1, 2, 3):
    MissionEvent.objects.create(
        mission=m, sequence=seq, timestamp=timezone.now(),
        type=EventType.LOG.value, stage=MissionStage.BASELINE.value,
        state=MissionState.BASELINE.value, status=EventStatus.RUNNING.value,
        severity=Severity.INFO.value, message=f'live verify event {seq}',
        payload={'kind': 'log', 'text': f'line {seq}'},
        evidence_refs=[], metrics={}, trace_id='sse-live-verify-trace0000',
    )
print(str(m.id))
" 2>/dev/null | tail -1)
echo "mission_id=${MISSION_ID}"

echo
echo "=== case 1: full replay through nginx, HTTP/1.1, proxy_buffering off ==="
echo "(expect: preamble + 3 events arriving incrementally, not as one lump)"
curl -sk --http1.1 -N --max-time 4 \
  "${BASE}/api/v1/missions/${MISSION_ID}/events" -H "${AUTH}" \
  -w '\n[curl] time_starttransfer=%{time_starttransfer}s total=%{time_total}s\n' \
  || true

echo
echo "=== case 2: reconnect with Last-Event-ID: 1 -> replays only sequence 2 and 3 ==="
curl -sk --http1.1 -N --max-time 4 \
  "${BASE}/api/v1/missions/${MISSION_ID}/events" -H "${AUTH}" -H "Last-Event-ID: 1" \
  || true

echo
echo "=== case 3: idle stream survives past its own heartbeat interval (SSE_HEARTBEAT_INTERVAL_SECONDS=2) ==="
echo "(expect: ': heartbeat' comment lines, connection held open by nginx's proxy_read_timeout 3600s, not dropped)"
curl -sk --http1.1 -N --max-time 7 \
  "${BASE}/api/v1/missions/${MISSION_ID}/events?since_sequence=3" -H "${AUTH}" \
  -w '\n[curl] total=%{time_total}s (curl'"'"'s own --max-time ended it, not nginx or the app)\n' \
  || true

echo
echo "=== case 4: the 429 cap, through nginx, with a real second connection held open ==="
(curl -sk --http1.1 -N --max-time 6 "${BASE}/api/v1/missions/${MISSION_ID}/events" -H "${AUTH}" >/dev/null &)
sleep 1
for i in 1 2 3 4; do
  (curl -sk --http1.1 -N --max-time 6 "${BASE}/api/v1/missions/${MISSION_ID}/events" -H "${AUTH}" >/dev/null &)
done
sleep 1
echo -n "5th concurrent connection to the same mission -> "
curl -sk --http1.1 -o /dev/null -w "HTTP %{http_code}\n" --max-time 3 \
  "${BASE}/api/v1/missions/${MISSION_ID}/events" -H "${AUTH}"
sleep 6

echo
echo "=== case 5: events survive a process restart (\"#13 AC\") ==="
echo "Stopping the control-api container (uvicorn process dies), then starting the SAME"
echo "container (same SQLite file, fresh process) and replaying from sequence 0."
docker stop "${API}" >/dev/null
docker start "${API}" >/dev/null
for _ in $(seq 1 60); do
  if docker exec "${API}" python -c "import socket; socket.create_connection(('127.0.0.1',8000),1).close()" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
echo -n "replay after restart -> "
curl -sk --http1.1 "${BASE}/api/v1/missions/${MISSION_ID}/events/replay?since_sequence=0" -H "${AUTH}"
echo

echo
echo "=== control-api log tail (uvicorn access log) ==="
docker logs "${API}" 2>&1 | tail -30

echo
echo "verify-live-sse-through-nginx: DONE"
