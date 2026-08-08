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
