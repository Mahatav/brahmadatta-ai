"""libFuzzer build/run support for CMake C targets.

This is intentionally narrower than `pipeline.py`: it only answers #28 for the
demo `pktcfg` target and similarly-shaped CMake targets that expose a libFuzzer
harness behind a CMake cache option. Reproducer replay remains separate (#83).

Generalizing beyond pktcfg (#288/#289/#291)
--------------------------------------------
Three related gaps, found by running this module's real entry points against four
non-pktcfg targets (LAVA-M base64, Magma libpng, stb_image), fixed together here:

* **#288** — `configure_argv` used to hardcode the literal CMake cache-option names
  `-DPKTCFG_SANITIZE=ON -DPKTCFG_FUZZ=ON`, so a target with its own naturally-named
  options (`STB_SANITIZE`/`STB_FUZZ`, say) silently failed to build its fuzz target at
  all — CMake no-ops an unrecognized `-D` cache variable rather than erroring.
  `run_libfuzzer_campaign` now takes a `cache_entries` mapping, exactly the shape
  `adapters/cpp/variants.py::VariantSpec.cache_entries` already uses for BASELINE/
  ASAN_UBSAN, defaulting to `DEFAULT_CACHE_ENTRIES` (pktcfg's own two options) so pktcfg
  itself is completely unaffected. `harness_target`/`harness_binary` were already
  parameters before this fix; what was missing was a way to override the *cache entries*
  that make the target buildable in the first place.
* **#289** — no way to pass sanitizer runtime environment (`ASAN_OPTIONS`, e.g.
  `detect_leaks=0`) into the live campaign, unlike `pipeline.py::run_reproducer`, which
  already applies `VariantSpec.runtime_env` for exactly this reason. `sanitizer_env` is
  the equivalent knob here — opt-in (`None` by default, preserving pktcfg's prior
  behaviour exactly: no extra env, same as before this parameter existed).
* **#291** — `parse_libfuzzer_metrics` used to fold `slow-unit-*`/`timeout-*`/`oom-*`
  artifacts into the same `crashes_found`/`unique_crashes` bucket as real `crash-*`/
  `leak-*` sanitizer reports, and defaulted `sanitizers` to `("address", "undefined")`
  whenever sanitizer text appeared *anywhere* in the session output, not tied to
  whichever artifact actually stopped the run. Both are fixed by classifying each
  discovered artifact by its libFuzzer-assigned kind (`_artifact_kind`) and only
  crediting `crashes_found`/`unique_crashes`/`sanitizers` from the kinds
  (`crash`, `leak`) that are actually sanitizer-relevant, gated on the *stopping*
  artifact's own output carrying a `SUMMARY: ...Sanitizer:` line (`_stopping_artifact`).
  A `slow-unit`/`timeout`/`oom` artifact remains visible on `artifact_paths` (it is
  still real evidence of a hang/resource-limit finding) but never counts as a crash and
  never sets `sanitizers`.
"""

from __future__ import annotations

import dataclasses
import os
import re
import shutil
import time
from collections.abc import Mapping
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
    "DEFAULT_CACHE_ENTRIES",
    "FUZZ_ARTIFACT_DIR",
    "FUZZ_BUILD_DIR",
    "MAX_DURABLE_ARTIFACT_BYTES",
    "ZERO_EXECUTION_INFRA_FAILURE_STEP",
    "DurableArtifact",
    "FuzzFailure",
    "FuzzToolchainRecord",
    "LibFuzzerMetrics",
    "LibFuzzerRunResult",
    "parse_libfuzzer_metrics",
    "run_libfuzzer_campaign",
]

FUZZ_BUILD_DIR = "build-libfuzzer"
FUZZ_ARTIFACT_DIR = "fuzz-artifacts"

#: `FuzzFailure.step` value for #302 finding 2's distinct "the harness process itself
#: never meaningfully ran" outcome -- see `run_libfuzzer_campaign`'s own inline comment
#: for the exact three-part signal this is gated on. Exported so a caller (e.g.
#: `workers/fuzzing/dispatch.py`) can branch on it by name rather than a literal string.
ZERO_EXECUTION_INFRA_FAILURE_STEP = "FUZZ_ZERO_EXECUTION_INFRA_FAILURE"
_STEP_ZERO_EXECUTION_INFRA_FAILURE = ZERO_EXECUTION_INFRA_FAILURE_STEP

