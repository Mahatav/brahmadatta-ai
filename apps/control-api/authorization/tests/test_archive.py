"""`authorization.archive`: honest counts, and archives it should refuse."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

import pytest

from authorization.archive import build_tar_from_directory, enumerate_members
from authorization.errors import UnreadableArchiveError


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
