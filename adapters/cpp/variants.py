"""Build variants — #27's "selectable adapter configurations".

A variant is a named bundle of three things: the CMake cache entries that turn the
instrumentation on, the environment the resulting binaries need at *run* time, and the
`AnalyzerTool` values a finding from this variant may be attributed to.

Why the runtime environment belongs here
----------------------------------------

ASan defaults to printing its report and calling ``_exit(1)``. That is fine for a human and
useless for a gate: with ``abort_on_error=0`` the process exits 1 the same way a failed
assertion does, and with ``halt_on_error=0`` UBSan does not exit at all. The report is only
reliable evidence if the options that produce it travel with the variant. Putting them in a
dict beside the flags is what stops a caller building an ASan binary and then running it
with whatever ``ASAN_OPTIONS`` the operator's shell happened to export — the jail scrubs
the environment to an allowlist (`packages/sandbox/policy.py`'s `DEFAULT_ENV_ALLOWLIST`),
so if the variant does not supply them, nothing does.

``detect_leaks=0``: LeakSanitizer is a separate signal from the memory-safety defect this
mission is about, it is unsupported on Darwin, and a leak in a test harness would turn the
sanitised baseline red for a reason that has nothing to do with the target. Turning it off
is a deliberate narrowing of scope, not a way to make a red build green — the seeded defect
is a heap-buffer-overflow and ASan reports it regardless.

`min_jail_memory_bytes`: RLIMIT_AS and AddressSanitizer do not coexist
------------------------------------------------------------------------------

Found the hard way: `adapters/cpp/pipeline.py::run_variant` for `ASAN_UBSAN` passes
locally on macOS and failed in CI on Linux, both times against the identical source and
flags — `packages.sandbox.Jail`'s `RLIMIT_AS` (`JailPolicy.memory_bytes`, default 2 GiB)
is not enforced on Darwin at all (documented there), but it *is* enforced on Linux. Every
ASan-instrumented test process aborted at startup:

    AddressSanitizer failed to allocate 0x1bfe00000000 (30777735643136) bytes ...
    ReserveShadowMemoryRange failed while trying to map ... bytes. Perhaps you're using ulimit -v

That is ASan reserving shadow memory for its whole-address-space instrumentation — roughly
**28 TiB of virtual address space**, measured directly in a `ubuntu:24.04` container
(gcc 13.3.0, x86_64) via `docker run` reproducing the CI failure exactly. This is
documented ASan behaviour, not a bug in this target or this adapter: `RLIMIT_AS`
(`ulimit -v`) constrains *virtual* address space, and ASan's shadow region is sized against
the whole 64-bit address space regardless of how much memory the program under test
actually touches. No "reasonable" `RLIMIT_AS` value accommodates it — 2 GiB fails, 16 GiB
fails, and the requirement only clears at the tens-of-TiB range, confirmed empirically:
64 GiB still aborts, 64 TiB and `unlimited` both pass 8/8.

`MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS` below is **not a memory budget** — treating it as
one would be the same "a name is not a measurement" mistake `packages/sandbox`'s own
`limits_applied` design (D-054) exists to catch, just with an honest-looking number
standing in for the platform name. It exists for exactly one reason: so `RLIMIT_AS` does
not block ASan from starting at all. A caller building `ASAN`, `UBSAN`, or `ASAN_UBSAN`
must construct its `Jail` with a `JailPolicy(memory_bytes=...)` at least this large —
`adapters/cpp/tests/test_sanitizer.py` does this for its two sanitizer-variant tests, and
this is the reason those two (and only those two) needed it. `BASELINE`'s
`min_jail_memory_bytes` is `None`: no sanitizer, no shadow memory, the jail's own default
is a real, meaningful cap there.

**This is a structural limitation of pairing `RLIMIT_AS`-based memory limiting with
AddressSanitizer, not something scoped to this adapter or this variant table.** Flagged to
the `packages/sandbox` owner rather than solved unilaterally in that package — the durable
fix (an `RLIMIT_DATA`- or cgroup-based memory limit that actually constrains an
ASan-instrumented process, or an opt-out of `RLIMIT_AS` specifically) is `packages/sandbox`
`jail.py`'s call to make, not this adapter's. This constant is the honest, scoped
workaround on this side of that boundary until that lands.

The pktcfg property this protects
---------------------------------

`demo/repositories/pktcfg/README.md`: *"The baseline suite is green with and without
sanitizers … precisely because none of the eight tests trips the seeded defect on its
own."* So `ASAN_UBSAN` + `ctest` is a usable gate rather than a permanent red, and #41's
standing prohibition — never add a test to that target that fails on the unpatched build —
is what keeps it that way. Nothing in this package adds tests to a target.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = ["MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS", "Variant", "VariantSpec", "spec_for"]

#: See the module docstring's "`min_jail_memory_bytes`: RLIMIT_AS and AddressSanitizer do
#: not coexist" section. Measured requirement was ~28 TiB (0x1bfe00000000 bytes) on
#: ubuntu:24.04/gcc 13.3.0/x86_64; this is 64 TiB for headroom across compiler/arch
#: variation, empirically confirmed sufficient in the same reproduction. Not a budget.
MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS = 64 * 1024 * 1024 * 1024 * 1024  # 64 TiB


class Variant(StrEnum):
    """Selectable adapter configurations."""

    #: No instrumentation. This is the one whose `ctest` counts are the regression
    #: denominator (#17).
    BASELINE = "BASELINE"
    #: Both sanitizers together, which is how the target's own README documents it and how
    #: `PKTCFG_SANITIZE=ON` is written.
    ASAN_UBSAN = "ASAN_UBSAN"
    #: AddressSanitizer alone — for isolating whether a report is a memory-safety finding
    #: or an undefined-behaviour one when both are on.
    ASAN = "ASAN"
    #: UndefinedBehaviorSanitizer alone.
    UBSAN = "UBSAN"


@dataclass(frozen=True, slots=True)
class VariantSpec:
    """Everything that differs between variants, in one place."""

    variant: Variant
    build_type: str
    #: Raw compiler/linker flags. Applied through `CMAKE_C_FLAGS` / `CMAKE_EXE_LINKER_FLAGS`
    #: so a target with no sanitizer option of its own still gets instrumented.
    sanitizer_flags: tuple[str, ...] = ()
    #: Extra `-D` cache entries. Used for a target that exposes its own switch — pktcfg's
    #: `PKTCFG_SANITIZE` is the case in point, and setting it is better than bolting flags
    #: on from outside because the project knows where they belong.
    cache_entries: dict[str, str] = field(default_factory=dict)
    #: Environment for the *test* run, not the build.
    runtime_env: dict[str, str] = field(default_factory=dict)
    #: `contracts.enums.AnalyzerTool` values a finding from this variant may claim.
    analyzer_tools: tuple[str, ...] = ()
    #: `None` when this variant places no special demand on the jail's memory policy.
    #: Set for every sanitizer variant — see the module docstring. A caller MUST build
    #: its `Jail` with `JailPolicy(memory_bytes=...)` at least this large before calling
    #: `pipeline.run_variant`/`run_reproducer` with this variant, or every instrumented
    #: process aborts before running a single check.
    min_jail_memory_bytes: int | None = None

    @property
    def instrumented(self) -> bool:
        return bool(self.sanitizer_flags)

    def as_dict(self) -> dict[str, object]:
        return {
            "variant": self.variant.value,
            "build_type": self.build_type,
            "sanitizer_flags": list(self.sanitizer_flags),
            "cache_entries": dict(self.cache_entries),
            "runtime_env": dict(self.runtime_env),
            "analyzer_tools": list(self.analyzer_tools),
            "min_jail_memory_bytes": self.min_jail_memory_bytes,
        }


_COMMON_SAN_FLAGS = ("-fno-omit-frame-pointer", "-fno-optimize-sibling-calls", "-g")

_ASAN_OPTIONS = ":".join(
    (
        "abort_on_error=0",
        "detect_leaks=0",
        "symbolize=1",
        "print_stacktrace=1",
        "halt_on_error=1",
        "exitcode=66",
    )
)
_UBSAN_OPTIONS = ":".join(("print_stacktrace=1", "halt_on_error=1", "exitcode=66"))

_SPECS: dict[Variant, VariantSpec] = {
    Variant.BASELINE: VariantSpec(
        variant=Variant.BASELINE,
        build_type="Debug",
        analyzer_tools=("CTEST", "COMPILER_DIAGNOSTIC"),
    ),
    Variant.ASAN_UBSAN: VariantSpec(
        variant=Variant.ASAN_UBSAN,
        build_type="Debug",
        sanitizer_flags=("-fsanitize=address,undefined", *_COMMON_SAN_FLAGS),
        runtime_env={"ASAN_OPTIONS": _ASAN_OPTIONS, "UBSAN_OPTIONS": _UBSAN_OPTIONS},
        analyzer_tools=("ADDRESS_SANITIZER", "UNDEFINED_BEHAVIOUR_SANITIZER", "CTEST"),
        min_jail_memory_bytes=MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS,
    ),
    Variant.ASAN: VariantSpec(
        variant=Variant.ASAN,
        build_type="Debug",
        sanitizer_flags=("-fsanitize=address", *_COMMON_SAN_FLAGS),
        runtime_env={"ASAN_OPTIONS": _ASAN_OPTIONS},
        analyzer_tools=("ADDRESS_SANITIZER", "CTEST"),
        min_jail_memory_bytes=MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS,
    ),
    Variant.UBSAN: VariantSpec(
        variant=Variant.UBSAN,
        build_type="Debug",
        sanitizer_flags=("-fsanitize=undefined", *_COMMON_SAN_FLAGS),
        runtime_env={"UBSAN_OPTIONS": _UBSAN_OPTIONS},
        analyzer_tools=("UNDEFINED_BEHAVIOUR_SANITIZER", "CTEST"),
        # UBSan alone links no shadow-memory runtime, so it does not strictly need this —
        # applied anyway for uniformity across the three sanitizer variants and because a
        # future flag change (e.g. combining with ASan again) should not silently need a
        # policy change too.
        min_jail_memory_bytes=MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS,
    ),
}


def spec_for(variant: Variant) -> VariantSpec:
    return _SPECS[variant]
