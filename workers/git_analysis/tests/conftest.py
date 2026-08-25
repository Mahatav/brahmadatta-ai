from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PKTCFG_SOURCE = REPO_ROOT / "demo" / "repositories" / "pktcfg"
RESTORE_SCRIPT = REPO_ROOT / "demo" / "repositories" / "restore-pktcfg-history.sh"
BUNDLE = REPO_ROOT / "demo" / "repositories" / "pktcfg-history.bundle"

#: #5's answer key (`demo/repositories/pktcfg/README.md` "Git history and the bisect
#: answer key") -- the commit `git bisect` must land on for every test in this file.
KNOWN_BAD_COMMIT = "114383dd517e49e1285b53608184cb744adb2aaa"
KNOWN_GOOD_COMMIT = "1fe6d02d4209f256d5436a661fb7b9698a6ba745"

pytestmark = pytest.mark.skipif(
    not PKTCFG_SOURCE.is_dir()
    or not BUNDLE.is_file()
    or shutil.which("cmake") is None
    or shutil.which("ctest") is None,
    reason="demo/repositories/pktcfg, its history bundle, or the CMake toolchain is not available in this checkout",
)


@pytest.fixture
def pktcfg_repo() -> Iterator[Path]:
    """`demo/repositories/pktcfg` with its real, bisectable git history materialised
    from the bundle (#5/D-146) -- restored fresh before the test and always left back
    on `main` afterwards, so this test never leaves a shared fixture checked out
    mid-bisect for whatever runs against it next (`workers/baseline/tests` included).
    """
    subprocess.run(
        ["bash", str(RESTORE_SCRIPT)], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    )
    try:
        yield PKTCFG_SOURCE
    finally:
        subprocess.run(
            ["git", "bisect", "reset"], cwd=PKTCFG_SOURCE, capture_output=True, text=True
        )
        subprocess.run(
            ["git", "checkout", "-q", "-f", "main"], cwd=PKTCFG_SOURCE, capture_output=True, text=True
        )
