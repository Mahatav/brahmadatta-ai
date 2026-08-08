"""Content-addressed artifact storage (architecture spec §5.2).

`ARTIFACT_ROOT/<sha256[0:2]>/<sha256>`, mode 0600, directory 0700. The digest is not a
label chosen by whoever calls `ingest_from_path` — it is computed here, by reading the
bytes back off disk one chunk at a time, and it is the name the bytes are stored under.
There is no code path in this module that writes a file at a path a caller picked.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from authorization.errors import UnreadableArchiveError

#: 1 MiB. Small enough to keep memory flat over an arbitrarily large archive, large
#: enough that the syscall overhead is not the bottleneck for the sizes this build
#: handles (demo targets are single-digit megabytes).
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class IngestResult:
    sha256: str
    path: Path
    bytes_written: int


def path_for(root: Path, sha256: str) -> Path:
    return root / sha256[:2] / sha256


def ingest_from_path(root: Path, source: Path, *, max_bytes: int) -> IngestResult:
    """Read `source`, hash it, and store it under its own digest.

    The return value's `sha256` is the only trustworthy digest for these bytes — it is
    what was actually read, not what anyone claimed about the file beforehand. The
    caller compares it against an asserted digest and refuses on mismatch; this
    function has no opinion about what the digest "should" be.

    Idempotent by construction: if the destination already exists, the freshly-read
    bytes are discarded rather than rewritten, so two concurrent ingests of the same
    content never race on the same destination file. Refuses (`UnreadableArchiveError`)
    if `source` is not a regular, readable file, or if it exceeds `max_bytes` — the
    read stops the instant the ceiling is crossed, so an oversized archive is never
    fully buffered or written to disk first.
    """
    if not source.is_file():
        raise UnreadableArchiveError(
            "The snapshot source could not be read as a regular file.",
            details={"source": str(source)},
        )

    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    tmp_dir = root / ".tmp"
    tmp_dir.mkdir(mode=0o700, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid.uuid4().hex}.tmp"

    digest = hashlib.sha256()
    written = 0
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with source.open("rb") as src, os.fdopen(fd, "wb") as out:
            fd = -1  # ownership transferred to the file object
            while True:
                chunk = src.read(CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise UnreadableArchiveError(
                        f"Snapshot source exceeds the {max_bytes}-byte ceiling.",
                        details={"max_bytes": max_bytes},
                    )
                digest.update(chunk)
                out.write(chunk)

        sha256 = digest.hexdigest()
        dest = path_for(root, sha256)
        dest.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if dest.exists():
            tmp_path.unlink(missing_ok=True)
        else:
            os.replace(tmp_path, dest)
        return IngestResult(sha256=sha256, path=dest, bytes_written=written)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        tmp_path.unlink(missing_ok=True)
        raise
