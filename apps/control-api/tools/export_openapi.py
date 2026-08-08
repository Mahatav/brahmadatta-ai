#!/usr/bin/env python
"""Dump the OpenAPI schema to `packages/schemas/openapi.json`.

Run from `apps/control-api/`:

    .venv/bin/python tools/export_openapi.py

The output is deterministic — sorted keys, two-space indent, trailing newline — so a
contract change shows up as a readable diff rather than a reshuffle.
`contracts/tests/test_openapi_dump.py` regenerates it and fails if the committed file
has drifted, which is what makes the freeze enforceable in CI rather than by memory.

## Determinism includes the interpreter (#103)

django-ninja labels each response with `http.client.responses[status]`, which comes
from the standard library's `HTTPStatus` table — and that table changes between Python
releases. 3.13 renamed four phrases, one of which (422) appears twenty-three times in
our document. The dump was therefore interpreter-dependent, so the CI drift check
failed for a reason that had nothing to do with the contract.

**A check that fails for reasons unrelated to the contract is worse than no check**:
the first time it cries wolf someone adds a bypass, and after that a real drift sails
through. So the reason phrases are pinned in `CANONICAL_REASON_PHRASES` below and
substituted during rendering. A version pin in `requirements.txt` was rejected (D-049
part 3) — it holds only until someone runs the exporter locally on a newer interpreter,
which is exactly how this was found.
"""

from __future__ import annotations

import json
import os
import sys
from http.client import responses as _STDLIB_REASON_PHRASES
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent.parent
OUTPUT_PATH = REPO_ROOT / "packages" / "schemas" / "openapi.json"

#: Reason phrases this project publishes, owned here rather than inherited from
#: whichever interpreter happened to run the exporter. Names follow RFC 9110, which is
#: why 422 reads "Unprocessable Content": pinning to a name the standard has retired
#: invites a future "correction" that silently reintroduces the drift.
#:
#: Every status django-ninja can label in our surface is listed. A status that appears
#: with a stdlib-derived description and no entry here raises, so adding an endpoint
#: with a new status code cannot quietly reopen #103 — it fails the export instead.
CANONICAL_REASON_PHRASES: dict[int, str] = {
    200: "OK",
    201: "Created",
    202: "Accepted",
    204: "No Content",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Content",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
    503: "Service Unavailable",
}


class UnpinnedReasonPhrase(Exception):
    """A response carried a stdlib reason phrase this project has not pinned."""


def _normalize_reason_phrases(schema: dict) -> dict:
    """Replace interpreter-supplied reason phrases with the pinned ones.

    Only descriptions that are *exactly* the running interpreter's phrase for that
    status are touched. A hand-written description — the SSE stream's, for instance —
    never matches one, so it is left alone.
    """
    for operations in schema.get("paths", {}).values():
        for operation in operations.values():
            if not isinstance(operation, dict):
                continue
            for status, response in operation.get("responses", {}).items():
                if not isinstance(response, dict):
                    continue
                try:
                    code = int(status)
                except (TypeError, ValueError):
                    continue
                stdlib_phrase = _STDLIB_REASON_PHRASES.get(code)
                if stdlib_phrase is None:
                    continue
                if response.get("description") != stdlib_phrase:
                    continue
                if code not in CANONICAL_REASON_PHRASES:
                    raise UnpinnedReasonPhrase(
                        f"HTTP {code} is described by the interpreter's reason phrase "
                        f"{stdlib_phrase!r}, which differs between Python releases. "
                        f"Add {code} to CANONICAL_REASON_PHRASES in "
                        f"tools/export_openapi.py so the dump stays byte-identical "
                        f"across interpreters (#103)."
                    )
                response["description"] = CANONICAL_REASON_PHRASES[code]
    return schema


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
    document = _normalize_reason_phrases(_stringify_keys(schema))
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    # An optional output path, so CI can regenerate to a scratch file and diff it against
    # the committed dump. Without this the drift check regenerated OVER the committed file
    # and then compared it with itself — it could never fail, which made the contract freeze
    # in #6 honour-based on the day it was declared frozen. Found by QA (BUG-002).
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else OUTPUT_PATH
    text = render(build_schema())
    out.parent.mkdir(parents=True, exist_ok=True)
    previous = out.read_text(encoding="utf-8") if out.exists() else ""
    out.write_text(text, encoding="utf-8")
    status = "unchanged" if previous == text else "updated"
    print(f"{status}: {out} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
