"""Independent redaction pass for `GateResult.detail` at every point it can reach an
exported artifact (#168 T6, SEC-48/SEC-50, `.project/decisions.md` D-071b/D-071c).

As of SEC-50 (D-071c), this function's primary call site is `orchestrator.
evidence_bundle.assemble_evidence_bundle` itself — upstream of both of its
consumers, `api/routers/evidence.py::get_evidence` (which previously returned the
raw bundle unredacted) and `orchestrator.evidence_export.export_mission` (which
retains its own independent calls to this function as defense in depth). See
`evidence_bundle.py`'s module docstring for the full reasoning on why the
sanitization point moved there.

`contracts/verdict.py::GateResult.detail`'s own docstring promises "User-safe summary.
Never raw target output, never secrets." `orchestrator.verification._summarize`
(SEC-45, on the still-unmerged `feat/168-t5-verify-executor` branch as of this fix) is
the *one* place upstream that is supposed to keep that promise, by constructing
`detail` only from an explicit, known-safe vocabulary: a tool name, an `exit=<code>`
token, and a handful of hand-written literal prefixes or bare integers pulled from a
fixed regex capture group — never raw subprocess stdout/stderr.

D-071b's binding ruling is that the export boundary (`orchestrator.evidence_export`,
plus `orchestrator.evidence_bundle._gates_not_run`, which bakes `detail` into a string
before the export boundary ever sees it) must not depend on that upstream promise
holding for every gate, every contributor, forever — it is the last code that runs
before a `detail` string leaves the system entirely, inside a tarball handed to an
external competition judge who has never had any access to this deployment's
environment. This module is that independent check: called at every one of the
locations SEC-48 named, so a violation anywhere upstream — today's reproduced leak, or
the next one nobody has found yet — is caught here too, not only fixed at its source.

## Allowlist, not denylist

A denylist (regex for `KEY=VALUE`, `postgresql://`, `redis://`, ...) only catches
secret *shapes* someone already thought to name; a secret in a shape nobody predicted
sails through unredacted. That is the same blind spot SEC-44/SEC-45's own fix rejected
in favour of `packages.sandbox.policy.DEFAULT_ENV_ALLOWLIST` (an allowlist of
environment variables, not a blocklist of secret names) — this module mirrors that
choice for the export boundary's own layer: `sanitize_detail` does not try to
recognise *unsafe* content. It recognises *safe* content, structurally, and replaces
anything that does not match with a fixed, non-leaking placeholder.

A `detail` value is treated as safe only if **all** of the following hold:

* it contains no newline/carriage-return/tab (a one-line "summary" has none; raw
  captured subprocess output almost always does);
* it is no longer than `_MAX_SAFE_DETAIL_CHARS` (generous for a one-line summary,
  far short of what a raw dump needs);
* removing every well-formed `exit=<code>` token (the one sanctioned use of `=` this
  allowlist grants — T5's own canonical shape) leaves no `=` anywhere else, which
  rules out `KEY=value`-style environment-variable lines and most other assignment-
  shaped secrets regardless of what character class they otherwise satisfy;
* it does not contain a `://` scheme separator (the one two-character sequence every
  connection-string shape this review named shares — `postgresql://`, `redis://`,
  `mysql://`, `mongodb://`, `amqp://` — and a plain English sentence never needs, even
  though `:` and `/` are each independently allowed below);
* it does not contain a `-----BEGIN` marker (PEM-encoded key/certificate material);
  and
* every character in it is drawn from a narrow, explicitly-listed set: letters,
  digits, space, and `.,:;'"()/_%+=-` — the vocabulary a plain-English "tool: outcome
  exit=N"-shaped summary needs and nothing else (no backtick, `$`, `<`, `>`, `@`,
  `{`, `}`, `[`, `]`, backslash, `|`, `~`, `^`, `&`, `*`, `#`, `!`, or `?` — none of
  which a summary this schema's own docstring describes needs, and several of which
  are exactly what a shell snippet or raw stack trace would carry).

Never truncates and returns *part* of an unsafe string — a truncated secret is still a
partial secret. Either the whole value passes every check, or the whole value is
replaced.

## Known limitation, stated rather than hidden

This allowlist does not attempt to detect a bare secret that carries no `=`, no
`://`, no PEM marker, no newline, and no character outside the safe set — e.g. a raw
credential pasted as space-separated tokens rather than `KEY=value` or a connection
URL. An earlier draft of this module added a "run of N+ token-shaped characters"
heuristic aimed at exactly that case, and it produced a real false positive:
`contracts/verdict.py`'s own `_CUT_REASON` ("Not run: cut from the seven-day build
(see docs/09-company/03-seven-day-plan.md).", the default `detail` on every
`STATIC_DELTA`/`RENEWED_FUZZING` gate in every `GateMatrix`) is a long unbroken
path-like run and would have been wrongly redacted on every single export. Given the
concrete leak class this review reproduced and reasoned about (`DATABASE_URL=
postgresql://...`-shaped content embedded in raw captured subprocess output — always
either multi-line, or carrying an assignment/scheme marker, or both), the checks
above close that class without the false-positive risk a length/entropy heuristic
would add on legitimate short structured text. Flagged here rather than silently
dropped; a tighter shape-allowlist (recognising only T5's exact canonical `_summarize`
grammar and rejecting everything else, including hand-written NOT_RUN prose) would
close this residual gap and is a reasonable follow-up once `detail`'s shape is fully
standardized upstream.
"""

