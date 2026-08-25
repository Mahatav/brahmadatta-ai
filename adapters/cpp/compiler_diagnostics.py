"""Structural parsing of gcc/clang compiler diagnostics (#23).

Neither gcc nor clang has a stable machine-readable diagnostic format on the
path this project builds through (`-fdiagnostics-format=json` exists on gcc but
not on the AppleClang toolchain this codebase was partly developed against, and
`packages/sandbox/policy.py`'s env allowlist and this project's "no
project-specific compiler flags beyond what a target already ships" rule both
argue against forcing one compiler-specific flag onto every C/C++ target this
adapter might ever see). Both compilers do share one text grammar, though —
originally gcc's, adopted verbatim by clang specifically so tooling like this
does not need two parsers:

    <file>:<line>:<column>: <severity>: <message> [<-Wflag>]

verified against real, freshly-compiled output from both compilers (never
hand-typed): AppleClang 21.0.0 (macOS host) and gcc 13.4.0 (`gcc:13` container
image), same source file, same `-Wall -Wextra -Wshadow -Wconversion` flags
`demo/repositories/pktcfg/CMakeLists.txt` already builds with. See
`adapters/cpp/tests/test_compiler_diagnostics.py` for the exact captured text.

Same "structural, not scraped" contract `adapters/cpp/sanitizer.py` already
established for ASan/UBSan output: named fields (file, line, column, severity,
message, the `-W` flag) out of a fixed grammar, not a free-text blob pasted
into an evidence field. `raw` still carries the original line for a human, the
same way `SanitizerFinding.raw` does.

## What this module deliberately does not parse

* Compiler *note:* lines (e.g. "previous declaration is here") are structurally
  parsed (so they never get misread as a fourth diagnostic file:line:severity
  the caller has to special-case) but are not, by themselves, findings — a
  `note:` only ever appears attached to a preceding `warning:`/`error:` and
  restates *its* location, not a new one. `parse_compiler_diagnostics` returns
  them (`severity="note"`) for a caller that wants the full transcript; the one
  production caller (`workers/baseline/dispatch.py`) filters to
  `warning`/`error` before turning anything into a `Finding` row.
* Build-system noise (`[ 17%] Building C object ...`, CMake's own `Error`
  lines, `N warnings generated.`) never matches the grammar above — no `:line:
  column:` in any of those — so it is excluded structurally, not by a denylist
  of literal strings that would need updating for every CMake/Make version.
* GCC's `<file>: In function 'X':` context line (printed once before a run of
  diagnostics for that function) also never matches — it has no `:line:` at
  all — so it is silently skipped rather than mis-parsed as a diagnostic with
  no line number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["CompilerDiagnostic", "parse_compiler_diagnostics"]

#: `file:line:column: severity: message`, column optional (clang always emits
#: it for a diagnostic with a caret location; a small number of gcc
#: diagnostics — e.g. some link-time or whole-program ones — omit it).
_DIAGNOSTIC_RE = re.compile(
    r"^(?P<file>[^\n:]+):(?P<line>\d+):(?:(?P<column>\d+):)?\s*"
    r"(?P<severity>error|warning|note):\s*(?P<message>.*)$",
    re.MULTILINE,
)

#: The `[-Wsomething]` tag gcc/clang append to (almost) every `warning:` line.
#: Never present on `error:`/`note:` lines in either compiler's real output.
_FLAG_RE = re.compile(r"\s*\[(?P<flag>-W[a-zA-Z0-9=,-]+)\]\s*$")


@dataclass(frozen=True, slots=True)
class CompilerDiagnostic:
    """One real gcc/clang diagnostic line, structurally decoded.

    :attr:`file` is exactly what the compiler printed — normalizing it
    relative to a mission's source root (stripping the jail/workspace prefix,
    the same treatment Semgrep's own `_strip_root` gives `SemgrepMatch.
    file_path` in `adapters/semgrep/parser.py`) is the caller's job, once it
    knows the mission's source directory; this module has no such context and
    does not guess one.
    """

    severity: str  # "error" | "warning" | "note"
    file: str
    line: int
    column: int | None
    message: str
    flag: str | None
    raw: str

    def as_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "flag": self.flag,
            "raw": self.raw,
        }


def parse_compiler_diagnostics(text: str) -> tuple[CompilerDiagnostic, ...]:
    """Extract every gcc/clang diagnostic line from a build's combined
    stdout/stderr.

    Returns an empty tuple when nothing matches the grammar — a clean build
    with no diagnostics at all is a real, valid outcome (`demo/repositories/
    pktcfg` itself builds this way today, even with `-Wall -Wextra -Wshadow
    -Wconversion` on — see this module's docstring), never papered over with a
    fabricated finding.

    De-duplicates exact repeats (identical file/line/column/severity/message)
    in first-seen order: a warning inside a header shared by several
    translation units prints once per TU that includes it, and that is a
    build-system artifact of *how many times the same line was compiled*, not
    evidence of more than one distinct diagnostic location.
    """
    seen: set[tuple[str, int, int | None, str, str]] = set()
    out: list[CompilerDiagnostic] = []
    for match in _DIAGNOSTIC_RE.finditer(text):
        message = match.group("message").strip()
        flag: str | None = None
        flag_match = _FLAG_RE.search(message)
        if flag_match:
            flag = flag_match.group("flag")
            message = message[: flag_match.start()].rstrip()

        column = int(match.group("column")) if match.group("column") else None
        file_ = match.group("file").strip()
        line = int(match.group("line"))
        severity = match.group("severity")

        key = (file_, line, column, severity, message)
        if key in seen:
            continue
        seen.add(key)

        out.append(
            CompilerDiagnostic(
                severity=severity,
                file=file_,
                line=line,
                column=column,
                message=message,
                flag=flag,
                raw=match.group(0).strip(),
            )
        )
    return tuple(out)
