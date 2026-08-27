"""SEC-57 (#181) fast-follow condition (a): a repo/target allowlist for mission
ingestion, self-expiring after the 2026-08-20 competition demo date — quoting the
issue's own text verbatim, so read that expiry literally, not as a decoration:

    "enforce a repo/target allowlist in code, self-expiring after 2026-08-20 (the
    competition demo date)"

**This is already past its own expiry as of the date this module was written
(2026-08-26/27) — flag this loudly, do not let it read as live protection it is not.**
`is_enforced()` below returns `False` for any `now` after `EXPIRES`, which is every
date this module has ever run under so far. The condition's own reasoning, at the time
it was written (`.project/decisions.md`'s SEC-57 entry, T1's engineering-manager
review), was that BASELINE/VERIFY's lack of `ContainerJail` isolation was an accepted,
bounded-blast-radius gap *for the pre-demo competition scope only, against a
team-owned, trusted fixture (`pktcfg`)* — the allowlist's entire job was narrowing
"which targets can reach the still-unisolated pipeline" until that pipeline was fixed
for real. #181 (this same change) wires `ContainerJail` into both stages, which is the
actual fix the allowlist was standing in for — so by the time this file exists, the
gap it was scoped to narrow is closed by a different mechanism, for any deployment that
has `settings.SANDBOX_BUILD_IMAGE` configured (`workers/baseline/dispatch.py`,
`orchestrator/verify_dispatch.py`; both fall back to the un-isolated path when it is
not — see either module's own docstring).

Built anyway, literally as specified, for two reasons stated here rather than silently
assumed: (1) the fast-follow conditions were a condition of building #181 at all, not
optional once #181 is real work, per the issue's own text; (2) `ContainerJailPolicy`'s
own isolation is not a total guarantee (D-024's own accepted residual gaps — rootful
daemon, no seccomp/user-namespace — `workers/baseline/run.py::
CONTAINER_ISOLATION_UNPROTECTED_AGAINST`), and a deployment that has NOT yet configured
`SANDBOX_BUILD_IMAGE` is running the exact pre-#181 gap this allowlist was written
against, unmitigated by anything this PR adds except this file. Whether to convert this
into a permanent, non-expiring allowlist (rather than one whose own literal terms are
already inert) is exactly the call `.project/decisions.md`'s SEC-57 entry asks the CTO
to make explicitly — this module does not make that call unilaterally by quietly
removing the expiry.
"""

from __future__ import annotations

from datetime import date

from django.conf import settings
from django.utils import timezone

from authorization.errors import RepositoryOutOfScopeError

__all__ = ["DEFAULT_ALLOWED_TARGETS", "EXPIRES", "assert_target_allowed", "is_enforced"]

#: The AI Kavach competition demo date — CLAUDE.md's "Schedule" section and
#: `docs/04-development/37-branch-naming-guide.md`'s "Fixed MVP competition decisions"
#: both name this literally. Not read from settings/env: the issue's own text names
#: this exact date, and a config-driven expiry would let a deploy-time environment
#: variable silently extend (or shorten) a decision the issue itself pinned to a
#: specific day.
EXPIRES = date(2026, 8, 20)

#: Names, not paths — matches `authorization.service._repository_lookup_name`'s own
#: "the lookup key is a name, not a path" discipline; this is checked against exactly
#: the same `name` that function already resolves. `pktcfg` is the only real,
#: team-owned demo target this system has ever been authorized against — see
#: `.project/decisions.md`'s SEC-57 disposition comment ("the actual target in scope
#: (pktcfg) is a team-owned, trusted fixture, not adversarial input").
DEFAULT_ALLOWED_TARGETS: frozenset[str] = frozenset({"pktcfg"})


def is_enforced(*, now: date | None = None) -> bool:
    """`True` strictly through `EXPIRES` (inclusive), `False` after — see this
    module's own docstring on why that is presently `False` for any real caller."""
    today = now if now is not None else timezone.now().date()
    return today <= EXPIRES


def _configured_allowlist() -> frozenset[str]:
    """`MISSION_TARGET_ALLOWLIST` (`config/settings/base.py`, `.env.example`) if an
    operator set one, else `DEFAULT_ALLOWED_TARGETS`. `config/settings/base.py` turns
    an unset/empty `MISSION_TARGET_ALLOWLIST` env var into `None` specifically so this
    function's `is None` check is the real "operator did not configure this" signal —
    `env.get_list`'s own empty-string-becomes-empty-list behavior has no way to
    distinguish "absent" from "explicitly empty" at the env-var layer, so that
    distinction is made once, at the settings boundary, rather than guessed at here.
    A caller (or a test) that genuinely needs "allow nothing" can still pass
    `allowed=frozenset()` directly to `assert_target_allowed`.
    """
    configured = getattr(settings, "MISSION_TARGET_ALLOWLIST", None)
    if configured is None:
        return DEFAULT_ALLOWED_TARGETS
    return frozenset(configured)


def assert_target_allowed(
    repository_name: str,
    *,
    now: date | None = None,
    allowed: frozenset[str] | None = None,
) -> None:
    """Raise `RepositoryOutOfScopeError` (the same exception `authorization.service.
    _resolve_repository_ref`'s own path-scoping check already raises — an allowlist
    violation is exactly that kind of refusal) when `repository_name` is outside the
    allowlist AND today is still within the enforcement window (`is_enforced`). A
    no-op, by design, once `is_enforced()` is `False` — see this module's own opening
    docstring for why that is the honest, current state, not a bug.

    `allowed` lets a caller (or a test) inject a specific set rather than reading
    `settings.MISSION_TARGET_ALLOWLIST`/`DEFAULT_ALLOWED_TARGETS` — the same pattern
    `now` already gives for the date.
    """
    if not is_enforced(now=now):
        return
    allowlist = allowed if allowed is not None else _configured_allowlist()
    if repository_name not in allowlist:
        raise RepositoryOutOfScopeError(
            f"{repository_name!r} is not on the pre-{EXPIRES.isoformat()} SEC-57 "
            f"target allowlist ({sorted(allowlist)!r}). This mission's repository_ref "
            "must name one of the allowlisted targets while this gate is enforced.",
            details={"repository_name": repository_name, "allowlist": sorted(allowlist)},
        )
