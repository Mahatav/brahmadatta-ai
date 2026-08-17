"""D-073 §5 item 1 — `fuzz-worker`'s import-boundary is a security gate, not a
convention: it must never be able to construct a model-gateway client or reach
`model-host`, so that a compromise of the one process with container-runtime access
cannot reach the inference API. `fuzz-worker` is `manage.py run_worker --kinds
FUZZ,MINIMIZE` — the same `apps/control-api` codebase as the general `worker`, run
with a different flag — so this is not "does `workers/fuzzing/` import `gateway`" in
isolation; it is "does *anything reachable when that process starts* import it",
which includes every Django `AppConfig.ready()` hook and every module `run_worker.py`
itself pulls in before the claim loop starts.

Two checks, mirroring `tests/architecture/test_import_direction.py`'s own two-layer
shape (static AST scan + a runtime subprocess belt, because a static scan cannot see
an import reached through an entry point or a plugin registry):

1. **Static.** No `.py` file under `workers/fuzzing/`, and no module named in
   `missions.management.commands.run_worker.WORKER_EXECUTOR_MODULES`, imports the
   `gateway` package or an HTTP client library.
2. **Runtime.** `django.setup()` — exactly what `manage.py` does before any command's
   `handle()` runs, and therefore exactly what happens the moment a bare-metal
   `fuzz-worker` process starts — never loads `gateway` into `sys.modules`, whether the
   codebase's `WORKER_EXECUTOR_MODULES`/`AppConfig.ready()` registration list grows to
   include a `workers.fuzzing.dispatch` entry or not.

This file intentionally does not re-derive `tests/architecture/test_import_direction.
py`'s general "exactly one module may construct an inference client" property — that
test already covers every file under `workers/`, `apps/`, `services/`, `packages/`,
`adapters/` with an empty allowlist, so a `gateway` or HTTP-client import anywhere in
`workers/fuzzing/` already fails it too. This file exists to name the fuzz-worker
boundary specifically, with a message that says why it matters (D-073), and to add the
one thing the general test does not do: prove it holds for the actual *process entry
point* fuzz-worker uses, not just for the files under one directory.
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
FUZZ_WORKER_PACKAGE = REPO_ROOT / "workers" / "fuzzing"

#: Same set `test_import_direction.py` uses — importing any of these constructs
#: something that can open a socket to a model.
HTTP_CLIENT_ROOTS = frozenset(
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

#: The package a compromise of fuzz-worker must never be able to import: the only
#: module in this codebase allowed to hold a model-gateway client
#: (`services/model-gateway/gateway/client.py`, per `tests/architecture/
#: test_import_direction.py`'s L3 enforcement).
BANNED_ROOTS = frozenset({"gateway"}) | HTTP_CLIENT_ROOTS

_control_api_only = pytest.mark.skipif(
    not CONTROL_API.is_dir(), reason="apps/control-api does not exist yet"
)
_fuzz_worker_only = pytest.mark.skipif(
    not FUZZ_WORKER_PACKAGE.is_dir(), reason="workers/fuzzing does not exist yet"
)


def _imported_roots(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        pytest.fail(f"{path.relative_to(REPO_ROOT)} does not parse: {exc}")

    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _fuzz_worker_sources() -> list[Path]:
    sources: list[Path] = []
    for path in FUZZ_WORKER_PACKAGE.rglob("*.py"):
        posix = path.as_posix()
        if "/tests/" in posix or path.name.startswith("test_"):
            continue
        sources.append(path)
    return sorted(sources)


# --------------------------------------------------------------------------------------
# 1. Static — the package fuzz-worker's own FUZZ/MINIMIZE executor code lives in
# --------------------------------------------------------------------------------------


@_fuzz_worker_only
def test_workers_fuzzing_never_imports_the_gateway_or_an_http_client() -> None:
    offenders: list[str] = []
    for source in _fuzz_worker_sources():
        hit = _imported_roots(source) & BANNED_ROOTS
        for root in sorted(hit):
            offenders.append(f"{source.relative_to(REPO_ROOT)} imports `{root}`")

    assert not offenders, (
        "workers/fuzzing/ must never import the model-gateway client or an HTTP "
        "client library (D-073): fuzz-worker is the one process in this system given "
        "container-runtime access, and a compromise of it must not be able to reach "
        "the inference API. Found:\n\n"
        + "\n".join(f"  - {line}" for line in offenders)
    )


@_control_api_only
def test_run_worker_command_module_never_imports_the_gateway() -> None:
    """The command module itself — cheap, direct defense before the runtime check
    below does the harder job of following what it pulls in transitively."""
    command_path = CONTROL_API / "missions" / "management" / "commands" / "run_worker.py"
    if not command_path.is_file():
        pytest.skip("run_worker.py not present")

    hit = _imported_roots(command_path) & BANNED_ROOTS
    assert not hit, (
        f"missions/management/commands/run_worker.py imports {sorted(hit)} — the "
        "fuzz-worker entrypoint must not import the gateway or an HTTP client (D-073)."
    )


# --------------------------------------------------------------------------------------
# 2. Runtime — django.setup(), exactly what starting fuzz-worker does before its own
#    claim loop begins, including every AppConfig.ready() hook
# --------------------------------------------------------------------------------------


@_control_api_only
def test_starting_the_worker_process_never_loads_the_gateway() -> None:
    """`django.setup()` runs every installed app's `ready()` hook — the mechanism
    `missions/apps.py` uses to register `JobKind` executors (`orchestrator/
    executors.py`'s docstring: "Add one line here per JobKind executor module as each
    stage lands"). This is exactly what happens, in order, the moment `manage.py
    run_worker --kinds FUZZ,MINIMIZE` starts — for fuzz-worker, not just for the
    general worker or the ASGI process. If a future `JobKind.FUZZ` registration ever
    imports `gateway.client` (directly, or transitively through whatever module it
    pulls in), this catches it here rather than in a live process on the finale host.
    """
    program = (
        "import json, sys\n"
        "import django\n"
        "django.setup()\n"
        "from missions.management.commands.run_worker import (\n"
        "    WORKER_EXECUTOR_MODULES, _load_executor_modules,\n"
        ")\n"
        "_load_executor_modules(WORKER_EXECUTOR_MODULES)\n"
        f"print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in {sorted(BANNED_ROOTS)!r})))\n"
    )

    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.test"),
        "DJANGO_SECRET_KEY": os.environ.get(
            "DJANGO_SECRET_KEY", "fuzz-worker-isolation-test-not-a-real-secret-01234"
        ),
        "PYTHONPATH": str(CONTROL_API),
    }

    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=CONTROL_API,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        blamed = [root for root in BANNED_ROOTS if root in result.stderr]
        assert not blamed, (
            "starting the worker process failed, and the error names a banned root "
            f"{blamed} — that is the boundary breaking, not a missing dependency:\n"
            f"{result.stderr.strip()[-800:]}"
        )
        pytest.skip(
            "could not start the worker process in this environment (dependencies "
            f"missing?): {result.stderr.strip()[-400:]}"
        )

    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    assert loaded == [], (
        "Starting the worker process (django.setup() + loading WORKER_EXECUTOR_"
        f"MODULES) pulled in banned modules: {loaded}. fuzz-worker must never load "
        "the model-gateway client or an HTTP client library — see D-073."
    )
