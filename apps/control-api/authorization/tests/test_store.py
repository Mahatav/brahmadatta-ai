"""`authorization.store`: the digest is computed, never trusted."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from authorization.errors import UnreadableArchiveError
from authorization.store import ingest_from_path, path_for


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def test_ingest_returns_the_real_digest_of_the_bytes_it_read(tmp_path: Path):
    source = _write(tmp_path / "src.bin", b"hello brahmadatta")
    result = ingest_from_path(tmp_path / "store", source, max_bytes=10_000)

    assert result.sha256 == hashlib.sha256(b"hello brahmadatta").hexdigest()
    assert result.path.read_bytes() == b"hello brahmadatta"


def test_ingest_stores_content_addressed_with_the_right_layout_and_mode(tmp_path: Path):
    source = _write(tmp_path / "src.bin", b"content")
    root = tmp_path / "store"
    result = ingest_from_path(root, source, max_bytes=10_000)

    expected = path_for(root, hashlib.sha256(b"content").hexdigest())
    assert result.path == expected
    assert oct(result.path.stat().st_mode)[-3:] == "600"
    assert oct(result.path.parent.stat().st_mode)[-3:] == "700"


def test_a_digest_is_a_function_of_content_not_of_the_callers_claim(tmp_path: Path):
    """Two different byte strings never collide, and the caller never gets to name
    the digest — it falls straight out of what was actually read."""
    a = _write(tmp_path / "a.bin", b"AAAA")
    b = _write(tmp_path / "b.bin", b"BBBB")
    root = tmp_path / "store"

    result_a = ingest_from_path(root, a, max_bytes=10_000)
    result_b = ingest_from_path(root, b, max_bytes=10_000)

    assert result_a.sha256 != result_b.sha256
    assert result_a.path != result_b.path


def test_ingesting_the_same_bytes_twice_is_idempotent(tmp_path: Path):
    source = _write(tmp_path / "src.bin", b"same content")
    root = tmp_path / "store"

    first = ingest_from_path(root, source, max_bytes=10_000)
    second = ingest_from_path(root, source, max_bytes=10_000)

    assert first.sha256 == second.sha256
    assert first.path == second.path


def test_an_oversized_source_is_refused_and_no_partial_file_is_left_in_the_store(
    tmp_path: Path,
):
    source = _write(tmp_path / "big.bin", b"x" * 100)
    root = tmp_path / "store"

    with pytest.raises(UnreadableArchiveError):
        ingest_from_path(root, source, max_bytes=10)

    # Nothing was written under any digest, and the scratch directory is clean.
    tmp_dir = root / ".tmp"
    if tmp_dir.exists():
        assert list(tmp_dir.iterdir()) == []
    leftover = list(root.glob("*/*"))
    assert leftover == [], f"unexpected file(s) left behind: {leftover}"


def test_a_missing_source_is_refused(tmp_path: Path):
    with pytest.raises(UnreadableArchiveError):
        ingest_from_path(tmp_path / "store", tmp_path / "does-not-exist.bin", max_bytes=100)
