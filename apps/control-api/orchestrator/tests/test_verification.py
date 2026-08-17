"""#38 — clean-worktree deterministic verification."""

from __future__ import annotations

from pathlib import Path
import inspect
import os
import shutil
import subprocess
import sys
import time
import typing

import pytest

from adapters.cpp.variants import MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS
from contracts.enums import GateStatus, PatchProvenance, Verdict
from contracts.verdict import GateMatrix, derive_verdict
from orchestrator import verification
from orchestrator.tests.conftest import CANDIDATE_A, CANDIDATE_B
from orchestrator.verification import (
    CommandResult,
    VerificationBaseline,
    _ENV_ALLOWLIST,
    _sanitizers_enabled,
    _subprocess_runner,
    run_verification,
)
from packages.sandbox import JailPolicy


DEMO_REPOSITORY = CANDIDATE_A.parents[1]
CRASH = DEMO_REPOSITORY / "crash" / "crash-literal-tab.bin"
BASELINE = VerificationBaseline(expected_regression_tests=8)


def test_run_verification_signature_is_provenance_blind():
    signature = inspect.signature(run_verification)

    assert list(signature.parameters) == [
        "worktree",
        "candidate_diff",
        "reproducer",
        "baseline",
        "runner",
    ]
    hints = typing.get_type_hints(run_verification)
    assert hints["return"] is GateMatrix

    forbidden = {"patch", "candidate", "provenance", "model", "confidence", "rationale"}
    for name, parameter in signature.parameters.items():
        if name == "candidate_diff":
            continue
        assert not any(token in name.lower() for token in forbidden)
        assert not any(token in str(parameter.annotation).lower() for token in forbidden)


def test_verifier_is_provenance_blind():
    """The same diff gets the same gates regardless of how evidence labels it."""

    # These are deliberately not passed to run_verification; the verifier has no slot
    # for them.
    model_recorded_as = PatchProvenance.MODEL_GENERATED
    operator_recorded_as = PatchProvenance.OPERATOR_SUPPLIED
    assert model_recorded_as is not operator_recorded_as

    model_run = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=ScriptedRunner(),
    )
    operator_run = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=ScriptedRunner(),
    )

    assert model_run.model_dump(mode="json") == operator_run.model_dump(mode="json")
    assert derive_verdict(model_run) is Verdict.VERIFIED


def test_verified_path_runs_in_a_fresh_worktree():
    runner = ScriptedRunner()

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=runner,
    )

    assert derive_verdict(gates) is Verdict.VERIFIED
    assert gates.compile.status is GateStatus.PASS
    assert gates.reproducer_eliminated.status is GateStatus.PASS
    assert gates.regression_preserved.status is GateStatus.PASS
    assert runner.cwd_seen
    assert all(cwd != DEMO_REPOSITORY for cwd in runner.cwd_seen)
    assert all(DEMO_REPOSITORY not in cwd.parents for cwd in runner.cwd_seen)
    assert runner.applied_diffs == [CANDIDATE_A.read_text()]


def test_reproducer_eliminated_but_regression_failed_is_rejected():
    runner = ScriptedRunner(
        regression=CommandResult(
            argv=("ctest",),
            returncode=8,
            stdout="88% tests passed, 1 tests failed out of 8\n"
            "The following tests FAILED:\n"
            "4 - test_tab_expansion (Failed)\n",
        )
    )

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_B.read_text(),
        CRASH,
        BASELINE,
        runner=runner,
    )

    assert gates.reproducer_eliminated.status is GateStatus.PASS
    assert gates.regression_preserved.status is GateStatus.FAIL
    assert "Regression suite failed" in gates.regression_preserved.detail
    assert derive_verdict(gates) is Verdict.REJECTED


def test_regression_coverage_drop_is_not_a_pass():
    runner = ScriptedRunner(
        regression=CommandResult(
            argv=("ctest",),
            returncode=0,
            stdout="100% tests passed, 0 tests failed out of 5\n",
        )
    )

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=runner,
    )

    assert gates.reproducer_eliminated.status is GateStatus.PASS
    assert gates.regression_preserved.status is GateStatus.FAIL
    assert "Regression coverage dropped" in gates.regression_preserved.detail
    assert derive_verdict(gates) is Verdict.REJECTED


