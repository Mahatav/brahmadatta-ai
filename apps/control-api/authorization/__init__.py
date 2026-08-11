"""The authorization gate (#18, P0-1).

Everything the product claims downstream — every finding, every patch, every verdict —
is bound to a mission that an operator authorized and to the snapshot digest recorded
here. If this gate is bypassable, nothing after it means anything.

Four properties this package exists to hold, each with the test that demonstrates it
named beside it. Where a property is *intended* rather than demonstrated, it says so.

1. **Authorization is an explicit recorded operator action.** A row in `authorization`
   with a named human (`granted_by`), a server-set `granted_at`, and a hard expiry.
   Not a boolean, not a side effect of creating a mission.
   — `api/tests/test_authorize_snapshot.py::test_authorize_records_an_operator_identity_and_a_server_timestamp`

2. **The authorization covers the mission's own repository.** The declaration names a
   `repository_ref`; if it is not the one the mission will actually run against, the
   record would attest to a repository nobody is going to touch. Refused.
   — `::test_an_authorization_for_a_different_repository_is_refused`

3. **The snapshot digest is computed by the server over bytes the server read.** The
   caller's `archive_sha256` is an assertion, and it is checked against a re-hash of
   the archive in the content-addressed store. There is no path where a digest is
   recorded because a client said so.
   — `::test_a_digest_the_server_cannot_verify_is_refused`,
     `::test_a_swapped_archive_is_refused`

4. **No stage runs without an active record.** Enforced in
   `contracts.state_machine.assert_stage_can_run`, called from `guard.py` before any
   business logic in the endpoints, and again inside
   `orchestrator.transitions.transition` under the mission row lock.
   — `::test_snapshot_without_an_authorization_is_refused`,
     `::test_snapshot_with_an_expired_authorization_is_refused`,
     `::test_snapshot_with_a_revoked_authorization_is_refused`

   **Demonstrated at exactly one stage: `INGEST`, via `/snapshot`.** SEC-31 (round-4
   security review) caught this docstring citing two tests against `preflight`/`start`
   that do not exist, and cannot yet — `preflight_mission` and `start_mission`
   (`api/routers/missions.py`) are unconditional `NotImplementedYetError`; nothing in
   them reaches the authorization gate, the orchestrator, or any business logic at
   all. The property is *intended* to hold at every stage once each is wired to the
   orchestrator (#12), and is proven, today, only at the one stage that already is.
   Add each stage's own citation here as it lands — do not restore a citation for a
   test that has not been written.

## The shape of every write in here

One transaction, `SELECT … FOR UPDATE` on the mission row taken first, every id in the
request checked against that locked row before anything is written, and the state
transition performed by `orchestrator.transitions` inside the same transaction — so a
refused transition rolls the record back rather than leaving an orphan grant behind
(`::test_a_refused_authorize_leaves_no_authorization_row_behind`).

That ordering is deliberate. SEC-15 on PR #110 was not a forged record or a broken
convention: it was an id accepted from a request and never compared to the thing it was
supposed to belong to. `mission_id`, `repository_ref` (the authorization-declaration
check) and `archive_sha256`/`Artifact.sha256` are each checked against the locked
mission row or the mission-scoped record it produced — see `service.py`'s own
docstring for exactly where each check lives. `archive_ref` now follows the same
shape for SEC-30: `_materialize_source` resolves it under
`SNAPSHOT_STAGING_ROOT/<mission_id>`, using the locked mission row rather than a flat
global staging namespace. The upload endpoint is still future work, but its writer
must stage bytes into that same mission-owned directory for the reader to see them.
"""
