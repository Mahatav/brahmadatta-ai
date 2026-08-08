"""Configure → build → ctest, for one variant. The one entry point everything else calls.

`run_variant` is #16's whole job in one function: detect the build system, probe and
record the toolchain, configure, build, and run CTest, all through the jail, all raising
:class:`StepFailure` with the target/step/command/exit-code/first-error-line #16 asks for
on any step that could not complete — never on a red test suite, which is a valid, fully
reported result, not a pipeline failure.

`run_reproducer` is separate on purpose. `demo/repositories/pktcfg`'s baseline is
documented as green *under sanitizers too* — no CTest case trips the seeded defect on its
own (`README.md`: *"none of the eight tests trips the seeded defect on its own"*). The
sanitizer confirmation #27 asks for comes from replaying the committed reproducer
(`crash/crash-literal-tab.bin`) through the sanitized binary directly, which is a distinct
step from CTest and is never wired into it — doing so would violate #41's standing
prohibition against adding a test to the target that fails on the unpatched build.

Callers MUST keep the `Jail` open (inside its `with Jail.create(...) as jail:` block) for
the full `run_variant`/`run_reproducer` sequence
--------------------------------------------------------------------------------------

`packages.sandbox.Jail` deletes its whole scratch directory — including `build_dir` and
everything CTest wrote into it — the moment its `with` block exits (D-053/D-054). There is
no persistent log path or build tree to come back to afterwards, unlike this package's own
retired `jail.py`, which kept a caller-owned workspace alive across calls. Concretely:

    with Jail.create(policy) as jail:
        result = run_variant(source, jail, Variant.ASAN_UBSAN)      # ok: jail is open
        repro = run_reproducer(jail, result.build_dir / "x", (...), spec=spec)  # still open
    # jail.root and everything under it, including result.build_dir, no longer exist here.
    # Only already-extracted data survives: result.ctest, result.toolchain, repro.findings.

This also means there is no durable on-disk log artifact for a `StepFailure` to point at —
`captured_stdout`/`captured_stderr` on the failure/result types carry whatever
`JailResult` captured (subject to its own output cap), and it is the caller's job (e.g.
`workers/baseline/run.py`) to persist that text into its own evidence store *before* the
`with` block closes, if it wants to keep it past this call. This package does not own
evidence persistence — see `docs/09-company/06-architecture-spec.md` §5, the
evidence-builder service's territory.

There is also no per-step timeout anymore. `packages.sandbox.JailPolicy.wall_clock_seconds`
is set once, for the whole `Jail`, and applies to every command run inside it — configure,
build, and ctest share one budget rather than each getting their own. Size the policy for
the whole sequence (the D3 gate's own 15-minute ceiling is exactly that shape already).
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from packages.sandbox import Jail, JailResult, LimitKind

from .ctest_report import CTestSummary, run_ctest
from .detect import BuildSystem, DetectedTarget, detect
from .errors import BuildStep, StepFailure, ToolchainError, first_error_line
from .sanitizer import SanitizerFinding, parse_sanitizer_output
from .toolchain import ToolchainRecord, probe_build_tools, read_compiler_identity
from .variants import Variant, VariantSpec, spec_for

__all__ = ["BuildResult", "ReproducerResult", "run_reproducer", "run_variant"]


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Everything #16 and #17 need out of one configure/build/ctest pass.

    :attr:`build_dir` is only valid while the `Jail` that produced it is still open — see
    the module docstring. Extract what you need (:attr:`ctest`, :attr:`toolchain`) before
    the `with` block closes.
    """

    variant: Variant
    detected: DetectedTarget
    toolchain: ToolchainRecord
    build_dir: Path
    configure: JailResult
    build: JailResult
    ctest: CTestSummary
    duration_seconds: float

    @property
    def configure_ok(self) -> bool:
        return self.configure.ok

    @property
    def build_ok(self) -> bool:
        return self.build.ok

    def as_dict(self) -> dict[str, object]:
        return {
            "variant": self.variant.value,
            "detected": self.detected.as_dict(),
            "toolchain": self.toolchain.as_dict(),
            "build_dir": str(self.build_dir),
            "configure_ok": self.configure_ok,
            "build_ok": self.build_ok,
            "ctest": self.ctest.as_dict(),
            "duration_seconds": self.duration_seconds,
        }


@dataclass(frozen=True, slots=True)
class ReproducerResult:
    """The result of replaying a fixed input through a built (usually sanitized) binary."""

    argv: tuple[str, ...]
    exit_code: int
    duration_seconds: float
    findings: tuple[SanitizerFinding, ...]
    timed_out: bool
    captured_stdout: str
    captured_stderr: str

    @property
    def crashed(self) -> bool:
        return bool(self.findings) or (self.exit_code != 0 and not self.timed_out)

    def as_dict(self) -> dict[str, object]:
        return {
            "argv": list(self.argv),
            "exit_code": self.exit_code,
            "duration_seconds": self.duration_seconds,
            "findings": [f.as_dict() for f in self.findings],
            "timed_out": self.timed_out,
        }


