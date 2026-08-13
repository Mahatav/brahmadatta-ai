from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
EGRESS_IMPORTS = {
    "aiohttp",
    "http.client",
    "httpcore",
    "httpx",
    "requests",
    "urllib.request",
    "urllib3",
}
ALLOWED_EGRESS_MODULES = {"gateway.client"}


def test_http_egress_imports_only_live_in_gateway_client() -> None:
    offenders: dict[str, list[str]] = {}
    egress_modules: set[str] = set()

    for path in sorted(PACKAGE.rglob("*.py")):
        if path.parts[-2] == "tests":
            continue
        module = "gateway." + path.relative_to(PACKAGE).with_suffix("").as_posix().replace("/", ".")
        imported = _egress_imports(path)
        if imported:
            egress_modules.add(module)
        if imported and module not in ALLOWED_EGRESS_MODULES:
            offenders[module] = imported

    assert egress_modules == ALLOWED_EGRESS_MODULES
    assert offenders == {}


def _egress_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_egress_import(alias.name):
                    imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if _is_egress_import(node.module):
                imports.append(node.module)
    return sorted(set(imports))


def _is_egress_import(module: str) -> bool:
    return any(module == item or module.startswith(item + ".") for item in EGRESS_IMPORTS)
