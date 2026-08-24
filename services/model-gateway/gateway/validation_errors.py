"""Safe rendering of a pydantic `ValidationError`, for anything that may reach a log
line, an exception message, or a dev CLI's stdout (#258).

Mirrors the fix `apps/control-api/api/sse.py::safe_to_schema` applies (#229, D-130/
D-131, and its own #258 follow-up): a pydantic `ValidationError`'s `errors()` carries
each failing field's actual *value* under `"input"` (and again inside `ctx`/`msg` for
some error kinds), and `ValidationError.__str__`/`__repr__` — what `logger.exception`,
an f-string, or a bare `raise ... from exc` all end up calling — embeds that same value
as `input_value=...`. A malformed or attacker-influenced payload is exactly the thing
not to trust the well-formedness, or safety, of for something that gets logged, printed,
or handed back in an exception message.

`loc` (the field-path tuple) has no value in it and is normally safe to keep — that is
the whole point of using `loc`/`type` instead of the raw error. But when the failure is
a forbidden-extra-field rejection (`StrictSchema`'s `extra="forbid"`, this package's
schemas use the pydantic default `ConfigDict(extra="forbid")`), `loc` ends in the extra
field's own *key name* — and a payload can make that key name secret-shaped
(`{"sk-live-...": "y"}` → `loc=(..., "sk-live-...")`) without the failing *value* being
secret-shaped at all. `looks_secret_shaped`/`safe_validation_error_shape` below close
that channel too.

This package cannot import `apps/control-api/orchestrator/redaction.py` directly —
`services/model-gateway` is deliberately its own dependency closure (see that module's
own docstring, and `tests/architecture/test_import_direction.py`) — so this module
mirrors its `looks_secret_shaped`/`redact_loc` shape and `gateway/context.py::
_SECRET_LINE`'s secret-keyword vocabulary (`api[_-]?key|token|secret|password`,
case-insensitive) rather than inventing a third, differently-shaped detector. If this
module and either of those drift apart, that is a real signal (the threat model
changed for one but not the others) rather than an oversight — but a reviewer touching
any of the three should check the other two.
"""

from __future__ import annotations

import re

from pydantic import ValidationError

__all__ = [
    "REDACTED_LOC_SEGMENT",
    "looks_secret_shaped",
    "safe_validation_error_shape",
]

#: Same secret-keyword vocabulary as `gateway/context.py::_SECRET_LINE` (and its
#: control-api mirror, `orchestrator/redaction.py::_SECRET_KEYWORD_RE`). No `\s*[:=]`
#: requirement, unlike `_SECRET_LINE`: this is applied to a single bare string (a
#: `loc` segment / dict key), never a `key: value`-shaped line.
_SECRET_KEYWORD_RE = re.compile(r"api[_-]?key|token|secret|password", re.IGNORECASE)

#: What a secret-shaped `loc` segment is replaced with. Keeps the segment's position in
#: the tuple, and that it was a string, without the one thing that cannot be kept: the
#: literal key name.
REDACTED_LOC_SEGMENT = "<redacted secret-shaped segment>"


def looks_secret_shaped(value: object) -> bool:
    """True if `value` is a string containing the secret-keyword vocabulary
    (`api[_-]?key`, `token`, `secret`, `password`, case-insensitive) this package
    already uses elsewhere to recognise a `key: value`-shaped secret line.

    Non-string values (an int list-index segment of `loc`, for instance) are never
    secret-shaped by construction and always return `False`.
    """
    return isinstance(value, str) and bool(_SECRET_KEYWORD_RE.search(value))


def _redact_loc(loc: tuple[object, ...]) -> tuple[object, ...]:
    return tuple(
        REDACTED_LOC_SEGMENT if looks_secret_shaped(segment) else segment for segment in loc
    )


def safe_validation_error_shape(exc: ValidationError) -> list[dict[str, object]]:
    """`exc.errors(include_url=False)`, reduced to only `loc`/`type` — never `input`,
    `msg`, or `ctx`, where a failing field's actual value lives — and with any
    secret-shaped `loc` segment replaced by `REDACTED_LOC_SEGMENT`.

    Safe to log, print, or embed in an exception message/`details` dict: unlike
    `exc.errors()` or `str(exc)`, nothing in the return value can carry a payload
    value or a secret-shaped forbidden-field key name.
    """
    return [
        {"loc": _redact_loc(error["loc"]), "type": error["type"]}
        for error in exc.errors(include_url=False)
    ]
