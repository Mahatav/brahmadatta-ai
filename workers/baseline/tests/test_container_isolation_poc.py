"""#181/SEC-57 proof-of-concept: BASELINE running a target's own (potentially
adversarial) CTest suite inside `packages.sandbox.jail.Jail` (the subprocess-only
jail, no network/filesystem isolation from the host — see that module's own opening
warning) versus inside `packages.sandbox.container.ContainerJail` via `workers.
baseline.run.run_baseline_stage`'s new `container_policy=` parameter.

This is the PoC the issue itself asks for: inject a CTest case into a real copy of
`demo/repositories/pktcfg` that attempts (a) a filesystem read of a file outside the
jail root and (b) an outbound TCP connection, and show that BOTH succeed under the
pre-#181 (subprocess-`Jail`-only) code path and BOTH now fail once `run_baseline_stage`
is given a `container_policy` — the exact isolation gap #181/SEC-57 names, closed for
real, not asserted.

Builds a real `brahmadatta-build-toolchain` image from `infrastructure/compose/images/
build-toolchain.Dockerfile` and runs a real `docker run --network none --cap-drop ALL
--read-only ...` container — skipped loudly, never silently, when `docker` is not on
`PATH` (this module's own `pytestmark`), the same standing rule `packages/sandbox/
tests/test_container_jail.py`'s header states for every test that actually starts a
container.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from adapters.cpp.ctest_report import parse_ctest_junit
from packages.sandbox.container import ContainerJailPolicy
from workers.baseline.run import run_baseline_stage

REPO_ROOT = Path(__file__).resolve().parents[3]
PKTCFG_SOURCE = REPO_ROOT / "demo" / "repositories" / "pktcfg"
DOCKERFILE = REPO_ROOT / "infrastructure" / "compose" / "images" / "build-toolchain.Dockerfile"
BUILD_CONTEXT = DOCKERFILE.parent

HAS_DOCKER = shutil.which("docker") is not None

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not PKTCFG_SOURCE.is_dir() or shutil.which("cmake") is None or shutil.which("ctest") is None,
        reason="demo/repositories/pktcfg or the CMake toolchain is not available in this checkout",
    ),
    pytest.mark.skipif(not HAS_DOCKER, reason="docker is not on PATH"),
]

#: A CTest case injected into the copied source, appended to its `CMakeLists.txt`
#: (which already calls `enable_testing()` well before this point in the file — see
#: `demo/repositories/pktcfg/CMakeLists.txt`). Deliberately two independent probes:
#:
#: * `sec57_poc_filesystem_escape` reads a marker file this test module writes
#:   OUTSIDE any jail root (a fresh `tempfile.mkdtemp()`, unrelated to
#:   `workspace_root`/the copied source) — `cat`ing it and exiting 0 only if the read
#:   actually returned the expected marker bytes, not merely "some file existed".
#: * `sec57_poc_network_egress` attempts a raw TCP connect to a public DNS resolver
#:   using bash's `/dev/tcp` pseudo-device, with a short `timeout` so a
#:   `--network none` container fails fast (`connect: Network is unreachable`) rather
#:   than hanging for the connect timeout.
#:
#: Both are appended as plain text onto a fresh copy of pktcfg's own `CMakeLists.txt`
#: per test run — never onto the tracked fixture in `demo/repositories/pktcfg` itself.
_POC_CMAKE_SNIPPET = """
add_test(NAME sec57_poc_filesystem_escape
         COMMAND bash -c "test \\"$(cat '{marker_path}' 2>/dev/null)\\" = '{marker_contents}'")
add_test(NAME sec57_poc_network_egress
         COMMAND bash -c "timeout 3 bash -c 'exec 3<>/dev/tcp/8.8.8.8/53' 2>/dev/null")
