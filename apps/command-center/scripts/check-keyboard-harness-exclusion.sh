#!/usr/bin/env bash
# #56 — proves the keyboard-operability test harness is genuinely absent from the finale/
# production artifact, structured identically to `check-presentation-build-exclusion.sh` (#52,
# D-058 §2.7). Two assertions:
#   1. `npm run build` (no BD_KEYBOARD_HARNESS_BUILD) produces exactly one page and zero
#      references anywhere in dist/ to the harness route or component.
#   2. `BD_KEYBOARD_HARNESS_BUILD=true npm run build:keyboard-harness` produces a second page
#      (/__dev/keyboard-harness) and DOES contain those references — proving the grep in (1) is
#      a real negative, not a tautology from a broken build.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

MARKERS=(
  'KeyboardHarness'
  'KEYBOARD HARNESS'
  'OPEN CANDIDATE COMPARE'
)

echo '== building finale/production artifact (no BD_KEYBOARD_HARNESS_BUILD) =='
rm -rf dist dist-keyboard-harness
npm run build >/tmp/bd-finale-build-56.log 2>&1 || { cat /tmp/bd-finale-build-56.log; exit 1; }

page_count=$(find dist -name '*.html' | wc -l | tr -d ' ')
if [[ "${page_count}" != "1" ]]; then
  echo "FAIL: finale build produced ${page_count} HTML page(s), expected exactly 1 (/index.html only)"
  exit 1
fi
if [[ -d dist/__dev ]]; then
  echo 'FAIL: finale build produced a /__dev/keyboard-harness route — it must not exist at all'
  exit 1
fi

for marker in "${MARKERS[@]}"; do
  if grep -rl -- "${marker}" dist >/dev/null 2>&1; then
    echo "FAIL: finale build's dist/ contains a reference to keyboard-harness marker: ${marker}"
    grep -rl -- "${marker}" dist
    exit 1
  fi
done
echo 'PASS: finale build contains exactly one page and zero keyboard-harness references'

echo
echo '== building command-center:keyboard-harness artifact (BD_KEYBOARD_HARNESS_BUILD=true) =='
BD_KEYBOARD_HARNESS_BUILD=true npm run build:keyboard-harness >/tmp/bd-keyboard-harness-build-56.log 2>&1 || { cat /tmp/bd-keyboard-harness-build-56.log; exit 1; }

if [[ ! -f dist-keyboard-harness/__dev/keyboard-harness/index.html ]]; then
  echo 'FAIL: keyboard-harness build did not produce /__dev/keyboard-harness/index.html'
  exit 1
fi

found_any=0
for marker in "${MARKERS[@]}"; do
  if grep -rl -- "${marker}" dist-keyboard-harness >/dev/null 2>&1; then
    found_any=1
  fi
done
if [[ "${found_any}" != "1" ]]; then
  echo 'FAIL: keyboard-harness build contains NONE of the expected markers — the negative check above would be vacuous'
  exit 1
fi
echo 'PASS: keyboard-harness build genuinely contains the harness (proves the finale check above is not vacuous)'

echo
echo 'check-keyboard-harness-exclusion: PASS'