def test_failed_compile_discloses_gates_that_did_not_run():
    runner = ScriptedRunner(build=CommandResult(argv=("cmake", "--build"), returncode=2))

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        runner=runner,
    )

    assert gates.compile.status is GateStatus.FAIL
    assert gates.reproducer_eliminated.status is GateStatus.NOT_RUN
    assert gates.regression_preserved.status is GateStatus.NOT_RUN
    assert "build failed" in gates.reproducer_eliminated.detail
    assert derive_verdict(gates) is Verdict.REJECTED


# --------------------------------------------------------------------------------
# SEC-44 — every verification subprocess runs under an explicit env allowlist, never
# the worker's full (secret-bearing) process environment.
# --------------------------------------------------------------------------------


def test_env_allowlist_is_exactly_the_documented_minimal_set():
    """Pinned so a future edit that quietly widens the allowlist (e.g. re-adding a
    blanket `os.environ.copy()`) shows up as a diff to this test, not a silent gap."""
    assert set(_ENV_ALLOWLIST) == {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "TERM",
        "CC",
        "CXX",
        "CMAKE_BUILD_PARALLEL_LEVEL",
        "MAKEFLAGS",
    }
    assert "DATABASE_URL" not in _ENV_ALLOWLIST


def test_subprocess_runner_drops_process_secrets_from_the_child_env(monkeypatch, tmp_path):
    """SEC-44's direct proof: a spawned verification subprocess must never see a
    process-inherited secret such as `DATABASE_URL`, even though `_subprocess_runner`
    receives no `env=` override from any of its callers — the allowlist is enforced
    inside the runner itself.

    The child process prints its own real environment; the assertion reads that
    straight from the test's own in-memory `CommandResult.stdout`, never through a
    `GateResult` or any persisted artifact, so this test cannot itself become the kind
    of leak SEC-45 closes.
    """
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://real-user:real-secret-token@db:5432/prod"
    )
    monkeypatch.setenv("SOME_OTHER_SERVICE_TOKEN", "another-leaked-value")

    result = _subprocess_runner(
        [sys.executable, "-c", "import os, sys; sys.stdout.write(repr(dict(os.environ)))"],
        tmp_path,
        None,
        10,
    )

    assert result.ok, result.stderr
    assert "real-secret-token" not in result.stdout
    assert "DATABASE_URL" not in result.stdout
    assert "another-leaked-value" not in result.stdout
    assert "SOME_OTHER_SERVICE_TOKEN" not in result.stdout


def test_subprocess_runner_env_is_an_allowlist_not_a_secret_blocklist(monkeypatch, tmp_path):
    """A variable with no secret-shaped name at all is still dropped unless it is on
    `_ENV_ALLOWLIST` — proves this is allowlisting, not pattern-matching on names that
    happen to look like credentials, which is exactly the "misses the next secret"
    failure mode the review flagged against a blocklist approach."""
    monkeypatch.setenv("TOTALLY_HARMLESS_LOOKING_VAR", "nothing-secret-here")
    monkeypatch.setenv("PATH", os.environ.get("PATH", "/usr/bin:/bin"))

    result = _subprocess_runner(
        [sys.executable, "-c", "import os, sys; sys.stdout.write(repr(dict(os.environ)))"],
        tmp_path,
        None,
        10,
    )

    assert result.ok, result.stderr
    assert "TOTALLY_HARMLESS_LOOKING_VAR" not in result.stdout
    assert "nothing-secret-here" not in result.stdout
    # Sanity check the allowlist positive case in the same breath: PATH *is* allowlisted
    # and *is* set, so it must still make it through.
    assert "'PATH'" in result.stdout


