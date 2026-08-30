"""#313/D-174: regression tests for the input-hardening follow-up to #312's
cybersecurity review (D-173).

Neither gap here was ever exploitable — every consumer of these fields executes via
an argv list, never a shell (see `contracts/schemas/missions.py`'s module-level
docstrings) — but both are tightened as defense in depth. Two properties matter and
both are proven here:

1. The tightened `fuzz_harness_target`/`fuzz_harness_binary` pattern rejects `.`,
   `..`, and any other path-traversal-shaped value, while continuing to accept every
   real harness name this codebase's own test suites already send.
2. `fuzz_cache_entries`/`fuzz_sanitizer_env` now reject keys shaped like
   cybersecurity's own adversarial examples (`CMAKE_TOOLCHAIN_FILE=/etc/passwd`-style
   embedded `=`, whitespace, shell metacharacters), while continuing to accept every
   real cache-entry/sanitizer-env key this codebase's own test suites already send.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.schemas.missions import MissionPolicy

# ---------------------------------------------------------------------------------
# 1. fuzz_harness_target / fuzz_harness_binary
# ---------------------------------------------------------------------------------

#: Every real value these two fields are set to across the codebase's own test
#: suites today (grepped from workers/fuzzing/tests, adapters/cpp/tests,
#: apps/control-api/orchestrator/tests) plus the schema's own pktcfg default.
REAL_HARNESS_NAMES = [
    "pktcfg_fuzz",  # default (missions.py); adapters/cpp, workers/fuzzing, orchestrator tests
    "njson_fuzz",  # apps/control-api/orchestrator/tests/test_fuzz_executor.py, workers/fuzzing/tests/test_cli.py
    "synth_fuzz",  # workers/fuzzing/tests/test_real_campaign.py
    "synth_leak_fuzz",  # workers/fuzzing/tests/test_real_campaign.py (with_leak_harness)
    "subdirsynth_fuzz",  # workers/fuzzing/tests/test_real_campaign.py (subdirectory binary resolution)
    "stb_fuzz",  # workers/fuzzing/tests/test_run_fuzzing.py, adapters/cpp/tests/test_fuzzing.py
]

#: Path-traversal-shaped and otherwise-malformed values the tightened pattern must
#: reject. `.`/`..` are the two the issue names explicitly; the rest generalize
#: "path-traversal-shaped" within the character class's own alphabet (no `/` was
#: ever legal, so a real `../etc/passwd`-style value was never reachable — the gap
#: was purely the bare-dot/dot-run shapes).
TRAVERSAL_SHAPED_HARNESS_NAMES = [
    ".",
    "..",
    "...",
    "....",
    "foo..bar",
    "..foo",
    "foo..",
    "..pktcfg_fuzz",
    "pktcfg_fuzz..",
]


@pytest.mark.parametrize("name", REAL_HARNESS_NAMES)
def test_real_harness_names_are_still_accepted(name: str):
    policy = MissionPolicy(fuzz_harness_target=name, fuzz_harness_binary=name)
    assert policy.fuzz_harness_target == name
    assert policy.fuzz_harness_binary == name


@pytest.mark.parametrize("name", TRAVERSAL_SHAPED_HARNESS_NAMES)
def test_traversal_shaped_harness_target_is_rejected(name: str):
    with pytest.raises(ValidationError):
        MissionPolicy(fuzz_harness_target=name)


@pytest.mark.parametrize("name", TRAVERSAL_SHAPED_HARNESS_NAMES)
def test_traversal_shaped_harness_binary_is_rejected(name: str):
    with pytest.raises(ValidationError):
        MissionPolicy(fuzz_harness_binary=name)


def test_default_harness_names_are_unaffected():
    """A mission that never sets these fields still gets pktcfg's own default —
    the "byte for byte unaffected" property #301 promised, unaffected by #313."""
    policy = MissionPolicy()
    assert policy.fuzz_harness_target == "pktcfg_fuzz"
    assert policy.fuzz_harness_binary == "pktcfg_fuzz"


def test_a_single_dot_used_as_a_real_separator_still_passes():
    """Only dot-only values and `..` runs are rejected — a single dot as an ordinary
    separator inside an otherwise-legal name is not "traversal-shaped" and stays
    legal, matching CMake's own permissive target-name character set."""
    policy = MissionPolicy(fuzz_harness_target="my.target", fuzz_harness_binary="my.bin")
    assert policy.fuzz_harness_target == "my.target"
    assert policy.fuzz_harness_binary == "my.bin"


# ---------------------------------------------------------------------------------
# 2. fuzz_cache_entries / fuzz_sanitizer_env key validation
# ---------------------------------------------------------------------------------

