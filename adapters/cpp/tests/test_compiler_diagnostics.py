"""Compiler diagnostic parsing, pinned against real captured gcc/clang transcripts.

Both captures below came from actually compiling the same small C file
(reproduced in this module for reference) with `-Wall -Wextra -Wshadow
-Wconversion` — the exact flags `demo/repositories/pktcfg/CMakeLists.txt`
already builds with — never hand-typed. `_REAL_CLANG_CAPTURE` is AppleClang
21.0.0 (`cc --version`, this development host, macOS arm64). `_REAL_GCC_CAPTURE`
is gcc 13.4.0, real GNU gcc (not AppleClang's `/usr/bin/gcc` shim), from the
`gcc:13` Docker Hub image (`docker run --rm gcc:13 gcc --version`), the same
family of compiler `infrastructure/scripts/build-analyze-image.sh`'s sibling
`control-api.Dockerfile` installs via `build-essential` for the real Linux
worker image this stage actually runs in.

The source that produced both (for anyone re-verifying — not itself under
test, just provenance):

    #include <stdio.h>

    int compute(int limit) {
        int unused_total = 0;
        short small = 70000;
        for (int limit = 0; limit < 10; limit++) {
            printf("%d\\n", limit);
        }
        return small;
    }

    int main(void) {
        return compute(5);
    }
"""

from __future__ import annotations

from adapters.cpp.compiler_diagnostics import parse_compiler_diagnostics

# `cc -Wall -Wextra -Wshadow -Wconversion -c sample.c -o sample.o` (AppleClang 21.0.0).
_REAL_CLANG_CAPTURE = """\
sample.c:6:14: warning: declaration shadows a local variable [-Wshadow]
    6 |     for (int limit = 0; limit < 10; limit++) {
      |              ^
sample.c:3:17: note: previous declaration is here
    3 | int compute(int limit) {
      |                 ^
sample.c:4:9: warning: unused variable 'unused_total' [-Wunused-variable]
    4 |     int unused_total = 0;
      |         ^~~~~~~~~~~~
sample.c:3:17: warning: unused parameter 'limit' [-Wunused-parameter]
    3 | int compute(int limit) {
      |                 ^
sample.c:5:19: warning: implicit conversion from 'int' to 'short' changes value from 70000 to 4464 [-Wconstant-conversion]
    5 |     short small = 70000;
      |           ~~~~~   ^~~~~
4 warnings generated.
"""

# `gcc -Wall -Wextra -Wshadow -Wconversion -c sample.c -o sample.o` (gcc 13.4.0, `gcc:13`).
_REAL_GCC_CAPTURE = """\
sample.c: In function 'compute':
sample.c:5:19: warning: overflow in conversion from 'int' to 'short int' changes value from '70000' to '4464' [-Woverflow]
    5 |     short small = 70000;
      |                   ^~~~~
sample.c:6:14: warning: declaration of 'limit' shadows a parameter [-Wshadow]
    6 |     for (int limit = 0; limit < 10; limit++) {
      |              ^~~~~
sample.c:3:17: note: shadowed declaration is here
    3 | int compute(int limit) {
      |             ~~~~^~~~~
sample.c:4:9: warning: unused variable 'unused_total' [-Wunused-variable]
    4 |     int unused_total = 0;
      |         ^~~~~~~~~~~~
sample.c:3:17: warning: unused parameter 'limit' [-Wunused-parameter]
    3 | int compute(int limit) {
      |             ~~~~^~~~~
"""

# A real, clean build's compiler output has no diagnostic lines at all
# (`demo/repositories/pktcfg` builds this way today, verified directly with
# `-Wall -Wextra -Wshadow -Wconversion` already on — see this PR's handoff).
_REAL_CLEAN_BUILD_OUTPUT = """\
[  4%] Building C object CMakeFiles/pktcfg.dir/src/config.c.o
[  8%] Building C object CMakeFiles/pktcfg.dir/src/decode.c.o
[ 17%] Building C object CMakeFiles/pktcfg.dir/src/parse.c.o
[ 21%] Linking C static library libpktcfg.a
[ 21%] Built target pktcfg
"""


def test_clean_build_produces_no_diagnostics() -> None:
    assert parse_compiler_diagnostics(_REAL_CLEAN_BUILD_OUTPUT) == ()