@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake not installed")
@pytest.mark.skipif(shutil.which("ctest") is None, reason="ctest not installed")
@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_real_ctest_injected_env_dump_does_not_see_the_process_secret(tmp_path, monkeypatch):
    """The exact proof-of-concept SEC-44 names: a one-line `CMakeLists.txt` addition —
    `add_test(... COMMAND sh -c "env")` — registered as a regression test and executed
    by the real `ctest` gate against a real (if trivial) CMake target, through the real
    `run_verification` pipeline end to end (no `ScriptedRunner`).

    This is a stronger check than the `.detail`-only tests below: it confirms the
    *actual child process* `ctest` spawns cannot observe this process's `DATABASE_URL`,
    not merely that the `GateResult` returned to the caller doesn't quote it.
    """
    secret = "s3cr3t-postgres-credential-should-never-leak"
    monkeypatch.setenv("DATABASE_URL", f"postgresql://real:{secret}@db:5432/prod")

    source = tmp_path / "trivial_target"
    source.mkdir()
    (source / "main.c").write_text("int main(void) { return 0; }\n")
    (source / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\n"
        "project(trivial C)\n"
        "add_executable(trivial main.c)\n"
        "enable_testing()\n"
        "add_test(NAME trivial_test COMMAND trivial)\n"
    )

    def _git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=source, check=True, capture_output=True, text=True)

    _git("init", "-q")
    _git("-c", "user.email=t@example.com", "-c", "user.name=t", "add", "-A")
    _git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "baseline")

    dump_path = tmp_path / "exfiltrated-env.txt"
    cmakelists = source / "CMakeLists.txt"
    cmakelists.write_text(
        cmakelists.read_text() + f"add_test(NAME dump_env COMMAND sh -c \"env > '{dump_path}'\")\n"
    )
    diff = subprocess.run(
        ["git", "diff"], cwd=source, check=True, capture_output=True, text=True
    ).stdout
    assert diff, "expected a non-empty diff for the injected CMakeLists.txt change"

    # Restore the working tree to the clean baseline so `run_verification` applies the
    # captured diff itself, exactly like the real VERIFY pipeline does against a
    # candidate diff it did not author.
    _git("checkout", "--", "CMakeLists.txt")

    gates = run_verification(
        source,
        diff,
        tmp_path / "no-reproducer-for-this-fixture",
        VerificationBaseline(),
    )

    assert gates.compile.status is GateStatus.PASS, gates.compile.detail
    # The injected test genuinely ran (it is a real ctest case now) — this is the
    # actual SEC-44 assertion: what it wrote never contains the secret this process
    # held, because the child never received it in the first place.
    assert dump_path.is_file(), "the injected ctest case did not run at all"
    dumped_env = dump_path.read_text()
    assert secret not in dumped_env
    assert "DATABASE_URL" not in dumped_env
    # Belt and suspenders — SEC-45, on this same real run.
    for gate in gates.results():
        assert secret not in gate.detail


@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake not installed")
@pytest.mark.skipif(shutil.which("ctest") is None, reason="ctest not installed")
@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_real_replay_binary_injected_env_dump_does_not_see_process_secrets_on_real_demo_target(
    tmp_path, monkeypatch
):
    """QA fresh adversarial probe (independent of the SEC-44 review/fix cycle's own
    scenario above): a different secret shape, a different leak channel, and the real
    pktcfg demo target rather than a synthetic trivial CMake project.

    The prior test attacks via `ctest` (a registered regression test spawning `sh -c
    "env"`) and only ever exercises `DATABASE_URL`. This attacks via the *compiled
    patched binary itself* — `pktcfg_replay`, the reproducer/replay gate's own
    executable — which is the specific higher-risk call site cybersecurity's original
    BLOCKED review named explicitly ("what actually runs unsandboxed is not 'just git
    apply'... execution of the compiled patched binary"). It also targets two
    differently-shaped secrets that were never part of the original SEC-44 exploit
    scenario: this project's own real `CONTROL_API_ADMIN_TOKEN` (D-040) and a
    generic-shaped `AWS_SECRET_ACCESS_KEY`, so the property is shown to hold for
    "any secret in the allowlist's complement", not merely for the one Postgres
    connection string the original PoC and its regression test happened to use.

    Runs against `VerificationBaseline()`'s real, unmodified default (sanitizers on),
    through the real, unmodified `run_verification` — the actual default `Jail`-backed
    runner, no injected `ScriptedRunner` — so this also stands as independent
    confirmation that SEC-47's `Jail.run()` environment scrubbing holds for this call
    site specifically, not just for `git apply`/`cmake`/`ctest`.
    """
    admin_token_secret = "qa-adversarial-admin-token-should-never-leak-4f9c2e"
    aws_secret = "AKIAQAADVERSARIALPROBE-should-never-leak-77219c"
    monkeypatch.setenv("CONTROL_API_ADMIN_TOKEN", admin_token_secret)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", aws_secret)

    dump_path = tmp_path / "replay-binary-exfiltrated-env.txt"

    scratch = tmp_path / "pktcfg_env_probe_scratch"
    scratch_tools = scratch / "tools"
    scratch_tools.mkdir(parents=True)
    original_source = (DEMO_REPOSITORY / "tools" / "pktcfg_replay.c").read_text()
    (scratch_tools / "pktcfg_replay.c").write_text(original_source)

    def _git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=scratch, check=True, capture_output=True, text=True)

    _git("init", "-q")
    _git("-c", "user.email=t@example.com", "-c", "user.name=t", "add", "-A")
    _git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "baseline")

    # Dump `environ` to a file as the very first thing `main` does — before the
    # existing, still-present seeded bug gets a chance to crash the process — so a
    # successful dump is proof the *compiled patched binary* itself ran with the
    # worker's real environment reachable, not merely that some subprocess did.
    injected_source = original_source.replace(
        "int main(int argc, char **argv)\n{\n",
        "extern char **environ;\n\n"
        "int main(int argc, char **argv)\n{\n"
        "    {\n"
        f'        FILE *qa_probe_dump = fopen("{dump_path.as_posix()}", "w");\n'
        "        if (qa_probe_dump != NULL) {\n"
        "            char **qa_probe_envp;\n"
        "            for (qa_probe_envp = environ; *qa_probe_envp != NULL; qa_probe_envp++) {\n"
        '                fprintf(qa_probe_dump, "%s\\n", *qa_probe_envp);\n'
        "            }\n"
        "            fclose(qa_probe_dump);\n"
        "        }\n"
        "    }\n",
        1,
    )
    assert injected_source != original_source, "insertion point not found in pktcfg_replay.c"
    (scratch_tools / "pktcfg_replay.c").write_text(injected_source)

    diff = subprocess.run(
        ["git", "diff"], cwd=scratch, check=True, capture_output=True, text=True
    ).stdout
    assert diff, "expected a non-empty diff for the injected pktcfg_replay.c change"

    gates = run_verification(DEMO_REPOSITORY, diff, CRASH, BASELINE)

    assert gates.compile.status is GateStatus.PASS, gates.compile.detail
    assert dump_path.is_file(), (
        "the patched pktcfg_replay binary never ran at all — the probe proves nothing"
    )
    dumped_env = dump_path.read_text()
    assert admin_token_secret not in dumped_env
    assert aws_secret not in dumped_env
    assert "CONTROL_API_ADMIN_TOKEN" not in dumped_env
    assert "AWS_SECRET_ACCESS_KEY" not in dumped_env
    # Belt and suspenders — SEC-45, on this same real run: whatever verdict this
    # (still seeded-vulnerable-in-every-other-line) source reaches, no gate detail on
    # the way there ever carries either secret either.
    for gate in gates.results():
        assert admin_token_secret not in gate.detail
        assert aws_secret not in gate.detail


