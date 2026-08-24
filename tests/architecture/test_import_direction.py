"""C5 — the `gateway` package must not be reachable from the ASGI process.

Why this is a test and not a code review note. The decision was "modules, not services":
the gateway, the orchestrator and the control API are packages inside one process rather
than separate deployments. That is a good call at this size, and it has exactly one failure
mode — the boundaries are conventions, and conventions decay. Without an assertion, a
`from gateway import ...` in a view is a one-line change that nobody notices, and by the
end of the week there is one mud ball with no seam to split along.

The direction matters and only one direction is banned:

    gateway  --may import-->  contracts        (schemas are shared)
    api      --may import-->  contracts
    api      --MUST NOT import-->  gateway     <-- this test

The control API talks to the gateway through the queue and the database, never by import.
Two reasons that is worth enforcing rather than just intending: an inference client
imported into the ASGI process is an inference client inside the request path, which is the
process holding operator credentials and repository snapshots; and an import edge is what
makes "extract the gateway to its own service" a rewrite instead of a move.

The api→gateway checks skip when apps/control-api is absent.

## Widened for `services/` — CTO condition 3 on PR #111

This file used to walk `apps/` only. The gateway package lives in
`services/model-gateway/`, so the test enforcing *"exactly one module may construct an
inference client"* could not see the module that constructs one. It was passing by not
looking.

`test_only_declared_modules_may_construct_an_inference_client` now walks `apps/`,
`services/` and `workers/` together. Its allowlist is **empty today**, and that is the
honest state rather than an oversight: there is no live backend in the tree yet (#35/#36),
so nothing imports an HTTP client outside a test. The moment one arrives it has to be added
here deliberately, in a diff somebody reviews.

`test_the_endpoint_policy_imports_without_django` is CTO condition 1. The endpoint policy
is being consolidated into `contracts/` so that the gateway and the control API share one
implementation (D-050). That only works while the module's import closure is stdlib —
`model_policy → errors → enums → stdlib`. One `ninja.Schema` import and the duplication
returns by necessity, so the property is asserted rather than remembered.
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
MODEL_GATEWAY = REPO_ROOT / "services" / "model-gateway"

# Packages that make up the ASGI process. Anything reachable from here is "in the request
# path" for the purposes of this test.
ASGI_PACKAGES = ("config", "api", "contracts")

BANNED_ROOTS = ("gateway",)

#: Every tree holding first-party Python. `apps/` alone was the bug.
SOURCE_TREES = ("apps", "services", "workers", "adapters", "packages")

#: Importing any of these is constructing something that can open a socket to a model.
#: `urllib.parse` is deliberately absent — parsing a URL is not opening one, and the
#: endpoint policy's whole job is to parse without connecting.
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
        "google",  # google.generativeai
        "boto3",  # bedrock-runtime
        "litellm",
        "langchain",
        "ollama",
        "llama_cpp",
        "transformers",
    }
)

#: Repository-relative paths permitted to import one of the above. A single reviewed
#: line per module, per this test's own point: exactly one place may hold the client
#: that talks to a model.
#:
#: `services/model-gateway/gateway/client.py` is that one place (D-121, #35/#36's live
#: backend) — it already used `urllib.request.urlopen`/`Request` (not itself tracked by
#: `HTTP_CLIENT_ROOTS`, since `urllib` is stdlib, not a third-party client) without
#: needing an entry here. Found live 2026-08-24 (D-132): PR #250/D-130 added
#: `import http.client` to the same file, solely to reference `http.client.
#: IncompleteRead` as an exception type to catch — no new client construction, but
#: `_imports_http_client_connection` correctly can't distinguish "importing http.client
#: for its exception class" from "importing it to build a raw HTTPConnection," so it
#: fired. Allowlisting the file this test already intended to be the one inference
#: client is the correct fix, not narrowing the check.
INFERENCE_CLIENT_ALLOWLIST: frozenset[str] = frozenset(
    {"services/model-gateway/gateway/client.py"}
)

_control_api_only = pytest.mark.skipif(
    not CONTROL_API.is_dir(),
    reason="apps/control-api does not exist yet",
)


def _imported_roots(path: Path) -> set[str]:
    """Top-level module names imported by one file, from its AST."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:  # a syntax error is the other test's problem, not this one
        pytest.fail(f"{path.relative_to(REPO_ROOT)} does not parse: {exc}")

    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # `from . import x` has no module; a relative import cannot escape the package.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


