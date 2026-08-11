"""Reading and building the archives the snapshot endpoint hashes.

Two directions:

* `enumerate_members` — the archive already exists (an uploaded file, or an already
  materialized export); this reads it well enough to report honest `file_count` and
  `bytes_total`, and refuses one it cannot safely account for. It never extracts a
  member to disk itself, so nothing here writes anywhere — but the refusal is the
  promise this module makes to whatever *does* extract this archive later (the
  BASELINE stage, not yet built): an archive `enumerate_members` accepts is meant to
  be extractable the ordinary way without a downstream consumer having to re-derive
  its own safety checks with less context than this one has.
* `build_tar_from_directory` — the archive does not exist yet; the mission's own
  repository is a local, allowlisted directory (`source="git"` with no `archive_ref`),
  and this walks it into a deterministic tar. No `git` subprocess, no shell, no network
  — plain file I/O over a path that `authorization.service` has already checked resolves
  inside the allowlisted source root.

## SEC-26 — link-following is a distinct defect from path-traversal, and both are refused

`_is_safe_member_name` defends the *name* a member is written at — the classic zip-slip
path-traversal shape (`../../etc/passwd`, an absolute path). It says nothing about a
member's *type*. A tar symlink or hardlink member can carry a fully safe `name` while its
`linkname` points anywhere the extracting process can reach; `enumerate_members` counting
such a member as an ordinary file does not make it one, and Python's own
`tarfile.extractall` does not filter this by default on this project's target interpreter
(3.12 — PEP 706's `extraction_filter` only defaults to a filtering mode starting in 3.14).
A snapshot archive has no legitimate reason to contain a symlink or hardlink —
`build_tar_from_directory`, the only writer this module ships, never produces one — so
`_enumerate_tar` refuses every symlink and hardlink member outright rather than trying to
validate where they point. The zip case gets the analogous check for the same reason,
even though `zipfile.extractall` does not itself materialize symlinks from Unix mode bits
the way `tarfile.extractall` does — the archive is refused before that distinction matters.
"""

from __future__ import annotations

import stat
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
                # SEC-26: a symlink or hardlink member's `name` can be perfectly safe
                # while its `linkname` points anywhere the extracting process can
                # reach. `_is_safe_member_name` above never looks at `linkname`, so
                # link members are refused by type rather than validated by target —
                # a repository snapshot has no legitimate reason to contain one, and
                # `build_tar_from_directory` never produces one.
                if member.issym() or member.islnk():
                    raise UnreadableArchiveError(
                        "The snapshot archive contains a symlink or hardlink member.",
                        details={"member": member.name, "linkname": member.linkname},
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
                # SEC-26, the zip half. `zipfile.extractall` does not itself turn a
                # POSIX symlink mode bit into a filesystem symlink, but the archive is
                # refused before that distinction gets to matter — the same "no
                # legitimate reason for one to exist here" reasoning as the tar case.
                unix_mode = info.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise UnreadableArchiveError(
                        "The snapshot archive contains a symlink member.",
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