#: Conservative ceiling for one crash artifact copied out of a `ContainerJail`
#: worktree before it tears down (D-106; see `_copy_crash_artifacts_durably`'s own
#: docstring for the full security reasoning). This module has no Django dependency
#: (D-026 boundary — it does not import `config.settings`), so this is a plain
#: constant, not a settings-derived value; `workers.fuzzing.dispatch` applies its own,
#: Django-configurable ceiling (`FUZZ_REPRODUCER_ARTIFACT_MAX_BYTES`) a second time
#: when it ingests these bytes into the content-addressed store, mirroring the
#: belt-and-suspenders pattern `orchestrator/evidence_export.py` already uses for the
#: evidence bundle tarball (size checked once before `store.ingest_from_path`, and
#: `ingest_from_path` enforces its own ceiling independently). libFuzzer crash inputs
#: for this project's demo-sized targets are single-digit kilobytes; 64 MiB is
#: generous headroom, not a realistic expectation.
MAX_DURABLE_ARTIFACT_BYTES = 64 * 1024 * 1024

_COPY_CHUNK_SIZE = 1024 * 1024

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

#: Matches the libFuzzer-assigned artifact kind out of a discovered artifact's own
#: (already workspace-relative) path — `crash-*`/`leak-*` are real sanitizer-relevant
#: findings, `timeout-*`/`oom-*`/`slow-unit-*` are resource-limit artifacts (a hang or an
#: allocation blowup, not necessarily a memory-safety defect). See `_artifact_kind` and
#: the module docstring's "#291" section.
_ARTIFACT_KIND_RE = re.compile(r"(?:^|/)(crash|leak|timeout|oom|slow-unit)-")

#: Artifact kinds whose discovery is actually evidence of a sanitizer-relevant finding.
#: `timeout`/`oom`/`slow-unit` are real findings too (CWE-400-shaped, typically) but are
#: never memory-safety crashes on their own — #291's whole point.
_SANITIZER_RELEVANT_KINDS = frozenset({"crash", "leak"})

#: pktcfg's own CMake cache-entry names for turning on ASan/UBSan and building the
#: libFuzzer harness target (`demo/repositories/pktcfg/CMakeLists.txt`'s `PKTCFG_SANITIZE`/
#: `PKTCFG_FUZZ` options). This is the *default* value of `run_libfuzzer_campaign`'s
#: `cache_entries` parameter — never a literal baked into the configure argv (#288) — so
#: pktcfg keeps working identically while a target with its own naturally-named options
#: (or none at all, driven entirely through generic `-DCMAKE_C_FLAGS=`/
#: `-DCMAKE_EXE_LINKER_FLAGS=`, the way `adapters/cpp/pipeline.py::_configure_argv`
#: already does for `VariantSpec.sanitizer_flags`) can pass its own mapping instead. Order
#: matters only in that it reproduces pktcfg's own historical argv order exactly (dict
#: insertion order, Python 3.7+).
DEFAULT_CACHE_ENTRIES: Mapping[str, str] = {"PKTCFG_SANITIZE": "ON", "PKTCFG_FUZZ": "ON"}


def _artifact_kind(path: str) -> str | None:
    """The libFuzzer-assigned kind (`crash`/`leak`/`timeout`/`oom`/`slow-unit`) encoded in
    a discovered artifact's file name, or `None` if it does not match any of them (never
    silently treated as sanitizer-relevant when unrecognised)."""
    match = _ARTIFACT_KIND_RE.search(path)
    return match.group(1) if match else None


def _stopping_artifact(discovered: set[str], output: str) -> str | None:
    """Which discovered artifact actually stopped this campaign, for #291's "only the
    stopping artifact's own output can confirm a sanitizer finding" rule.

    In the common case there is at most one: a single `ContainerJail` run executes the
    harness once and libFuzzer itself stops at the first crash/leak/timeout/OOM it hits,
    so `discovered` has 0 or 1 entries. When there is more than one (a test double
    supplying a pre-populated `artifact_paths`, or a merge-mode session this module does
    not otherwise support), the artifact whose "Test unit written to ..."-style line
    appears *last* in the captured output is the one that actually ended the run — session
    output is append-only and libFuzzer writes that line immediately before exiting.
    Falls back to the lexicographically last path when the output carries no such line at
    all (nothing to order by), which is deterministic rather than arbitrary."""
    if not discovered:
        return None
    if len(discovered) == 1:
        return next(iter(discovered))
    write_order = [
        _normalize_crash_artifact(match.group("path").rstrip("'\""))
        for match in _CRASH_RE.finditer(output)
    ]
    for path in reversed(write_order):
        if path in discovered:
            return path
    return max(discovered)


