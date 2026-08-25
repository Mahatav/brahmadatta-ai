"""Failure types for the Semgrep adapter, and its own `require_pinned`.

`require_pinned` mirrors `adapters.cpp.toolchain.require_pinned` byte-for-byte in
behaviour (refuse anything but `name@sha256:<64 hex>`) but is a small, separate copy
rather than a cross-import. Two reasons, not just convenience:

1. `adapters/cpp/toolchain.py` is compiler-toolchain-engineer-owned territory built
   for the C/C++ build/fuzz path specifically (`ToolchainRecord`'s own fields —
   `compiler_id`, `generator` — are meaningless for a tool that never invokes a
   compiler). Importing a semgrep-adapter dependency into it, or importing it into
   here, creates a coupling that runs semantically backwards: Semgrep scans C/C++
   *targets*, it is not part of the C/C++ toolchain itself.
2. The function this mirrors is eleven lines with no C-specific logic in it at all
   (see `adapters/cpp/toolchain.py::require_pinned`'s own body) — small enough that a
   second, independently-reviewable copy costs less than the cross-package edge
   would, and any future drift between the two copies is visible in a diff, not
   hidden behind a shared import neither owner fully controls.
"""

from __future__ import annotations

import re

__all__ = ["SemgrepAdapterError", "ToolchainError", "UnpinnedToolchain", "require_pinned"]

#: A digest is `sha256:` plus 64 lowercase hex characters. Anything else — `:latest`,
#: `:local`, a bare name, a semver tag — is mutable and can be repointed at new code
#: without a single change on our side. Identical pattern to
#: `adapters.cpp.toolchain._DIGEST`.
_DIGEST = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")


class SemgrepAdapterError(Exception):
    """Base for everything this package raises deliberately."""


class ToolchainError(SemgrepAdapterError):
    """A required tool is missing, or its version could not be established, or the
    vendored ruleset directory this adapter was pointed at does not exist."""


class UnpinnedToolchain(SemgrepAdapterError):
    """A container image was named by a mutable tag rather than a digest."""


def require_pinned(image_reference: str | None) -> str:
    """Return `image_reference` if it names a digest; raise otherwise.

    See `adapters.cpp.toolchain.require_pinned` — same contract, same reasoning
    (`SANDBOX_ANALYZE_IMAGE` must be pinned the same way `SANDBOX_FUZZ_IMAGE` is).
    """
    if not image_reference:
        raise UnpinnedToolchain(
            "no container image was given. SANDBOX_ANALYZE_IMAGE has no safe default "
            "— see .env.example."
        )
    if not _DIGEST.match(image_reference):
        raise UnpinnedToolchain(
            f"image reference is not pinned to a digest: {image_reference!r}\n"
            "A tag is mutable and can be repointed at new code with no change on our "
            "side. Use name@sha256:<64 hex>."
        )
    return image_reference
