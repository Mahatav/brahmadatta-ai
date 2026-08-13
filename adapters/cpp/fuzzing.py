"""libFuzzer build/run support for CMake C targets.

This is intentionally narrower than `pipeline.py`: it only answers #28 for the
demo `pktcfg` target and similarly-shaped CMake targets that expose a libFuzzer
harness behind a CMake cache option. Reproducer replay remains separate (#83).
"""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packages.sandbox import LimitKind
from packages.sandbox.container import (
    ISOLATION_MODE,
    ContainerJail,
    ContainerJailPolicy,
    ContainerJailResult,
)

from .errors import BuildStep, StepFailure, ToolchainError, first_error_line
from .toolchain import ToolVersion, require_pinned

__all__ = [
    "FUZZ_ARTIFACT_DIR",
    "FUZZ_BUILD_DIR",
    "FuzzFailure",
    "FuzzToolchainRecord",
    "LibFuzzerMetrics",
    "LibFuzzerRunResult",
    "parse_libfuzzer_metrics",
    "run_libfuzzer_campaign",
]

FUZZ_BUILD_DIR = "build-libfuzzer"
FUZZ_ARTIFACT_DIR = "fuzz-artifacts"

_EXEC_RE = re.compile(r"^#(?P<execs>\d+)\b(?P<body>.*)$", re.MULTILINE)
_COV_RE = re.compile(r"\bcov:\s*(?P<cov>\d+)")
_STAT_EXECS_RE = re.compile(r"stat::number_of_executed_units:\s*(?P<execs>\d+)")
_CRASH_RE = re.compile(
    r"\b(?:Test unit written to|artifact_prefix=.*?)(?:\s|')"
    r"(?P<path>\S*?(?:crash|leak|timeout|oom|slow-unit)-[0-9A-Za-z._-]+)"
)
_SANITIZER_RE = re.compile(r"SUMMARY:\s*([A-Za-z]+Sanitizer):")
_CMAKE_VERSION_RE = re.compile(r"cmake version\s+([0-9][0-9A-Za-z.\-+]*)")
_CLANG_VERSION_RE = re.compile(r"(?:Apple clang|clang) version\s+([0-9][0-9A-Za-z.\-+]*)")


@dataclass(frozen=True, slots=True)
class LibFuzzerMetrics:
    """Numbers parsed from libFuzzer output, plus sandbox timing."""

    executions: int = 0
    crashes_found: int = 0
    unique_crashes: int = 0
    coverage: int = 0
    corpus_size: int = 0
    artifact_paths: tuple[str, ...] = ()
    sanitizers: tuple[str, ...] = ("address", "undefined")

    def as_dict(self) -> dict[str, Any]:
        return {
            "executions": self.executions,
            "crashes_found": self.crashes_found,
            "unique_crashes": self.unique_crashes,
            "coverage": self.coverage,
            "corpus_size": self.corpus_size,
            "artifact_paths": list(self.artifact_paths),
            "sanitizers": list(self.sanitizers),
        }


@dataclass(frozen=True, slots=True)
class FuzzToolchainRecord:
    """The pinned container image and the tool versions observed inside it."""

    image: str
    isolation_mode: str
    tools: tuple[ToolVersion, ...]

    @property
    def image_digest(self) -> str:
        return self.image.split("@", 1)[1]

    def as_dict(self) -> dict[str, Any]:
        return {
            "image": self.image,
            "image_digest": self.image_digest,
            "pinned": True,
            "isolation_mode": self.isolation_mode,
            "tools": [tool.as_dict() for tool in self.tools],
        }


@dataclass(frozen=True, slots=True)
class FuzzFailure:
    """A build/toolchain/run failure that still reports exactly what happened."""

    step: str
    command: tuple[str, ...]
    exit_code: int
    first_error: str
    timed_out: bool = False
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "command": list(self.command),
            "exit_code": self.exit_code,
            "first_error": self.first_error,
            "timed_out": self.timed_out,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class LibFuzzerRunResult:
    """Complete result of one headless libFuzzer campaign."""

    harness: str
    engine: str
    runtime_seconds: float
    metrics: LibFuzzerMetrics
    toolchain: FuzzToolchainRecord | None
    configure: ContainerJailResult | None = None
    build: ContainerJailResult | None = None
    run: ContainerJailResult | None = None
    failure: FuzzFailure | None = None
    events: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def completed(self) -> bool:
        return self.failure is None and self.run is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "harness": self.harness,
            "engine": self.engine,
            "runtime_seconds": self.runtime_seconds,
            "metrics": self.metrics.as_dict(),
            "toolchain": self.toolchain.as_dict() if self.toolchain else None,
            "completed": self.completed,
            "failure": self.failure.as_dict() if self.failure else None,
            "events": list(self.events),
        }


