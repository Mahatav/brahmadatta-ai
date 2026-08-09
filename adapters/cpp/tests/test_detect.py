from __future__ import annotations

from pathlib import Path

import pytest

from adapters.cpp.detect import BuildSystem, detect
from adapters.cpp.errors import AdapterError


def test_pktcfg_is_detected_as_cmake_ctest(pktcfg_source: Path) -> None:
    result = detect(pktcfg_source)
    assert result.build_system is BuildSystem.C_CMAKE_CTEST
    assert result.project_name == "pktcfg"
    assert result.marker.name == "CMakeLists.txt"


def test_a_bare_makefile_is_detected_as_make(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("all:\n\techo hi\n")
    result = detect(tmp_path)
    assert result.build_system is BuildSystem.C_MAKE_CTEST


def test_cmake_wins_when_both_are_present(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("all:\n\techo hi\n")
    (tmp_path / "CMakeLists.txt").write_text("project(x)\n")
    result = detect(tmp_path)
    assert result.build_system is BuildSystem.C_CMAKE_CTEST


def test_an_empty_directory_is_not_detected(tmp_path: Path) -> None:
    """Injected violation: nothing recognisable is present — detection must refuse to
    guess, not default to one of the two build systems."""
    with pytest.raises(AdapterError, match="no supported build system"):
        detect(tmp_path)


def test_a_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(AdapterError):
        detect(tmp_path / "does-not-exist")
