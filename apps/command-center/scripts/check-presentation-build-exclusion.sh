#!/usr/bin/env bash
# #52 / D-058 §2.7, acceptance criterion 1 — "A build of the finale/production artifact
# contains no reference to the presentation-mode components or flag, checkable by grepping the
# built bundle." This is that check, run for real against two real `astro build` outputs rather
# than asserted in prose. cybersecurity's D-086-flagged review of this exclusion should run this
# script directly, not just read this comment.
#
# Two assertions:
#   1. `npm run build` (no BD_PRESENTATION_BUILD) produces exactly one page and zero references
#      anywhere in dist/ to presentation-mode component names, CSS classes, or disclosure copy.
#   2. `BD_PRESENTATION_BUILD=true npm run build:presentation` produces a second page
#      (/presentation) and DOES contain those references — proving the grep in (1) is a real
#      negative, not a tautology from a broken build.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

MARKERS=(
  'MOCK DATA'
  'PresentationModeChip'
  'MockDataWatermark'
  'PresentationMissionCommandCenter'
  'bd-presentation-strip'
  'bd-mock-watermark'
  'REAL MISSION DETECTED'
)

# #272 — two DEAD-NAME traces cybersecurity's #52/D-148 review found leaking into the finale
# bundle even though the build-exclusion property above (the components/routes themselves) was
# already airtight: `--bd-z-presentation` (a z-index token that used to live in the shared,
# always-imported `packages/ui-components/tokens.css`) and `mockSource` (a `MissionSnapshot`
# field that used to live in the shared, always-imported `src/lib/events/store.ts`). Neither was
# ever exploitable or active in the finale build — nothing read them there — but their mere
# textual presence overstated "zero references to presentation-mode code." Both were moved to
# presentation-only files (`src/styles/presentation-mode.css`,
# `src/lib/presentation/provenance.ts`); checked separately from MARKERS above because, unlike
# those functional markers, these two must be present in the presentation build's CSS/JS bundle
# specifically (not merely "somewhere in dist-presentation/"), so the positive half of this check
# greps the right file types rather than the whole directory tree indiscriminately.
DEAD_NAME_TRACES=(
  '\-\-bd-z-presentation'
  'mockSource'
)

echo '== building finale/production artifact (no BD_PRESENTATION_BUILD) =='
rm -rf dist dist-presentation
npm run build >/tmp/bd-finale-build.log 2>&1 || { cat /tmp/bd-finale-build.log; exit 1; }

page_count=$(find dist -name '*.html' | wc -l | tr -d ' ')
if [[ "${page_count}" != "1" ]]; then
  echo "FAIL: finale build produced ${page_count} HTML page(s), expected exactly 1 (/index.html only)"
  exit 1
fi
if [[ -d dist/presentation ]]; then
  echo 'FAIL: finale build produced a /presentation route — it must not exist at all'
  exit 1
fi

for marker in "${MARKERS[@]}"; do
  if grep -rl -- "${marker}" dist >/dev/null 2>&1; then
    echo "FAIL: finale build's dist/ contains a reference to presentation-mode marker: ${marker}"
    grep -rl -- "${marker}" dist
    exit 1
  fi
done
echo 'PASS: finale build contains exactly one page and zero presentation-mode references'

echo
echo '== #272: finale build must be literally clean of the two dead-name traces =='
for trace in "${DEAD_NAME_TRACES[@]}"; do
  if grep -rlE -- "${trace}" dist >/dev/null 2>&1; then
    echo "FAIL: finale build's dist/ still contains dead-name trace: ${trace}"
    grep -rlE -- "${trace}" dist
    exit 1
  fi
done
echo 'PASS: finale build contains neither --bd-z-presentation nor mockSource anywhere in dist/'

echo
echo '== building command-center:presentation artifact (BD_PRESENTATION_BUILD=true) =='
BD_PRESENTATION_BUILD=true npm run build:presentation >/tmp/bd-presentation-build.log 2>&1 || { cat /tmp/bd-presentation-build.log; exit 1; }

if [[ ! -f dist-presentation/presentation/index.html ]]; then
  echo 'FAIL: presentation build did not produce /presentation/index.html'
  exit 1
fi

found_any=0
for marker in "${MARKERS[@]}"; do
  if grep -rl -- "${marker}" dist-presentation >/dev/null 2>&1; then
    found_any=1
  fi
done
if [[ "${found_any}" != "1" ]]; then
  echo 'FAIL: presentation build contains NONE of the expected markers — the negative check above would be vacuous'
  exit 1
fi
echo 'PASS: presentation build genuinely contains the disclosure chrome (proves the finale check above is not vacuous)'

echo
echo '== #272: presentation build must still genuinely contain the two dead-name traces =='
found_any_trace=0
for trace in "${DEAD_NAME_TRACES[@]}"; do
  if grep -rlE -- "${trace}" dist-presentation >/dev/null 2>&1; then
    found_any_trace=1
  fi
done
if [[ "${found_any_trace}" != "1" ]]; then
  echo 'FAIL: presentation build contains NEITHER dead-name trace — the finale negative check above would be vacuous'
  exit 1
fi
echo 'PASS: presentation build genuinely still uses --bd-z-presentation/mockSource where legitimately needed (proves the finale check above is not vacuous)'

echo
echo 'check-presentation-build-exclusion: PASS'
