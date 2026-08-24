# pktcfg — controlled demo target

`pktcfg` parses **PKTC**, a compact binary configuration packet: an 8-byte header
followed by a list of named entries, each carrying a length-prefixed name and a
length-prefixed value. Values can be flagged as escaped, in which case they are run
through a small unescaper (`\n`, `\r`, `\0`, `\\`, `\xHH`, `\t`). Tabs, whether written
as the `\t` escape or as a literal 0x09 byte, are normalised to `PKT_TAB_WIDTH` spaces.

## Authorization

**This target is purpose-built by the Brahmadatta AI team, for Brahmadatta AI, and is
authorized for Brahmadatta's own automated testing — analysis, fuzzing, crash
reproduction, patch generation, and patch verification.** It contains a deliberately
seeded memory-safety defect, documented below. It is a test fixture and nothing else: it
is not a library anyone should depend on, it is not deployed anywhere, and no third
party's code or intellectual property is involved.

It exists because the demo of record needs a target that is guaranteed to build, whose
test baseline is guaranteed green, and whose defect is guaranteed reachable. See
[`docs/09-company/01-vision-and-p0-cut.md`](../../../docs/09-company/01-vision-and-p0-cut.md)
§5.4 option A, and §3 for the nine-step run this feeds.

## The seeded defect

| Field | Value |
|---|---|
| Class | Heap buffer overflow (out-of-bounds write), CWE-787, CWE-131 |
| Root cause | `src/decode.c:75-77` — the sizing pass omits the literal-tab case that the writing pass handles |
| Crash site | `src/decode.c:31` (`emit_tab`), reached from `src/decode.c:136`; also `src/decode.c:141` when later bytes follow the tab |
| Allocation | `src/parse.c:108`, sized by `src/parse.c:106` |
| Trigger | Any entry value containing a literal 0x09 byte |
| Overflow size | `PKT_TAB_WIDTH - 1` bytes per literal tab, so 3 bytes with the current width |
| Entry point | `pktcfg_fuzz_one_input(const uint8_t *data, size_t size)` |
| Reproducer | `crash/crash-literal-tab.bin` (22 bytes) |

`pkt_decoded_length()` and `pkt_decode_into()` in `src/decode.c` walk the same bytes and
have to agree on how many bytes come out. They agree on every escape sequence. They
disagree on one thing: `pkt_decode_into()` expands a literal 0x09 byte into four spaces
(`decode.c:131-139`), while `pkt_decoded_length()` counts it as a single byte along with
every other ordinary character (`decode.c:75-77`). `pkt_parse()` allocates from the
sizing pass and then writes with the other one, so every literal tab in a value writes
three bytes past the end of the heap allocation.

The framing checks in `src/parse.c` are correct. Magic, version, reserved field, name
length bounds, and both truncation checks all hold, and the tests cover them. The defect
is entirely inside the decoder's two-pass contract, which is where this class of bug
tends to live in real code.

The literal-tab path has no unit test at baseline. That is deliberate and is the honest
reason a defect like this survives review: the escape form is tested, the equivalent
literal form is not.

## Reproducing it

```sh
cmake -S . -B build-asan -DCMAKE_BUILD_TYPE=Debug -DPKTCFG_SANITIZE=ON
cmake --build build-asan
./build-asan/pktcfg_replay crash/crash-literal-tab.bin 5
```

`pktcfg_replay` feeds a file straight into the fuzzable entry point, so the reproducer
runs on any toolchain, with or without a fuzzing engine. A `-DPKTCFG_FUZZ=ON` build adds
a libFuzzer harness (`fuzz/pktcfg_fuzz.c`) and instruments the library for coverage; it
needs an LLVM clang that ships libFuzzer, which Apple clang does not. Seeds for it are in
`corpus/`.

## The benchmark candidate patches

The point of this target is not the crash. It is step 7 of the minimum viable demo, where
a plausible-looking patch has to be **rejected** by the gates rather than accepted. The
candidate fixtures are checked in under `patches/`.