def parse_libfuzzer_metrics(
    output: str, *, corpus_size: int, artifact_paths: tuple[str, ...] = ()
) -> LibFuzzerMetrics:
    """Extract the metrics the Command Center needs from libFuzzer output."""
    executions = 0
    coverage = 0
    for match in _EXEC_RE.finditer(output):
        executions = max(executions, int(match.group("execs")))
        cov_match = _COV_RE.search(match.group("body"))
        if cov_match:
            coverage = max(coverage, int(cov_match.group("cov")))

    stat_match = _STAT_EXECS_RE.search(output)
    if stat_match:
        executions = max(executions, int(stat_match.group("execs")))

    discovered = {_normalize_crash_artifact(path) for path in artifact_paths}
    for match in _CRASH_RE.finditer(output):
        discovered.add(_normalize_crash_artifact(match.group("path").rstrip("'\"")))

    sanitizer_names = {
        name.replace("Sanitizer", "").lower() for name in _SANITIZER_RE.findall(output)
    }
    sanitizers = tuple(sorted(sanitizer_names)) or ("address", "undefined")

    return LibFuzzerMetrics(
        executions=executions,
        crashes_found=len(discovered),
        unique_crashes=len(discovered),
        coverage=coverage,
        corpus_size=corpus_size,
        artifact_paths=tuple(sorted(discovered)),
        sanitizers=sanitizers,
    )


def _normalize_crash_artifact(path: str) -> str:
    """Store crash artifacts by workspace-relative path, regardless of fuzzer wording."""
    marker = f"{FUZZ_ARTIFACT_DIR}/"
    if marker in path:
        return marker + path.rsplit(marker, 1)[1]
    return path


def run_libfuzzer_campaign(
    source_dir: Path | str,
    policy: ContainerJailPolicy,
    *,
    harness_target: str = "pktcfg_fuzz",
    harness_binary: str = "pktcfg_fuzz",
    corpus_dir: str = "corpus",
    budget_seconds: int = 1800,
    mission_ref: str = "libfuzzer",
) -> LibFuzzerRunResult:
    """Build and run a libFuzzer harness in a no-network container."""
    started = time.monotonic()
    image = require_pinned(policy.image)
    source = Path(source_dir).resolve()
    if not source.is_dir():
        raise ToolchainError(f"source directory does not exist: {source}")

    with ContainerJail.create(policy, mission_ref=mission_ref) as sandbox:
        target_source = sandbox.root / "source"
        shutil.copytree(
            source,
            target_source,
            ignore=shutil.ignore_patterns(
                "build",
                "build-*",
                FUZZ_BUILD_DIR,
                FUZZ_ARTIFACT_DIR,
                "fuzz-out",
                "crashes",
            ),
        )

        toolchain = _probe_fuzz_toolchain(sandbox, image)
        build_dir = f"/workspace/{FUZZ_BUILD_DIR}"
        src_dir = "/workspace/source"
        artifact_dir = f"/workspace/{FUZZ_ARTIFACT_DIR}"

        configure_argv = [
            "cmake",
            "-S",
            src_dir,
            "-B",
            build_dir,
            "-DCMAKE_BUILD_TYPE=Debug",
            "-DPKTCFG_SANITIZE=ON",
            "-DPKTCFG_FUZZ=ON",
            "-DCMAKE_C_COMPILER=clang",
        ]
        configure = sandbox.run(configure_argv)
        if not configure.ok:
            return _failed_result(
                started,
                harness_binary,
                toolchain,
                configure,
                step=BuildStep.CONFIGURE.value,
            )

        build_argv = ["cmake", "--build", build_dir, "--target", harness_target, "--parallel"]
        build = sandbox.run(build_argv)
        if not build.ok:
            return _failed_result(
                started,
                harness_binary,
                toolchain,
                build,
                step=BuildStep.BUILD.value,
                configure=configure,
            )

        corpus_path = target_source / corpus_dir
        seeds = sorted(corpus_path.glob("*")) if corpus_path.is_dir() else []
        run_argv = [
            f"{build_dir}/{harness_binary}",
            f"-max_total_time={budget_seconds}",
            "-print_final_stats=1",
            f"-artifact_prefix={artifact_dir}/",
            f"{src_dir}/{corpus_dir}",
        ]
        mkdir = sandbox.run(["mkdir", "-p", artifact_dir])
        if not mkdir.ok:
            return _failed_result(
                started,
                harness_binary,
                toolchain,
                mkdir,
                step="FUZZ_ARTIFACT_DIR",
                configure=configure,
                build=build,
            )

        run = sandbox.run(run_argv)
        artifact_paths = tuple(
            f"{FUZZ_ARTIFACT_DIR}/{path.name}"
            for path in sorted((sandbox.root / FUZZ_ARTIFACT_DIR).glob("*"))
            if path.is_file()
        )
        metrics = parse_libfuzzer_metrics(
            run.stdout + "\n" + run.stderr,
            corpus_size=len(seeds),
            artifact_paths=artifact_paths,
        )
        return LibFuzzerRunResult(
            harness=harness_binary,
            engine="libFuzzer",
            runtime_seconds=run.wall_seconds,
            metrics=metrics,
            toolchain=toolchain,
            configure=configure,
            build=build,
            run=run,
            events=tuple(_events_from_metrics(metrics, runtime_seconds=run.wall_seconds)),
        )


