"""Shared fixtures for the C/C++ adapter test suite.

Every fixture that builds a "broken" tree does so by copying the real
`demo/repositories/pktcfg` and mutating the copy — never by mutating the committed tree —
and every mutation that touches the target's own tests goes through the committed
`.patch` files rather than a hand-edited assertion, so the test suite exercises the same
artifacts the demo does.

Tests that shell out to `cmake`/`ctest` are marked `slow`; run everything with
`pytest -m ""` to include them, or `pytest -m "not slow"` for a fast subset. CI runs both.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PKTCFG_SOURCE = REPO_ROOT / "demo" / "repositories" / "pktcfg"

pytestmark = pytest.mark.skipif(
    not PKTCFG_SOURCE.is_dir(),
    reason="demo/repositories/pktcfg is not present in this checkout",
)


def _require_tool(name: str) -> None:
    if shutil.which(name) is None:
        pytest.skip(f"{name} not on PATH — cannot run adapter integration tests")


@pytest.fixture(scope="session", autouse=True)
def _require_toolchain() -> None:
    _require_tool("cmake")
    _require_tool("ctest")


@pytest.fixture
def pktcfg_source() -> Path:
    """The real, unmodified demo target. Never write into this fixture's tree."""
    return PKTCFG_SOURCE


@pytest.fixture
def candidate_b_source(tmp_path: Path) -> Path:
    """A private copy of pktcfg with the *rejected* crash-only patch applied.

    This is `patches/candidate-b-rejected-crash-only-fix.patch` — the real, committed
    candidate the verification demo is built to reject — not a hand-written test double.
    Standing prohibition (#41): nothing here is ever written back to the committed target.
    """
    if shutil.which("patch") is None:
        pytest.skip("`patch` not on PATH")
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


@pytest.fixture
def candidate_a_source(tmp_path: Path) -> Path:
    """A private copy of pktcfg with the *correct* fix applied."""
    if shutil.which("patch") is None:
        pytest.skip("`patch` not on PATH")
    dest = tmp_path / "pktcfg-candidate-a"
    shutil.copytree(PKTCFG_SOURCE, dest)
    patch_file = PKTCFG_SOURCE / "patches" / "candidate-a-correct-bounds-fix.patch"
    result = subprocess.run(
        ["patch", "-p1", "-i", str(patch_file)],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"failed to apply candidate-a patch: {result.stderr}"
    return dest


@pytest.fixture
def broken_configure_source(tmp_path: Path) -> Path:
    """A private copy of pktcfg whose `CMakeLists.txt` cannot configure.

    Exercises the CONFIGURE failure path with a real CMake error, not a mocked one.
    """
    dest = tmp_path / "pktcfg-broken"
    shutil.copytree(PKTCFG_SOURCE, dest)
    cmakelists = dest / "CMakeLists.txt"
    cmakelists.write_text("this is not valid CMake syntax (((\n" + cmakelists.read_text())
    return dest


@pytest.fixture
def pre_cmake_policy_floor_source(tmp_path: Path) -> Path:
    """A private copy of pktcfg whose `cmake_minimum_required` predates CMake 4.0's
    policy floor — mirroring the real situation #290 found running BASELINE against
    Magma's libpng target: `cmake_minimum_required(VERSION 3.1)` (libpng's own,
    unmodified) is rejected outright by CMake >= 4.0 ("Compatibility with CMake < 3.5
    has been removed from CMake") unless `-DCMAKE_POLICY_VERSION_MINIMUM=3.5` is also
    passed. `3.1` (not `3.5` itself) matches libpng's real, still-current
    `CMakeLists.txt` exactly, and is a real value CMake genuinely rejects — confirmed
    interactively against the CMake installed in this environment (4.2.3) before this
    fixture was written.

    Exercises `adapters/cpp/pipeline.py::run_variant`'s `extra_cache_entries`
    parameter / `adapters/cpp/variants.py::VariantSpec.with_extra_cache_entries`: this
    fixture's CONFIGURE step fails without the extra cache entry and succeeds with it
    (`test_pipeline.py`), and the CMakeLists.txt is otherwise byte-for-byte pktcfg, so
    a successful build still reports the same 8 real ctest cases.
    """
    dest = tmp_path / "pktcfg-pre-cmake-3-5"
    shutil.copytree(PKTCFG_SOURCE, dest)
    cmakelists = dest / "CMakeLists.txt"
    text = cmakelists.read_text()
    assert text.startswith("cmake_minimum_required(VERSION 3.16)"), (
        "fixture assumes pktcfg's own CMakeLists.txt still opens with "
        "cmake_minimum_required(VERSION 3.16) — update this fixture if that changed"
    )
    cmakelists.write_text(
        text.replace(
            "cmake_minimum_required(VERSION 3.16)",
            "cmake_minimum_required(VERSION 3.1)",
            1,
        )
    )
    return dest


@pytest.fixture
def broken_compile_source(tmp_path: Path) -> Path:
    """A private copy of pktcfg with a source file that fails to compile.

    Exercises the BUILD failure path (as opposed to CONFIGURE) with a real compiler error.
    """
    dest = tmp_path / "pktcfg-broken-compile"
    shutil.copytree(PKTCFG_SOURCE, dest)
    config_c = dest / "src" / "config.c"
    config_c.write_text("this is not valid C at all !!! ###\n" + config_c.read_text())
    return dest
