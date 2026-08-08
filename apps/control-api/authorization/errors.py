"""Refusals raised by the authorization gate.

Every one is a `ContractError`, so `api.errors` renders it into the one error envelope
with the right status and an `ErrorCode` from the frozen vocabulary — no translation
table in the router, and no status this API does not already document in
`api.errors.ERROR_RESPONSES` (400, 401, 403, 404, 409, 422, 501).

No new `ErrorCode` member is introduced here. `ErrorCode` is a `StrEnum` consumed by the
generated TypeScript client, so adding a member is a contract change and a frontend
rebuild (D-030, and DR-BE-1 on #110 made the same call). The specifics travel in
`details`.
"""

from __future__ import annotations

from contracts.enums import ErrorCode
from contracts.errors import ContractError


class MissionNotFoundError(ContractError):
    """No mission with that id. 404 before anything else is read or written."""

    code = ErrorCode.NOT_FOUND
    http_status = 404
    default_message = "No mission with that id."


class AuthorizationScopeError(ContractError):
    """The declaration does not cover the repository the mission will run against.

    The mission row owns `repository_ref`; the operator's declaration names one too. If
    they differ, the record attests to a repository that no stage is going to touch,
    which is an audit trail that reads as valid and proves nothing. Refused with the
    same status and code as a missing record, because it is the same failure: no
    authority covers this work.
    """

    code = ErrorCode.INVALID_AUTHORIZATION
    http_status = 403
    default_message = (
        "The authorization declares a different repository than the mission targets."
    )


class SnapshotAlreadyRecordedError(ContractError):
    """A mission has exactly one snapshot, and it is write-once.

    Re-posting the *same* digest is an idempotent replay and returns the existing
    record. A *different* digest is an attempt to move the ground under an
    authorization that has already been granted, and is refused.
    """

    code = ErrorCode.CONFLICT
    http_status = 409
    default_message = "This mission already has a snapshot with a different digest."


class SnapshotDigestMismatchError(ContractError):
    """The archive in the store does not hash to the digest the caller asserted."""

    code = ErrorCode.CONFLICT
    http_status = 409
    default_message = (
        "The stored archive does not hash to the digest supplied with the request."
    )


class SnapshotArtifactUnavailableError(ContractError):
    """There are no bytes to hash.

    Fail closed. A snapshot record whose digest was never computed from an archive is
    a hash of nothing, and every downstream claim would reference it.
    """

    code = ErrorCode.CONFLICT
    http_status = 409
    default_message = (
        "No archive for that digest in the artifact store. Ingest the archive before "
        "recording the snapshot."
    )


class SnapshotArtifactClaimedError(ContractError):
    """The digest is already registered in the artifact index to another mission."""

    code = ErrorCode.CONFLICT
    http_status = 409
    default_message = (
        "That archive digest is registered to a different mission in the artifact "
        "index."
    )


class UnreadableArchiveError(ContractError):
    """The archive is not an enumerable tar or zip, or is larger than the ceiling.

    `SnapshotRecord.file_count` and `bytes_total` are counts in an evidence bundle. An
    archive whose members cannot be enumerated has no honest value for either, and
    `0` would be a fabricated one.
    """

    code = ErrorCode.UNSUPPORTED_REPOSITORY
    http_status = 422
    default_message = "The snapshot archive could not be read as a tar or zip archive."


class RepositoryOutOfScopeError(ContractError):
    """`repository_ref` does not resolve to a path inside the allowlisted source root.

    Refused before any byte of it is read. This is the filesystem half of the safety
    boundary: authorized repositories and isolated environments only — a mission
    cannot point itself at an arbitrary path on the host and have the control API
    read it.

    SEC-28 (round-4 security review). This is raised from `_resolve_repository_ref`,
    which only ever runs *after* `authorization.guard.require_active_authorization`
    has already confirmed an active, unrevoked, unexpired authorization covers this
    stage — so by the time a caller can hit this error, the authorization is not in
    question. `ErrorCode.INVALID_AUTHORIZATION` told the operator the opposite of what
    had just been established. `UNSUPPORTED_REPOSITORY` is what `UnreadableArchiveError`
    two classes below already uses for the identical class of failure — the source
    material can't be read, not the authorization — and this now matches it. `403` is
    kept rather than following that sibling to `422`: this is a scope/permission
    refusal (the deployment's allowlist does not cover this reference at all) rather
    than a content-validity one (the archive was read and could not be parsed), and
    403 is the better fit for "you may not point this endpoint here," independent of
    the code fix above.
    """

    code = ErrorCode.UNSUPPORTED_REPOSITORY
    http_status = 403
    default_message = (
        "The repository reference does not resolve to a repository this deployment "
        "is configured to read."
    )


class InvalidOperatorInputError(ContractError):
    """Boundary validation that pydantic's length limits do not cover.

    `min_length=20` on a statement is satisfied by twenty spaces; `min_length=1` on
    `granted_by` is satisfied by one. Neither is an accountable human.
    """

    code = ErrorCode.VALIDATION_ERROR
    http_status = 422
    default_message = "Request failed validation."