# --------------------------------------------------------------------------------
# SEC-47 — run_verification's default runner routes every command through exactly one
# packages.sandbox.Jail, with real (not merely documented) resource limits.
# --------------------------------------------------------------------------------


def test_run_verification_opens_exactly_one_jail_sized_from_the_baseline_timeout(
    monkeypatch,
):
    """SEC-47: `run_verification` must actually open a `Jail` for its default runner,
    not merely be capable of one — and exactly one per call, for the whole
    configure+build+ctest sequence (mirroring `workers/baseline/run.py`'s pattern),
    not one per command. Spies on the real `Jail.create` (still calling through to it,
    so this exercises the genuine object, not a mock standing in for one) and asserts
    the `JailPolicy` it was given is sized from `VerificationBaseline.timeout_seconds`.
    """
    created_policies: list[object] = []
    real_create = verification.Jail.create

    def _spy_create(policy=None, **kwargs):
        created_policies.append(policy)
        return real_create(policy, **kwargs)

    monkeypatch.setattr(verification.Jail, "create", staticmethod(_spy_create))

    runner = ScriptedRunner()
    gates = run_verification(
        DEMO_REPOSITORY, CANDIDATE_A.read_text(), CRASH, BASELINE, runner=runner
    )

    assert derive_verdict(gates) is Verdict.VERIFIED
    assert len(created_policies) == 1, (
        "run_verification should open exactly one Jail per call, for the whole "
        "configure+build+ctest sequence"
    )
    assert created_policies[0].wall_clock_seconds == float(BASELINE.timeout_seconds)


