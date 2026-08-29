"""Toolchain identification and pinning.

Two jobs, and it matters that they are separate:

**Recording** what actually ran. CMake writes the compiler's identity and version into the
build tree as CMake variables — `CMakeFiles/<ver>/CMakeCCompiler.cmake` and
`CMakeCache.txt`. Reading those is structural: they are key/value assignments CMake itself
generated, not a `--version` banner whose wording changes between releases. `cmake` and
`ctest` do have to be asked directly, so those two are parsed from `--version`, whose first
line has been ``cmake version X.Y.Z`` for the entire 3.x/4.x series.

**Pinning.** Recording a version is not pinning it. Real pinning is a container image
digest, which this D3 path does not have — the subprocess jail runs on whatever the host
has. `ToolchainRecord` therefore carries `image_digest: str | None` and
`isolation_mode`, and :func:`require_pinned` refuses a floating tag. The honest reading of
#16's fifth acceptance criterion on the host path is: **not satisfied, and recorded as not
satisfied.** The rule is enforced for the container path the moment #15 lands, and
`test_toolchain.py::test_a_floating_tag_is_rejected` demonstrates the enforcement rather
than asserting the intent.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from packages.sandbox import ISOLATION_MODE, Jail

from .errors import BuildStep, StepFailure, ToolchainError, UnpinnedToolchain, first_error_line

#: `packages/sandbox` is a subprocess jail (#81), not a container — see
#: `packages/sandbox/jail.py`'s module docstring for the full list of what it does and
#: does not protect against. Carried here under our own name so a `ToolchainRecord`
#: doesn't have to import that module just to cite the caveat.
ISOLATION_UNPROTECTED_AGAINST: tuple[str, ...] = (
    "network egress from the target's build and test processes",
    "filesystem reads outside the jail root",
    "a hostile target: no seccomp, no user namespace, no capability drop",
    "memory exhaustion on a kernel that refuses RLIMIT_AS — see JailResult.limits_applied "
    "for whether it took effect on this run, never assumed from the platform name",
    "toolchain reproducibility: the host toolchain is whatever the host has",
)

__all__ = [
    "ISOLATION_UNPROTECTED_AGAINST",
    "ToolVersion",
    "ToolchainRecord",
    "probe_build_tools",
    "read_compiler_identity",
    "require_pinned",
]

_VERSION_BANNER = re.compile(r"^\s*\w[\w\s-]*?version\s+([0-9][0-9A-Za-z.\-+]*)", re.MULTILINE)
_CMAKE_SET = re.compile(r'^\s*set\(\s*(?P<key>[A-Z0-9_]+)\s+"(?P<value>[^"]*)"\s*\)', re.MULTILINE)

#: A digest is `sha256:` plus 64 lowercase hex characters. Anything else — `:latest`,
#: `:main`, a bare name, a semver tag — is mutable and can be repointed at new code
#: without a single change on our side.
_DIGEST = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ToolVersion:
    """One tool, its resolved absolute path, and its version string."""

    name: str
    version: str
    path: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ToolchainRecord:
    """What #16 calls "the run record": compiler version, CMake version, image digest.

    :attr:`image_digest` is ``None`` on the subprocess-jail path and that is not an
    oversight — see the module docstring. :attr:`pinned` is derived, never stored, so the
    claim cannot be set to ``True`` by a caller who would like it to be.
    """

    tools: tuple[ToolVersion, ...]
    compiler_id: str
    compiler_version: str
    compiler_path: str
    generator: str
    isolation_mode: str = ISOLATION_MODE
    image_digest: str | None = None
    isolation_unprotected_against: tuple[str, ...] = field(default=ISOLATION_UNPROTECTED_AGAINST)

    @property
    def pinned(self) -> bool:
        """True only when a container image digest was recorded.

        Version strings are provenance, not pinning: `cmake 4.2.3` on two machines is two
        builds of CMake. Only a digest makes the toolchain the same bytes.
        """
        return self.image_digest is not None and bool(_DIGEST.match(self.image_digest))

    def tool(self, name: str) -> ToolVersion | None:
        return next((entry for entry in self.tools if entry.name == name), None)

    def as_dict(self) -> dict[str, object]:
        return {
            "tools": [entry.as_dict() for entry in self.tools],
            "compiler_id": self.compiler_id,
            "compiler_version": self.compiler_version,
            "compiler_path": self.compiler_path,
            "generator": self.generator,
            "isolation_mode": self.isolation_mode,
            "image_digest": self.image_digest,
            "pinned": self.pinned,
            "isolation_unprotected_against": list(self.isolation_unprotected_against),
        }


def require_pinned(image_reference: str | None) -> str:
    """Return ``image_reference`` if it names a digest; raise otherwise.

    Called by whatever wires the container path in (#15). It exists now, with a test, so
    that "we pin to digests" is a property something checks rather than a sentence in a
    README.
    """
    if not image_reference:
        raise UnpinnedToolchain(
            "no container image was given. The subprocess-jail path is unpinned by "
            "construction; record image_digest=None and say so, do not invent a value."
        )
    if not _DIGEST.match(image_reference):
        raise UnpinnedToolchain(
            f"image reference is not pinned to a digest: {image_reference!r}\n"
            "A tag is mutable and can be repointed at new code with no change on our side. "
            "Use name@sha256:<64 hex>."
        )
    return image_reference


def _banner_version(output: str) -> str | None:
    match = _VERSION_BANNER.search(output)
    return match.group(1) if match else None


def probe_build_tools(
    jail: Jail, names: tuple[str, ...] = ("cmake", "ctest")
) -> tuple[ToolVersion, ...]:
    """Resolve and version each tool, running it inside ``jail``.

    Raises :class:`ToolchainError` when a tool is absent and :class:`StepFailure` when it is
    present but will not report a version — those are different problems for the operator.

    ``jail`` must still be open (inside its ``with`` block) — `packages.sandbox.Jail`
    tears its scratch directory down on `__exit__`, and there is no persistent log path
    to fall back on afterwards (see `pipeline.py`'s module docstring for why callers keep
    the whole configure/build/test sequence inside one `with Jail.create(...)` block).

    #181/SEC-57: resolved via ``jail.which(name)``, not a module-level `shutil.which`
    call — `shutil.which` resolves against the ORCHESTRATOR HOST's `PATH`, which is
    correct for the subprocess `Jail` (same filesystem, same `PATH`) and silently wrong
    for a container-backed jail with its own, differently-built filesystem. `Jail.which`
    and `packages.sandbox.container_runner.ContainerJailRunner.which` each resolve this
    correctly for their own backend — see either docstring.
    """
    probed: list[ToolVersion] = []
    for name in names:
        path = jail.which(name)
        if path is None:
            raise ToolchainError(f"required tool not found on PATH: {name}")
        result = jail.run([path, "--version"])
        if not result.ok:
            raise StepFailure(
                step=BuildStep.PROBE_TOOLCHAIN,
                target=name,
                command=result.argv,
                exit_code=result.exit_code,
                first_error=first_error_line(result.stderr, result.stdout),
                timed_out=result.limit_hit.value == "WALL_CLOCK",
            )
        version = _banner_version(result.stdout) or _banner_version(result.stderr)
        if version is None:
            raise StepFailure(
                step=BuildStep.PROBE_TOOLCHAIN,
                target=name,
                command=result.argv,
                exit_code=result.exit_code,
                first_error=first_error_line(result.stdout, result.stderr),
                detail=f"could not read a version out of {name} --version output",
            )
        probed.append(ToolVersion(name=name, version=version, path=path))
    return tuple(probed)


def read_compiler_identity(build_dir: Path) -> tuple[str, str, str, str]:
    """``(compiler_id, compiler_version, compiler_path, generator)`` from the build tree.

    Reads CMake's own generated files rather than running the compiler again, so the
    recorded identity is the one that compiled the code — not whatever ``cc`` resolves to
    when the report is written.
    """
    candidates = sorted(build_dir.glob("CMakeFiles/*/CMakeCCompiler.cmake"))
    candidates += sorted(build_dir.glob("CMakeFiles/*/CMakeCXXCompiler.cmake"))
    if not candidates:
        raise ToolchainError(
            f"no CMakeCCompiler.cmake under {build_dir}/CMakeFiles — the configure step did "
            "not complete, so there is no compiler identity to record"
        )
    values: dict[str, str] = {}
    for candidate in candidates:
        for match in _CMAKE_SET.finditer(candidate.read_text(encoding="utf-8", errors="replace")):
            values.setdefault(match.group("key"), match.group("value"))

    def pick(*keys: str) -> str:
        for key in keys:
            value = values.get(key)
            if value:
                return value
        return "unknown"

    compiler_id = pick("CMAKE_C_COMPILER_ID", "CMAKE_CXX_COMPILER_ID")
    compiler_version = pick("CMAKE_C_COMPILER_VERSION", "CMAKE_CXX_COMPILER_VERSION")
    compiler_path = pick("CMAKE_C_COMPILER", "CMAKE_CXX_COMPILER")

    generator = "unknown"
    cache = build_dir / "CMakeCache.txt"
    if cache.is_file():
        for line in cache.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("CMAKE_GENERATOR:"):
                generator = line.split("=", 1)[1].strip() if "=" in line else "unknown"
                break

    if compiler_id == "unknown" or compiler_version == "unknown":
        raise ToolchainError(
            f"CMake did not record a compiler id/version in {build_dir}. "
            "Refusing to write a run record with an unknown compiler."
        )
    return compiler_id, compiler_version, compiler_path, generator
