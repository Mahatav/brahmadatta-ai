"""`JobKind.ANALYZE` — the real static-analysis stage (#22, D-144).

Mirrors `workers/fuzzing/`'s split: `run.py` is the mission-facing wrapper around the
adapter (`adapters.semgrep.run_semgrep.run_semgrep_scan`); `dispatch.py` wires it into
the `orchestrator.executors` contract and persists `Finding`/`StageToolRun` rows.

Named `static_analysis` (underscore), not `static-analysis` as
`docs/04-development/35-project-folder-structure.md`'s planning-stage layout names it
— a hyphen is not a valid Python package-name character and every other worker
package in this repository (`workers.baseline`, `workers.fuzzing`) is already a plain
importable identifier; that document predates this Django-based implementation in
several other ways too (`apps/control-api` as FastAPI, a separate `services/
orchestrator`), listed in `CLAUDE.md`'s own "Stack" section as superseded.
"""

from __future__ import annotations
