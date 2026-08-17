"""SEC-54 (#198) — closes the coverage gap `tests/architecture/test_fuzz_worker_
isolation.py` left open: that file's static half only scans `workers/fuzzing/` (which
does not exist on this branch yet) and `run_worker.py` itself; its runtime half only
observes `sys.modules` right after `django.setup()` + loading `WORKER_EXECUTOR_MODULES`
— i.e. whatever ran at *import* time. Neither one AST-scans the *contents* of the
modules `WORKER_EXECUTOR_MODULES` actually names.

That gap is exactly what #198 demonstrated: cybersecurity injected a lazy
`import gateway.client` inside a *function body* in `apps/control-api/orchestrator/
executors.py` (the one module `WORKER_EXECUTOR_MODULES` names today) and it passed all
11 then-existing checks cleanly, because the import only executes if and when that
function is called — never during `django.setup()`, and never in a directory-scoped
static scan that doesn't cover this file at all.

## What this file does about it

1. **Resolves `WORKER_EXECUTOR_MODULES` dynamically, at test time, from the real
   source of truth** (`missions.management.commands.run_worker.
   WORKER_EXECUTOR_MODULES`) rather than hardcoding today's one entry
   (`"orchestrator.executors"`). Done via a subprocess that runs `django.setup()` —
   the constant lives in a Django management command module, so importing it in-process
   (this test module has no Django settings configured) is not an option — mirroring
   the belt-and-suspenders pattern `test_fuzz_worker_isolation.py` already uses for its
   own runtime half.
2. **AST-scans each named module's actual file for `gateway`/HTTP-client-library
   imports anywhere in the tree** — `ast.walk()` visits every node regardless of
   nesting, so an import statement inside a function body (a lazy/deferred import, the
   exact #198 bypass class) is caught exactly the same way a module-level import would
   be. This is the one property neither existing check proves.
3. **Auto-extends with zero test-code changes.** When T2's `workers.fuzzing.dispatch`
   lands and registers itself in `WORKER_EXECUTOR_MODULES` (see that constant's own
   docstring: "each `JobKind` task adds its own module's dotted path... when it
   lands"), the next run of this file resolves the grown tuple and scans the new file
   too — nothing here names `orchestrator.executors` or T2's module directly. Today,
   before T2 merges, the tuple has exactly one entry and this file scans exactly that
   one file; it does not fail against code that doesn't exist yet, because it never
   looks for a module the constant doesn't currently name.

See `docs/09-company/08-security-review.md`'s SEC-54 finding (also filed as GitHub
issue #198) and PR #197 (#189, D-073) for the fuller narrative.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_API = REPO_ROOT / "apps" / "control-api"
RUN_WORKER_MODULE = "missions.management.commands.run_worker"

#: Mirrors `test_fuzz_worker_isolation.py`'s own `BANNED_ROOTS` — importing any of
#: these constructs something that can open a socket to a model or the model-gateway
#: client (`services/model-gateway/gateway/client.py`, the only module in this
#: codebase `tests/architecture/test_import_direction.py`'s L3 enforcement allows to
#: hold one). Kept as an independent copy rather than a cross-module import: this file
#: has no `__init__.py`-backed package to import across (see `tests/conftest.py`'s own
#: `sys.path` note), and the two lists are short enough that a docstring cross-
#: reference is enough to keep them from silently diverging.
_HTTP_CLIENT_ROOTS = frozenset(
    {
        "httpx",
        "requests",
        "aiohttp",
        "urllib3",
        "openai",
        "anthropic",
        "cohere",
        "mistralai",
        "together",
        "groq",
        "google",
        "boto3",
        "litellm",
        "langchain",
        "ollama",
        "llama_cpp",
        "transformers",
    }
)
BANNED_ROOTS = frozenset({"gateway"}) | _HTTP_CLIENT_ROOTS

_control_api_only = pytest.mark.skipif(
    not CONTROL_API.is_dir(), reason="apps/control-api does not exist yet"
)


def _run_worker_env() -> dict[str, str]:
    return {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.test"),
        "DJANGO_SECRET_KEY": os.environ.get(
            "DJANGO_SECRET_KEY", "worker-executor-modules-import-boundary-test-not-a-real-secret"
        ),
        "PYTHONPATH": str(CONTROL_API),
    }


def _resolve_worker_executor_modules() -> tuple[str, ...]:
    """The one piece of dynamic resolution this file depends on: ask the real
    `run_worker.py` module, via a fresh interpreter with Django set up (exactly what
    starting the `manage.py run_worker` process does before its claim loop runs), what
    `WORKER_EXECUTOR_MODULES` actually contains right now. Never hardcoded here.
    """
    program = (
        "import json\n"
        "import django\n"
        "django.setup()\n"
        f"from {RUN_WORKER_MODULE} import WORKER_EXECUTOR_MODULES\n"
        "print(json.dumps(list(WORKER_EXECUTOR_MODULES)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=CONTROL_API,
        env=_run_worker_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        pytest.skip(
            "could not resolve WORKER_EXECUTOR_MODULES in this environment "
            f"(dependencies missing?): {result.stderr.strip()[-600:]}"
        )
    return tuple(json.loads(result.stdout.strip().splitlines()[-1]))


def _module_file(dotted: str) -> Path:
    """Dotted import path -> source file, by plain filesystem path-joining (not by
    importing the module, which would require Django set up in *this* process for
    every module that happens to import Django models). Every entry
    `WORKER_EXECUTOR_MODULES` names is a plain module or package under
    `apps/control-api` (see `run_worker.py`'s own docstring: "e.g.
    `workers.baseline.dispatch`" / `orchestrator.executors`), so this mapping is exact
    for the modules this constant is documented to ever hold.
    """
    as_module = CONTROL_API / Path(*dotted.split(".")).with_suffix(".py")
    if as_module.is_file():
        return as_module
    as_package = CONTROL_API / Path(*dotted.split(".")) / "__init__.py"
    if as_package.is_file():
        return as_package
    pytest.fail(
        f"WORKER_EXECUTOR_MODULES names {dotted!r}, but neither "
        f"{as_module.relative_to(REPO_ROOT)} nor {as_package.relative_to(REPO_ROOT)} "
        "exists. Either the constant is stale, or this test's module-to-file mapping "
        "no longer matches how these modules are laid out — fix whichever is true "
        "before trusting this file's scan."
    )


def _banned_imports(path: Path) -> list[str]:
    """Every `gateway`/HTTP-client-root import in `path`, module-level OR nested
    inside a function/class/branch — `ast.walk` visits the whole tree regardless of
    nesting depth, so a lazy `import gateway.client` buried inside a function body
    (#198's exact PoC) is found exactly the same way a top-level import would be.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        pytest.fail(f"{path.relative_to(REPO_ROOT)} does not parse: {exc}")

    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BANNED_ROOTS:
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{node.lineno}: `import {alias.name}` "
                        f"(banned root `{root}`)"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                root = node.module.split(".")[0]
                if root in BANNED_ROOTS:
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{node.lineno}: "
                        f"`from {node.module} import ...` (banned root `{root}`)"
                    )
    return offenders


@pytest.fixture(scope="module")
def worker_executor_module_files() -> list[Path]:
    dotted_modules = _resolve_worker_executor_modules()
    assert dotted_modules, (
        "WORKER_EXECUTOR_MODULES resolved to an empty tuple — that would make this "
        "test vacuous (nothing to scan). `orchestrator.executors` must always be "
        "present per that constant's own docstring; an empty result means resolution "
        "itself is broken, not that there is genuinely nothing to check."
    )
    return [_module_file(dotted) for dotted in dotted_modules]


@_control_api_only
def test_worker_executor_modules_resolves_to_at_least_orchestrator_executors(
    worker_executor_module_files: list[Path],
) -> None:
    """Sanity check on the resolution mechanism itself, independent of the import
    scan below: today's `WORKER_EXECUTOR_MODULES` must include `orchestrator/
    executors.py` (T0's own reference registration) — proves the subprocess
    resolution + file-mapping pipeline actually found the right file, not an empty or
    unrelated list that would make the scan below pass for the wrong reason."""
    assert CONTROL_API / "orchestrator" / "executors.py" in worker_executor_module_files


@_control_api_only
def test_no_worker_executor_module_imports_gateway_or_an_http_client_anywhere(
    worker_executor_module_files: list[Path],
) -> None:
    """The property SEC-54/#198 asked for: every module `WORKER_EXECUTOR_MODULES`
    currently names — i.e. everything `manage.py run_worker` (including `fuzz-worker`,
    `--kinds FUZZ,MINIMIZE`) imports before its claim loop starts — must be free of
    `gateway`/HTTP-client imports **anywhere in the file**, not just at module level.
    fuzz-worker is the one process in this system given container-runtime access
    (D-073); a compromise of it must not be able to construct a model-gateway client
    or reach `model-host`, including through a deferred import that only executes once
    a specific function actually runs.
    """
    offenders: list[str] = []
    for path in worker_executor_module_files:
        offenders.extend(_banned_imports(path))

    assert not offenders, (
        "A module named in WORKER_EXECUTOR_MODULES imports the model-gateway client "
        "or an HTTP client library — including, possibly, only inside a function "
        "body (a lazy/deferred import; see #198). fuzz-worker must never be able to "
        "reach the inference API (D-073). Found:\n\n"
        + "\n".join(f"  - {line}" for line in offenders)
    )