@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake not installed")
@pytest.mark.skipif(shutil.which("ctest") is None, reason="ctest not installed")
@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_real_wall_clock_limit_stops_a_hung_build(tmp_path):
    """A real build against a real (if trivial) CMake target, through the real,
    unmodified `run_verification` (no injected `runner=`), where the build step runs a
    multi-minute `sleep`. Proves the pipeline as a whole does not hang forever on a
    stuck build — real and valuable on its own — but is not, by itself, proof that
    `Jail` specifically is what stopped it: `_subprocess_runner` also honours
    `timeout_seconds` via plain `subprocess.run(timeout=...)`, so this same assertion
    would also have passed before SEC-47 (verified directly: reverting
    `run_verification`'s default runner to `_subprocess_runner` while leaving this test
    unchanged still passes, in well under the 60s budget below). The next test,
    `test_run_verification_default_runner_actually_invokes_jail_run`, is the one that
    specifically discriminates "routed through `Jail`" from "any reasonable per-command
    timeout, however implemented."
    """
    source = tmp_path / "hangs_forever"
    source.mkdir()
    (source / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\n"
        "project(hangs C)\n"
        "add_custom_command(OUTPUT stamp COMMAND sleep 300 COMMAND touch stamp)\n"
        "add_custom_target(hangs ALL DEPENDS stamp)\n"
    )

    def _git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=source, check=True, capture_output=True, text=True)

    _git("init", "-q")
    _git("-c", "user.email=t@example.com", "-c", "user.name=t", "add", "-A")
    _git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "baseline")

    cmakelists = source / "CMakeLists.txt"
    cmakelists.write_text(cmakelists.read_text() + "# a no-op comment, just to have a diff\n")
    diff = subprocess.run(
        ["git", "diff"], cwd=source, check=True, capture_output=True, text=True
    ).stdout
    assert diff, "expected a non-empty diff for the injected CMakeLists.txt change"
    _git("checkout", "--", "CMakeLists.txt")

    started = time.monotonic()
    gates = run_verification(
        source,
        diff,
        tmp_path / "no-reproducer-for-this-fixture",
        VerificationBaseline(timeout_seconds=3),
    )
    elapsed = time.monotonic() - started

    # Generous relative to the 3-second policy (kill grace + the detached-descendant
    # sweep add real but bounded overhead) and tiny relative to the 300-second sleep
    # a missing/bypassed Jail would have actually waited out.
    assert elapsed < 60, (
        f"run_verification took {elapsed:.1f}s against a build that sleeps 300s; "
        "some timeout mechanism should have stopped it within seconds"
    )
    assert gates.compile.status is GateStatus.FAIL


@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake not installed")
@pytest.mark.skipif(shutil.which("ctest") is None, reason="ctest not installed")
@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_run_verification_default_runner_actually_invokes_jail_run(monkeypatch, tmp_path):
    """The test that actually discriminates "routed through `Jail`" from "any runner
    that happens to honour a timeout" — spies on the real `Jail.run` (still calling
    through to it, so the genuine method runs) and asserts it is the thing that
    executes every command in a real, unmodified `run_verification` call (no injected
    `runner=`) against a real (if trivial) CMake target: `git apply`, `cmake` configure,
    `cmake --build`, `ctest`.
    """
    source = tmp_path / "trivial_target"
    source.mkdir()
    (source / "main.c").write_text("int main(void) { return 0; }\n")
    (source / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\n"
        "project(trivial C)\n"
        "add_executable(trivial main.c)\n"
        "enable_testing()\n"
        "add_test(NAME trivial_test COMMAND trivial)\n"
    )

    def _git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=source, check=True, capture_output=True, text=True)

    _git("init", "-q")
    _git("-c", "user.email=t@example.com", "-c", "user.name=t", "add", "-A")
    _git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "baseline")

    cmakelists = source / "CMakeLists.txt"
    cmakelists.write_text(cmakelists.read_text() + "# a no-op comment, just to have a diff\n")
    diff = subprocess.run(
        ["git", "diff"], cwd=source, check=True, capture_output=True, text=True
    ).stdout
    assert diff, "expected a non-empty diff for the injected CMakeLists.txt change"
    _git("checkout", "--", "CMakeLists.txt")

    real_run = verification.Jail.run
    calls: list[tuple[str, ...]] = []

    def _spy_run(self, argv, **kwargs):
        calls.append(tuple(argv))
        return real_run(self, argv, **kwargs)

    monkeypatch.setattr(verification.Jail, "run", _spy_run)

    gates = run_verification(
        source, diff, tmp_path / "no-reproducer-for-this-fixture", VerificationBaseline()
    )

    assert gates.compile.status is GateStatus.PASS, gates.compile.detail
    assert len(calls) >= 4, f"expected at least 4 Jail.run() calls, got {calls}"
    first_args = [call[0] for call in calls]
    assert "git" in first_args
    assert first_args.count("cmake") >= 2  # configure, then --build
    assert "ctest" in first_args