def _probe_fuzz_toolchain(sandbox: ContainerJail, image: str) -> FuzzToolchainRecord:
    probed: list[ToolVersion] = []
    for name, version_re in (
        ("cmake", _CMAKE_VERSION_RE),
        ("clang", _CLANG_VERSION_RE),
    ):
        result = sandbox.run([name, "--version"])
        if not result.ok:
            raise StepFailure(
                step=BuildStep.PROBE_TOOLCHAIN,
                target="libFuzzer",
                command=result.argv,
                exit_code=result.exit_code,
                first_error=first_error_line(result.stderr, result.stdout),
                timed_out=result.limit_hit is LimitKind.WALL_CLOCK,
                detail=result.stderr[-2000:] if result.stderr else "",
            )
        match = version_re.search(result.stdout + "\n" + result.stderr)
        if match is None:
            raise ToolchainError(f"could not parse {name} version from container output")
        probed.append(ToolVersion(name=name, version=match.group(1), path=name))
    return FuzzToolchainRecord(image=image, isolation_mode=ISOLATION_MODE, tools=tuple(probed))


def _failed_result(
    started: float,
    harness: str,
    toolchain: FuzzToolchainRecord,
    result: ContainerJailResult,
    *,
    step: str,
    configure: ContainerJailResult | None = None,
    build: ContainerJailResult | None = None,
) -> LibFuzzerRunResult:
    failure = FuzzFailure(
        step=step,
        command=result.argv,
        exit_code=result.exit_code,
        first_error=first_error_line(result.stderr, result.stdout),
        timed_out=result.limit_hit is LimitKind.WALL_CLOCK,
        detail=result.stderr[-2000:] if result.stderr else "",
    )
    configure_result = configure
    if configure_result is None and step == BuildStep.CONFIGURE.value:
        configure_result = result
    build_result = build
    if build_result is None and step == BuildStep.BUILD.value:
        build_result = result
    return LibFuzzerRunResult(
        harness=harness,
        engine="libFuzzer",
        runtime_seconds=time.monotonic() - started,
        metrics=LibFuzzerMetrics(),
        toolchain=toolchain,
        configure=configure_result,
        build=build_result,
        failure=failure,
    )


def _events_from_metrics(
    metrics: LibFuzzerMetrics, *, runtime_seconds: float
) -> list[dict[str, Any]]:
    return [
        {
            "type": "STAGE_PROGRESS",
            "payload": {
                "kind": "fuzzing",
                "report": {
                    "mode": "LIVE_CAMPAIGN",
                    "harness": "pktcfg_fuzz_one_input",
                    "engine": "libFuzzer",
                    "runtime_seconds": runtime_seconds,
                    "executions": metrics.executions,
                    "crashes_found": metrics.crashes_found,
                    "unique_crashes": metrics.unique_crashes,
                    "corpus_size": metrics.corpus_size,
                    "sanitizers": list(metrics.sanitizers),
                },
            },
            "metrics": {
                "executions": float(metrics.executions),
                "coverage": float(metrics.coverage),
                "crashes_found": float(metrics.crashes_found),
                "unique_crashes": float(metrics.unique_crashes),
                "runtime_seconds": runtime_seconds,
            },
        }
    ]
