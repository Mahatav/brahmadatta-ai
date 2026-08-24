#!/usr/bin/env bash
# Materialise pktcfg's own seeded git history (#5) from the bundle checked into this
# repository, so `git -C demo/repositories/pktcfg bisect ...` works the ordinary way.
#
# demo/repositories/pktcfg/.git is not itself committed to brahmadatta-ai (see the
# .gitignore entry for it, and demo/repositories/pktcfg/README.md #git-history-and-the-
# bisect-answer-key for the full write-up): a directory containing its own .git becomes a
# submodule gitlink the moment `git add` sees it in the outer repo, which is more than a
# fixture needs. Instead the real 14-commit history ships as a git bundle at
# demo/repositories/pktcfg-history.bundle, and this script turns that bundle back into a
# working nested repository whose tracked file content already matches what the outer
# repo ships at demo/repositories/pktcfg/.
#
# Safe to re-run. Entirely offline -- the bundle is a local file, nothing is fetched over
# the network, which matters for an air-gapped rehearsal or the finale itself.
#
# Usage: demo/repositories/restore-pktcfg-history.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE="$SCRIPT_DIR/pktcfg-history.bundle"
TARGET="$SCRIPT_DIR/pktcfg"

if [ ! -f "$BUNDLE" ]; then
    echo "restore-pktcfg-history: bundle not found at $BUNDLE" >&2
    exit 1
fi
if [ ! -d "$TARGET" ]; then
    echo "restore-pktcfg-history: target directory not found at $TARGET" >&2
    exit 1
fi

git bundle verify "$BUNDLE" >/dev/null

rm -rf "$TARGET/.git"
# init onto a throwaway branch name: `git fetch bundle main:main` refuses to write
# refs/heads/main while it is the branch currently checked out (HEAD), which it always
# is right after `git init -b main`.
git -C "$TARGET" init -q -b _import
git -C "$TARGET" fetch -q "$BUNDLE" main:main

# --hard by design: the fixture's whole point is that the nested repo's working tree
# matches its own HEAD, which is also exactly what the outer repo already tracks at this
# path, so this should not actually change any file on disk. If it does, the bundle and
# the outer-tracked snapshot have drifted, and that is worth knowing loudly.
git -C "$TARGET" checkout -q -f main
# _import was never actually committed to (an "unborn" branch the whole time), so there
# is usually no ref left to clean up -- this is best-effort, not a correctness check.
git -C "$TARGET" branch -q -D _import 2>/dev/null || true

echo "restore-pktcfg-history: $TARGET is now a standalone git repo at $(git -C "$TARGET" rev-parse --short HEAD) ($(git -C "$TARGET" log --oneline | wc -l | tr -d ' ') commits)"