# --------------------------------------------------------------------------------
# PR #175 functional re-review (commit 8ffdccd) — `JailPolicy.memory_bytes` must be sized
# off `adapters.cpp.variants.MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS` whenever
# `VerificationBaseline.configure_args` turns a sanitizer on, mirroring
# `workers/replay/run.py`'s identical sizing decision — otherwise every ASan-instrumented
# process aborts at startup on real Linux (RLIMIT_AS is unenforced on Darwin, which is why
# the original SEC-47 fix's own tests passed locally without catching this).
# --------------------------------------------------------------------------------


def test_sanitizers_enabled_detects_pktcfgs_default_configure_args():
    """`VerificationBaseline`'s own default is the exact case this bug hit: pktcfg's
    `-DPKTCFG_SANITIZE=ON` cache entry, not a raw `-fsanitize=` compiler flag."""
    assert _sanitizers_enabled(VerificationBaseline().configure_args) is True


@pytest.mark.parametrize(
    "configure_args",
    [
        (),
        ("-DPKTCFG_WERROR=ON",),
        ("-DPKTCFG_SANITIZE=OFF",),
        ("-DPKTCFG_SANITIZE=0",),
        ("-DSOME_OTHER_FLAG=ON",),
    ],
)
def test_sanitizers_enabled_is_false_when_no_sanitizer_is_turned_on(configure_args):
    assert _sanitizers_enabled(configure_args) is False


@pytest.mark.parametrize(
    "configure_args",
    [
        ("-DPKTCFG_SANITIZE=ON",),
        ("-DPKTCFG_SANITIZE=on",),
        ("-DPKTCFG_SANITIZE=TRUE",),
        ("-DPKTCFG_SANITIZE=1",),
        ("-DCMAKE_C_FLAGS=-fsanitize=address,undefined",),
        ("-DSOME_OTHER_FLAG=ON", "-DPKTCFG_SANITIZE=ON"),
    ],
)
def test_sanitizers_enabled_recognises_every_documented_spelling(configure_args):
    assert _sanitizers_enabled(configure_args) is True


def test_run_verification_sizes_jail_memory_for_the_default_sanitizer_configure_args(
    monkeypatch,
):
    """The regression itself, at the unit level: `run_verification`'s default
    `VerificationBaseline` turns sanitizers on, so the one `Jail` it opens must be sized
    from `MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS` — not `JailPolicy`'s generic 2 GiB
    default, which is what the original SEC-47 fix left in place. Spies on the real
    `Jail.create` (still calling through), so this exercises the genuine policy object
    `run_verification` actually builds.
    """
    created_policies: list[JailPolicy] = []
    real_create = verification.Jail.create

    def _spy_create(policy=None, **kwargs):
        created_policies.append(policy)
        return real_create(policy, **kwargs)

    monkeypatch.setattr(verification.Jail, "create", staticmethod(_spy_create))

    gates = run_verification(
        DEMO_REPOSITORY, CANDIDATE_A.read_text(), CRASH, BASELINE, runner=ScriptedRunner()
    )

    assert derive_verdict(gates) is Verdict.VERIFIED
    assert len(created_policies) == 1
    assert created_policies[0].memory_bytes == MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS


def test_run_verification_leaves_jail_memory_at_the_generic_default_without_sanitizers(
    monkeypatch,
):
    """The inverse case, so the fix is proven scoped rather than "always maximal": a
    `VerificationBaseline` whose `configure_args` do not enable a sanitizer must not pay
    the (deliberately enormous, RLIMIT_AS-workaround-only) sanitizer memory floor."""
    created_policies: list[JailPolicy] = []
    real_create = verification.Jail.create

    def _spy_create(policy=None, **kwargs):
        created_policies.append(policy)
        return real_create(policy, **kwargs)

    monkeypatch.setattr(verification.Jail, "create", staticmethod(_spy_create))

    no_sanitizer_baseline = VerificationBaseline(
        configure_args=("-DPKTCFG_WERROR=ON",), expected_regression_tests=8
    )
    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        no_sanitizer_baseline,
        runner=ScriptedRunner(),
    )

    assert derive_verdict(gates) is Verdict.VERIFIED
    assert len(created_policies) == 1
    assert created_policies[0].memory_bytes == JailPolicy().memory_bytes
    assert created_policies[0].memory_bytes != MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS


@pytest.mark.skipif(
    sys.platform == "darwin",
    reason="RLIMIT_AS is not enforced on Darwin at all, so neither the original bug nor "
    "this fix can be observed here — Linux-only by construction, the same way "
    "adapters/cpp/tests/test_sanitizer.py::test_the_jails_default_memory_policy_cannot_run_asan "
    "is. Confirmed reproducing (and fixed) in a ubuntu:24.04 Docker container while "
    "diagnosing PR #175's functional re-review finding.",
)
@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake not installed")
@pytest.mark.skipif(shutil.which("ctest") is None, reason="ctest not installed")
@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
@pytest.mark.slow
def test_real_verify_achieves_verified_under_sanitizers_on_linux():
    """The end-to-end proof the functional re-review asked for: a real `cmake`/`ctest`
    build of pktcfg with sanitizers on (`VerificationBaseline`'s actual default), through
    the real, unmodified `run_verification` — no `ScriptedRunner` — against the real
    correct-fix candidate diff, must reach `VERIFIED` on real Linux. Before this fix, this
    failed every gate on Linux (`AddressSanitizer failed to allocate ...`,
    `ReserveShadowMemoryRange failed`) while looking like an ordinary `REJECTED` verdict —
    the exact silent failure mode the functional re-review flagged.
    """
    gates = run_verification(DEMO_REPOSITORY, CANDIDATE_A.read_text(), CRASH, BASELINE)

    assert derive_verdict(gates) is Verdict.VERIFIED, [
        (g.name, g.status, g.detail) for g in gates.results()
    ]


@pytest.mark.skipif(
    sys.platform == "darwin",
    reason="RLIMIT_AS is not enforced on Darwin at all — see the other Linux-only test "
    "above for the full explanation.",
)
@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake not installed")
@pytest.mark.skipif(shutil.which("ctest") is None, reason="ctest not installed")
@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
@pytest.mark.slow
def test_real_verify_without_sanitizer_memory_sizing_fails_every_gate_on_linux(monkeypatch):
    """Pins the actual regression the functional re-review found, reproduced through the
    real pipeline rather than only inferred: force `_sanitizers_enabled` to report `False`
    (simulating the original SEC-47 fix's unconditional `JailPolicy(wall_clock_seconds=...)`
    with no `memory_bytes` override) while `VerificationBaseline`'s real default still
    builds with `-DPKTCFG_SANITIZE=ON`. Every gate must come back FAIL — not an exception,
    not a `NOT_RUN` — which is exactly why this silently read as a normal `REJECTED`
    verdict in production rather than an obvious infra error.
    """
    monkeypatch.setattr(verification, "_sanitizers_enabled", lambda configure_args: False)

    gates = run_verification(DEMO_REPOSITORY, CANDIDATE_A.read_text(), CRASH, BASELINE)

    assert gates.compile.status is GateStatus.PASS, (
        "configure/build themselves do not need the shadow-memory reservation — only "
        "running the instrumented binaries does"
    )
    assert gates.reproducer_eliminated.status is GateStatus.FAIL
    assert gates.regression_preserved.status is GateStatus.FAIL
    assert derive_verdict(gates) is Verdict.REJECTED, (
        "this is the dangerous part: the tooling never actually ran, but the verdict "
        "reads as an ordinary, legitimate rejection"
    )


# --------------------------------------------------------------------------------
# SEC-45 — GateResult.detail never carries raw subprocess output, success or failure.
# --------------------------------------------------------------------------------


_FAKE_SECRET = "DATABASE_URL=postgresql://real-user:should-never-appear-in-detail@db:5432/prod"


def test_gate_detail_never_contains_raw_output_on_compile_failure():
    runner = ScriptedRunner(
        build=CommandResult(
            argv=("cmake", "--build"),
            returncode=2,
            stdout="",
            stderr=f"CMake Error: build failed\n{_FAKE_SECRET}\n",
        )
    )

    gates = run_verification(
        DEMO_REPOSITORY, CANDIDATE_A.read_text(), CRASH, BASELINE, runner=runner
    )

    assert gates.compile.status is GateStatus.FAIL
    for gate in gates.results():
        assert _FAKE_SECRET not in gate.detail
        assert "should-never-appear-in-detail" not in gate.detail


def test_gate_detail_never_contains_raw_output_on_reproducer_failure():
    runner = ScriptedRunner(
        replay=CommandResult(
            argv=("pktcfg_replay",),
            returncode=1,
            stderr=f"AddressSanitizer: heap-buffer-overflow\n{_FAKE_SECRET}\n",
        )
    )

    gates = run_verification(
        DEMO_REPOSITORY, CANDIDATE_A.read_text(), CRASH, BASELINE, runner=runner
    )

    assert gates.reproducer_eliminated.status is GateStatus.FAIL
    for gate in gates.results():
        assert _FAKE_SECRET not in gate.detail
        assert "should-never-appear-in-detail" not in gate.detail