#: Every real key sent to these two fields across the codebase's own test suites
#: today (grepped from workers/fuzzing/tests, adapters/cpp/tests,
#: apps/control-api/orchestrator/tests, workers/baseline's own
#: baseline_extra_cmake_args tests for the same key shape).
REAL_CACHE_ENTRY_KEYS = [
    "PKTCFG_SANITIZE",
    "PKTCFG_FUZZ",
    "NJSON_SANITIZE",
    "NJSON_FUZZ",
    "SYNTH_SANITIZE",
    "SYNTH_FUZZ",
    "SUBDIRSYNTH_SANITIZE",
    "SUBDIRSYNTH_FUZZ",
    "STB_SANITIZE",
    "STB_FUZZ",
    "ASAN_OPTIONS",
    "CMAKE_POLICY_VERSION_MINIMUM",
    "CMAKE_VERBOSE_MAKEFILE",
    "FOO",
]

#: The exact shapes cybersecurity's review of #312 confirmed pass through unrejected
#: today: a key with an embedded `=` (so the "key" is actually smuggling its own
#: value, `CMAKE_TOOLCHAIN_FILE=/etc/passwd`-style), whitespace, and shell-meta
#: characters — none of which a real CMake cache variable or environment variable
#: name has ever needed.
ADVERSARIAL_CACHE_ENTRY_KEYS = [
    "CMAKE_TOOLCHAIN_FILE=/etc/passwd",
    "LD_PRELOAD=/tmp/evil.so",
    "FOO BAR",
    "FOO\tBAR",
    "FOO\nBAR",
    "FOO;rm -rf /",
    "FOO$(whoami)",
    "FOO`whoami`",
    "FOO|BAR",
    "FOO&BAR",
    "../etc/passwd",
    "",
    "1FOO",  # must not start with a digit
]


@pytest.mark.parametrize("key", REAL_CACHE_ENTRY_KEYS)
def test_real_cache_entry_keys_are_still_accepted(key: str):
    policy = MissionPolicy(
        fuzz_cache_entries={key: "ON"}, fuzz_sanitizer_env={key: "ON"}
    )
    assert policy.fuzz_cache_entries == {key: "ON"}
    assert policy.fuzz_sanitizer_env == {key: "ON"}


@pytest.mark.parametrize("key", ADVERSARIAL_CACHE_ENTRY_KEYS)
def test_adversarial_cache_entries_key_is_rejected(key: str):
    with pytest.raises(ValidationError):
        MissionPolicy(fuzz_cache_entries={key: "ON"})


@pytest.mark.parametrize("key", ADVERSARIAL_CACHE_ENTRY_KEYS)
def test_adversarial_sanitizer_env_key_is_rejected(key: str):
    with pytest.raises(ValidationError):
        MissionPolicy(fuzz_sanitizer_env={key: "ON"})


def test_fuzz_cache_entries_values_stay_unrestricted():
    """Values are deliberately not validated: a legitimate CMake cache value is
    itself an arbitrary string or path (e.g. a toolchain file's real, legitimate
    path). Only keys are constrained."""
    policy = MissionPolicy(
        fuzz_cache_entries={"CMAKE_TOOLCHAIN_FILE": "/opt/real-toolchain.cmake"}
    )
    assert policy.fuzz_cache_entries == {
        "CMAKE_TOOLCHAIN_FILE": "/opt/real-toolchain.cmake"
    }


def test_fuzz_sanitizer_env_values_stay_unrestricted():
    policy = MissionPolicy(
        fuzz_sanitizer_env={"ASAN_OPTIONS": "detect_leaks=0:log_path=/tmp/asan.log"}
    )
    assert policy.fuzz_sanitizer_env == {
        "ASAN_OPTIONS": "detect_leaks=0:log_path=/tmp/asan.log"
    }


def test_fuzz_cache_entries_none_default_is_unaffected():
    """`None` is the field's default and the "byte for byte unaffected" sentinel
    (#301) — the validator must be a no-op on it, not coerce it to `{}`."""
    policy = MissionPolicy()
    assert policy.fuzz_cache_entries is None
    assert policy.fuzz_sanitizer_env == {}


def test_a_real_multi_key_mission_policy_from_the_dispatch_test_suite_round_trips():
    """The exact payload apps/control-api/orchestrator/tests/test_fuzz_executor.py
    sends through the real dispatch path — proof the two suites agree on what
    counts as real, existing, already-tested usage."""
    policy = MissionPolicy(
        fuzz_harness_target="njson_fuzz",
        fuzz_harness_binary="njson_fuzz",
        fuzz_cache_entries={"NJSON_SANITIZE": "ON", "NJSON_FUZZ": "ON"},
        fuzz_sanitizer_env={"ASAN_OPTIONS": "detect_leaks=0"},
    )
    assert policy.fuzz_harness_target == "njson_fuzz"
    assert policy.fuzz_harness_binary == "njson_fuzz"
    assert policy.fuzz_cache_entries == {"NJSON_SANITIZE": "ON", "NJSON_FUZZ": "ON"}
    assert policy.fuzz_sanitizer_env == {"ASAN_OPTIONS": "detect_leaks=0"}
