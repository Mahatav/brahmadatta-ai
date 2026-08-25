"""Semgrep static-analysis adapter (#22, D-144).

`run_semgrep.py` runs a real, live Semgrep scan inside `packages.sandbox.container.
ContainerJail` against a vendored, repo-committed ruleset (`adapters/semgrep/rules/`)
-- see that module's own docstring for why a vendored ruleset, not a live registry
fetch, is the only thing that works inside a `--network none` sandbox.
"""

from __future__ import annotations
