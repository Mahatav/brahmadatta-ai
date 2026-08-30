"""Mission lifecycle schemas.

Two safety properties are expressed in the types rather than in validation code:

* `SandboxPolicy.network` is `Literal["deny"]`. The API has no vocabulary for a
  sandbox with egress. An operator cannot request one, the UI cannot offer one, and
  a future caller cannot enable one without changing this file and the frozen
  OpenAPI dump alongside it.
* `MissionDetail.authorization` is the record itself, not a boolean. The Command
  Center displays who authorized the run and until when, because "authorized: true"
  is exactly the kind of claim that survives a bug.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

#: Shape shared by `fuzz_harness_target`/`fuzz_harness_binary` below: a bare CMake
#: target/binary name, never a path. `run_libfuzzer_campaign` (`adapters/cpp/fuzzing.
#: py`) interpolates this directly into a `cmake --build ... --target <name>` argv
#: entry and a `f"{build_dir}/{name}"` executable path (both real argv-list entries,
#: never a shell string — see that module's own `_docker_run_args`/`ContainerJail.run`
#: for why shell metacharacters are not the threat model here) — restricted to CMake's
#: own legal target-name character set anyway, so a malformed value fails obviously at
#: the schema boundary rather than producing a confusing "No rule to make target" or a
#: `RUNTIME_OUTPUT_DIRECTORY`-relative path that does not mean what the operator
#: intended.
#:
#: #313/D-174: the character class alone still let a bare `.` or `..` through (both
#: legal single characters in `[A-Za-z0-9_.+-]`), and more generally any dot-only or
#: dot-dot-containing value — traversal-shaped even though nothing downstream ever
#: joins this into a filesystem path across a `/` today (the class never allowed `/`,
#: so an actual `../..`-style escape was never reachable; this closes the character-
#: level gap cybersecurity flagged in #312's review rather than a live exploit path).
#: This character class is unchanged — the dot-traversal exclusion is enforced by
#: `_validate_harness_names` below instead of by extending this pattern, because
#: pydantic-core's regex engine (Rust `regex`, not Python `re`) does not support
#: look-around, so `(?!\.+$)`/`(?!.*\.\.)` cannot live in a `Field(pattern=...)`
#: string. The validator rejects a value that is nothing but dots (covers `.`, `..`,
#: `...`, ...) and a value containing any `..` run anywhere, even inside an otherwise
#: -legal name (`foo..bar`). A single dot used as a real separator (`foo.bar`) still
#: passes, since CMake and the dogfooding targets this repo actually uses
#: (`pktcfg_fuzz`, `njson_fuzz`, `synth_fuzz`, `synth_leak_fuzz`, `subdirsynth_fuzz`,
#: `stb_fuzz` — none of which contain a dot at all) are unaffected either way.
_HARNESS_NAME_PATTERN = r"^[A-Za-z0-9_.+-]{1,200}$"

#: #313/D-174: allowlist for `fuzz_cache_entries`/`fuzz_sanitizer_env` *keys* only —
#: values stay unrestricted (see those fields' own docstrings for why: legitimate
#: CMake cache values and sanitizer-option strings are themselves arbitrary paths and
#: option lists, e.g. `ASAN_OPTIONS=detect_leaks=0:log_path=/tmp/asan`). Every real key
#: this codebase's own tests already send — `PKTCFG_SANITIZE`, `PKTCFG_FUZZ`,
#: `NJSON_SANITIZE`, `NJSON_FUZZ`, `SYNTH_SANITIZE`, `SYNTH_FUZZ`,
#: `SUBDIRSYNTH_SANITIZE`, `SUBDIRSYNTH_FUZZ`, `STB_SANITIZE`, `STB_FUZZ`,
#: `ASAN_OPTIONS`, `CMAKE_POLICY_VERSION_MINIMUM`, `CMAKE_VERBOSE_MAKEFILE`, `FOO` —
#: is a CMake-cache-variable-shaped or environment-variable-shaped identifier: starts
#: with a letter or underscore, then letters/digits/underscores only. That is also
#: exactly the shape that makes `CMAKE_TOOLCHAIN_FILE=/etc/passwd`-style keys (a key
#: with an embedded `=`), whitespace, or shell-metacharacter keys impossible to express
#: — not because argv-list execution needed the backstop (it already prevented shell
#: interpretation, D-173), but because a key is supposed to name a variable, and
#: nothing downstream has ever needed one that does not.
_CACHE_KEY_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"

from contracts.authorization import AuthorizationRecord
from contracts.enums import (
    LanguageAdapter,
    MissionPosture,
    MissionStage,
    MissionState,
    Verdict,
)
from contracts.schemas.common import ResourceUsage, StrictSchema
from contracts.schemas.envelope import MissionEvent
from contracts.schemas.evidence import MissionVerdictSummary


class SandboxPolicy(StrictSchema):
    """Resource ceilings and the isolation posture for the target sandbox (P0-2)."""

    network: Literal["deny"] = Field(
        default="deny",
        description="Egress is denied. There is no other permitted value — the type "
        "is the enforcement.",
    )
    cpu_limit: int = Field(default=4, ge=1, le=64)
    memory_mb: int = Field(default=8192, ge=512, le=131072)
    max_seconds: int = Field(default=5400, ge=60, le=43200)
    runtime: Literal["podman", "docker", "subprocess-jail"] = Field(
        default="docker",
        description="Container runtime, or the subprocess-jail fallback (#81). "
        "`docker` is D-024's accepted substitute for rootless Podman — a standard "
        "rootful-daemon container with `--network none`, never reported as "
        "`podman`'s stronger isolation claim. The subprocess-jail fallback is "
        "weaker isolation still and is reported as such everywhere it is used — "
        "it is not a silent substitution.",
    )


class PatchPolicy(StrictSchema):
    """The limits that make a rejection demonstrable as well as safe (P0-9)."""

    allowed_paths: list[str] = Field(
        default_factory=list,
        description="Glob allowlist. A candidate touching anything else is rejected "
        "before it is ever built.",
    )
    max_files_changed: int = Field(default=1, ge=1, le=10)
    max_lines_changed: int = Field(default=40, ge=1, le=500)


class MissionPolicy(StrictSchema):
    sandbox: SandboxPolicy = Field(default_factory=SandboxPolicy)
    patch: PatchPolicy = Field(default_factory=PatchPolicy)
    fuzz_seconds: int = Field(default=1800, ge=0, le=43200)
    renewed_fuzz_seconds: int = Field(
        default=120,
        ge=0,
        le=3600,
        description="Budget for VERIFY's RENEWED_FUZZING gate (#40): a bounded, "
        "targeted re-check against the patched build, deliberately much smaller than "
        "fuzz_seconds' open-ended discovery budget. 0 disables the campaign for this "
        "mission (the gate still runs and is disclosed, as NOT_RUN with a reason — "
        "see orchestrator/verification.py — never silently omitted). Added by "
        "#40/D-144 — not present in the original architecture spec's MissionPolicy "
        "listing, documented here as the addition it is (backend-developer's "
        "minor-contract-detail authority per its own role brief).",
    )
    reproducer_replay_attempts: int = Field(
        default=5,
        ge=1,
        le=100,
        description="How many times a minimized input must replay from a clean "
        "build before `reproducible` is set.",
    )
    patch_generation_attempts: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Fan-out width for JobKind.PATCH_GENERATE (D-027, architecture "
        "spec §3.4: '1 job, N attempts internally'). Each attempt that produces a "
        "parseable candidate is persisted as its own PatchCandidate row the moment "
        "it is produced, whether policy-accepted or not. Default 10 matches the D6 "
        "kill criterion's supporting threshold ('at least 3 of 10 attempts', "
        "docs/09-company/01-vision-and-p0-cut.md). Added by #168 T4 — not present "
        "in the original architecture spec's MissionPolicy listing, so documented "
        "here as the addition it is (backend-developer's minor-contract-detail "
        "authority per its own role brief).",
    )
    baseline_extra_cmake_args: dict[str, str] = Field(
        default_factory=dict,
        max_length=20,
        description="Extra CMake `-D` cache entries (key -> value, no leading `-D` "
        "and no surrounding quotes) merged into BASELINE's own configure step "
        "(adapters/cpp/variants.py::VariantSpec.with_extra_cache_entries), the "
        "operator-supplied value winning on a key collision with the variant's own "
        "fixed cache entries. The escape hatch for a real, pre-2021 third-party "
        "CMake target whose own `cmake_minimum_required` predates CMake 4.0's "
        "policy floor: e.g. {\"CMAKE_POLICY_VERSION_MINIMUM\": \"3.5\"} for a target "
        "like libpng that declares `cmake_minimum_required(VERSION 3.1)`, which "
        "CMake >= 4.0 otherwise rejects outright before BASELINE can reach even a "
        "legitimate red result (#290). Applied only to BASELINE, not to the "
        "sanitizer variants, which are driven by `adapters/cpp/pipeline.py::"
        "run_variant`'s own generic `CMAKE_C_FLAGS`/`CMAKE_EXE_LINKER_FLAGS` path "
        "independently of this field. An authorizing operator's own choice about "
        "their own authorized target, not attacker-controlled target content — "
        "same trust boundary as `PatchPolicy.allowed_paths` above. Added by #290 — "
        "not present in the original architecture spec's MissionPolicy listing, so "
        "documented here as the addition it is (backend-developer's "
        "minor-contract-detail authority per its own role brief).",
    )
    fuzz_harness_target: str = Field(
        default="pktcfg_fuzz",
        pattern=_HARNESS_NAME_PATTERN,
        description="The CMake target name FUZZ's libFuzzer campaign builds "
        "(`cmake --build <build_dir> --target <this>`), threaded through to "
        "`adapters/cpp/fuzzing.py::run_libfuzzer_campaign`'s `harness_target` "
        "parameter by `workers/fuzzing/dispatch.py`. Default is pktcfg's own target "
        "name, so a mission that does not set this gets exactly pktcfg's prior, "
        "unaffected behaviour. #296 generalized the adapter function itself to accept "
        "a non-pktcfg harness; #301 is this field, the wiring that actually lets a "
        "real mission (not just a one-off script) reach that generalization. Added by "
        "#301 — not present in the original architecture spec's MissionPolicy "
        "listing, documented here as the addition it is (backend-developer's "
        "minor-contract-detail authority per its own role brief).",
    )
    fuzz_harness_binary: str = Field(
        default="pktcfg_fuzz",
        pattern=_HARNESS_NAME_PATTERN,
        description="The built executable's bare file name inside FUZZ's build "
        "directory (`adapters/cpp/fuzzing.py::run_libfuzzer_campaign`'s "
        "`harness_binary` parameter) — usually, but not required to be, identical to "
        "`fuzz_harness_target`. Default is pktcfg's own binary name; unset, this "
        "field changes nothing about pktcfg's existing behaviour. Added by #301, "
        "same authority note as `fuzz_harness_target` above.",
    )

    @field_validator("fuzz_harness_target", "fuzz_harness_binary")
    @classmethod
    def _validate_harness_names(cls, value: str) -> str:
        """#313/D-174: reject `.`, `..`, any dot-only value, and any value containing
        a `..` run anywhere - path-traversal-shaped even though the character class
        (`_HARNESS_NAME_PATTERN`) never allowed a `/` for an actual traversal to walk
        across. Runs after the `pattern=` charset check, using Python `re` (which
        supports the look-around pydantic-core's Rust regex engine does not)."""
        if re.fullmatch(r"\.+", value) or ".." in value:
            raise ValueError(
                "must be a bare CMake target/binary name, not '.', '..', or any "
                f"value containing a '..' run: {value!r}"
            )
        return value

    fuzz_cache_entries: dict[str, str] | None = Field(
        default=None,
        max_length=20,
        description="CMake `-D<key>=<value>` cache entries FUZZ's configure step "
        "applies (`adapters/cpp/fuzzing.py::run_libfuzzer_campaign`'s `cache_entries` "
        "parameter) — the target's own naturally-named sanitizer/fuzz-enable options "
        "(e.g. `{\"STB_SANITIZE\": \"ON\", \"STB_FUZZ\": \"ON\"}` for a target that "
        "does not use pktcfg's `PKTCFG_*` names). `None` (the default, and the only "
        "value that reproduces pktcfg's exact prior behaviour) defers to "
        "`run_libfuzzer_campaign`'s own `DEFAULT_CACHE_ENTRIES` — pktcfg's two "
        "options — so a mission that does not set this field is byte-for-byte "
        "unaffected by #301. An explicit `{}` is a distinct, deliberate choice (no "
        "cache entries at all), not a synonym for `None`. Added by #301, same "
        "authority note as `fuzz_harness_target` above. #313/D-174: keys are "
        "validated against `_CACHE_KEY_PATTERN` (see `_validate_cache_entry_keys` "
        "below); values are intentionally left unrestricted since a legitimate CMake "
        "cache value is itself an arbitrary string or path.",
    )
    fuzz_sanitizer_env: dict[str, str] = Field(
        default_factory=dict,
        max_length=20,
        description="Sanitizer runtime environment (e.g. "
        "`{\"ASAN_OPTIONS\": \"detect_leaks=0\"}`) merged into FUZZ's container "
        "environment for the live campaign (`adapters/cpp/fuzzing.py::"
        "run_libfuzzer_campaign`'s `sanitizer_env` parameter, #289). Empty (the "
        "default) adds nothing — pktcfg's own prior behaviour, unaffected unless an "
        "operator sets this. Added by #301, same authority note as "
        "`fuzz_harness_target` above. #313/D-174: keys are validated against "
        "`_CACHE_KEY_PATTERN`, same as `fuzz_cache_entries`; values stay "
        "unrestricted for the same reason (e.g. `ASAN_OPTIONS` values are "
        "colon-separated option strings, not identifiers).",
    )

    @field_validator("fuzz_cache_entries", "fuzz_sanitizer_env")
    @classmethod
    def _validate_cache_entry_keys(
        cls, value: dict[str, str] | None
    ) -> dict[str, str] | None:
        """#313/D-174: reject keys shaped like `CMAKE_TOOLCHAIN_FILE=/etc/passwd` —
        i.e. containing `=`, whitespace, or any other shell/CMake metacharacter —
        before they ever reach `run_libfuzzer_campaign`'s argv-list `-D<key>=<value>`
        construction. Argv-list execution already prevents shell interpretation
        (D-173); this is defense in depth so a malformed key fails loudly at the
        schema boundary with a clear reason, rather than silently producing a
        `-D<key>=<value>=<attacker-value>`-shaped cache entry that CMake itself would
        have to reject (or worse, accept in some confusing way). Values are
        deliberately not validated here — see the fields' own docstrings."""
        if value is None:
            return value
        bad_keys = [key for key in value if not re.match(_CACHE_KEY_PATTERN, key)]
        if bad_keys:
            raise ValueError(
                "cache entry keys must look like a CMake cache variable or "
                "environment variable name (start with a letter or underscore, "
                "then letters/digits/underscores only) — rejected: "
                f"{bad_keys!r}"
            )
        return value


class MissionCreateRequest(StrictSchema):
    name: str = Field(min_length=1, max_length=200)
    repository_ref: str = Field(
        min_length=1,
        max_length=500,
        description="Authorized repository URL or the name of an uploaded archive. "
        "Never a public target chosen at scan time.",
    )
    adapter: LanguageAdapter
    policy: MissionPolicy = Field(default_factory=MissionPolicy)
    idempotency_key: str | None = Field(
        default=None,
        max_length=200,
        description="Replaying a create with the same key returns the same mission "
        "rather than creating a second one.",
    )


class SnapshotRequest(StrictSchema):
    """Ingest an immutable snapshot of the authorized repository (P0-1).

    The digest is supplied by the caller and re-computed server-side; a mismatch is
    a hard failure, so a swapped archive cannot inherit an existing authorization.
    """

    source: Literal["upload", "git"] = "git"
    commit_sha: str | None = Field(default=None, max_length=64)
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_ref: str | None = Field(
        default=None,
        max_length=500,
        description="Pointer to the uploaded archive when source='upload'.",
    )
    idempotency_key: str | None = Field(default=None, max_length=200)


class SnapshotRecord(StrictSchema):
    id: UUID
    mission_id: UUID
    commit_sha: str | None = None
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_count: int = Field(ge=0)
    bytes_total: int = Field(ge=0)
    created_at: datetime
    immutable: Literal[True] = Field(
        default=True,
        description="Snapshots are write-once. The field exists so the evidence "
        "bundle states the property rather than implying it.",
    )


class PreflightCheck(StrictSchema):
    name: str = Field(max_length=120)
    passed: bool
    detail: str = Field(default="", max_length=1000)


class PreflightReport(StrictSchema):
    """Validates authorization, commands, adapter and limits before anything runs."""

    mission_id: UUID
    passed: bool
    checks: list[PreflightCheck]
    checked_at: datetime
    blocking_codes: list[str] = Field(
        default_factory=list,
        description="Error codes that must clear before the mission may start.",
    )


class StartRequest(StrictSchema):
    confirm_authorized: Literal[True] = Field(
        description="Explicit operator confirmation. Typed as a literal so an "
        "accidental `false` is a validation error rather than a silent no-op."
    )
    idempotency_key: str | None = Field(default=None, max_length=200)


class PauseRequest(StrictSchema):
    reason: str = Field(default="", max_length=500)


class CancelRequest(StrictSchema):
    reason: str = Field(default="", max_length=500)
    confirm: Literal[True] = Field(
        description="Cancellation tears down sandboxes and stops the run; it is "
        "always confirmed explicitly."
    )


class MissionProgress(StrictSchema):
    """What the Core renders. Derived server-side so two clients never disagree."""

    stage: MissionStage | None = None
    stages_completed: list[MissionStage] = Field(default_factory=list)
    percent_complete: float | None = Field(default=None, ge=0, le=100)
    last_event_sequence: int = Field(default=0, ge=0)


class MissionCounts(StrictSchema):
    """Summary counters. Every one is a real count from the evidence database."""

    findings: int = Field(default=0, ge=0)
    reproducible_findings: int = Field(default=0, ge=0)
    patch_candidates: int = Field(default=0, ge=0)
    verifications: int = Field(default=0, ge=0)
    tests_passed: int = Field(default=0, ge=0)
    tests_failed: int = Field(default=0, ge=0)


class MissionSummary(StrictSchema):
    id: UUID
    name: str = Field(max_length=200)
    state: MissionState
    posture: MissionPosture
    adapter: LanguageAdapter
    repository_ref: str = Field(max_length=500)
    authorized: bool = Field(
        description="True only when an unrevoked, unexpired authorization record "
        "exists. Derived from the record, never set directly."
    )
    verdict: Verdict | None = None
    created_at: datetime
    updated_at: datetime


class MissionDetail(StrictSchema):
    id: UUID
    name: str = Field(max_length=200)
    state: MissionState
    posture: MissionPosture
    adapter: LanguageAdapter
    repository_ref: str = Field(max_length=500)
    policy: MissionPolicy
    authorization: AuthorizationRecord | None = Field(
        default=None,
        description="The record itself. Absent means nothing may run.",
    )
    snapshot: SnapshotRecord | None = None
    progress: MissionProgress
    counts: MissionCounts
    resource_usage: ResourceUsage
    verdict: Verdict | None = Field(
        default=None,
        description="The mission verdict, derived from the set of per-candidate "
        "verdicts. Never displayed without `verdict_summary` beside it.",
    )
    verdict_summary: MissionVerdictSummary | None = Field(
        default=None,
        description="Per-candidate breakdown. A mission runs N candidates through the "
        "identical pipeline — the demo runs two, one Verified and one Rejected — and "
        "the rejection is the differentiator, so it travels with the mission verdict "
        "rather than being reduced away.",
    )
    allowed_transitions: list[MissionState] = Field(
        default_factory=list,
        description="What the operator controls may legally do next. The UI disables "
        "its buttons from this rather than duplicating the state machine.",
    )
    last_event: MissionEvent | None = None
    created_at: datetime
    updated_at: datetime
