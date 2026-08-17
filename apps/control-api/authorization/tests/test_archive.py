"""`authorization.archive`: honest counts, and archives it should refuse."""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from authorization.archive import build_tar_from_directory, enumerate_members, extract_archive
from authorization.errors import SnapshotExtractionFailedError, UnreadableArchiveError


def test_enumerate_members_counts_a_real_tar_honestly(tmp_path: Path):
    tar_path = tmp_path / "a.tar"
    with tarfile.open(tar_path, "w") as tar:
        for name, content in [("a.txt", b"12345"), ("dir/b.txt", b"1234567")]:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            import io

            tar.addfile(info, io.BytesIO(content))

    info = enumerate_members(tar_path)
    assert info.file_count == 2
    assert info.bytes_total == 12


def test_enumerate_members_counts_a_real_zip_honestly(tmp_path: Path):
    zip_path = tmp_path / "a.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("a.txt", b"12345")
        zf.writestr("dir/b.txt", b"1234567")

    info = enumerate_members(zip_path)
    assert info.file_count == 2
    assert info.bytes_total == 12


def test_a_file_that_is_neither_tar_nor_zip_is_refused(tmp_path: Path):
    junk = tmp_path / "junk.bin"
    junk.write_bytes(b"not an archive at all")

    with pytest.raises(UnreadableArchiveError):
        enumerate_members(junk)


def test_a_tar_with_a_path_traversal_member_is_refused(tmp_path: Path):
    """Inject the violation and confirm it actually fails: this is the exact defect
    zip-slip depends on, and the test proves the guard trips on it rather than
    trusting that it would."""
    tar_path = tmp_path / "evil.tar"
    with tarfile.open(tar_path, "w") as tar:
        info = tarfile.TarInfo("../../etc/passwd")
        info.size = 4
        import io

        tar.addfile(info, io.BytesIO(b"pwnd"))

    with pytest.raises(UnreadableArchiveError):
        enumerate_members(tar_path)


def test_a_zip_with_an_absolute_member_path_is_refused(tmp_path: Path):
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("/etc/passwd", b"pwnd")

    with pytest.raises(UnreadableArchiveError):
        enumerate_members(zip_path)


