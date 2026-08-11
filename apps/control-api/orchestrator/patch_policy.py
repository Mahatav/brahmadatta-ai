"""Deterministic patch policy over unified diffs (#37).

The model gateway may propose text, but this module is the first gate that decides
whether a candidate is even eligible for verification. It reads only the diff and the
mission policy, so provenance, confidence and rationale cannot influence the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase

from contracts.enums import PatchPolicyStatus
from contracts.schemas.missions import PatchPolicy


@dataclass(frozen=True)
class PatchPolicyDecision:
    status: PatchPolicyStatus
    files_changed: int
    lines_changed: int
    changed_paths: tuple[str, ...]
    detail: str

    @property
    def accepted(self) -> bool:
        return self.status is PatchPolicyStatus.ACCEPTED


def evaluate_patch_policy(diff: str, policy: PatchPolicy) -> PatchPolicyDecision:
    """Return the policy decision and the measured diff shape.

    An empty `allowed_paths` list is intentionally strict: if a mission wants patches to
    be considered, it records the allowlist in mission policy first. That gives the
    evidence record the limits that were in force when the candidate was accepted or
    rejected.
    """
    parsed = _parse_unified_diff(diff)
    if parsed is None:
        return PatchPolicyDecision(
            status=PatchPolicyStatus.REJECTED_MALFORMED_DIFF,
            files_changed=0,
            lines_changed=0,
            changed_paths=(),
            detail=_detail(
                "malformed unified diff",
                policy,
                files_changed=0,
                lines_changed=0,
                changed_paths=(),
            ),
        )

    changed_paths, lines_changed = parsed
    files_changed = len(changed_paths)
    if files_changed > policy.max_files_changed:
        return PatchPolicyDecision(
            status=PatchPolicyStatus.REJECTED_TOO_MANY_FILES,
            files_changed=files_changed,
            lines_changed=lines_changed,
            changed_paths=changed_paths,
            detail=_detail(
                "too many files changed",
                policy,
                files_changed,
                lines_changed,
                changed_paths,
            ),
        )

    denied_paths = tuple(
        path for path in changed_paths if not _path_allowed(path, policy.allowed_paths)
    )
    if denied_paths:
        return PatchPolicyDecision(
            status=PatchPolicyStatus.REJECTED_PATH_NOT_ALLOWED,
            files_changed=files_changed,
            lines_changed=lines_changed,
            changed_paths=changed_paths,
            detail=_detail(
                f"path not allowed: {', '.join(denied_paths)}",
                policy,
                files_changed,
                lines_changed,
                changed_paths,
            ),
        )

    if lines_changed > policy.max_lines_changed:
        return PatchPolicyDecision(
            status=PatchPolicyStatus.REJECTED_TOO_MANY_LINES,
            files_changed=files_changed,
            lines_changed=lines_changed,
            changed_paths=changed_paths,
            detail=_detail(
                "too many changed lines",
                policy,
                files_changed,
                lines_changed,
                changed_paths,
            ),
        )

    return PatchPolicyDecision(
        status=PatchPolicyStatus.ACCEPTED,
        files_changed=files_changed,
        lines_changed=lines_changed,
        changed_paths=changed_paths,
        detail=_detail("accepted", policy, files_changed, lines_changed, changed_paths),
    )


def _parse_unified_diff(diff: str) -> tuple[tuple[str, ...], int] | None:
    paths: list[str] = []
    in_file = False
    saw_hunk = False
    lines_changed = 0

    for line in diff.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if (
                len(parts) != 4
                or not parts[2].startswith("a/")
                or not parts[3].startswith("b/")
            ):
                return None
            path = _normalize_path(parts[3][2:])
            if path is None:
                return None
            paths.append(path)
            in_file = True
            continue

        if line.startswith("@@ "):
            if not in_file:
                return None
            saw_hunk = True
            continue

        if not saw_hunk:
            continue

        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            lines_changed += 1

    if not paths or not saw_hunk:
        return None

    return tuple(dict.fromkeys(paths)), lines_changed


def _normalize_path(path: str) -> str | None:
    if not path or path == "/dev/null" or path.startswith("/") or "\x00" in path:
        return None
    segments = path.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        return None
    return path


def _path_allowed(path: str, allowed_paths: list[str]) -> bool:
    return any(fnmatchcase(path, pattern) for pattern in allowed_paths)


def _detail(
    reason: str,
    policy: PatchPolicy,
    files_changed: int,
    lines_changed: int,
    changed_paths: tuple[str, ...],
) -> str:
    allowed = ", ".join(policy.allowed_paths) if policy.allowed_paths else "<none>"
    paths = ", ".join(changed_paths) if changed_paths else "<none>"
    return (
        f"{reason}; files={files_changed}/{policy.max_files_changed}; "
        f"lines={lines_changed}/{policy.max_lines_changed}; paths={paths}; "
        f"allowed_paths={allowed}"
    )
