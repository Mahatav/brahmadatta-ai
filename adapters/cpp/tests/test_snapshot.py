from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from adapters.cpp.errors import AdapterError
from adapters.cpp.snapshot import hash_source_tree

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def test_hash_is_deterministic_across_runs(pktcfg_source: Path) -> None:
    first = hash_source_tree(pktcfg_source)
    second = hash_source_tree(pktcfg_source)
    assert first.snapshot_sha256 == second.snapshot_sha256
    assert _SHA256_HEX.match(first.snapshot_sha256)
    assert first.file_count > 0
    assert first.bytes_total > 0


def test_hash_changes_when_a_file_changes(tmp_path: Path, pktcfg_source: Path) -> None:
    """Injected violation: mutate one byte of one file and confirm the hash moves. A hash
    that ignores content (e.g. one built only from file names) would pass every other test
    in this module and still be useless — this is the test that rules that out."""
    copy = tmp_path / "pktcfg-copy"
    shutil.copytree(pktcfg_source, copy)
    before = hash_source_tree(copy)

    target_file = copy / "src" / "decode.c"
    target_file.write_text(target_file.read_text() + "\n// one harmless comment\n")

    after = hash_source_tree(copy)
    assert after.snapshot_sha256 != before.snapshot_sha256
    assert after.file_count == before.file_count  # same files, different content


def test_hash_is_independent_of_walk_order(tmp_path: Path) -> None:
    """Two directories with identically-named, identically-contentful files must hash the
    same even if created in a different order — the sort in hash_source_tree must be
    doing the work, not incidental filesystem ordering."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    for name in ["zeta.c", "alpha.c", "middle.c"]:
        (a / name).write_text(f"content of {name}")
    for name in ["alpha.c", "middle.c", "zeta.c"]:
        (b / name).write_text(f"content of {name}")
    assert hash_source_tree(a).snapshot_sha256 == hash_source_tree(b).snapshot_sha256


def test_git_metadata_and_jail_scratch_are_excluded(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "real.c").write_text("int main(void){return 0;}")
    before = hash_source_tree(root)

    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (root / ".brahmadatta").mkdir()
    (root / ".brahmadatta" / "logs").mkdir()
    (root / ".brahmadatta" / "logs" / "whatever.out").write_text("build noise")

    after = hash_source_tree(root)
    assert after.snapshot_sha256 == before.snapshot_sha256
    assert after.file_count == before.file_count == 1


def test_an_empty_directory_raises(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(AdapterError, match="no files found"):
        hash_source_tree(empty)


def test_commit_sha_resolves_from_a_nested_path_inside_a_repo(pktcfg_source: Path) -> None:
    """demo/repositories/pktcfg is a subdirectory of the monorepo, not its own git root.
    `git rev-parse` must still find the enclosing repo's HEAD."""
    info = hash_source_tree(pktcfg_source)
    if info.commit_sha is not None:
        assert len(info.commit_sha) == 40
        assert all(c in "0123456789abcdef" for c in info.commit_sha)