def _configure_argv(
    cmake_path: str, detected: DetectedTarget, build_dir: Path, spec: VariantSpec
) -> list[str]:
    argv = [
        cmake_path,
        "-S",
        str(detected.source_dir),
        "-B",
        str(build_dir),
        f"-DCMAKE_BUILD_TYPE={spec.build_type}",
    ]
    for key, value in spec.cache_entries.items():
        argv.append(f"-D{key}={value}")
    if spec.sanitizer_flags:
        flags = " ".join(spec.sanitizer_flags)
        # Applied through the generic cache variables rather than a project-specific
        # switch, so a variant works on any CMake target, including one with no
        # `PKTCFG_SANITIZE`-style option of its own. This produces the identical flag set
        # pktcfg's own `-DPKTCFG_SANITIZE=ON` would (same `-fsanitize=...` string), so the
        # two are equivalent for this target and the generic path stays the only path.
        argv.append(f"-DCMAKE_C_FLAGS={flags}")
        argv.append(f"-DCMAKE_EXE_LINKER_FLAGS={flags}")
    return argv


def run_variant(
    source_dir: Path | str, jail: Jail, variant: Variant = Variant.BASELINE
) -> BuildResult:
    """Configure, build, and CTest ``source_dir`` under ``variant``, entirely inside ``jail``.

    ``jail`` must be an already-open `packages.sandbox.Jail` (inside its `with` block) and
    must stay open until you are done reading `BuildResult.build_dir` — see the module
    docstring. Its `JailPolicy.wall_clock_seconds` covers the whole configure+build+ctest
    sequence, not each step individually.

    Raises :class:`StepFailure` (never returns a partial result) when configure or build
    does not succeed, or when CTest itself could not produce a trustworthy report. A red
    but complete CTest run is returned normally — see the module docstring.
    """
    started = time.monotonic()
    detected = detect(source_dir)

    cmake_path = shutil.which("cmake")
    ctest_path = shutil.which("ctest")
    if cmake_path is None or ctest_path is None:
        raise ToolchainError(
            f"required tool missing on PATH: cmake={cmake_path!r} ctest={ctest_path!r}"
        )
    if detected.build_system is not BuildSystem.C_CMAKE_CTEST:
        # Make-only targets are the documented fallback: hardcode the recipe rather than
        # generalise past what #16 needs today. See docs/09-company/01-vision-and-p0-cut.md
        # line 170 and demo/repositories/pktcfg, which is CMake.
        raise ToolchainError(
            f"build system {detected.build_system.value} is not yet driven by this "
            "adapter; only C_CMAKE_CTEST is implemented. See the module docstring."
        )

    tools = probe_build_tools(jail)
    spec = spec_for(variant)
    build_dir = jail.root / f"build-{variant.value.lower()}"
    build_dir.mkdir(parents=True, exist_ok=True)

    configure_argv = _configure_argv(cmake_path, detected, build_dir, spec)
    configure_result = jail.run(configure_argv, cwd=jail.root)
    if not configure_result.ok:
        raise StepFailure(
            step=BuildStep.CONFIGURE,
            target=detected.project_name,
            command=configure_result.argv,
            exit_code=configure_result.exit_code,
            first_error=first_error_line(configure_result.stderr, configure_result.stdout),
            timed_out=configure_result.limit_hit is LimitKind.WALL_CLOCK,
            detail=configure_result.stderr[-2000:] if configure_result.stderr else "",
        )

    build_argv = [cmake_path, "--build", str(build_dir), "--parallel"]
    build_result = jail.run(build_argv, cwd=jail.root)
    if not build_result.ok:
        raise StepFailure(
            step=BuildStep.BUILD,
            target=detected.project_name,
            command=build_result.argv,
            exit_code=build_result.exit_code,
            first_error=first_error_line(build_result.stderr, build_result.stdout),
            timed_out=build_result.limit_hit is LimitKind.WALL_CLOCK,
            detail=build_result.stderr[-2000:] if build_result.stderr else "",
        )

    compiler_id, compiler_version, compiler_path, generator = read_compiler_identity(build_dir)
    toolchain_record = ToolchainRecord(
        tools=tools,
        compiler_id=compiler_id,
        compiler_version=compiler_version,
        compiler_path=compiler_path,
        generator=generator,
    )

    ctest_summary = run_ctest(build_dir, jail, ctest_path)

    return BuildResult(
        variant=variant,
        detected=detected,
        toolchain=toolchain_record,
        build_dir=build_dir,
        configure=configure_result,
        build=build_result,
        ctest=ctest_summary,
        duration_seconds=time.monotonic() - started,
    )


def run_reproducer(
    jail: Jail,
    binary_path: Path | str,
    args: tuple[str, ...],
    *,
    spec: VariantSpec,
) -> ReproducerResult:
    """Replay a fixed input through a built binary and structurally parse any sanitizer
    finding out of its combined output.

    ``jail`` must still be open — ``binary_path`` almost always points inside a
    `BuildResult.build_dir` from a `run_variant` call made against this same jail.

    Sanitizer runtime options (`spec.runtime_env` — `ASAN_OPTIONS`/`UBSAN_OPTIONS`) are
    supplied here because the jail scrubs the environment down to an allowlist
    (`packages/sandbox/policy.py`'s `DEFAULT_ENV_ALLOWLIST`): if the variant does not
    carry them, nothing does, and a caller cannot accidentally inherit whatever the host
    shell happens to export.
    """
    resolved_binary = jail.resolve(binary_path)
    argv = (str(resolved_binary), *args)
    result = jail.run(list(argv), cwd=jail.root, extra_env=dict(spec.runtime_env))
    findings = parse_sanitizer_output(result.stdout + "\n" + result.stderr)
    return ReproducerResult(
        argv=argv,
        exit_code=result.exit_code,
        duration_seconds=result.wall_seconds,
        findings=findings,
        timed_out=result.limit_hit is LimitKind.WALL_CLOCK,
        captured_stdout=result.stdout,
        captured_stderr=result.stderr,
    )