@dataclass(frozen=True, slots=True)
class LibFuzzerMetrics:
    """Numbers parsed from libFuzzer output, plus sandbox timing."""

    executions: int = 0
    crashes_found: int = 0
    unique_crashes: int = 0
    coverage: int = 0
    corpus_size: int = 0
    artifact_paths: tuple[str, ...] = ()
    #: Populated only when a `crash`/`leak`-kind artifact actually stopped the run AND
    #: that stopping artifact's own captured output carries a `SUMMARY: ...Sanitizer:`
    #: line (#291) — empty otherwise, including for a clean run, a build/configure
    #: failure (`LibFuzzerMetrics()`'s own bare default), and a `timeout`/`oom`/
    #: `slow-unit` stop. Never defaults to "address"/"undefined" as a guess.
    sanitizers: tuple[str, ...] = ()

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
class DurableArtifact:
    """One crash artifact whose bytes survived `ContainerJail.close()` (D-106).

    `relative_path` is the same workspace-relative string `LibFuzzerMetrics.
    artifact_paths` already carries (`fuzz-artifacts/<name>`) — kept alongside the
    durable copy so a caller can still match a durable artifact back to the metrics
    entry it came from. `host_path` is the durable, non-jail location
    (`workers.fuzzing.dispatch` reads bytes from here to ingest into the
    content-addressed store); it is never included in `FuzzingOutcome.as_dict()` or
    any mission event payload — same "no raw filesystem path leaves this boundary"
    discipline `orchestrator/evidence_repository.py` documents for every other
    artifact kind (callers receive hash-addressed pointers, never a path, once this
    reaches persistence)."""

    relative_path: str
    host_path: str
    size_bytes: int


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
    durable_artifacts: tuple[DurableArtifact, ...] = field(default_factory=tuple)

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

    # #291: only `crash`/`leak`-kind artifacts count as a crash. `timeout`/`oom`/
    # `slow-unit` (and anything unrecognised) remain visible on `artifact_paths` — they
    # are real evidence — but are never folded into `crashes_found`/`unique_crashes`.
    sanitizer_relevant = {
        path for path in discovered if _artifact_kind(path) in _SANITIZER_RELEVANT_KINDS
    }

    # #291: `sanitizers` is only ever populated when the artifact that actually stopped
    # the run is itself `crash`/`leak`-kind AND that run's own captured output contains a
    # `SUMMARY: ...Sanitizer:` line — never "any sanitizer text anywhere in the session".
    stopping = _stopping_artifact(discovered, output)
    stopping_is_sanitizer_relevant = (
        stopping is not None and _artifact_kind(stopping) in _SANITIZER_RELEVANT_KINDS
    )
    sanitizer_names = tuple(
        sorted({name.replace("Sanitizer", "").lower() for name in _SANITIZER_RE.findall(output)})
    )
    sanitizers = sanitizer_names if stopping_is_sanitizer_relevant else ()

    return LibFuzzerMetrics(
        executions=executions,
        crashes_found=len(sanitizer_relevant),
        unique_crashes=len(sanitizer_relevant),
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
    cache_entries: Mapping[str, str] | None = None,
    corpus_dir: str = "corpus",
    budget_seconds: int = 1800,
    mission_ref: str = "libfuzzer",
    workspace_root: Path | str | None = None,
    sanitizer_env: Mapping[str, str] | None = None,
) -> LibFuzzerRunResult:
    """Build and run a libFuzzer harness in a no-network container.

    `cache_entries` (#288) is the same shape `adapters/cpp/variants.py::VariantSpec.
    cache_entries` uses for BASELINE/ASAN_UBSAN: `-D<key>=<value>` CMake cache entries
    applied at configure time. `None` (the default) uses `DEFAULT_CACHE_ENTRIES` —
    pktcfg's own `PKTCFG_SANITIZE`/`PKTCFG_FUZZ` options — so this call is completely
    unchanged for pktcfg. A target with its own naturally-named options (or none at all)
    passes its own mapping instead of being forced to literally reuse pktcfg's names,
    which is the #288 bug: CMake silently no-ops an unrecognised `-D` cache variable
    rather than erroring, so a mismatched name looks like success until the build step
    fails with "No rule to make target".

    `sanitizer_env` (#289) is sanitizer runtime environment (`ASAN_OPTIONS`, e.g.
    `"detect_leaks=0"`, mirroring `pipeline.py::run_reproducer`'s own `VariantSpec.
    runtime_env` precedent) merged into the container's environment for every command run
    in this campaign's sandbox, including the fuzz binary itself. `None` (the default)
    adds nothing — pktcfg's behaviour is unchanged; without this, the very first
    LeakSanitizer report a real target's harness produces is indistinguishable from a
    genuine memory-safety crash (see the module docstring's "#289" note and this
    parameter is what lets a caller suppress that class of false positive deliberately,
    the same way `adapters/cpp/variants.py`'s `_ASAN_OPTIONS` does for the sanitized
    baseline/reproducer path).

    `workspace_root` (D-106; mirrors `workers/baseline/run.py::run_baseline_stage`'s
    existing `workspace_root` parameter) is host-side scratch space that is NOT
    inside `sandbox`'s worktree and does not get deleted when `ContainerJail.close()`
    runs `shutil.rmtree` on `sandbox.root` at the bottom of this `with` block. When
    provided and the campaign discovers at least one crash artifact, each artifact's
    bytes are copied there — safely, see `_copy_crash_artifacts_durably` — before the
    jail tears down, and the durable copies are returned on
    `LibFuzzerRunResult.durable_artifacts`. `None` (the default) preserves this
    function's prior behaviour exactly: no copy attempted, `durable_artifacts` stays
    empty, matching every caller that predates D-106 (`workers/fuzzing/cli.py`, this
    module's own tests)."""
    started = time.monotonic()
    image = require_pinned(policy.image)
    source = Path(source_dir).resolve()
    if not source.is_dir():
        raise ToolchainError(f"source directory does not exist: {source}")

    resolved_cache_entries = DEFAULT_CACHE_ENTRIES if cache_entries is None else cache_entries
    if sanitizer_env:
        # `ContainerJailPolicy.extra_env` (frozen) is fixed at `ContainerJail.create()`
        # time and applies to every command this sandbox runs, not a per-`run()` env —
        # `dataclasses.replace` is the only way to layer #289's caller-supplied sanitizer
        # options on top of whatever the caller's own `policy.extra_env` already carries,
        # without mutating the caller's policy object.
        policy = dataclasses.replace(policy, extra_env={**policy.extra_env, **sanitizer_env})

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
            *(f"-D{key}={value}" for key, value in resolved_cache_entries.items()),
            "-DCMAKE_C_COMPILER=clang",
            # #300: without an explicit CXX compiler pin, CMake's own auto-detection
            # happens to land on a compatible C++ compiler ONLY because this image ships
            # exactly one (see fuzz-toolchain.Dockerfile) — fragile by coincidence, not by
            # design. Pinned explicitly, matching CMAKE_C_COMPILER, so a future image with
            # more than one C++ toolchain (or a differently named one) cannot silently
            # drift the fuzz harness onto a compiler that was never actually verified to
            # carry libFuzzer/ASan/UBSan support.
            "-DCMAKE_CXX_COMPILER=clang++",
            # #302 finding 1: force every target's runtime output into the flat
            # `build_dir` CMake was told to configure into, regardless of which
            # subdirectory of `src_dir` actually declares it. Without this,
            # `run_argv`'s `f"{build_dir}/{harness_binary}"` below only resolves for a
            # target declared in the project's top-level CMakeLists.txt (true for
            # pktcfg's own `pktcfg_fuzz`) — a completely normal layout with the fuzz
            # harness declared in a subdirectory (e.g. `fuzz/CMakeLists.txt`) builds
            # successfully but then fails at run time with `exec: .../<binary>: not
            # found`, because CMake's own per-target default `RUNTIME_OUTPUT_DIRECTORY`
            # mirrors the *source* subdirectory structure under `build_dir`, not the flat
            # build root. `CMAKE_RUNTIME_OUTPUT_DIRECTORY` is the documented CMake
            # variable that seeds every target's own `RUNTIME_OUTPUT_DIRECTORY` property
            # at the point the target is created (CMake reference docs, `RUNTIME_OUTPUT_
            # DIRECTORY` property page) — a no-op for pktcfg (whose `pktcfg_fuzz` target
            # is already declared at the top level and lands here regardless), and the
            # fix for the subdirectory case. The one case this does NOT cover: a target
            # whose own CMakeLists.txt calls `set_target_properties(... RUNTIME_OUTPUT_
            # DIRECTORY ...)` on itself, which wins over this global default by CMake's
            # own documented precedence — that is a deliberate choice by the target's own
            # build, not something a caller-side flag can or should override.
            f"-DCMAKE_RUNTIME_OUTPUT_DIRECTORY={build_dir}",
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

        # #302 finding 2: a genuine 0-execution infra failure (the binary was not found
        # at the resolved path, the corpus directory was unreadable, the container's
        # entrypoint could not exec at all, ...) must not read identically to "the
        # fuzzer genuinely ran under budget and found nothing." Both used to produce
        # `failure: None, crashes_found: 0, executions: 0` — indistinguishable.
        #
        # The signal used here is deliberately narrow so it cannot regress real-crash
        # detection (which this module's own #291 fix depends on `run`'s exit code
        # being allowed to be nonzero — see this function's own long-standing rule:
        # "a real crash makes libFuzzer exit nonzero... treating any nonzero exit as
        # failure would misclassify every real crash as an infra failure instead"):
        #
        #   * `metrics.executions == 0` -- libFuzzer's own progress/stats output never
        #     recorded a single executed unit.
        #   * `not artifact_paths` -- no crash/leak/timeout/oom/slow-unit artifact of
        #     ANY kind was discovered either, so this is not the "crashed before the
        #     first stats line" edge case a genuine early crash can produce.
        #   * `not run.ok` -- the run itself did not exit cleanly (nonzero exit code,
        #     or the container's own wall-clock/other limit). A real clean campaign
        #     that legitimately found nothing within its budget exits 0.
        #
        # All three together is the "the harness process itself never meaningfully
        # ran" signature; any one alone is not enough (e.g. a real target can
        # legitimately execute 0 units and still exit 0 on an absurdly small budget --
        # that is reported as an ordinary, if unusual, clean result, not this failure).
        if metrics.executions == 0 and not artifact_paths and not run.ok:
            return _failed_result(
                started,
                harness_binary,
                toolchain,
                run,
                step=_STEP_ZERO_EXECUTION_INFRA_FAILURE,
                configure=configure,
                build=build,
            )

        durable_artifacts: tuple[DurableArtifact, ...] = ()
        if workspace_root is not None and artifact_paths:
            # Copied here, still inside the `with ContainerJail.create(...)` block —
            # `sandbox.root` (and everything under it, including the artifact bytes
            # `artifact_paths` names) is `shutil.rmtree`'d by `ContainerJail.close()`
            # the moment this block exits (D-106's own gap statement). Never raises:
            # a hostile or corrupted artifact is skipped, not allowed to fail an
            # otherwise-real crash-discovery result — see the helper's own docstring.
            durable_artifacts = _copy_crash_artifacts_durably(
                sandbox,
                artifact_paths,
                Path(workspace_root),
                mission_ref,
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
            events=tuple(
                _events_from_metrics(
                    metrics, runtime_seconds=run.wall_seconds, harness=harness_binary
                )
            ),
            durable_artifacts=durable_artifacts,
        )