def test_empty_output_produces_no_diagnostics() -> None:
    assert parse_compiler_diagnostics("") == ()


def test_clang_warnings_are_parsed_structurally() -> None:
    diagnostics = parse_compiler_diagnostics(_REAL_CLANG_CAPTURE)

    # 4 warnings + 1 note, in source order, exactly as clang printed them.
    assert [d.severity for d in diagnostics] == [
        "warning",
        "note",
        "warning",
        "warning",
        "warning",
    ]

    shadow = diagnostics[0]
    assert shadow.file == "sample.c"
    assert shadow.line == 6
    assert shadow.column == 14
    assert shadow.severity == "warning"
    assert shadow.flag == "-Wshadow"
    assert shadow.message == "declaration shadows a local variable"

    note = diagnostics[1]
    assert note.severity == "note"
    assert note.file == "sample.c"
    assert note.line == 3
    assert note.column == 17
    assert note.flag is None  # gcc/clang never tag a `note:` with a `-W` flag

    unused_var = diagnostics[2]
    assert unused_var.flag == "-Wunused-variable"
    assert unused_var.message == "unused variable 'unused_total'"
    assert unused_var.line == 4

    unused_param = diagnostics[3]
    assert unused_param.flag == "-Wunused-parameter"
    assert unused_param.line == 3
    assert unused_param.column == 17

    conversion = diagnostics[4]
    assert conversion.flag == "-Wconstant-conversion"
    assert conversion.line == 5
    assert "70000 to 4464" in conversion.message
    # The raw line is preserved verbatim (minus surrounding whitespace) for a
    # human reading the finding later.
    assert conversion.raw.startswith("sample.c:5:19: warning:")


def test_gcc_warnings_are_parsed_structurally_and_agree_with_clang_on_locations() -> None:
    diagnostics = parse_compiler_diagnostics(_REAL_GCC_CAPTURE)

    # gcc's own "sample.c: In function 'compute':" context line has no
    # `:line:column:` and must not be mis-parsed as a sixth diagnostic.
    assert len(diagnostics) == 5

    by_flag = {d.flag: d for d in diagnostics if d.flag}
    assert set(by_flag) == {
        "-Woverflow",
        "-Wshadow",
        "-Wunused-variable",
        "-Wunused-parameter",
    }

    # Same source, same lines: gcc's shadow/unused-variable/unused-parameter
    # warnings land on the identical (file, line) pairs clang reported for the
    # semantically equivalent diagnostics, even though the two compilers use
    # different flag names for the truncation warning (-Woverflow vs
    # -Wconstant-conversion) and slightly different wording throughout.
    assert by_flag["-Wshadow"].line == 6
    assert by_flag["-Wunused-variable"].line == 4
    assert by_flag["-Wunused-parameter"].line == 3
    assert by_flag["-Woverflow"].line == 5

    notes = [d for d in diagnostics if d.severity == "note"]
    assert len(notes) == 1
    assert notes[0].line == 3


def test_exact_duplicate_diagnostics_are_collapsed() -> None:
    # The same diagnostic line, verbatim, twice over (as would happen if a
    # warning-producing header is compiled into two translation units) must
    # collapse to one CompilerDiagnostic, not two.
    text = _REAL_CLANG_CAPTURE + _REAL_CLANG_CAPTURE
    once = parse_compiler_diagnostics(_REAL_CLANG_CAPTURE)
    twice = parse_compiler_diagnostics(text)
    assert once == twice


def test_a_distinct_diagnostic_on_the_same_line_is_not_dropped() -> None:
    # sample.c:3:17 carries two DIFFERENT real diagnostics (unused-parameter
    # warning, and the shadow note) - same file, same line, same column even -
    # and both must survive. Same-line collapsing is a caller-side policy
    # (dedup against a different TOOL's finding on the same line, #23's own
    # acceptance criterion), never something this parser does to two of its
    # own distinct diagnostics.
    diagnostics = parse_compiler_diagnostics(_REAL_CLANG_CAPTURE)
    same_location = [d for d in diagnostics if d.file == "sample.c" and d.line == 3]
    assert len(same_location) == 2
    assert {d.severity for d in same_location} == {"warning", "note"}
