#!/usr/bin/env python
"""Dump the OpenAPI schema to `packages/schemas/openapi.json`.

Run from `apps/control-api/`:

    .venv/bin/python tools/export_openapi.py

The output is deterministic — sorted keys, two-space indent, trailing newline — so a
contract change shows up as a readable diff rather than a reshuffle.
`contracts/tests/test_openapi_dump.py` regenerates it and fails if the committed file
has drifted, which is what makes the freeze enforceable in CI rather than by memory.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent.parent
OUTPUT_PATH = REPO_ROOT / "packages" / "schemas" / "openapi.json"


def build_schema() -> dict:
    sys.path.insert(0, str(BASE_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

    import django

    django.setup()

    from api.api import api

    return api.get_openapi_schema()


def _stringify_keys(node):
    """Normalize mapping keys to strings.

    django-ninja emits response-status keys as integers where they were declared as
    integers and as strings where they came from `openapi_extra`. JSON object keys are
    strings either way; normalizing here keeps the dump stable and sortable.
    """
    if isinstance(node, dict):
        return {str(key): _stringify_keys(value) for key, value in node.items()}
    if isinstance(node, (list, tuple)):
        return [_stringify_keys(item) for item in node]
    return node


def render(schema: dict) -> str:
    return (
        json.dumps(_stringify_keys(schema), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    )


def main() -> int:
    text = render(build_schema())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    previous = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
    OUTPUT_PATH.write_text(text, encoding="utf-8")
    status = "unchanged" if previous == text else "updated"
    print(f"{status}: {OUTPUT_PATH} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
