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
def pre_cmake_policy_floor_source(tmp_path: Path) -> Path:
    """A private copy of pktcfg whose `cmake_minimum_required` predates CMake 4.0's
    policy floor — mirroring #290's real finding running BASELINE against Magma's
    libpng target. See `adapters/cpp/tests/conftest.py`'s identical fixture for the
    full rationale; kept as its own copy here rather than a cross-package import,
    matching this file's existing convention (`broken_configure_source` above is
    already duplicated the same way, not imported from `adapters/cpp/tests`).
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
def warning_producing_source(tmp_path: Path) -> Path:
    """A real copy of pktcfg with one real, compiler-diagnostic-producing function
    appended to `src/config.c` (#23) — never a mutation of the committed tree.

    `-Wall -Wextra -Wshadow -Wconversion` is already on for every pktcfg source file
    (`CMakeLists.txt`), so this genuinely warns under the exact flags BASELINE already
    builds with; no CMake change needed. Two distinct, real diagnostics: an unused
    local variable (`-Wunused-variable`) and a narrowing implicit conversion
    (`-Wconversion`), on two different lines, so `test_run_baseline.py`'s assertions
    can check more than one location is captured.
    """
    dest = tmp_path / "pktcfg-warnings"
    shutil.copytree(PKTCFG_SOURCE, dest)
    config_c = dest / "src" / "config.c"
    config_c.write_text(
        config_c.read_text()
        + "\n"
        "/* #23 test fixture: a real, intentional compiler diagnostic. */\n"
        "static int pkt_debug_probe_diagnostic(void)\n"
        "{\n"
        "    int diagnostic_probe_unused = 0;\n"
        "    long wide_value = 90000;\n"
        "    short narrowed_value = wide_value;\n"
        "    return narrowed_value;\n"
        "}\n"
    )
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
