"""Re-exports fixtures this directory's tests need from `orchestrator/tests/conftest.py`.

pytest discovers fixtures from `conftest.py` files up the directory tree, not from an
arbitrary module import — importing a fixture function directly into a *test* module
(rather than a `conftest.py`) and then also using its name as a test-function
parameter reads, to a static analyzer, as the parameter shadowing the imported name
(`ruff`'s F811), even though pytest itself resolves it correctly by dependency
injection. Re-exporting here instead keeps `missions/tests/*.py` free of that false
positive and matches the idiomatic pytest pattern for sharing fixtures across a
package boundary.
"""

from __future__ import annotations

from orchestrator.tests.conftest import mission  # noqa: F401 - re-exported fixture
