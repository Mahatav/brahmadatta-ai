"""Immutable snapshot hashing.

`contracts.schemas.envelope.SnapshotPayload` and
`contracts.schemas.missions.SnapshotRecord` already define the shape this has to produce:
a `snapshot_sha256` matching `^[0-9a-f]{64}$`, an optional `commit_sha`, `file_count`, and
`bytes_total`. This module computes that hash from the tree actually handed to the build —
not from `git rev-parse HEAD`, which only identifies the commit and says nothing about
whether the working tree matches it.

Why content, not just the commit
---------------------------------

A commit SHA identifies what should be on disk. It does not prove what is. A build
directory can be a `git archive` export, a snapshot ingested from an upload (D-025's
`source: "upload"` path, `contracts.schemas.missions.SnapshotRequest`), or a working tree
with local changes — including a patch candidate applied for verification, which is a
legitimate part of the mission and must produce a *different* hash from the baseline's
pristine tree, on purpose. Recording `commit_sha` when one exists is still useful
provenance, but `snapshot_sha256` is what makes two runs against "the same input"
verifiable rather than assumed.

Hash construction
------------------

Deterministic and platform-independent:

1. Walk every regular file under the root, sorted by POSIX-style relative path (``/``
   separator regardless of host OS) so the same tree hashes the same way on Linux and
   macOS.
2. Skip VCS metadata (``.git/``) and this package's own jail scratch directory
   (``.brahmadatta/``, created by `adapters/cpp/jail.py`) — neither is part of the target,
   and the jail directory does not even exist until a build has already started, which
   would make the hash depend on how far the pipeline had gotten.
3. Feed a running SHA-256 the sequence ``path_bytes, b"\\0", file_sha256, b"\\n"`` per file,
   where ``file_sha256`` is the file's own content hash (streamed, not loaded whole — a
   large corpus directory should not require holding it in memory).

This is a Merkle-style path+content hash, not a tar/cpio byte-for-byte hash, precisely so
it does not depend on file ordering, mtimes, permission bits, or archive format — the
things that make two byte-identical trees produce different tarballs.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import AdapterError

__all__ = ["SnapshotInfo", "hash_source_tree"]

_EXCLUDED_DIR_NAMES = frozenset({".git", ".brahmadatta"})
_READ_CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class SnapshotInfo:
    """Matches the field names of `contracts.schemas.missions.SnapshotRecord` /
    `SnapshotPayload` exactly, so a caller can pass `**info.as_dict()` straight into the
    contract type once #14's models exist."""

    snapshot_sha256: str
    commit_sha: str | None
    file_count: int
    bytes_total: int

    def as_dict(self) -> dict[str, object]:
        return {
            "snapshot_sha256": self.snapshot_sha256,
            "commit_sha": self.commit_sha,
            "file_count": self.file_count,
            "bytes_total": self.bytes_total,
        }


def _file_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_READ_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _git_commit_sha(root: Path) -> str | None:
    """`HEAD` of the repo containing ``root``, or ``None`` when there isn't one.

    Deliberately does not require ``root`` itself to be a repo root: the demo target at
    `demo/repositories/pktcfg/` is a subdirectory of the monorepo's single `.git`, not a
    repo of its own, and `git rev-parse` already climbs parent directories to find it — the
    same way it would from any subdirectory on a command line. An upload-sourced snapshot
    with no `.git` anywhere above it correctly falls through to `None`.
    """
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, shell=False, read-only
            [git, "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def hash_source_tree(root: Path | str) -> SnapshotInfo:
    """Compute the immutable snapshot hash for the tree at ``root``.

    Raises :class:`AdapterError` if ``root`` does not exist or contains no files — an
    empty hash is not a snapshot of anything.
    """
    resolved = Path(root).resolve()
    if not resolved.is_dir():
        raise AdapterError(f"snapshot root does not exist or is not a directory: {resolved}")

    entries: list[tuple[str, str, int]] = []
    for path in resolved.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _EXCLUDED_DIR_NAMES for part in path.relative_to(resolved).parts[:-1]):
            continue
        rel = path.relative_to(resolved).as_posix()
        file_hash, size = _file_sha256(path)
        entries.append((rel, file_hash, size))

    if not entries:
        raise AdapterError(f"no files found under snapshot root: {resolved}")

    entries.sort(key=lambda entry: entry[0])

    tree_digest = hashlib.sha256()
    bytes_total = 0
    for rel, file_hash, size in entries:
        tree_digest.update(rel.encode("utf-8"))
        tree_digest.update(b"\0")
        tree_digest.update(file_hash.encode("ascii"))
        tree_digest.update(b"\n")
        bytes_total += size

    return SnapshotInfo(
        snapshot_sha256=tree_digest.hexdigest(),
        commit_sha=_git_commit_sha(resolved),
        file_count=len(entries),
        bytes_total=bytes_total,
    )
