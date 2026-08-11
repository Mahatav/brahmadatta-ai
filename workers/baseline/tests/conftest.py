from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PKTCFG_SOURCE = REPO_ROOT / "demo" / "repositories" / "pktcfg"

pytestmark = pytest.mark.skipif(
    not PKTCFG_SOURCE.is_dir() or shutil.which("cmake") is None or shutil.which("ctest") is None,
    reason="demo/repositories/pktcfg or the CMake toolchain is not available in this checkout",
)


@pytest.fixture
def pktcfg_source() -> Path:
    return PKTCFG_SOURCE


@pytest.fixture
def broken_configure_source(tmp_path: Path) -> Path:
    dest = tmp_path / "pktcfg-broken"
    shutil.copytree(PKTCFG_SOURCE, dest)
    cmakelists = dest / "CMakeLists.txt"
    cmakelists.write_text("this is not valid CMake syntax (((\n" + cmakelists.read_text())
    return dest


@pytest.fixture
def candidate_b_source(tmp_path: Path) -> Path:
    if shutil.which("patch") is None:
        pytest.skip("`patch` not on PATH")
    import subprocess

    dest = tmp_path / "pktcfg-candidate-b"
    shutil.copytree(PKTCFG_SOURCE, dest)
    patch_file = PKTCFG_SOURCE / "patches" / "candidate-b-rejected-crash-only-fix.patch"
    result = subprocess.run(
        ["patch", "-p1", "-i", str(patch_file)],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"failed to apply candidate-b patch: {result.stderr}"
    return dest
