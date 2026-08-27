"""#181/SEC-57 fast-follow condition (a): `authorization.target_allowlist`.

Two things worth proving directly, not just by inspection: the self-expiring window
actually expires (a `now` after `EXPIRES` is a real no-op, not merely documented as
one), and the allowlist itself actually refuses an out-of-scope name while that window
is open.
"""

from __future__ import annotations

from datetime import date

import pytest

from authorization.errors import RepositoryOutOfScopeError
from authorization.target_allowlist import (
    DEFAULT_ALLOWED_TARGETS,
    EXPIRES,
    assert_target_allowed,
    is_enforced,
)

WITHIN_WINDOW = date(2026, 8, 15)
ON_THE_BOUNDARY = EXPIRES
AFTER_WINDOW = date(2026, 8, 21)
FAR_AFTER_WINDOW = date(2026, 9, 1)


def test_is_enforced_true_within_and_on_the_boundary():
    assert is_enforced(now=WITHIN_WINDOW) is True
    assert is_enforced(now=ON_THE_BOUNDARY) is True


def test_is_enforced_false_after_the_expiry_date():
    """The literal point of "self-expiring": this must actually flip to `False`, not
    just be described as doing so. `FAR_AFTER_WINDOW` is deliberately closer to this
    module's own real-world "today" than the boundary case above."""
    assert is_enforced(now=AFTER_WINDOW) is False
    assert is_enforced(now=FAR_AFTER_WINDOW) is False


def test_default_allowlist_contains_pktcfg_only():
    assert DEFAULT_ALLOWED_TARGETS == frozenset({"pktcfg"})


def test_allowed_target_within_window_is_not_refused():
    assert_target_allowed("pktcfg", now=WITHIN_WINDOW)  # must not raise


def test_disallowed_target_within_window_is_refused():
    with pytest.raises(RepositoryOutOfScopeError) as excinfo:
        assert_target_allowed("some-other-repo", now=WITHIN_WINDOW)
    assert "some-other-repo" in str(excinfo.value)
    assert excinfo.value.details["repository_name"] == "some-other-repo"


def test_disallowed_target_after_the_window_is_not_refused():
    """The honest, documented consequence of the window closing: this becomes a
    no-op, not a bug — see the module's own opening docstring for why."""
    assert_target_allowed("some-other-repo", now=AFTER_WINDOW)  # must not raise


def test_an_explicit_allowed_set_overrides_the_default():
    assert_target_allowed("custom-target", now=WITHIN_WINDOW, allowed=frozenset({"custom-target"}))
    with pytest.raises(RepositoryOutOfScopeError):
        assert_target_allowed("pktcfg", now=WITHIN_WINDOW, allowed=frozenset({"custom-target"}))
