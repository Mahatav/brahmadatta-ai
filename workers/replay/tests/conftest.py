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

