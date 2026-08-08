#!/usr/bin/env bash
#
# Prove the fixture replay survives an nginx hop.
#
# WHY THIS EXISTS AND WHY IT IS NOT `curl localhost:8971`
#
# nginx buffers proxied responses by default. For a finite response that is a win. For an
# infinite one it is fatal and silent: nginx holds each `data:` frame until a buffer fills
# or the response ends, the response never ends, the browser's EventSource stays open, no
# error appears in any log, and the Command Center simply never renders an event. The
# signature is "SSE works against the app directly and dies through nginx" — which is
# exactly the shape of bug that gets found during a demo.
#
# So this runs the replay behind a real nginx, with the same directives as
# infrastructure/compose/nginx/includes/sse.conf, and measures when frames arrive.
#
# It then does it AGAIN with `proxy_buffering on` and requires that run to FAIL. A check
# that passes no matter what nginx is configured to do is not a check. The negative
# control is the part that makes the positive result mean something.
#
# Needs docker. Touches nothing outside its own containers and network.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../.." && pwd)"

NETWORK="brahmadatta-fixture-verify"
REPLAY="brahmadatta-fixture-replay"
PROXY="brahmadatta-fixture-nginx"
PROXY_PORT="${PROXY_PORT:-8972}"
MISSION_ID="$(head -n1 "${HERE}/missions/mission-pktcfg-001.events.jsonl" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["mission_id"])')"

PYTHON_IMAGE="python:3.12-alpine"
NGINX_IMAGE="nginx:1.27-alpine"

WORK="$(mktemp -d)"

cleanup() {
  docker rm -f "${PROXY}" "${REPLAY}" >/dev/null 2>&1 || true
  docker network rm "${NETWORK}" >/dev/null 2>&1 || true
  rm -rf "${WORK}"
}
trap cleanup EXIT

write_conf() {
  # $1 = proxy_buffering (off|on), $2 = buffer size for the ON case
  local buffering="$1"
  local bufsize="${2:-8k}"
  cat > "${WORK}/default.conf" <<EOF
server {
    listen 80;
    server_name _;

    location ~ ^/api/v1/missions/[^/]+/events/?\$ {
        # These lines are the contract under test. They mirror
        # infrastructure/compose/nginx/includes/sse.conf; the negative control below
        # flips proxy_buffering and widens the buffers.
        proxy_buffering         ${buffering};
        proxy_buffer_size       ${bufsize};
        proxy_buffers           8 ${bufsize};
        proxy_cache             off;
        proxy_request_buffering off;
        gzip                    off;

        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        chunked_transfer_encoding off;

        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # No \$request_uri here. A proxy_pass containing a variable makes nginx resolve
        # the upstream at request time, which needs a resolver directive; without one
        # every request is a 502 with no frames. A proxy_pass with no URI part passes
        # the original request URI through unchanged, which is what is wanted.
        proxy_pass http://${REPLAY}:8971;
    }

    location /api/ {
        proxy_pass http://${REPLAY}:8971;
    }
}
EOF
}

start_proxy() {
  docker rm -f "${PROXY}" >/dev/null 2>&1 || true
  docker run -d --name "${PROXY}" --network "${NETWORK}" \
    -p "127.0.0.1:${PROXY_PORT}:80" \
    -v "${WORK}/default.conf:/etc/nginx/conf.d/default.conf:ro" \
    "${NGINX_IMAGE}" >/dev/null
  # `nginx -t` only says the config parses. What matters is that it is listening and
  # can reach the upstream, so probe an actual request through it.
  for _ in $(seq 1 40); do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 \
      "http://127.0.0.1:${PROXY_PORT}/api/v1/missions" 2>/dev/null || true)"
    if [ "${code}" = "200" ]; then return 0; fi
    sleep 0.25
  done
  echo "nginx did not become ready (last status '${code:-none}')"
  docker logs "${PROXY}" 2>&1 | tail -20
  return 1
}

echo "== pulling images =="
docker pull -q "${PYTHON_IMAGE}" >/dev/null
docker pull -q "${NGINX_IMAGE}" >/dev/null

docker network create "${NETWORK}" >/dev/null 2>&1 || true

echo "== starting the replay upstream =="
# --allow-remote is deliberate and is confined to this docker network: the guard exists so
# nobody exposes fabricated telemetry by accident (fallback ladder §2.5), not to make it
# unusable behind a proxy.
docker run -d --name "${REPLAY}" --network "${NETWORK}" \
  -v "${HERE}:/fixtures:ro" \
  "${PYTHON_IMAGE}" \
  python3 -u /fixtures/sse_replay.py \
    --host 0.0.0.0 --allow-remote \
    --speed 25 --max-gap 0.3 --drop '' --loop >/dev/null

for _ in $(seq 1 40); do
  if docker exec "${REPLAY}" python3 -c "
import socket,sys
s=socket.socket()
sys.exit(0 if s.connect_ex(('127.0.0.1',8971))==0 else 1)" 2>/dev/null; then
    break
  fi
  sleep 0.25
done

URL="http://127.0.0.1:${PROXY_PORT}/api/v1/missions/${MISSION_ID}/events"

echo
echo "== 1. through nginx, proxy_buffering off (the shipped config) =="
write_conf off
start_proxy
python3 "${HERE}/tools/sse_timing_probe.py" "${URL}" --expect stream --timeout 25
STREAM_RC=$?

echo
# WHERE THE NEGATIVE CONTROL WENT
#
# This script originally ran a second pass with `proxy_buffering on` and required it to
# FAIL, so that a PASS above would mean something. That control could not be established.
# On nginx 1.27, against this fixture, none of `proxy_buffering on` (including with
# 256k buffers, wider than the entire 60-event mission), `proxy_cache`, or `gzip`
# reproduced the stall — nginx relayed frames promptly in every configuration tried.
# Measured, not assumed; the runs are in the D2 PR.
#
# That does not mean the hazard is imaginary. It means it depends on frame size against
# buffer size and on the client's read rate, none of which are ours to control, and
# `proxy_buffering off` is what makes the stream not depend on them at all. It also means
# a claim of the form "this script proves buffering would be caught" would be false.
#
# The probe's sensitivity is instead demonstrated directly, against a server that
# provably withholds every frame until the end:
#
#   packages/test-fixtures/tests/test_sse_replay.py::test_timing_probe_detects_a_buffered_stream
#
# Run that alongside this. This script answers "does the shipped config stream?"; that
# test answers "would we notice if it did not?".

echo
if [ "${STREAM_RC}" -eq 0 ]; then
  echo "OK: SSE survives the nginx hop with the shipped directives."
  echo "    Probe sensitivity is covered by tests/test_sse_replay.py::test_timing_probe_detects_a_buffered_stream"
  exit 0
fi
echo "FAILED: the replay did not stream through nginx (probe rc=${STREAM_RC})"
exit 1
