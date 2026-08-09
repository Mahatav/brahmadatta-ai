from __future__ import annotations

from adapters.cpp.variants import Variant, spec_for


def test_baseline_has_no_sanitizer_flags() -> None:
    spec = spec_for(Variant.BASELINE)
    assert spec.sanitizer_flags == ()
    assert spec.instrumented is False
    assert spec.runtime_env == {}


def test_asan_ubsan_carries_both_sanitizers_and_halts_on_first_error() -> None:
    spec = spec_for(Variant.ASAN_UBSAN)
    assert spec.instrumented is True
    assert "-fsanitize=address,undefined" in spec.sanitizer_flags
    assert "ASAN_OPTIONS" in spec.runtime_env
    assert "UBSAN_OPTIONS" in spec.runtime_env
    # halt_on_error=1 and a distinguishable exitcode are what make a sanitizer report
    # reliable evidence rather than something a caller has to guess happened.
    assert "halt_on_error=1" in spec.runtime_env["ASAN_OPTIONS"]
    assert "exitcode=66" in spec.runtime_env["ASAN_OPTIONS"]
    assert "detect_leaks=0" in spec.runtime_env["ASAN_OPTIONS"], (
        "LeakSanitizer is a separate signal from the seeded memory-safety defect and is "
        "unsupported on Darwin — must be explicitly disabled, not left to the platform default"
    )


def test_asan_only_does_not_carry_ubsan_options() -> None:
    spec = spec_for(Variant.ASAN)
    assert "-fsanitize=address" in spec.sanitizer_flags
    assert "undefined" not in " ".join(spec.sanitizer_flags)
    assert "UBSAN_OPTIONS" not in spec.runtime_env


def test_ubsan_only_does_not_carry_asan_options() -> None:
    spec = spec_for(Variant.UBSAN)
    assert "-fsanitize=undefined" in spec.sanitizer_flags
    assert "ASAN_OPTIONS" not in spec.runtime_env


def test_every_variant_has_a_spec() -> None:
    for variant in Variant:
        spec = spec_for(variant)
        assert spec.variant is variant