@_control_api_only
def test_asgi_packages_do_not_import_the_gateway() -> None:
    """Static check. Catches the offending import the moment it is written."""
    offenders: list[str] = []

    for package in ASGI_PACKAGES:
        package_dir = CONTROL_API / package
        if not package_dir.is_dir():
            continue
        for source in sorted(package_dir.rglob("*.py")):
            if "/tests/" in source.as_posix() or source.name.startswith("test_"):
                continue
            for root in sorted(_imported_roots(source) & set(BANNED_ROOTS)):
                offenders.append(f"{source.relative_to(REPO_ROOT)} imports `{root}`")

    assert not offenders, (
        "The ASGI process must not import the gateway package.\n\n"
        + "\n".join(f"  - {line}" for line in offenders)
        + "\n\nThe control API reaches the gateway through the queue and the database, "
        "never by import. See tests/architecture/test_import_direction.py for why."
    )


@_control_api_only
def test_importing_the_asgi_app_does_not_load_the_gateway() -> None:
    """Runtime check. Catches an import arriving through a path the AST scan cannot see —
    a settings module string, an entry point, a plugin registry."""
    if not (CONTROL_API / "config" / "asgi.py").is_file():
        pytest.skip("config/asgi.py not present")

    program = (
        "import json, sys\n"
        "import config.asgi  # noqa: F401\n"
        "print(json.dumps(sorted(m for m in sys.modules "
        f"if m.split('.')[0] in {BANNED_ROOTS!r})))\n"
    )

    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.test"),
        "DJANGO_SECRET_KEY": os.environ.get(
            "DJANGO_SECRET_KEY", "import-direction-test-not-a-real-secret-0123456789"
        ),
        "PYTHONPATH": str(CONTROL_API),
    }

    # Fixed argv, no shell: the only variable is the program text built above.
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=CONTROL_API,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        pytest.skip(
            "could not import config.asgi in this environment "
            f"(dependencies missing?): {result.stderr.strip()[-400:]}"
        )

    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    assert loaded == [], (
        "Importing the ASGI application pulled in banned modules: "
        f"{loaded}. The gateway must not be loaded inside the request path."
    )


# --------------------------------------------------------------------------------------
# CTO condition 3 on #111 — the scan walks services/, not just apps/
# --------------------------------------------------------------------------------------


def _first_party_sources() -> list[Path]:
    """Every non-test Python file in every source tree.

    The previous version of this module walked `apps/` only, which is why a package in
    `services/` could import anything it liked without this file noticing.
    """
    sources: list[Path] = []
    for tree in SOURCE_TREES:
        root = REPO_ROOT / tree
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            posix = path.as_posix()
            if "/tests/" in posix or path.name.startswith("test_") or "/.venv/" in posix:
                continue
            if path.name == "conftest.py":
                continue
            sources.append(path)
    return sorted(sources)


def test_the_scan_actually_reaches_the_gateway_package() -> None:
    """Guards the guard.

    The failure this whole widening corrects is a scan that passes because it is looking at
    an empty set. If `services/model-gateway/` exists, its modules must appear in what the
    scan walks — otherwise the assertions below are vacuous and say so.
    """
    if not MODEL_GATEWAY.is_dir():
        pytest.skip("services/model-gateway does not exist yet")

    scanned = {p.relative_to(REPO_ROOT).as_posix() for p in _first_party_sources()}
    assert "services/model-gateway/gateway/backends.py" in scanned, (
        "the import scan does not reach the gateway package. That is the exact defect CTO "
        "condition 3 was raised about: the test enforcing 'exactly one module may "
        "construct an inference client' could not see the module that constructs one."
    )


