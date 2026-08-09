"""Build-system detection.

`contracts.enums.LanguageAdapter` allows exactly two values — ``C_CMAKE_CTEST`` and
``C_MAKE_CTEST`` — so detection is not open-ended. It answers one question: does this tree
configure with CMake, or is it a bare Makefile?

CMake wins whenever a top-level `CMakeLists.txt` exists, even if a `Makefile` sits beside
it, because in a CMake project a checked-in `Makefile` is usually a convenience wrapper
around `cmake --build`. Running the wrapper instead of CMake would leave no `CMakeCache.txt`
to read the compiler identity out of and no `CTestTestfile.cmake` to run tests from.

Detection is deliberately shallow. #16's fallback position, written down in
`docs/09-company/01-vision-and-p0-cut.md` line 170, is to *"hardcode the build recipe, and
drop adapter generality"* — so a wrong guess on an exotic tree costs a config override, not
a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .errors import AdapterError

__all__ = ["BuildSystem", "DetectedTarget", "detect"]


class BuildSystem(StrEnum):
    """Mirrors `contracts.enums.LanguageAdapter`. Equality with that enum is asserted by
    `tests/test_contract_conformance.py::test_build_system_matches_language_adapter`."""

    C_CMAKE_CTEST = "C_CMAKE_CTEST"
    C_MAKE_CTEST = "C_MAKE_CTEST"


@dataclass(frozen=True, slots=True)
class DetectedTarget:
    """What was found, and the evidence for it."""

    build_system: BuildSystem
    source_dir: Path
    #: The file that decided it. Carried so a surprising detection can be argued with.
    marker: Path
    project_name: str

    def as_dict(self) -> dict[str, str]:
        return {
            "build_system": self.build_system.value,
            "source_dir": str(self.source_dir),
            "marker": self.marker.name,
            "project_name": self.project_name,
        }


_MAKEFILES = ("GNUmakefile", "makefile", "Makefile")


def _project_name(cmakelists: Path) -> str:
    """The `project(<name> ...)` argument, or the directory name.

    A regex would have to cope with comments, multi-line calls and generator expressions;
    a token scan of the first `project(` call is shorter and wrong in fewer ways. Purely
    cosmetic — it names the target in failure reports.
    """
    text = cmakelists.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        lowered = stripped.lower()
        if lowered.startswith("project(") or lowered.startswith("project ("):
            inner = stripped[stripped.index("(") + 1 :]
            token = inner.replace(")", " ").split()
            if token:
                return token[0].strip("\"'")
    return cmakelists.parent.name


def detect(source_dir: Path | str) -> DetectedTarget:
    """Identify how ``source_dir`` builds. Raises when nothing recognised is present."""
    root = Path(source_dir).resolve()
    if not root.is_dir():
        raise AdapterError(f"target source directory does not exist: {root}")

    cmakelists = root / "CMakeLists.txt"
    if cmakelists.is_file():
        return DetectedTarget(
            build_system=BuildSystem.C_CMAKE_CTEST,
            source_dir=root,
            marker=cmakelists,
            project_name=_project_name(cmakelists),
        )

    for name in _MAKEFILES:
        makefile = root / name
        if makefile.is_file():
            return DetectedTarget(
                build_system=BuildSystem.C_MAKE_CTEST,
                source_dir=root,
                marker=makefile,
                project_name=root.name,
            )

    raise AdapterError(
        f"no supported build system in {root}. Looked for CMakeLists.txt and "
        f"{', '.join(_MAKEFILES)}. Supported adapters: "
        f"{', '.join(system.value for system in BuildSystem)}."
    )
