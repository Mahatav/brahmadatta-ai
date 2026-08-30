"""Tests for `packages.sandbox.container_runner.ContainerJailRunner` (#181/SEC-57),
focused on #303: a caller that does NOT pre-resolve its `parent=` before
`ContainerJail.create()`/`ContainerJailRunner.create()` must still get correct
host-to-container path translation out of `_translate()`.

No container runtime is needed for anything in this file — `_translate()` is pure
string logic over `self._jail.root`, and `ContainerJail.create()` itself never shells
out to `docker` (only `run()` does).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from packages.sandbox.container import ContainerJailPolicy
from packages.sandbox.container_runner import ContainerJailRunner

#: `_translate`/`resolve` never actually start a container in this file, so any
#: non-empty reference satisfies `ContainerJailPolicy.__post_init__`'s "image is
#: required" check without needing a real, pullable image.
DUMMY_IMAGE = "pinned-build-toolchain@sha256:0000000000000000000000000000000000000000000000000000000000000000"


def _policy() -> ContainerJailPolicy:
    return ContainerJailPolicy(image=DUMMY_IMAGE, cpu_limit=1.0)


@pytest.fixture
def macos_style_symlinked_tmp(tmp_path, monkeypatch):
    """Reproduces, without needing to actually run on macOS, the exact mismatch #303
    describes: `tempfile.gettempdir()` (used whenever no `parent=` is passed) returns
    an UNRESOLVED path that is really a symlink to a canonical, resolved one — on
    macOS that's `/var/folders/...` -> `/private/var/folders/...`.

    Monkeypatches `tempfile.mkdtemp` as seen from `packages.sandbox.container` so
    that, whenever it is called the way a caller who does NOT pre-resolve its
    `parent=` calls it (i.e. `dir=None`), the directory is physically created under
    a "resolved" real directory but the path string handed back to the caller runs
    through a symlink pointing at that same directory — mirroring `/var/folders` vs
    `/private/var/folders` being the same inode tree under two different path
    spellings. Returns `(unresolved_base, resolved_base)`.
    """
    resolved_base = tmp_path / "private_var_folders"
    resolved_base.mkdir()
    unresolved_base = tmp_path / "var_folders"
    os.symlink(resolved_base, unresolved_base)

    real_mkdtemp = tempfile.mkdtemp

    def fake_mkdtemp(prefix: str = "", dir: str | None = None) -> str:
        if dir is not None:
            # A caller that DID pass its own `parent=` (already resolved, by
            # convention every real call site in this codebase follows) is not the
            # scenario under test here -- behave exactly like the real thing.
            return real_mkdtemp(prefix=prefix, dir=dir)
        # No `parent=` -> falls back to `tempfile.gettempdir()`-equivalent behaviour:
        # physically create the directory under the resolved/canonical location, but
        # hand back the path spelled through the unresolved symlink, exactly like
        # macOS's real `tempfile.gettempdir()` does.
        real_dir = real_mkdtemp(prefix=prefix, dir=str(resolved_base))
        name = os.path.basename(real_dir)
        return str(unresolved_base / name)

    monkeypatch.setattr(tempfile, "mkdtemp", fake_mkdtemp)
    return unresolved_base, resolved_base


def test_create_resolves_the_tempdir_even_when_the_caller_passes_no_parent(
    macos_style_symlinked_tmp,
):
    """#303's core fix: `ContainerJail.create()` (via `ContainerJailRunner.create()`)
    must resolve its own tempdir, not rely on every caller to have pre-resolved a
    `parent=` before calling it. This is the exact call shape #303 flags as unsafe --
    `run_variant`/`ContainerJailRunner` invoked directly with no `parent=` at all."""
    _unresolved_base, resolved_base = macos_style_symlinked_tmp

    with ContainerJailRunner.create(_policy()) as runner:
        # The stored root must be the canonical path, not the symlinked spelling
        # `tempfile.mkdtemp()` handed back -- otherwise every host path a caller
        # builds from `runner.root` after calling `.resolve()` on it (exactly what
        # `adapters/cpp/detect.py::detect()` does) silently stops matching
        # `_translate()`'s prefix check.
        assert str(runner.root).startswith(str(resolved_base))
        assert resolved_base in runner.root.parents or runner.root == resolved_base


def test_translate_matches_a_caller_supplied_path_that_was_independently_resolved(
    macos_style_symlinked_tmp,
):
    """The actual regression from #303: a value built the way
    `adapters/cpp/pipeline.py`/`detect.py` build one -- `Path(something_under_the_
    jail).resolve()` -- must still be recognised by `_translate()` as living under
    `self._jail.root` and rewritten to `/workspace/...`, even though the caller never
    passed an already-resolved `parent=` to `create()`.

    Before the #303 fix, `self._jail.root` stayed as the unresolved symlinked path
    (e.g. `/var/folders/T/brahmadatta-sandbox-xyz`) while a caller's independently
    `.resolve()`-d path came back as the canonical one (`/private/var/folders/T/
    brahmadatta-sandbox-xyz/source`) -- two different strings for the same directory,
    so the `startswith` prefix check in `_translate` silently failed and the host
    path was passed into the container untranslated, producing exactly the reported
    `CMake Error: source directory does not exist`.
    """
    unresolved_base, _resolved_base = macos_style_symlinked_tmp

    with ContainerJailRunner.create(_policy()) as runner:
        (runner.root / "source").mkdir()

        # Mirror `detect()`: an independent `.resolve()` call on a path built from
        # the ORIGINAL (unresolved, symlinked) spelling the caller might reasonably
        # have started from -- not from `runner.root`, which is already resolved
        # post-fix and would trivially match.
        mkdtemp_name = runner.root.name
        caller_built_path = unresolved_base / mkdtemp_name / "source"
        caller_resolved_path = str(caller_built_path.resolve())

        translated = runner._translate(caller_resolved_path)

        assert translated == "/workspace/source", (
            f"expected the caller's resolved path to be recognised as living under "
            f"the jail root and rewritten to /workspace/source; got {translated!r} "
            f"instead -- this is #303's exact untranslated-host-path bug"
        )


def test_translate_still_passes_through_an_unrelated_host_path_unchanged(
    macos_style_symlinked_tmp,
):
    """Sanity check on the same fixture: a path genuinely outside the jail (a bare
    command name, or an external artifact the caller was responsible for staging
    under `self.root` first) must still be returned unchanged -- the fix must not
    turn `_translate` into something that rewrites everything."""
    with ContainerJailRunner.create(_policy()) as runner:
        assert runner._translate("cmake") == "cmake"
        assert runner._translate("/some/unrelated/host/path") == "/some/unrelated/host/path"
