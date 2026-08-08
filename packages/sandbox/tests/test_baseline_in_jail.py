"""The jail does the job it was split out of #15 to do: a build and a test run.

#81's whole justification is that the D3 gate — cold start to baseline with real ctest
counts on screen — needs a build and a test run, not container isolation. This is the
test that says whether that is true. It configures, builds and ctests the real demo
target inside the jail and reads the counts back out.

If this passes, the D3 gate is not blocked on #15. If it does not, the split was wrong.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.sandbox import Jail, JailPolicy, LimitKind

REPO_ROOT = Path(__file__).resolve().parents[3]
TARGET = REPO_ROOT / "demo" / "repositories" / "pktcfg"

pytestmark = [
    pytest.mark.skipif(not TARGET.is_dir(), reason="demo target not present"),
    pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake not installed"),
    pytest.mark.skipif(shutil.which("ctest") is None, reason="ctest not installed"),
]

CTEST_SUMMARY = re.compile(r"(\d+)% tests passed, (\d+) tests failed out of (\d+)")


def test_demo_target_configures_builds_and_tests_inside_the_jail() -> None:
    policy = JailPolicy(cpu_seconds=600, wall_clock_seconds=900)

    with Jail.create(policy) as jail:
        shutil.copytree(TARGET, jail.root / "src", symlinks=False)

        configure = jail.run(
            ["cmake", "-S", "src", "-B", "src/build", "-DCMAKE_BUILD_TYPE=Debug"],
        )
        assert configure.ok, f"configure failed:\n{configure.stderr[-2000:]}"

        build = jail.run(["cmake", "--build", "src/build", "-j", "2"])
        assert build.ok, f"build failed:\n{build.stderr[-2000:]}"

        tests = jail.run(["ctest", "--test-dir", "src/build"])
        assert tests.limit_hit is LimitKind.NONE, tests.summary()

        match = CTEST_SUMMARY.search(tests.stdout)
        assert match, f"could not read ctest counts from:\n{tests.stdout[-2000:]}"
        failed, total = int(match.group(2)), int(match.group(3))

        assert total == 8, f"pktcfg has 8 ctest cases, ctest reported {total}"
        assert failed == 0, f"{failed} of {total} baseline tests failed"

        # The counts the D3 gate puts on screen have to be real, and this is where they
        # come from. Measured resource usage travels with them.
        assert tests.cpu_seconds > 0
        assert build.peak_memory_mb > 0
        assert build.isolation_mode == "SUBPROCESS_JAIL"


def test_the_build_leaves_nothing_behind() -> None:
    """Cleanup has to remove a real build tree, not just an empty directory."""
    policy = JailPolicy(cpu_seconds=600, wall_clock_seconds=900)
    jail = Jail.create(policy)
    root = jail.root
    with jail:
        shutil.copytree(TARGET, jail.root / "src", symlinks=False)
        jail.run(["cmake", "-S", "src", "-B", "src/build", "-DCMAKE_BUILD_TYPE=Debug"])
        jail.run(["cmake", "--build", "src/build", "-j", "2"])
        assert (root / "src" / "build").is_dir()
    assert not root.exists(), "a populated build tree must still be cleaned up"
