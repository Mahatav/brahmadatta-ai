#!/usr/bin/env bash
# Assert the committed OpenAPI dump is current: regenerate it and diff.
#
#   infrastructure/scripts/openapi-contract-check.sh
#
# Why this is a gate and not a nicety. Issue #6's acceptance criterion is that a contract
# change breaks the frontend build. That is only true if the committed dump is the real
# contract. A hand-committed dump drifts the first time someone edits a schema and forgets
# to re-export, and from then on the frontend is generated from a file that describes an
# API that no longer exists — while every check stays green. Regenerate-and-diff is what
# makes the acceptance criterion true rather than aspirational.
#
# CONTRACT with apps/control-api (backend developer owns both sides):
#   - an exporter that writes the dump to stdout or to a path given as argv[1]
#   - a committed dump, byte-for-byte what the exporter produces
# Locations are auto-detected from the list below, or set explicitly:
#   OPENAPI_EXPORTER=apps/control-api/tools/export_openapi.py
#   OPENAPI_DUMP=packages/schemas/openapi.json
#
# If apps/control-api exists but neither is found, this FAILS rather than skipping. A
# silent skip here is precisely the drift the check exists to prevent.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && cd .. && pwd)"
CONTROL_API="${REPO_ROOT}/apps/control-api"

if [ ! -d "${CONTROL_API}" ]; then
  echo "openapi contract: SKIPPED — apps/control-api does not exist yet."
  echo "                  This stops being a skip the moment the control API lands."
  exit 0
fi

find_first() {
  for candidate in "$@"; do
    if [ -f "${REPO_ROOT}/${candidate}" ]; then
      printf '%s' "${candidate}"
      return 0
    fi
  done
  return 1
}

EXPORTER="${OPENAPI_EXPORTER:-$(find_first \
  apps/control-api/tools/export_openapi.py \
  apps/control-api/tools/export-openapi.py \
  || true)}"

DUMP="${OPENAPI_DUMP:-$(find_first \
  packages/schemas/openapi.json \
  apps/control-api/contracts/openapi.json \
  apps/control-api/openapi.json \
  || true)}"

if [ -z "${EXPORTER}" ] || [ -z "${DUMP}" ]; then
  cat >&2 <<EOF
openapi contract: FAILED — apps/control-api exists but the contract cannot be checked.

  exporter: ${EXPORTER:-NOT FOUND}
  dump:     ${DUMP:-NOT FOUND}

Provide both, or point at them explicitly:

  OPENAPI_EXPORTER=apps/control-api/tools/export_openapi.py \\
  OPENAPI_DUMP=packages/schemas/openapi.json \\
  infrastructure/scripts/openapi-contract-check.sh

Without this check, issue #6's acceptance criterion — "a contract change breaks the
frontend build" — is false, because the committed dump drifts silently.
EOF
  exit 1
fi

echo "  exporter: ${EXPORTER}"
echo "  dump:     ${DUMP}"

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
REGENERATED="${TMP}/openapi.json"

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.test}"
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-openapi-export-not-a-real-secret-0123456789}"
export PYTHONPATH="${CONTROL_API}${PYTHONPATH:+:${PYTHONPATH}}"

# Support both exporter shapes: writes to argv[1], or writes to stdout.
if ! ( cd "${CONTROL_API}" && python3 "${REPO_ROOT}/${EXPORTER}" "${REGENERATED}" ) 2>"${TMP}/err"; then
  if ! ( cd "${CONTROL_API}" && python3 "${REPO_ROOT}/${EXPORTER}" > "${REGENERATED}" ) 2>>"${TMP}/err"; then
    echo "openapi contract: FAILED — the exporter did not run." >&2
    sed 's/^/    /' "${TMP}/err" >&2
    exit 1
  fi
fi

if [ ! -s "${REGENERATED}" ]; then
  echo "openapi contract: FAILED — the exporter produced nothing." >&2
  exit 1
fi

# Compare canonicalised JSON, so key order and indentation are not the thing that fails.
normalise() {
  python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])), indent=2, sort_keys=True))' "$1"
}

if diff -u <(normalise "${REPO_ROOT}/${DUMP}") <(normalise "${REGENERATED}"); then
  echo "openapi contract: PASS — the committed dump matches the live schema"
  exit 0
fi

cat >&2 <<EOF

openapi contract: FAILED — the committed dump is stale.

The API schema changed and ${DUMP} was not regenerated. Anything generated from that
file — the frontend client above all — is now describing an API that does not exist.

Fix:
  python3 ${EXPORTER} ${DUMP}
  git add ${DUMP}

If the change was not intended, the schema edit is the bug, not the dump.
EOF
exit 1
