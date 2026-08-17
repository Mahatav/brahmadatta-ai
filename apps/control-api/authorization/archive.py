"""Reading, building, and extracting the archives the snapshot endpoint hashes.

Three directions:

* `enumerate_members` — the archive already exists (an uploaded file, or an already
  materialized export); this reads it well enough to report honest `file_count` and
  `bytes_total`, and refuses one it cannot safely account for. It never extracts a
  member to disk itself, so nothing here writes anywhere — but the refusal is the
  promise this module makes to whatever *does* extract this archive later: an
  archive `enumerate_members` accepts is meant to be extractable the ordinary way
  without a downstream consumer having to re-derive its own safety checks with less
  context than this one has.
* `build_tar_from_directory` — the archive does not exist yet; the mission's own
  repository is a local, allowlisted directory (`source="git"` with no `archive_ref`),
  and this walks it into a deterministic tar. No `git` subprocess, no shell, no network
  — plain file I/O over a path that `authorization.service` has already checked resolves
  inside the allowlisted source root.
* `extract_archive` — the inverse of `build_tar_from_directory` (#168, T0b). A stored
  snapshot archive (`authorization.store.path_for(ARTIFACT_ROOT, sha256)`) needs to
  become a real, writable directory on disk before `workers.baseline.run_baseline_stage`
  or `orchestrator.verification.run_verification` can point a build/test tool at it.
  This does not trust that whatever produced the archive already ran it through
  `enumerate_members` — every member is re-validated here, independently, because this
  is the one function in the module that actually writes to disk and is the safety
  boundary of last resort for anything that reaches it.

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

import os
import shutil
import stat
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID

from authorization.errors import SnapshotExtractionFailedError, UnreadableArchiveError

#: Fixed, sane modes applied to every extracted entry, regardless of what the archive
#: itself carried. An archive member's mode bits are attacker-influenced input the
#: instant the archive is anything other than something this deployment built itself
#: (`build_tar_from_directory` never sets anything unusual, but `extract_archive` does
#: not get to assume the bytes it is handed came from there) — a setuid bit, a
#: world-writable directory, or a mode that disables the owner's own read access are
#: all things a hostile archive could otherwise smuggle onto disk. Fixed values close
#: that off entirely rather than trying to sanitize whatever was in the header.
_EXTRACTED_FILE_MODE = 0o644
_EXTRACTED_DIR_MODE = 0o755

#: 1 MiB. Mirrors `authorization.store.CHUNK_SIZE` — read/write in fixed chunks so a
#: single member's actual size (as opposed to what its header claims) is never
#: buffered in memory before the running extraction-budget check below gets to see it.
_COPY_CHUNK_SIZE = 1024 * 1024


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


def mission_staging_root(staging_root: Path, mission_id: UUID) -> Path:
    """Return the upload-staging namespace reserved for one mission.

    The upload endpoint is not implemented yet, but `source="upload"` already reads
    archives by `archive_ref`. Keeping this path shape here gives that future writer
    the same mission-bound contract that the snapshot reader enforces today.
    """
    return staging_root / str(mission_id)


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


def _copy_within_budget(
    src, out, *, member_name: str, bytes_so_far: int, max_bytes: int
) -> int:
    """Copy `src` into `out` in fixed-size chunks, refusing (`UnreadableArchiveError`)
    the instant the *cumulative* bytes written across the whole archive extraction —
    not just this one member — would exceed `max_bytes`. Returns the new running
    total on success.

    This is the decompression-bomb guard (round-4 review, HIGH-1): a `tar.gz` member
    of highly compressible content (e.g. runs of zero bytes) can sit at a ~1000:1
    compression ratio, so a multi-hundred-MB archive that itself passes
    `SNAPSHOT_MAX_BYTES` can decompress to hundreds of GB on disk. This checks bytes
    *actually read off the decompression stream and written to disk*, not
    `member.size` / `info.file_size` (the header fields the pre-check in
    `_extract_tar`/`_extract_zip` uses) — necessary for two reasons, one about a
    single member and one about many:

    * Defense in depth against a single member whose header lies. `member.size` /
      `info.file_size` are attacker-supplied input the moment the archive did not
      come from `build_tar_from_directory`, and this deployment does not get to
      assume `tarfile`/`zipfile`'s current internal behaviour of bounding `.read()`
      to the declared size (`_FileInFile.read`, `ZipExtFile._read1`, both in the
      stdlib as of this interpreter) holds forever, across every future Python
      version this deployment runs on, as the one thing standing between a lying
      header and an unbounded write.
    * The binding reason: the budget is cumulative *across every member written so
      far in this call*, not reset per member — this is what the pre-check, which
      only ever looks at one member's header in isolation, cannot see. Many
      individually honest, individually-under-cap members can still sum past the
      ceiling exactly as easily as one large one, and only a running total evaluated
      during the write pass itself catches that.

    Mirrors `authorization.store.ingest_from_path`'s "the read stops the instant the
    ceiling is crossed" contract: this raises mid-stream rather than buffering the
    whole member first, so a bomb is never fully decompressed before it is refused.
    """
    written = bytes_so_far
    while True:
        chunk = src.read(_COPY_CHUNK_SIZE)
        if not chunk:
            break
        written += len(chunk)
        if written > max_bytes:
            raise UnreadableArchiveError(
                "The snapshot archive would extract more than the "
                f"{max_bytes}-byte ceiling.",
                details={"member": member_name, "max_bytes": max_bytes},
            )
        out.write(chunk)
    return written


def _resolved_target_or_raise(dest_root: Path, member_name: str) -> Path:
    """The path `member_name` would be written at under `dest_root`, confirmed to
    still resolve inside it.

    Defense in depth, deliberately layered on top of `_is_safe_member_name` rather
    than replacing it: the lexical check above rejects `..` segments and a leading
    `/` or `\\`, but it uses `PurePosixPath`, which does not treat a Windows-style
    drive-qualified name (`C:\\Windows\\System32\\...`) as absolute — that string
    survives `_is_safe_member_name` on this project's Linux-only deployment target,
    where it is also harmless (`dest_root / "C:Windows/System32/..."` stays a plain,
    contained relative path; POSIX has no notion of a drive letter), but this check
    means that fact does not have to be reasoned about case by case. Every member
    this function accepts is proven, not merely assumed, to land under `dest_root`.
    """
    resolved_root = dest_root.resolve()
    target = (resolved_root / member_name).resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise UnreadableArchiveError(
            "The snapshot archive contains a member whose resolved path escapes the "
            "extraction directory.",
            details={"member": member_name},
        )
    return target


def extract_archive(archive_path: Path, dest_dir: Path, *, max_bytes: int) -> ArchiveInfo:
    """Safely extract `archive_path` (a tar or zip) into `dest_dir`, a fresh
    directory this function creates.

    `dest_dir` must not already exist — the caller hands this a scratch path it owns
    (a fresh, mission-scoped directory under a workspace root; see
    `orchestrator.snapshot.materialize_snapshot`), never a location that might already
    hold unrelated content extraction could be mistaken for having produced.

    `max_bytes` is a required, explicit ceiling on the *cumulative* bytes this call
    will write to disk across every member combined — the same "caller supplies the
    number, this function never guesses at one" contract `authorization.store.
    ingest_from_path` already uses for `max_bytes`. Callers reading it from
    `django.conf.settings` should pass `settings.SNAPSHOT_MAX_BYTES` (round-4 review,
    HIGH-1): reusing the ingest-side ceiling means the two ends of the archive
    round-trip — `build_tar_from_directory`/ingest capping the *compressed* bytes a
    caller may submit, and this function capping the *extracted* bytes it will ever
    write — share one number instead of two independently-chosen ones that could
    drift apart.

    Every member is checked four ways before anything is written for it, and nothing
    is written for *any* member until every member in the archive has passed all
    four — one unsafe member refuses the whole archive rather than leaving a
    partially-extracted tree with the bad member merely skipped:

    1. `_is_safe_member_name` — the zip-slip name check `enumerate_members` already
       applies, unchanged.
    2. Member *type*. Only regular files and directories are extracted. Symlinks and
       hardlinks are refused for the SEC-26 reason `enumerate_members` documents (a
       safe `name` says nothing about where a link's target points, and a repository
       snapshot has no legitimate reason to contain one); device nodes and FIFOs are
       refused outright too, since a tar archive can carry either and this deployment
       never produces or expects one.
    3. `_resolved_target_or_raise` — the resolved-path containment check described on
       that function, independent of and in addition to check 1.
    4. Declared size vs. `max_bytes` — a cheap pre-check (`member.size` / `info.
       file_size` against `max_bytes` alone, before any read is attempted) that
       catches a single member whose header alone already claims more than the
       ceiling. This is necessary but not sufficient: a header's declared size is
       attacker-supplied input, not a proof of the bytes a decompressor will actually
       produce. The binding enforcement is check 5, below, applied during the write
       pass itself.

    A fifth check applies only during the write pass, after every member above has
    already cleared checks 1-4: `_copy_within_budget` tracks the cumulative *actual*
    bytes read off each member's decompression stream and written to disk, across all
    members combined, and refuses the instant that running total would exceed
    `max_bytes` — this is the decompression-bomb guard proper (round-4 review,
    HIGH-1). A `tar.gz` member of highly compressible content can compress at up to
    ~1000:1, so an archive well under any reasonable upload-size ceiling can still
    decompress to hundreds of GB; this check bounds what actually reaches disk
    regardless of what the archive's own headers claim or how many members the excess
    is spread across.

    An extracted file's mode is never taken from the archive; see
    `_EXTRACTED_FILE_MODE` / `_EXTRACTED_DIR_MODE`.

    Raises `UnreadableArchiveError` for a corrupt, unparseable, unsafe, or
    over-budget archive — the same failure this deployment already treats as "no
    honest count exists for this archive" in `enumerate_members`. Raises
    `SnapshotExtractionFailedError` for a write-side failure (`OSError` — a full disk,
    a permission error, or anything else that stops bytes from reaching `dest_dir`)
    once the archive itself has already passed every safety check above. Either way,
    `dest_dir` is removed before the exception propagates: a caller must never be able
    to mistake a half-written, refused, or over-budget extraction for a complete one
    just because the directory still exists.
    """
    if dest_dir.exists():
        raise SnapshotExtractionFailedError(
            "Extraction destination already exists; refusing to extract into a "
            "directory that might already hold unrelated content.",
            details={"dest_dir": str(dest_dir)},
        )

    dest_dir.mkdir(parents=True, mode=0o700)
    try:
        if tarfile.is_tarfile(archive_path):
            info = _extract_tar(archive_path, dest_dir, max_bytes=max_bytes)
        elif zipfile.is_zipfile(archive_path):
            info = _extract_zip(archive_path, dest_dir, max_bytes=max_bytes)
        else:
            raise UnreadableArchiveError(
                "The snapshot archive is neither a readable tar nor a readable zip.",
                details={"path": str(archive_path)},
            )
        # `Path.mkdir(parents=True, mode=...)` only applies `mode` to the leaf
        # component it creates, not to any intermediate parent it has to create
        # along the way (documented pathlib behaviour) — so a nested member's
        # intermediate directories can end up with whatever the process umask
        # left them at rather than `_EXTRACTED_DIR_MODE`. Normalized in one pass
        # here rather than reasoned about per mkdir call above.
        # `dest_dir` itself is deliberately left at the restrictive `0700` it was
        # created with above (matching `authorization.store`'s own directory mode);
        # only the entries extracted *into* it are normalized to `_EXTRACTED_DIR_MODE`.
        for dirpath, dirnames, _filenames in os.walk(dest_dir):
            for name in dirnames:
                os.chmod(Path(dirpath) / name, _EXTRACTED_DIR_MODE)
        return info
    except BaseException:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise


def _extract_tar(path: Path, dest_dir: Path, *, max_bytes: int) -> ArchiveInfo:
    try:
        with tarfile.open(path, mode="r:*") as tar:
            members = tar.getmembers()

            # Pass 1: validate every member. Nothing is written until every member in
            # the archive has cleared every check — see extract_archive's docstring.
            for member in members:
                if not _is_safe_member_name(member.name):
                    raise UnreadableArchiveError(
                        "The snapshot archive contains an unsafe member path.",
                        details={"member": member.name},
                    )
                if member.issym() or member.islnk():
                    raise UnreadableArchiveError(
                        "The snapshot archive contains a symlink or hardlink member.",
                        details={"member": member.name, "linkname": member.linkname},
                    )
                if not (member.isfile() or member.isdir()):
                    raise UnreadableArchiveError(
                        "The snapshot archive contains a member that is not a "
                        "regular file or directory.",
                        details={"member": member.name},
                    )
                # Cheap pre-check against the *declared* size (round-4 review,
                # HIGH-1): catches a single member whose header alone already claims
                # more than the ceiling, before a single byte is read. `member.size`
                # is attacker-supplied input the moment this archive is not
                # `build_tar_from_directory`'s own output, so this narrows the field
                # early but is not the binding enforcement — see `_copy_within_budget`
                # in pass 2, which checks bytes actually produced, not declared.
                if member.isfile() and member.size > max_bytes:
                    raise UnreadableArchiveError(
                        "The snapshot archive contains a member whose declared size "
                        f"exceeds the {max_bytes}-byte extraction ceiling.",
                        details={
                            "member": member.name,
                            "declared_size": member.size,
                            "max_bytes": max_bytes,
                        },
                    )
                _resolved_target_or_raise(dest_dir, member.name)

            # Pass 2: write. Every member here already passed pass 1 in full.
            file_count = 0
            bytes_total = 0
            for member in members:
                target = dest_dir / member.name
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True, mode=_EXTRACTED_DIR_MODE)
                    continue
                target.parent.mkdir(
                    parents=True, exist_ok=True, mode=_EXTRACTED_DIR_MODE
                )
                extracted = tar.extractfile(member)
                if extracted is None:
                    # A regular-file member tarfile itself cannot hand back a stream
                    # for. Not observed in practice; refused rather than skipped.
                    raise UnreadableArchiveError(
                        "The snapshot archive has an unreadable file member.",
                        details={"member": member.name},
                    )
                with extracted, open(target, "wb") as out:
                    bytes_total = _copy_within_budget(
                        extracted,
                        out,
                        member_name=member.name,
                        bytes_so_far=bytes_total,
                        max_bytes=max_bytes,
                    )
                os.chmod(target, _EXTRACTED_FILE_MODE)
                file_count += 1
    except tarfile.TarError as exc:
        raise UnreadableArchiveError(
            "The snapshot archive could not be read as a tar archive.",
            details={"reason": str(exc)},
        ) from exc
    except OSError as exc:
        raise SnapshotExtractionFailedError(
            "Writing the extracted snapshot to disk failed.",
            details={"reason": str(exc)},
        ) from exc
    return ArchiveInfo(file_count=file_count, bytes_total=bytes_total)


def _extract_zip(path: Path, dest_dir: Path, *, max_bytes: int) -> ArchiveInfo:
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad is not None:
                raise UnreadableArchiveError(
                    "The snapshot archive failed its integrity check.",
                    details={"member": bad},
                )
            infos = zf.infolist()

            # Pass 1: validate every member, same shape as _extract_tar.
            for info in infos:
                if not _is_safe_member_name(info.filename):
                    raise UnreadableArchiveError(
                        "The snapshot archive contains an unsafe member path.",
                        details={"member": info.filename},
                    )
                unix_mode = info.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise UnreadableArchiveError(
                        "The snapshot archive contains a symlink member.",
                        details={"member": info.filename},
                    )
                # Cheap declared-size pre-check, same reasoning as _extract_tar's:
                # narrows the field before any read, not the binding enforcement.
                if not info.is_dir() and info.file_size > max_bytes:
                    raise UnreadableArchiveError(
                        "The snapshot archive contains a member whose declared size "
                        f"exceeds the {max_bytes}-byte extraction ceiling.",
                        details={
                            "member": info.filename,
                            "declared_size": info.file_size,
                            "max_bytes": max_bytes,
                        },
                    )
                _resolved_target_or_raise(dest_dir, info.filename)

            # Pass 2: write.
            file_count = 0
            bytes_total = 0
            for info in infos:
                target = dest_dir / info.filename
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True, mode=_EXTRACTED_DIR_MODE)
                    continue
                target.parent.mkdir(
                    parents=True, exist_ok=True, mode=_EXTRACTED_DIR_MODE
                )
                with zf.open(info) as src, open(target, "wb") as out:
                    bytes_total = _copy_within_budget(
                        src,
                        out,
                        member_name=info.filename,
                        bytes_so_far=bytes_total,
                        max_bytes=max_bytes,
                    )
                os.chmod(target, _EXTRACTED_FILE_MODE)
                file_count += 1
    except zipfile.BadZipFile as exc:
        raise UnreadableArchiveError(
            "The snapshot archive could not be read as a zip archive.",
            details={"reason": str(exc)},
        ) from exc
    except OSError as exc:
        raise SnapshotExtractionFailedError(
            "Writing the extracted snapshot to disk failed.",
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