from __future__ import annotations

import re

#: Every character a `GateResult.detail` value is allowed to contain, once the
#: `exit=<code>` token(s) have been stripped out by `sanitize_detail`. See the module
#: docstring for why this exact set and no more.
_SAFE_CHARS_RE = re.compile(r"^[A-Za-z0-9 .,:;'\"()/_%+=-]*$")

#: The one sanctioned use of `=` this allowlist grants: T5's own canonical
#: `_summarize` shape (`f"{tool}: {base}"` where `base` always contains
#: `exit=<returncode>`). Stripped out before the general `=`-ban below runs, so a
#: value can say `exit=1` but not `DATABASE_URL=...`.
_EXIT_CODE_TOKEN_RE = re.compile(r"\bexit=-?\d{1,6}\b")

#: The scheme separator every connection-string shape this review named shares.
_SCHEME_SEPARATOR = "://"

#: PEM-encoded key/certificate material always opens with this literal.
_PEM_MARKER = "-----BEGIN"

#: A generous ceiling for a one-line "user-safe summary". T5's own longest `_summarize`
#: shape ("Regression suite failed: N of M tests failed exit=-1") is well under 100
#: characters; 300 leaves headroom for a verbose hand-written NOT_RUN reason without
#: opening the door to a multi-KB dump smuggled in on a single line (no newline).
_MAX_SAFE_DETAIL_CHARS = 300

#: What every rejected `detail` is replaced with. Fixed and generic on purpose — it
#: names the fact of redaction, never a hint at what was redacted (a hint is its own
#: small leak).
REDACTED_DETAIL = "[redacted at export boundary: detail did not pass the safe-content check]"


def sanitize_detail(detail: str) -> str:
    """Return `detail` unchanged if it is safe to export, else `REDACTED_DETAIL`.

    Idempotent: `sanitize_detail(sanitize_detail(x)) == sanitize_detail(x)` for every
    `x`, so calling this more than once on the same value at more than one point in
    the export path (the defense-in-depth this module exists to provide) is always
    safe and never double-mangles an already-safe value.
    """
    if not detail:
        return detail
    if REDACTED_DETAIL in detail:
        return REDACTED_DETAIL
    if "\n" in detail or "\r" in detail or "\t" in detail:
        return REDACTED_DETAIL
    if len(detail) > _MAX_SAFE_DETAIL_CHARS:
        return REDACTED_DETAIL
    if _SCHEME_SEPARATOR in detail:
        return REDACTED_DETAIL
    if _PEM_MARKER in detail:
        return REDACTED_DETAIL
    without_exit_tokens = _EXIT_CODE_TOKEN_RE.sub("", detail)
    if "=" in without_exit_tokens:
        return REDACTED_DETAIL
    if not _SAFE_CHARS_RE.match(detail):
        return REDACTED_DETAIL
    return detail


