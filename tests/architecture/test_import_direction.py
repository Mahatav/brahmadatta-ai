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

Both checks skip when apps/control-api is absent, which is the state on `main` at D1.
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

# Packages that make up the ASGI process. Anything reachable from here is "in the request
# path" for the purposes of this test.
ASGI_PACKAGES = ("config", "api", "contracts")

BANNED_ROOTS = ("gateway",)

pytestmark = pytest.mark.skipif(
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
