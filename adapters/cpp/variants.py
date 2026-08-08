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
the environment (`adapters/cpp/jail.py`), so if the variant does not supply them, nothing
does.

``detect_leaks=0``: LeakSanitizer is a separate signal from the memory-safety defect this
mission is about, it is unsupported on Darwin, and a leak in a test harness would turn the
sanitised baseline red for a reason that has nothing to do with the target. Turning it off
is a deliberate narrowing of scope, not a way to make a red build green — the seeded defect
is a heap-buffer-overflow and ASan reports it regardless.

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

__all__ = ["Variant", "VariantSpec", "spec_for"]


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
    ),
    Variant.ASAN: VariantSpec(
        variant=Variant.ASAN,
        build_type="Debug",
        sanitizer_flags=("-fsanitize=address", *_COMMON_SAN_FLAGS),
        runtime_env={"ASAN_OPTIONS": _ASAN_OPTIONS},
        analyzer_tools=("ADDRESS_SANITIZER", "CTEST"),
    ),
    Variant.UBSAN: VariantSpec(
        variant=Variant.UBSAN,
        build_type="Debug",
        sanitizer_flags=("-fsanitize=undefined", *_COMMON_SAN_FLAGS),
        runtime_env={"UBSAN_OPTIONS": _UBSAN_OPTIONS},
        analyzer_tools=("UNDEFINED_BEHAVIOUR_SANITIZER", "CTEST"),
    ),
}


def spec_for(variant: Variant) -> VariantSpec:
    return _SPECS[variant]