"""

_MARKER_CONTENTS = "sec57-outside-the-jail-root"


@pytest.fixture(scope="module")
def build_toolchain_image() -> str:
    """Build `build-toolchain.Dockerfile` and resolve a real, pinned `name@sha256:...`
    reference — `require_pinned` (`adapters/cpp/toolchain.py`) refuses anything else,
    and this PoC exists specifically to prove the container path's real isolation, not
    to bypass its own pinning requirement with a floating tag.
    """
    tag = "brahmadatta-build-toolchain:local"
    # Skip rebuilding if this exact tag is already present — `docker build` re-checks
    # the base image's registry manifest even when every layer is already cached
    # locally, which this session measured taking well over a minute against a
    # throttled/shared registry connection. A test suite re-running this fixture on
    # every invocation should not pay that cost when nothing about the Dockerfile has
    # changed since the image was last built.
    existing = subprocess.run(
        ["docker", "image", "inspect", tag],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if existing.returncode != 0:
        subprocess.run(
            ["docker", "build", "-f", str(DOCKERFILE), "-t", tag, str(BUILD_CONTEXT)],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
    inspected = subprocess.run(
        ["docker", "inspect", "--format", "{{index .RepoDigests 0}}", tag],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    digest = inspected.stdout.strip()
    if not digest or "@sha256:" not in digest:
        pytest.skip(
            "this docker daemon's image store does not expose a local RepoDigest for "
            "a freshly built image (classic graphdriver storage, no registry configured "
            "for this test) — see infrastructure/scripts/build-baseline-verify-image.sh"
        )
    return digest


@pytest.fixture
def poc_source(tmp_path: Path) -> tuple[Path, Path]:
    """A copy of pktcfg with the two SEC-57 probes appended to its `CMakeLists.txt`.

    The marker file the filesystem-escape probe targets is written to a directory
    `tempfile`-allocates OUTSIDE `tmp_path` entirely (system default tmp root, not this
    test's own `tmp_path` tree) — `workspace_root` for both `run_baseline_stage` calls
    below is `tmp_path / "workspace-*"`, so this file is guaranteed to be outside any
    jail root either backend creates, exactly like an operator secret sitting anywhere
    else on the host would be.
    """
    import tempfile

    dest = tmp_path / "pktcfg-sec57-poc"
    shutil.copytree(PKTCFG_SOURCE, dest)
    cmakelists = dest / "CMakeLists.txt"
    marker_dir = Path(tempfile.mkdtemp(prefix="brahmadatta-sec57-outside-"))
    marker_path = marker_dir / "secret.txt"
    marker_path.write_text(_MARKER_CONTENTS)
    cmakelists.write_text(
        cmakelists.read_text()
        + _POC_CMAKE_SNIPPET.format(marker_path=marker_path, marker_contents=_MARKER_CONTENTS)
    )
    return dest, marker_dir


def _poc_test_statuses(log_ref: str | None) -> dict[str, str]:
    assert log_ref is not None, "run_baseline_stage produced no durable JUnit copy to read"
    summary = parse_ctest_junit(Path(log_ref))
    return {t.name: t.status for t in summary.tests}


class TestBeforeTheFixSubprocessJailDoesNotContain:
    """The gap #181/SEC-57 names: `packages.sandbox.jail.Jail` shares the host's
    filesystem and network, so a target's own CTest suite can read outside the jail
    root and reach the network — exactly what a hostile `CMakeLists.txt`/CTest
    configuration would do, and exactly what BASELINE ran, unchanged, before this PR.
    """

    def test_filesystem_escape_and_network_egress_both_succeed(
        self, poc_source: tuple[Path, Path], tmp_path: Path
    ) -> None:
        source, marker_dir = poc_source
        try:
            outcome = run_baseline_stage(
                "mission-sec57-poc-before", source, tmp_path / "workspace-jail"
            )
            statuses = _poc_test_statuses(outcome.log_ref)
            assert statuses["sec57_poc_filesystem_escape"] == "passed", (
                "expected the subprocess Jail to let a CTest case read a file outside "
                f"the jail root (the pre-#181 gap); got: {statuses}"
            )
            assert statuses["sec57_poc_network_egress"] == "passed", (
                "expected the subprocess Jail to let a CTest case reach the network "
                f"(the pre-#181 gap); got: {statuses}"
            )
            # The real demo target itself is unaffected by either probe.
            assert outcome.configure_ok and outcome.build_ok
        finally:
            shutil.rmtree(marker_dir, ignore_errors=True)


class TestAfterTheFixContainerJailContains:
    """The fix: the identical source, the identical two probes, run through
    `run_baseline_stage(..., container_policy=...)` instead — `ContainerJail`'s
    `--network none` / single bind-mounted `/workspace` (D-024) means neither probe
    has anything to reach.
    """

    def test_filesystem_escape_and_network_egress_both_fail(
        self, poc_source: tuple[Path, Path], tmp_path: Path, build_toolchain_image: str
    ) -> None:
        source, marker_dir = poc_source
        policy = ContainerJailPolicy(image=build_toolchain_image, wall_clock_seconds=300)
        try:
            outcome = run_baseline_stage(
                "mission-sec57-poc-after",
                source,
                tmp_path / "workspace-container",
                container_policy=policy,
            )
            statuses = _poc_test_statuses(outcome.log_ref)
            assert statuses["sec57_poc_filesystem_escape"] == "failed", (
                "expected ContainerJail's single bind mount to make the marker file "
                f"outside the jail root unreachable; got: {statuses}"
            )
            assert statuses["sec57_poc_network_egress"] == "failed", (
                "expected ContainerJail's --network none to block the TCP connect; "
                f"got: {statuses}"
            )
            # The real demo target itself is STILL unaffected by either probe --
            # this is the regression half of the PoC, not just the isolation half.
            assert outcome.configure_ok and outcome.build_ok
            assert outcome.tests_passed == 8  # pktcfg's own 8 tests, unaffected
            assert outcome.isolation_mode == "CONTAINER_NO_NETWORK"
        finally:
            shutil.rmtree(marker_dir, ignore_errors=True)
