"""Developer-facing CLI tooling for the control API (`export_openapi.py`, ...).

Was an implicit namespace package (no `__init__.py`) until #168 T1 put the repo
root on `sys.path` too (`config/settings/base.py`, for `workers`/`adapters`/
`packages`) — repo-root `tools/` (`fallback_demo.py`, `verdict_report.py`) is a
*different*, unrelated regular package that happens to share this bare name. A
namespace-portion directory loses to a regular package found anywhere else on
`sys.path`, regardless of search order, which silently pointed `import tools` at
the wrong one (`contracts/tests/test_openapi_dump.py`'s `from tools.export_openapi
import ...` started raising `ModuleNotFoundError` the moment both were reachable in
the same process). This file exists so `tools` is a regular package here too, which
makes the two never collapse into one namespace and restores ordinary sys.path-order
precedence — `apps/control-api` is inserted ahead of the repo root, so this one wins.
"""