**`patches/candidate-a-correct-bounds-fix.patch` — the correct fix.** Teaches
`pkt_decoded_length()` that a literal tab expands, so the allocation matches what gets
written. Crash gone, all 8 tests still pass.

**`patches/candidate-b-rejected-crash-only-fix.patch` — the tempting wrong fix.** Changes
`emit_tab()` to write one space instead of four. This is what the ASan stack trace points
at, it is minimal, and it does eliminate the crash — by deleting the feature that was
overflowing. Crash gone, and `test_tab_expansion` fails.

**`patches/candidate-p-policy-rejected-out-of-scope.patch` — the policy refusal.** Touches
`README.md` instead of the source allowlist. It is intentionally applyable, but the policy
gate must reject it before compile or verification work starts.

**`patches/candidate-c-compile-failure.patch` — the compile failure.** Changes one allowed
source file and stays tiny, but introduces an unbalanced block. The policy gate should pass
it and the compile gate should reject it without marking the mission itself failed.

### The test that catches the bad patch

**`tests/test_tab_expansion.c`.** It asserts that a `\t` escape decodes to exactly
`PKT_TAB_WIDTH` spaces, over three separate values and their lengths. Candidate B makes
six of its fourteen checks fail:

```
FAIL tests/test_tab_expansion.c:30: cfg->entries[0].value == "col1 col2", expected "col1    col2"
FAIL tests/test_tab_expansion.c:31: cfg->entries[0].value_len == 9, expected 12
FAIL tests/test_tab_expansion.c:39: cfg->entries[0].value == "a b c", expected "a    b    c"
FAIL tests/test_tab_expansion.c:40: cfg->entries[0].value_len == 5, expected 11
FAIL tests/test_tab_expansion.c:48: cfg->entries[0].value == " value", expected "    value"
FAIL tests/test_tab_expansion.c:49: cfg->entries[0].value_len == 6, expected 9
```

The asymmetry works because the crash is caused by the *sizing* function while the
overflow is *observed* in the writing function. Patching where the sanitizer points fixes
the symptom and breaks the behaviour. Patching one function away fixes the cause and
preserves it.

That test is labelled `asymmetry` in CTest, so it can be singled out:

```sh
ctest -L asymmetry
```

Do not relax those assertions to make a patch pass. If they get weakened, the demo has no
rejection to show.

## Building and testing

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build
cd build && ctest --output-on-failure
```

| Option | Default | Effect |
|---|---|---|
| `PKTCFG_SANITIZE` | `OFF` | `-fsanitize=address,undefined`, frame pointers, `-g` |
| `PKTCFG_FUZZ` | `OFF` | libFuzzer harness plus `-fsanitize=fuzzer-no-link` on the library |
| `PKTCFG_WERROR` | `OFF` | `-Werror` on the library |

Warnings are on by default (`-Wall -Wextra -Wshadow -Wconversion`) and the tree is clean
under them, so anything a worker sees in a build log is a real signal.

The baseline suite is green with and without sanitizers. That is a property worth
protecting: `PKTCFG_SANITIZE=ON` plus `ctest` is a meaningful gate precisely because none
of the eight tests trips the seeded defect on its own.

## Layout

```
include/pktcfg/pktcfg.h   public API, wire constants, the fuzzable entry point
src/parse.c               framing: header, entry headers, bounds checks
src/decode.c              value decoding and tab normalisation  <-- the defect
src/config.c              lifetime and lookup
src/fuzz_entry.c          pktcfg_fuzz_one_input()
fuzz/pktcfg_fuzz.c        libFuzzer harness (PKTCFG_FUZZ=ON)
tools/pktcfg_replay.c     deterministic reproducer runner
tests/                    8 CTest cases
corpus/                   fuzzing seeds
crash/                    the reproducer for the seeded defect
patches/                  the two candidates for the verification demo
```

## Wire format

```
header, 8 bytes
  0..3   magic "PKTC"
  4      version, must be 1
  5      entry_count
  6..7   reserved, u16 little-endian, must be zero

entry, repeated entry_count times
  0      name_len, 1..63
  1      flags, bit 0 = PKT_FLAG_ESCAPED
  2..3   value_len, u16 little-endian
  4..    name bytes, then value bytes
