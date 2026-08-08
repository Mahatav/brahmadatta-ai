from __future__ import annotations

from pathlib import Path

import pytest

from adapters.cpp.errors import ToolchainError, UnpinnedToolchain
from adapters.cpp.jail import Jail
from adapters.cpp.pipeline import run_variant
from adapters.cpp.toolchain import probe_build_tools, read_compiler_identity, require_pinned
from adapters.cpp.variants import Variant


def test_probe_build_tools_returns_real_versions(tmp_path: Path) -> None:
    jail = Jail(tmp_path)
    tools = probe_build_tools(jail)
    names = {t.name for t in tools}
    assert names == {"cmake", "ctest"}
    for tool in tools:
        assert tool.version[0].isdigit(), f"{tool.name} version {tool.version!r} does not start with a digit"
        assert Path(tool.path).is_file()


def test_probe_build_tools_raises_on_missing_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Injected violation: ask for a tool that does not exist on PATH."""
    jail = Jail(tmp_path)
    with pytest.raises(ToolchainError, match="not found"):
        probe_build_tools(jail, names=("this-tool-does-not-exist-anywhere",))


def test_read_compiler_identity_matches_a_real_build(tmp_path: Path, pktcfg_source: Path) -> None:
    jail = Jail(tmp_path)
    result = run_variant(pktcfg_source, jail, Variant.BASELINE)
    compiler_id, compiler_version, compiler_path, generator = read_compiler_identity(result.build_dir)
    assert compiler_id in ("GNU", "Clang", "AppleClang")
    assert compiler_version[0].isdigit()
    assert Path(compiler_path).is_file() or compiler_path  # absolute path recorded
    assert generator


def test_read_compiler_identity_refuses_an_unconfigured_directory(tmp_path: Path) -> None:
    """Injected violation: a build directory that was never configured has no
    CMakeCCompiler.cmake — refuse rather than record 'unknown' as a fact."""
    empty_build = tmp_path / "build"
    empty_build.mkdir()
    with pytest.raises(ToolchainError):
        read_compiler_identity(empty_build)


@pytest.mark.parametrize(
    "reference",
    [
        None,
        "",
        "myimage:latest",
        "myimage:main",
        "myimage",
        "myimage@sha256:tooshort",
        "myimage@sha256:" + "g" * 64,  # not hex
    ],
)
def test_a_floating_or_malformed_reference_is_rejected(reference: str | None) -> None:
    """Injected violation, one per case: every shape of 'not actually pinned' must raise."""
    with pytest.raises(UnpinnedToolchain):
        require_pinned(reference)


def test_a_real_digest_is_accepted() -> None:
    digest = "myimage@sha256:" + "a" * 64
    assert require_pinned(digest) == digest