def test_a_tar_symlink_with_a_safe_name_but_an_escaping_target_is_refused(tmp_path: Path):
    """SEC-26: the exact PoC shape from the round-4 security review. A symlink member
    can carry a fully safe `name` while its `linkname` points anywhere the extracting
    process can reach — `_is_safe_member_name` only ever looks at `name`, so this has
    to be caught by member type, not by re-checking the name a second way.

    Injected as the review found it: a symlink member named "innocuous_link" whose
    target escapes several directories up, plus a regular member that writes through
    it. `enumerate_members` must refuse the archive outright rather than report it as
    two ordinary, safely-named files.
    """
    tar_path = tmp_path / "evil-symlink.tar"
    with tarfile.open(tar_path, "w") as tar:
        link = tarfile.TarInfo("innocuous_link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../../../etc"
        tar.addfile(link)

        import io

        victim = tarfile.TarInfo("innocuous_link/passwd")
        victim.size = 14
        tar.addfile(victim, io.BytesIO(b"attacker bytes"))

    with pytest.raises(UnreadableArchiveError):
        enumerate_members(tar_path)


def test_a_tar_hardlink_member_is_refused(tmp_path: Path):
    tar_path = tmp_path / "evil-hardlink.tar"
    with tarfile.open(tar_path, "w") as tar:
        real = tarfile.TarInfo("real.txt")
        real.size = 4
        import io

        tar.addfile(real, io.BytesIO(b"data"))

        link = tarfile.TarInfo("link.txt")
        link.type = tarfile.LNKTYPE
        link.linkname = "/etc/shadow"
        tar.addfile(link)

    with pytest.raises(UnreadableArchiveError):
        enumerate_members(tar_path)


def test_a_zip_symlink_member_is_refused(tmp_path: Path):
    import stat as stat_module

    zip_path = tmp_path / "evil-symlink.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        info = zipfile.ZipInfo("innocuous_link")
        info.external_attr = (stat_module.S_IFLNK | 0o777) << 16
        zf.writestr(info, "../../../../etc/passwd")

    with pytest.raises(UnreadableArchiveError):
        enumerate_members(zip_path)


def test_a_tar_with_a_safe_regular_file_is_still_accepted(tmp_path: Path):
    """The symlink/hardlink refusal must not become a blanket refusal of every
    archive — an ordinary file-only tar is still accepted, same as before SEC-26."""
    tar_path = tmp_path / "fine.tar"
    with tarfile.open(tar_path, "w") as tar:
        info = tarfile.TarInfo("ordinary.txt")
        info.size = 3
        import io

        tar.addfile(info, io.BytesIO(b"abc"))

    result = enumerate_members(tar_path)
    assert result.file_count == 1
    assert result.bytes_total == 3


def test_build_tar_from_directory_excludes_git_metadata(tmp_path: Path):
    source = tmp_path / "repo"
    (source / ".git").mkdir(parents=True)
    (source / ".git" / "config").write_text("should not be in the snapshot")
    (source / "src").mkdir()
    (source / "src" / "main.c").write_text("int main(void) { return 0; }")

    dest = tmp_path / "out.tar"
    build_tar_from_directory(source, dest)

    with tarfile.open(dest) as tar:
        names = tar.getnames()
    assert names == ["src/main.c"]


def test_build_tar_from_directory_is_deterministic_across_runs(tmp_path: Path):
    import hashlib

    source = tmp_path / "repo"
    (source / "a").mkdir(parents=True)
    (source / "a" / "one.txt").write_text("one")
    (source / "b.txt").write_text("two")

    dest1 = tmp_path / "out1.tar"
    dest2 = tmp_path / "out2.tar"
    build_tar_from_directory(source, dest1)
    build_tar_from_directory(source, dest2)

    assert hashlib.sha256(dest1.read_bytes()).hexdigest() == hashlib.sha256(
        dest2.read_bytes()
    ).hexdigest()


# --- extract_archive: the round trip -------------------------------------------------


def test_extract_archive_round_trips_build_tar_from_directory(tmp_path: Path):
    """`extract_archive` is the inverse of `build_tar_from_directory` (#168, T0b):
    build a real tree, tar it, extract the tar, and confirm the extracted tree is
    byte-identical in both content and structure to the original — not merely
    "the right number of files"."""
    source = tmp_path / "repo"
    (source / "src").mkdir(parents=True)
    (source / "src" / "main.c").write_text("int main(void) { return 0; }\n")
    (source / "src" / "nested" / "deep").mkdir(parents=True)
    (source / "src" / "nested" / "deep" / "util.c").write_bytes(b"\x00\x01binary-ish\xff")
    (source / "README.md").write_text("demo target\n")

    tar_path = tmp_path / "snapshot.tar"
    build_tar_from_directory(source, tar_path)

    dest = tmp_path / "extracted"
    info = extract_archive(tar_path, dest)

    source_files = sorted(
        p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()
    )
    extracted_files = sorted(
        p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()
    )
    assert extracted_files == source_files
    for rel in source_files:
        assert (dest / rel).read_bytes() == (source / rel).read_bytes()

    assert info.file_count == len(source_files)
    assert info.bytes_total == sum((source / rel).stat().st_size for rel in source_files)


def test_extract_archive_normalizes_extracted_permissions(tmp_path: Path):
    """An extracted file's mode is never taken from the archive header — it is
    always the fixed, sane mode this module applies, regardless of what a
    (potentially hostile) archive's own header claimed."""
    tar_path = tmp_path / "weird-perms.tar"
    with tarfile.open(tar_path, "w") as tar:
        info = tarfile.TarInfo("setuid.txt")
        content = b"hi"
        info.size = len(content)
        info.mode = 0o4777  # setuid + world-writable, deliberately hostile
        tar.addfile(info, io.BytesIO(content))

    dest = tmp_path / "out"
    extract_archive(tar_path, dest)

    mode = (dest / "setuid.txt").stat().st_mode
    assert not (mode & 0o4000)  # setuid bit never survives
    assert (mode & 0o777) == 0o644


# --- extract_archive: malicious members are refused, not partially extracted --------


def test_extract_archive_refuses_a_tar_path_traversal_member(tmp_path: Path):
    tar_path = tmp_path / "evil.tar"
    with tarfile.open(tar_path, "w") as tar:
        info = tarfile.TarInfo("../../etc/passwd")
        info.size = 4
        tar.addfile(info, io.BytesIO(b"pwnd"))

    dest = tmp_path / "out"
    with pytest.raises(UnreadableArchiveError):
        extract_archive(tar_path, dest)

    # Nothing was left behind for a caller to mistake for a completed extraction, and
    # nothing was ever written outside tmp_path/out either.
    assert not dest.exists()
    assert not (tmp_path.parent / "etc").exists()


def test_extract_archive_refuses_a_tar_absolute_path_member(tmp_path: Path):
    tar_path = tmp_path / "evil-abs.tar"
    with tarfile.open(tar_path, "w") as tar:
        info = tarfile.TarInfo("/etc/passwd")
        info.size = 4
        tar.addfile(info, io.BytesIO(b"pwnd"))

    dest = tmp_path / "out"
    with pytest.raises(UnreadableArchiveError):
        extract_archive(tar_path, dest)
    assert not dest.exists()
    assert not Path("/etc/passwd-pwned-by-test").exists()


def test_extract_archive_refuses_a_zip_absolute_path_member(tmp_path: Path):
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("/etc/passwd", b"pwnd")

    dest = tmp_path / "out"
    with pytest.raises(UnreadableArchiveError):
        extract_archive(zip_path, dest)
    assert not dest.exists()


def test_extract_archive_refuses_a_tar_symlink_member(tmp_path: Path):
    """SEC-26's exact shape: a safely-named member whose target escapes the jail."""
    tar_path = tmp_path / "evil-symlink.tar"
    with tarfile.open(tar_path, "w") as tar:
        link = tarfile.TarInfo("innocuous_link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../../../etc"
        tar.addfile(link)
        victim = tarfile.TarInfo("innocuous_link/passwd")
        victim.size = 14
        tar.addfile(victim, io.BytesIO(b"attacker bytes"))

    dest = tmp_path / "out"
    with pytest.raises(UnreadableArchiveError):
        extract_archive(tar_path, dest)
    assert not dest.exists()


def test_extract_archive_refuses_a_tar_hardlink_member(tmp_path: Path):
    tar_path = tmp_path / "evil-hardlink.tar"
    with tarfile.open(tar_path, "w") as tar:
        real = tarfile.TarInfo("real.txt")
        real.size = 4
        tar.addfile(real, io.BytesIO(b"data"))
        link = tarfile.TarInfo("link.txt")
        link.type = tarfile.LNKTYPE
        link.linkname = "/etc/shadow"
        tar.addfile(link)

    dest = tmp_path / "out"
    with pytest.raises(UnreadableArchiveError):
        extract_archive(tar_path, dest)
    assert not dest.exists()


def test_extract_archive_refuses_a_tar_device_node_member(tmp_path: Path):
    """Not covered by `enumerate_members` (which only special-cases links), but a
    device-node member is exactly as unwelcome in a repository snapshot and has no
    legitimate reason to appear in one either."""
    tar_path = tmp_path / "evil-device.tar"
    with tarfile.open(tar_path, "w") as tar:
        node = tarfile.TarInfo("dev-node")
        node.type = tarfile.CHRTYPE
        node.devmajor = 1
        node.devminor = 5
        tar.addfile(node)

    dest = tmp_path / "out"
    with pytest.raises(UnreadableArchiveError):
        extract_archive(tar_path, dest)
    assert not dest.exists()


def test_extract_archive_a_mixed_archive_writes_nothing_if_one_member_is_unsafe(
    tmp_path: Path,
):
    """One unsafe member refuses the whole archive rather than extracting the
    innocent members and merely skipping the bad one."""
    tar_path = tmp_path / "mixed.tar"
    with tarfile.open(tar_path, "w") as tar:
        good = tarfile.TarInfo("fine.txt")
        good.size = 3
        tar.addfile(good, io.BytesIO(b"abc"))
        bad = tarfile.TarInfo("../escape.txt")
        bad.size = 3
        tar.addfile(bad, io.BytesIO(b"bad"))

    dest = tmp_path / "out"
    with pytest.raises(UnreadableArchiveError):
        extract_archive(tar_path, dest)
    assert not dest.exists()
    assert not (tmp_path / "escape.txt").exists()


# --- extract_archive: real failure modes, not just malice ---------------------------


def test_extract_archive_refuses_a_file_that_is_neither_tar_nor_zip(tmp_path: Path):
    junk = tmp_path / "junk.bin"
    junk.write_bytes(b"not an archive at all")

    dest = tmp_path / "out"
    with pytest.raises(UnreadableArchiveError):
        extract_archive(junk, dest)
    assert not dest.exists()


def test_extract_archive_refuses_a_corrupt_tar(tmp_path: Path):
    """A real tar, truncated mid-stream: `tarfile` accepts the magic bytes but fails
    while actually reading member data — the corrupt-archive case that is a genuine
    I/O failure mode, not an attack."""
    source = tmp_path / "repo"
    source.mkdir()
    (source / "a.txt").write_text("x" * 5000)
    good_tar = tmp_path / "good.tar"
    build_tar_from_directory(source, good_tar)

    corrupt = tmp_path / "corrupt.tar"
    original = good_tar.read_bytes()
    corrupt.write_bytes(original[: len(original) // 2])

    dest = tmp_path / "out"
    with pytest.raises(UnreadableArchiveError):
        extract_archive(corrupt, dest)
    assert not dest.exists()


def test_extract_archive_refuses_when_the_destination_already_exists(tmp_path: Path):
    source = tmp_path / "repo"
    source.mkdir()
    (source / "a.txt").write_text("hi")
    tar_path = tmp_path / "a.tar"
    build_tar_from_directory(source, tar_path)

    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "unrelated.txt").write_text("already here")

    with pytest.raises(SnapshotExtractionFailedError):
        extract_archive(tar_path, dest)
    # The pre-existing directory and its content are untouched, not wiped.
    assert (dest / "unrelated.txt").read_text() == "already here"


def test_extract_archive_reports_a_write_failure_and_cleans_up(tmp_path: Path):
    """Disk-full / permission-denied class of failure: the archive itself is fine,
    but writing an extracted member's bytes to disk raises `OSError`. Simulated
    rather than relying on an actually-full disk in the test environment."""
    source = tmp_path / "repo"
    source.mkdir()
    (source / "a.txt").write_text("hi")
    tar_path = tmp_path / "a.tar"
    build_tar_from_directory(source, tar_path)

    dest = tmp_path / "out"
    with patch(
        "authorization.archive.shutil.copyfileobj",
        side_effect=OSError(28, "No space left on device"),
    ):
        with pytest.raises(SnapshotExtractionFailedError):
            extract_archive(tar_path, dest)

    # Cleaned up rather than left as a half-written tree a caller could mistake for
    # a complete extraction.
    assert not dest.exists()