def test_gate_detail_never_contains_raw_output_on_regression_failure():
    runner = ScriptedRunner(
        regression=CommandResult(
            argv=("ctest",),
            returncode=8,
            stdout=f"88% tests passed, 1 tests failed out of 8\n{_FAKE_SECRET}\n",
        )
    )

    gates = run_verification(
        DEMO_REPOSITORY, CANDIDATE_A.read_text(), CRASH, BASELINE, runner=runner
    )

    assert gates.regression_preserved.status is GateStatus.FAIL
    # The structured signal (SEC-45's "extract just that", never the raw byte stream)
    # is still present and useful:
    assert "1 of 8 tests failed" in gates.regression_preserved.detail
    for gate in gates.results():
        assert _FAKE_SECRET not in gate.detail
        assert "should-never-appear-in-detail" not in gate.detail


def test_gate_detail_never_contains_raw_output_on_success():
    """Paranoia check: even a *passing* run's captured stdout/stderr must never reach
    `detail`, in case a future change starts threading `CommandResult` through `_pass`
    the way `_fail` already receives it."""
    runner = ScriptedRunner(
        build=CommandResult(argv=("cmake", "--build"), returncode=0, stdout=_FAKE_SECRET),
        replay=CommandResult(argv=("pktcfg_replay",), returncode=0, stdout=_FAKE_SECRET),
        regression=CommandResult(
            argv=("ctest",),
            returncode=0,
            stdout=f"100% tests passed, 0 tests failed out of 8\n{_FAKE_SECRET}\n",
        ),
    )

    gates = run_verification(
        DEMO_REPOSITORY, CANDIDATE_A.read_text(), CRASH, BASELINE, runner=runner
    )

    assert derive_verdict(gates) is Verdict.VERIFIED
    for gate in gates.results():
        assert _FAKE_SECRET not in gate.detail
        assert "should-never-appear-in-detail" not in gate.detail


class ScriptedRunner:
    def __init__(
        self,
        *,
        configure: CommandResult | None = None,
        build: CommandResult | None = None,
        replay: CommandResult | None = None,
        regression: CommandResult | None = None,
    ) -> None:
        self.configure = configure or CommandResult(argv=("cmake",), returncode=0)
        self.build = build or CommandResult(argv=("cmake", "--build"), returncode=0)
        self.replay = replay or CommandResult(argv=("pktcfg_replay",), returncode=0)
        self.regression = regression or CommandResult(
            argv=("ctest",),
            returncode=0,
            stdout="100% tests passed, 0 tests failed out of 8\n",
        )
        self.cwd_seen: list[Path] = []
        self.applied_diffs: list[str] = []

    def __call__(
        self,
        argv,
        cwd: Path,
        stdin: str | None,
        timeout: int,
    ) -> CommandResult:
        del timeout
        argv = tuple(argv)
        self.cwd_seen.append(cwd)

        if argv[:3] == ("git", "apply", "--whitespace=nowarn"):
            # SEC-47: the candidate diff arrives as a file path (argv[3]), never over
            # stdin — `Jail.run()` has no stdin channel, so `run_verification` writes
            # the diff to disk before calling `git apply <path>` regardless of which
            # runner is in use. `stdin` here is always `None`.
            assert stdin is None, "git apply should receive the diff as a file, not stdin"
            self.applied_diffs.append(Path(argv[3]).read_text())
            return CommandResult(argv=argv, returncode=0)

        if argv[:4] == ("cmake", "-S", ".", "-B"):
            return _with_argv(self.configure, argv)

        if argv[:2] == ("cmake", "--build"):
            result = _with_argv(self.build, argv)
            if result.ok:
                build_dir = cwd / argv[2]
                build_dir.mkdir(parents=True, exist_ok=True)
                replay_binary = build_dir / "pktcfg_replay"
                replay_binary.write_text("#!/bin/sh\nexit 0\n")
                replay_binary.chmod(0o755)
            return result

        if Path(argv[0]).name == "pktcfg_replay":
            return _with_argv(self.replay, argv)

        if argv[0] == "ctest":
            return _with_argv(self.regression, argv)

        raise AssertionError(f"unexpected command: {argv}")


def _with_argv(result: CommandResult, argv: tuple[str, ...]) -> CommandResult:
    return CommandResult(
        argv=argv,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