#: `http.client` is stdlib and holds both the classes that open a socket
#: (`HTTPConnection`, `HTTPSConnection`) and a pile of things that do not
#: (`responses` — a status-code-to-reason-phrase dict, exception classes, `HTTPMessage`).
#: A root-level check on `http` would flag `from http.client import responses`, which is
#: exactly what `apps/control-api/tools/export_openapi.py` does to render a schema and
#: opens no socket. Checked by name instead, so the guard is precise about what it is
#: guarding against rather than merely broad.
_HTTP_CLIENT_CONNECTION_NAMES = frozenset({"HTTPConnection", "HTTPSConnection"})


def _imports_http_client_connection(path: Path) -> bool:
    """True if `path` imports `http.client.HTTPConnection`/`HTTPSConnection`, or the
    whole `http.client` module by name — the shapes that can actually open a socket."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name in ("http.client", "http.client.*") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module == "http.client" and any(
                alias.name in _HTTP_CLIENT_CONNECTION_NAMES for alias in node.names
            ):
                return True
            if node.module == "http" and any(alias.name == "client" for alias in node.names):
                return True
    return False


def test_only_declared_modules_may_construct_an_inference_client() -> None:
    """L3 — exactly one module may construct an inference client, and it must be declared.

    Now across `apps/`, `services/` and `workers/` rather than `apps/` alone.

    The allowlist is empty today and that is the true state of the tree: there is no live
    backend, `UnavailableLiveBackend` raises instead of connecting, and nothing in product
    code imports an HTTP client. When #35/#36 adds one, this test fails until somebody
    writes the path into `INFERENCE_CLIENT_ALLOWLIST` — which is the point. A single
    reviewed line is the whole control.
    """
    offenders: list[str] = []
    for source in _first_party_sources():
        relative = source.relative_to(REPO_ROOT).as_posix()
        if relative in INFERENCE_CLIENT_ALLOWLIST:
            continue
        for root in sorted(_imported_roots(source) & HTTP_CLIENT_ROOTS):
            offenders.append(f"{relative} imports `{root}`")
        if _imports_http_client_connection(source):
            offenders.append(f"{relative} imports `http.client`'s connection classes")

    assert not offenders, (
        "A module that is not declared as the inference client imports an HTTP client:\n\n"
        + "\n".join(f"  - {line}" for line in offenders)
        + "\n\nExactly one module may hold the client that talks to a model, and it is "
        "named in INFERENCE_CLIENT_ALLOWLIST in this file. Anything else is a second "
        "place repository content can leave from, and the endpoint policy does not guard "
        "it. Add the path here in a diff somebody reviews, or route the call through the "
        "gateway."
    )


# --------------------------------------------------------------------------------------
# CTO condition 1 on #111 — the endpoint policy stays importable without Django
# --------------------------------------------------------------------------------------

#: (label, sys.path entry, module) for every copy of the endpoint policy in the tree.
#: Both are listed so the property is asserted before, during and after the consolidation
#: into `contracts/` (D-050) without this test needing to be edited on the day.
_POLICY_MODULES = (
    ("gateway", MODEL_GATEWAY, "gateway.endpoint_policy"),
    ("control-api", CONTROL_API, "contracts.model_policy"),
)

#: Importing any of these means the module can no longer be shared by both processes.
_HEAVY_ROOTS = ("django", "ninja", "pydantic")


def _module_file(root: Path, module: str) -> Path:
    return root.joinpath(*module.split(".")).with_suffix(".py")


def _import_closure(root: Path, module: str) -> dict[str, set[str]]:
    """Walk the module's first-party import graph, returning {module: imported roots}.

    Static, so it cannot skip and cannot be defeated by a missing dependency — which is
    how the first version of this test let an injected `import ninja` pass as a skip
    instead of a failure. Follows imports that resolve to a file under `root`; a
    third-party root is recorded and not descended into.
    """
    seen: dict[str, set[str]] = {}
    queue = [module]
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        path = _module_file(root, current)
        if not path.is_file():
            package_init = root.joinpath(*current.split(".")) / "__init__.py"
            if not package_init.is_file():
                continue
            path = package_init
        roots = _imported_roots(path)
        seen[current] = roots

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                if _module_file(root, node.module).is_file():
                    queue.append(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if _module_file(root, alias.name).is_file():
                        queue.append(alias.name)
    return seen


@pytest.mark.parametrize("label,path,module", _POLICY_MODULES, ids=[m[0] for m in _POLICY_MODULES])
def test_the_endpoint_policy_imports_without_django(label: str, path: Path, module: str) -> None:
    """The endpoint policy's import closure contains no Django, ninja or pydantic.

    This is what makes one shared implementation possible (D-050): `model_policy` →
    `errors` → `enums` → stdlib. One `ninja.Schema` import and the two copies come back by
    necessity, not by anybody choosing them — so the property is a test rather than a note
    in a review.

    Static on purpose. The first version of this test ran a subprocess and skipped when the
    import failed, which meant an injected `import ninja` produced a **skip** rather than a
    failure — the precise "passing by not looking" shape this whole widening exists to
    correct. A static walk cannot skip and needs no dependency installed.
    """
    if not path.is_dir():
        pytest.skip(f"{path.relative_to(REPO_ROOT)} does not exist yet")
    if not _module_file(path, module).is_file():
        pytest.skip(f"{module} does not exist in {path.relative_to(REPO_ROOT)} yet")

    closure = _import_closure(path, module)
    assert closure, f"the closure walk found nothing for {module} — it is asserting nothing"

    offenders = sorted(
        f"{name} imports `{root}`"
        for name, roots in closure.items()
        for root in roots & set(_HEAVY_ROOTS)
    )
    assert not offenders, (
        f"{module}'s import closure is no longer stdlib-only:\n\n"
        + "\n".join(f"  - {line}" for line in offenders)
        + "\n\nThe endpoint policy has to be importable by the control API *and* by the "
        "gateway, in processes that do not share a dependency set. A Django, ninja or "
        "pydantic import here forces the two copies back — which is the duplication D-050 "
        "just removed, and it would return without anybody deciding to bring it back."
    )


@pytest.mark.parametrize("label,path,module", _POLICY_MODULES, ids=[m[0] for m in _POLICY_MODULES])
def test_the_endpoint_policy_loads_in_a_bare_interpreter(
    label: str, path: Path, module: str
) -> None:
    """The same property at runtime, catching an import the AST walk cannot see.

    Belt to the static check's braces: a lazy import inside a function, an entry point, a
    plugin registry. Unlike the static check this one *can* skip when a dependency is
    genuinely absent — but a failure whose message names one of the heavy roots is treated
    as the violation it is, not as a missing dependency.
    """
    if not path.is_dir() or not _module_file(path, module).is_file():
        pytest.skip(f"{module} not present")

    program = (
        "import json, sys\n"
        f"import {module}  # noqa: F401\n"
        "print(json.dumps(sorted({m.split('.')[0] for m in sys.modules} & "
        f"set({_HEAVY_ROOTS!r}))))\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=path,
        env={**os.environ, "PYTHONPATH": str(path)},
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        blamed = [root for root in _HEAVY_ROOTS if root in result.stderr]
        assert not blamed, (
            f"{module} failed to import in a bare interpreter, and the error names "
            f"{blamed}. That is not a missing dependency, it is the policy having "
            f"acquired one:\n{result.stderr.strip()[-600:]}"
        )
        pytest.skip(
            f"could not import {module} here (unrelated dependency missing): "
            f"{result.stderr.strip()[-300:]}"
        )

    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    assert loaded == [], f"{module} pulled in {loaded} on a bare import."