```

Bytes after the declared entries are ignored. Every other malformation is an error, and
`pkt_status_str()` names it for the evidence report.

## Git history and the bisect answer key

This repository's own git history (`git -C demo/repositories/pktcfg log`, once the
history is materialised — see below) is a constructed fixture, seeded by
[issue #5](https://github.com/brahmadatta-ai/brahmadatta-ai/issues/5) for the `git
bisect` demo scenario (P1-1) and the bisect-timeline panel (#26). It is not derived from
the outer `brahmadatta-ai` repository's own commit history: `pktcfg` is a self-contained
nested git repository, materialised from a bundle checked into the outer repo (see
"Materialising the nested git history" below), specifically so that `git bisect` can run
against it directly, the ordinary way, without any awareness of the monorepo around it.

The defect documented above was introduced at exactly one commit:

| Field | Value |
|---|---|
| Commit | `114383dd517e49e1285b53608184cb744adb2aaa` |
| Subject | `decode: normalise literal tab bytes the same way as the \t escape` |
| Date | 2025-05-19 |
| Parent (last known-good) | `1fe6d02d4209f256d5436a661fb7b9698a6ba745` — `fuzz: add libFuzzer harness and a starter seed corpus` |
| Child (first known-bad after) | `af7c7472fdc2f662b3e98c769d26cdd3d38bfd59` — `fuzz: check in the literal-tab crash reproducer` |

That commit adds the `if (c == '\t') { out = emit_tab(dst, out); ... }` branch to
`pkt_decode_into()` in `src/decode.c` without adding the matching branch to
`pkt_decoded_length()`. Every commit before it builds clean and passes all available
tests, with no crash under `-DPKTCFG_SANITIZE=ON` against `crash/crash-literal-tab.bin`.
Every commit at or after it builds clean and passes the same CTest suite (the literal-tab
path has no unit test, by design — see above) but crashes under ASan against that same
reproducer.

Verified by hand with a checker script kept *outside* this repository, at
`demo/repositories/pktcfg-bisect-check.sh` in the outer `brahmadatta-ai` repo (deliberately
not tracked inside `pktcfg`'s own history — `git bisect run` checks out a different commit
before every invocation, and a script that is itself part of the bisected range can vanish
or change out from under it; the embedded 22-byte reproducer means the script also doesn't
depend on `crash/crash-literal-tab.bin` existing in whichever commit is checked out, which
it does not before commit `af7c747`):

```sh
cd demo/repositories/pktcfg
git bisect start
git bisect bad HEAD
git bisect good 1fe6d02d4209f256d5436a661fb7b9698a6ba745
git bisect run ../pktcfg-bisect-check.sh
```

which lands on `114383dd517e49e1285b53608184cb744adb2aaa` and no other commit. See
`demo/repositories/pktcfg-bisect-check.sh` for the exact build-and-replay logic (configures
`-DPKTCFG_SANITIZE=ON`, builds `pktcfg_replay`, feeds it the reproducer bytes, and exits
non-zero only on a sanitizer abort — never on a CTest failure, since the baseline suite is
green on both sides of the regression).

### Materialising the nested git history

`demo/repositories/pktcfg/.git` is not committed to the outer `brahmadatta-ai`
repository — a directory containing its own `.git` would otherwise become a submodule
gitlink, which is more machinery than this fixture needs, and the outer repo's own
`.gitignore` excludes `demo/repositories/pktcfg/.git/` for exactly that reason. Instead
the full, real history (14 commits, this one included) is shipped as a git bundle at
`demo/repositories/pktcfg-history.bundle`, one directory up from here. To get a working
`.git` back:

```sh
cd demo/repositories/pktcfg
git init -q -b main
git fetch -q ../pktcfg-history.bundle main:main
git checkout -q -f main
```

That last step is a hard checkout by design: it makes the working tree match the
bundle's `main` exactly, which is also exactly what's already tracked by the outer repo,
so nothing should actually change on disk. `demo/repositories/restore-pktcfg-history.sh`
does the above and is safe to re-run.
