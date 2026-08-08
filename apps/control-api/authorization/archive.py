"""Reading and building the archives the snapshot endpoint hashes.

Two directions:

* `enumerate_members` — the archive already exists (an uploaded file, or an already
  materialized export); this reads it well enough to report honest `file_count` and
  `bytes_total`, and refuses one it cannot safely account for. It never extracts a
  member to disk, so zip-slip / tar path-traversal member names cannot write anywhere
  — but a member name outside its own archive is still refused outright, because a
  downstream stage that *does* extract this archive should never have to make that
  judgement call again with less context than this one has.
* `build_tar_from_directory` — the archive does not exist yet; the mission's own
  repository is a local, allowlisted directory (`source="git"` with no `archive_ref`),
  and this walks it into a deterministic tar. No `git` subprocess, no shell, no network
  — plain file I/O over a path that `authorization.service` has already checked resolves
  inside the allowlisted source root.
"""

from __future__ import annotations

import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from authorization.errors import UnreadableArchiveError

#: A member name is refused if, once normalized, it is absolute or steps outside the
#: archive root. This is the same class of defect zip-slip exploits rely on; refusing
#: it here means no later, less careful consumer of this archive has to re-derive the
#: check from scratch.
def _is_safe_member_name(name: str) -> bool:
    if not name or name.startswith("/") or name.startswith("\\"):
        return False
    pure = PurePosixPath(name.replace("\\", "/"))
    if pure.is_absolute():
        return False
    return ".." not in pure.parts


@dataclass(frozen=True)
class ArchiveInfo:
    file_count: int
    bytes_total: int


def enumerate_members(path: Path) -> ArchiveInfo:
    if tarfile.is_tarfile(path):
        return _enumerate_tar(path)
    if zipfile.is_zipfile(path):
        return _enumerate_zip(path)
    raise UnreadableArchiveError(
        "The snapshot archive is neither a readable tar nor a readable zip.",
        details={"path": str(path)},
    )


def _enumerate_tar(path: Path) -> ArchiveInfo:
    file_count = 0
    bytes_total = 0
    try:
        with tarfile.open(path, mode="r:*") as tar:
            for member in tar.getmembers():
                if not _is_safe_member_name(member.name):
                    raise UnreadableArchiveError(
                        "The snapshot archive contains an unsafe member path.",
                        details={"member": member.name},
                    )
                if member.isfile():
                    file_count += 1
                    bytes_total += member.size
    except tarfile.TarError as exc:
        raise UnreadableArchiveError(
            "The snapshot archive could not be read as a tar archive.",
            details={"reason": str(exc)},
        ) from exc
    return ArchiveInfo(file_count=file_count, bytes_total=bytes_total)


def _enumerate_zip(path: Path) -> ArchiveInfo:
    file_count = 0
    bytes_total = 0
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad is not None:
                raise UnreadableArchiveError(
                    "The snapshot archive failed its integrity check.",
                    details={"member": bad},
                )
            for info in zf.infolist():
                if not _is_safe_member_name(info.filename):
                    raise UnreadableArchiveError(
                        "The snapshot archive contains an unsafe member path.",
                        details={"member": info.filename},
                    )
                if not info.is_dir():
                    file_count += 1
                    bytes_total += info.file_size
    except zipfile.BadZipFile as exc:
        raise UnreadableArchiveError(
            "The snapshot archive could not be read as a zip archive.",
            details={"reason": str(exc)},
        ) from exc
    return ArchiveInfo(file_count=file_count, bytes_total=bytes_total)


#: Directories never included in a directory-sourced snapshot. Version-control
#: metadata is not part of the authorized target's content, and including it would
#: make the snapshot hash depend on the operator's local git state rather than on the
#: tree being analyzed.
_EXCLUDED_DIR_NAMES = frozenset({".git"})


def build_tar_from_directory(source_dir: Path, dest_path: Path) -> None:
    """Write a deterministic tar of `source_dir` to `dest_path`.

    Deterministic across repeated calls against the same tree: files are added in
    sorted path order, and `mtime`/`uid`/`gid`/`uname`/`gname` are normalized rather
    than read from the filesystem. Two ingests of the same tree therefore hash to the
    same digest, which is what makes a caller-supplied `archive_sha256` a meaningful
    assertion rather than a coin flip.
    """
    entries = sorted(
        p
        for p in source_dir.rglob("*")
        if p.is_file() and not _EXCLUDED_DIR_NAMES.intersection(p.relative_to(source_dir).parts)
    )
    with tarfile.open(dest_path, mode="w") as tar:
        for file_path in entries:
            arcname = file_path.relative_to(source_dir).as_posix()
            info = tar.gettarinfo(str(file_path), arcname=arcname)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with file_path.open("rb") as fh:
                tar.addfile(info, fh)