def _copy_crash_artifacts_durably(
    sandbox: ContainerJail,
    artifact_paths: tuple[str, ...],
    workspace_root: Path,
    mission_ref: str,
    *,
    max_bytes: int = MAX_DURABLE_ARTIFACT_BYTES,
) -> tuple[DurableArtifact, ...]:
    """Copy each discovered crash artifact's bytes out of `sandbox.root` into
    `workspace_root`, before `ContainerJail.close()` deletes the former (D-106).

    `sandbox.root` is a host directory bind-mounted read-write into the container
    (`_docker_run_args`'s one `-v` mount, `packages/sandbox/container.py`); the
    fuzzed target runs as a fixed non-root uid under `--cap-drop ALL`/
    `--security-opt no-new-privileges` but is still, by this module's own security
    model, untrusted code (`ContainerJailPolicy`'s own docstring: this is the sandbox
    #28's fuzzing worker runs *untrusted* target code inside) — so a crash artifact
    discovered under it is untrusted input, not a trusted log the way `run_baseline_
    stage`'s JUnit report is. Two safeguards this function applies that a plain
    `shutil.copy` would not, both exercised directly by
    `adapters/cpp/tests/test_fuzzing.py` against a hostile fixture, not just asserted
    here:

    * **No symlink is ever followed.** Opened with `os.O_NOFOLLOW` — if the fuzzed
      process replaced a crash-artifact path with a symlink (to `/etc/passwd`, to a
      path outside `sandbox.root` the orchestrator's own host uid can read, or
      anywhere else), the `open()` call raises `OSError` (`ELOOP`) instead of
      dereferencing it, and this function skips that entry rather than copying
      whatever the symlink points at. `Path.resolve()` is also checked against
      `sandbox.root` first, as a second, independent check against the same class of
      escape (a `..`-shaped relative target, or a resolved path that leaves the
      sandbox root some other way) — belt and suspenders, not either/or.
    * **A hard per-file byte ceiling, enforced while reading, not after.** Mirrors
      `authorization.store.ingest_from_path`'s own "the read stops the instant the
      ceiling is crossed" discipline (that module's docstring) — an oversized or
      corrupted artifact is never fully buffered in memory or written to disk before
      the ceiling is discovered; the partial file that was written is removed.

    A rejected or vanished artifact (symlink, oversized, removed between discovery
    and copy) is skipped, not raised past this function — a hostile or corrupted
    crash artifact must not take down an otherwise-real fuzzing outcome, the same
    "a red result is a valid result, not an exception" discipline
    `workers/baseline/run.py`'s module docstring states for a failed build. A caller
    that needs to know whether every discovered artifact actually survived compares
    `len(artifact_paths)` against `len(durable_artifacts)`; `workers/fuzzing/
    dispatch.py` does exactly that before attaching a `Reproducer` row to a `Finding`
    (see that module's own docstring on why a mismatch means no reproducer is
    recorded at all, not a guessed one).
    """
    try:
        sandbox_root = sandbox.root.resolve(strict=True)
    except OSError:
        return ()

    destination_dir = workspace_root / f"{mission_ref}-fuzz-artifacts"
    copied: list[DurableArtifact] = []
    for relative in artifact_paths:
        name = Path(relative).name
        if not name or name in (".", ".."):
            continue
        source = sandbox.root / relative

        try:
            resolved = source.resolve(strict=True)
            resolved.relative_to(sandbox_root)
        except (OSError, ValueError):
            # Vanished since discovery, or would resolve outside the sandbox root
            # (a symlink target, most likely) — refused regardless of cause.
            continue

        fd = -1
        destination = destination_dir / name
        try:
            fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError:
            # A symlink (ELOOP) or otherwise unreadable — never followed, never
            # copied.
            continue

        written = 0
        ok = True
        try:
            destination_dir.mkdir(parents=True, exist_ok=True)
            with os.fdopen(fd, "rb") as src, destination.open("wb") as dst:
                fd = -1  # ownership transferred to the file object
                while True:
                    chunk = src.read(_COPY_CHUNK_SIZE)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        ok = False
                        break
                    dst.write(chunk)
        finally:
            if fd >= 0:
                os.close(fd)

        if not ok:
            destination.unlink(missing_ok=True)
            continue

        copied.append(
            DurableArtifact(relative_path=relative, host_path=str(destination), size_bytes=written)
        )

    return tuple(copied)


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
    metrics: LibFuzzerMetrics, *, runtime_seconds: float, harness: str
) -> list[dict[str, Any]]:
    return [
        {
            "type": "STAGE_PROGRESS",
            "payload": {
                "kind": "fuzzing",
                "report": {
                    "mode": "LIVE_CAMPAIGN",
                    "harness": harness,
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
