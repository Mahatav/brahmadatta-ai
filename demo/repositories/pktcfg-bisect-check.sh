#!/usr/bin/env bash
# Bisect oracle for pktcfg's seeded literal-tab heap-buffer-overflow (#5).
#
# Deliberately kept OUTSIDE the pktcfg repository it bisects: `git bisect run`
# checks out a different commit before every invocation, and a script that is
# itself part of the bisected commit range can disappear (early commits, no
# tools/pktcfg_replay.c yet) or change out from under itself mid-run. Running
# from outside the repo, with the reproducer bytes embedded rather than read
# from crash/crash-literal-tab.bin (which doesn't exist before commit
# af7c747), sidesteps both problems.
#
# Usage: pktcfg-bisect-check.sh [path-to-pktcfg-checkout]
# Exit status feeds directly to `git bisect run`:
#   0   = good (build succeeds, no sanitizer abort on the reproducer)
#   1   = bad  (build succeeds, sanitizer aborts on the reproducer)
#   125 = skip (this commit can't be built/tested at all -- git bisect run's
#               own convention for "untestable", never used within the
#               documented good..bad range for this fixture)
set -u

REPO="${1:-$(pwd)}"
BUILD_DIR="${PKTCFG_BISECT_BUILD_DIR:-/tmp/pktcfg-bisect-build}"

if [ ! -f "$REPO/CMakeLists.txt" ]; then
    echo "pktcfg-bisect-check: no CMakeLists.txt at $REPO, skipping" >&2
    exit 125
fi

rm -rf "$BUILD_DIR"
if ! cmake -S "$REPO" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Debug -DPKTCFG_SANITIZE=ON \
        >"$BUILD_DIR.cfg.log" 2>&1; then
    echo "pktcfg-bisect-check: configure failed, skipping (see $BUILD_DIR.cfg.log)" >&2
    exit 125
fi
if ! cmake --build "$BUILD_DIR" --target pktcfg_replay >"$BUILD_DIR.build.log" 2>&1; then
    echo "pktcfg-bisect-check: build failed, skipping (see $BUILD_DIR.build.log)" >&2
    exit 125
fi

# crash/crash-literal-tab.bin, embedded so this script doesn't depend on that
# file existing in whichever commit is checked out.
REPRO="$BUILD_DIR.repro.bin"
base64 -d >"$REPRO" <<'EOF'
UEtUQwEBAAAHAAMAY29sdW1uc2EJYg==
EOF

if "$BUILD_DIR/pktcfg_replay" "$REPRO" 5 >"$BUILD_DIR.replay.log" 2>&1; then
    echo "pktcfg-bisect-check: good ($REPO) -- no sanitizer abort"
    exit 0
else
    echo "pktcfg-bisect-check: bad ($REPO) -- sanitizer aborted, see $BUILD_DIR.replay.log"
    exit 1
fi
