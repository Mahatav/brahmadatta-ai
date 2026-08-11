"""Structural parsing of ASan/UBSan reports.

Neither sanitizer has a machine-readable output mode — both write a formatted text report
to stderr. "Structural" here means what #27's acceptance criteria ask for explicitly:
*"type, stack trace, offending function"* extracted into named fields by a parser with a
fixed grammar, not a `SanitizerReport.sanitizer_report: str` blob with the raw text pasted
in (that field still exists downstream, in `contracts.schemas.evidence.FindingDetail`, and
this module's job is to produce the structured fields that go *alongside* it).

Two report grammars, verified against real captured output during development (see
`tests/test_sanitizer.py`, which embeds the actual `pktcfg_replay` transcript from
`crash/crash-literal-tab.bin` rather than a hand-written fixture):

**AddressSanitizer**::

    ==<pid>==ERROR: AddressSanitizer: <kind> on address 0x... at pc ... bp ... sp ...
    <access> of size <n> at 0x... thread T0
        #0 0x... in <function> <file>:<line>
        #1 0x... in <function> <file>:<line>
        ...
    SUMMARY: AddressSanitizer: <kind> <file>:<line> in <function>

**UndefinedBehaviorSanitizer**::

    <file>:<line>:<col>: runtime error: <message>
        #0 0x... in <function> <file>:<line>
        ...
    SUMMARY: UndefinedBehaviorSanitizer: <kind> <file>:<line>:<col> in <function>

The `SUMMARY:` line is the parser's primary source for `kind`, `file`, `line`, and
`function` — it is the one line both sanitizers commit to keeping stable, specifically so
tools can key off it. The stack trace is parsed independently from the numbered `#N` frames
so a report is still useful if a future sanitizer version reformats its summary line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["SanitizerFinding", "StackFrame", "parse_sanitizer_output"]

_ASAN_HEADER = re.compile(r"==\d+==ERROR: AddressSanitizer: (?P<kind>\S+)")
_UBSAN_HEADER = re.compile(
    r"^(?P<file>[^\s:][^:]*):(?P<line>\d+):(?P<col>\d+): runtime error: (?P<message>.+)$",
    re.MULTILINE,
)
_FRAME = re.compile(
    r"^\s*#(?P<index>\d+)\s+0x[0-9a-fA-F]+\s+in\s+(?P<function>\S+)"
    r"(?:\s+(?P<file>[^\s()][^:]*):(?P<line>\d+)(?::(?P<col>\d+))?)?",
    re.MULTILINE,
)
_ASAN_SUMMARY = re.compile(
    r"^SUMMARY:\s*AddressSanitizer:\s*(?P<kind>\S+)\s+(?P<file>[^\s:]+):(?P<line>\d+)"
    r"(?::\d+)?\s+in\s+(?P<function>\S+)",
    re.MULTILINE,
)
_UBSAN_SUMMARY = re.compile(
    r"^SUMMARY:\s*UndefinedBehaviorSanitizer:\s*(?P<kind>\S+)\s+(?P<file>[^\s:]+):(?P<line>\d+)"
    r"(?::(?P<col>\d+))?\s+in\s+(?P<function>\S+)",
    re.MULTILINE,
)
_SYMBOL_OFFSET = re.compile(r"\+0x[0-9a-fA-F]+$")


@dataclass(frozen=True, slots=True)
class StackFrame:
    index: int
    function: str
    file: str | None
    line: int | None

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "function": self.function,
            "file": self.file,
            "line": self.line,
        }


@dataclass(frozen=True, slots=True)
class SanitizerFinding:
    """One sanitizer violation, structurally decoded.

    :attr:`function` and the ``file``/``line`` pair are the "offending function" #27 asks
    for, taken from the `SUMMARY:` line when present and from the first stack frame
    otherwise.
    """

    tool: str  # "ADDRESS_SANITIZER" | "UNDEFINED_BEHAVIOUR_SANITIZER" — matches AnalyzerTool
    kind: str
    message: str
    function: str
    file: str | None
    line: int | None
    stack: tuple[StackFrame, ...] = field(default_factory=tuple)
    raw: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "tool": self.tool,
            "kind": self.kind,
            "message": self.message,
            "function": self.function,
            "file": self.file,
            "line": self.line,
            "stack": [frame.as_dict() for frame in self.stack],
            "raw": self.raw,
        }


def _parse_stack(block: str) -> tuple[StackFrame, ...]:
    frames = []
    for match in _FRAME.finditer(block):
        frames.append(
            StackFrame(
                index=int(match.group("index")),
                function=_normalize_function(match.group("function")),
                file=match.group("file"),
                line=int(match.group("line")) if match.group("line") else None,
            )
        )
    return tuple(frames)


def _normalize_function(function: str) -> str:
    return _SYMBOL_OFFSET.sub("", function)


def _asan_finding(text: str, header: re.Match[str]) -> SanitizerFinding:
    # The primary stack is the frames between the header line and the next blank line —
    # ASan's "allocated by" / "freed by" traces start after a blank line and are a
    # different stack (the allocation site, not the crash site), so they are excluded
    # from the primary trace and left in `raw` for a human to read if they need it.
    after_header = text[header.end() :]
    block = after_header.split("\n\n", 1)[0]
    stack = _parse_stack(block)

    kind: str
    function: str
    file: str | None
    line: int | None

    summary = _ASAN_SUMMARY.search(text)
    if summary:
        kind = summary.group("kind")
        function = _normalize_function(summary.group("function"))
        file = summary.group("file")
        line = int(summary.group("line"))
    elif stack:
        kind = header.group("kind")
        function = stack[0].function
        file = stack[0].file
        line = stack[0].line
    else:
        kind = header.group("kind")
        function = "<unknown>"
        file = None
        line = None

    return SanitizerFinding(
        tool="ADDRESS_SANITIZER",
        kind=kind,
        message=header.group(0),
        function=function,
        file=file,
        line=line,
        stack=stack,
        raw=text,
    )


def _ubsan_findings(text: str) -> tuple[SanitizerFinding, ...]:
    findings = []
    headers = list(_UBSAN_HEADER.finditer(text))
    for idx, header in enumerate(headers):
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        block = text[header.end() : end]
        stack = _parse_stack(block.split("\n\n", 1)[0])
        kind: str
        function: str
        file: str | None
        line: int | None
        summary = _UBSAN_SUMMARY.search(block)
        if summary:
            kind = summary.group("kind")
            function = _normalize_function(summary.group("function"))
            file = summary.group("file")
            line = int(summary.group("line"))
        elif stack:
            kind = "undefined-behavior"
            function = stack[0].function
            file = stack[0].file
            line = stack[0].line
        else:
            kind = "undefined-behavior"
            function = "<unknown>"
            file = header.group("file")
            line = int(header.group("line"))
        findings.append(
            SanitizerFinding(
                tool="UNDEFINED_BEHAVIOUR_SANITIZER",
                kind=kind,
                message=header.group("message"),
                function=function,
                file=file,
                line=line,
                stack=stack,
                raw=header.group(0) + block,
            )
        )
    return tuple(findings)


def parse_sanitizer_output(text: str) -> tuple[SanitizerFinding, ...]:
    """Extract every sanitizer finding from a process's combined stderr/stdout.

    Returns an empty tuple when neither sanitizer's grammar matches — callers must treat
    that as "no finding," never fabricate one from a non-zero exit code alone. See
    `tests/test_sanitizer.py::test_no_sanitizer_output_produces_no_finding`.
    """
    findings: list[SanitizerFinding] = []
    asan_header = _ASAN_HEADER.search(text)
    if asan_header:
        findings.append(_asan_finding(text, asan_header))
    findings.extend(_ubsan_findings(text))
    return tuple(findings)