# ---------------------------------------------------------------------------------------
# `redact_sanitizer_report` — #191, a narrower sibling of SEC-48 above.
#
# #191's own title labels this "SEC-50", but that number was already assigned (see
# D-075/D-082 above) to a different, already-closed finding — the `GateResult.detail`
# export-boundary gap this same file's `sanitize_detail` fixes. Flagged rather than
# perpetuated: this comment and the `.project/decisions.md` entry for this fix use
# the issue number (#191) as the primary reference and leave renumbering the
# SEC-registry entry itself to whoever owns that registry (cybersecurity/CTO).
# ---------------------------------------------------------------------------------------
#
# `sanitize_detail` above cannot be reused verbatim for `Finding.sanitizer_report`
# (`missions/models.py`, surfaced through `contracts.schemas.evidence.FindingDetail`):
# its all-or-nothing allowlist rejects *any* newline outright, and a real ASan/UBSan
# report is inherently multi-line — the header, the stack frames, and the `SUMMARY:`
# line each sit on their own line by construction (`adapters/cpp/sanitizer.py`'s own
# module docstring lays out the exact grammar). Running a captured report through
# `sanitize_detail` would not redact it, it would *discard* it — replacing the whole
# crash type, stack trace, and offending function with `REDACTED_DETAIL`, i.e. the
# opposite of `FindingDetail.sanitizer_report`'s own field docstring: "Sanitized
# sanitizer output: stack frames and the failure kind. Absolute paths and
# environment values are stripped before it reaches here." That promise needs
# selective, in-place redaction of the unsafe spans, not a full-value replacement.
#
# The shape that *does* fit already exists, one layer over: `services/model-gateway/
# gateway/context.py::_redact`, built for the structurally identical problem of
# handing a sanitizer excerpt to a local model (same two leak classes: an absolute
# filesystem path, and an environment-variable-style assignment). It could not be
# imported here as-is, for two independent reasons, not merely convenience:
#
# 1. `tests/architecture/test_fuzz_worker_isolation.py` / `test_worker_executor_
#    modules_import_boundary.py` are a security gate (D-073, SEC-54): the fuzz-worker
#    process — the one process in this system with container-runtime access — must
#    never be able to import the `gateway` package, specifically so a compromise of
#    it cannot reach the inference API. `workers/fuzzing/dispatch.py` is exactly the
#    caller this function serves, so an import edge from there into `gateway` would
#    fail that gate by design, not by accident.
# 2. `services/model-gateway` is deliberately its own dependency closure — its
#    `pytest.ini` sets `pythonpath = .` and nothing under `gateway/` imports back
#    into this repository's `contracts`/`packages`/`orchestrator` trees today. Adding
#    that edge in either direction is a real cross-service coupling decision, not a
#    same-PR refactor for a MEDIUM finding.
#
# So this function mirrors `gateway/context.py::_redact`'s two regexes/behaviour
# (same two leak classes, same "substitute the unsafe span, keep the rest of the
# line" technique) as the one already-reviewed shape for this exact threat model,
# rather than inventing a third, differently-shaped implementation — see this PR's
# handoff for the fuller reasoning on why a byte-for-byte import was not an option.
# If `gateway/context.py` and this function drift apart, that is a real signal (the
# threat model changed for one but not the other) rather than an oversight — but a
# reviewer touching either should check the other.

#: Same leak class as `sanitize_detail`'s `=`-ban above (`DATABASE_URL=postgresql://
#: ...`-shaped content), but here redacting only the offending line rather than the
#: whole report: an `ALLCAPS_NAME=value` assignment, optionally `export`-prefixed,
#: is not a shape a genuine ASan/UBSan grammar line (header, stack frame, or
#: `SUMMARY:`) ever produces — see `adapters/cpp/sanitizer.py`'s module docstring for
#: that grammar.
_ENV_ASSIGNMENT_LINE_RE = re.compile(r"(?im)^.*\b(?:export\s+)?[A-Z_][A-Z0-9_]{2,}\s*=\s*\S.*$")

#: Mirrors `gateway/context.py::_SECRET_LINE`: a named-secret assignment
#: (`api_key=...`, `token: ...`) regardless of casing, which `_ENV_ASSIGNMENT_LINE_RE`
#: alone would miss for a lowercase key.
_SECRET_LINE_RE = re.compile(r"(?im)^.*\b(?:api[_-]?key|token|secret|password)\s*[:=].*$")

#: Mirrors `gateway/context.py::_ABSOLUTE_PATH`: a Unix absolute path or a Windows
#: drive path. Substituted in place (not a whole-line drop) so a stack frame line
#: like ``#0 0x... in emit_tab /Users/alice/proj/src/decode.c:43`` keeps its frame
#: index, address, and function name, and loses only the path span — the file/line
#: a report needs to *identify* the crash already lives in `Finding.file_path`/
#: `Finding.line` (structured columns parsed by `adapters.cpp.sanitizer`), not in
#: this free-text field.
_ABSOLUTE_PATH_RE = re.compile(r"(?<![\w./-])(?:/[A-Za-z0-9._@%+=:,~ -]+)+|[A-Za-z]:\\[^\s:]+")

REDACTED_LINE = "[redacted: line removed - looked like a secret or environment assignment]"
REDACTED_PATH = "[redacted absolute path]"


def redact_sanitizer_report(report: str) -> str:
    """Strip absolute paths and environment/secret-shaped lines from a raw ASan/
    UBSan report, keeping everything else — crash type, stack frames, offsets.

    Unlike `sanitize_detail`, never replaces the whole value: a truncated-to-nothing
    "redacted" sanitizer report is useless to an operator triaging a real crash, and
    the two leak classes this targets (a path, an assignment line) are each
    identifiable and removable in place without discarding the rest.

    Idempotent for the same reason `sanitize_detail` is: neither regex matches its
    own placeholder text, so `redact_sanitizer_report(redact_sanitizer_report(x)) ==
    redact_sanitizer_report(x)`.
    """
    if not report:
        return report
    redacted = _SECRET_LINE_RE.sub(REDACTED_LINE, report)
    redacted = _ENV_ASSIGNMENT_LINE_RE.sub(REDACTED_LINE, redacted)
    redacted = _ABSOLUTE_PATH_RE.sub(REDACTED_PATH, redacted)
    return redacted
