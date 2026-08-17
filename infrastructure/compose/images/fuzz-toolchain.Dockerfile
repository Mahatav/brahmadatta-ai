# syntax=docker/dockerfile:1.7
#
# Fuzzing-toolchain image — #189 (P0). Pinned by `packages.sandbox.container.
# ContainerJail`'s `ContainerJailPolicy.image` and consumed by
# `adapters/cpp/fuzzing.py::run_libfuzzer_campaign` / `workers/fuzzing/run.py::
# run_fuzzing_stage`, which is the only caller — this image is not a general-purpose
# build image, it exists to run ONE thing: a headless libFuzzer campaign against a CMake
# C/C++ target inside a `--network none`, non-root, `--cap-drop ALL` container.
#
# Why this had to be a new image, not `adapters/cpp`'s existing subprocess-jail path
# ---------------------------------------------------------------------------------
# `packages/sandbox/jail.py` (the subprocess jail `adapters/cpp/pipeline.py` uses for
# BASELINE/VERIFY) runs on whatever compiler the HOST happens to have — CI's ubuntu-24.04
# runner default is gcc/g++, which has libasan/libubsan for `-fsanitize=address,undefined`
# but does NOT ship libFuzzer (`-fsanitize=fuzzer` is a Clang/compiler-rt feature; GCC has
# no equivalent). `demo/repositories/pktcfg/fuzz/pktcfg_fuzz.c`'s own header states this
# directly: "requires a toolchain that ships libFuzzer (LLVM clang; Apple clang does not)."
# So FUZZ has always needed BOTH a different toolchain (real LLVM clang, not Apple clang,
# not gcc) AND a different isolation mechanism (a container, not a same-namespace
# subprocess — untrusted fuzzer input is exactly what #15/D-024 exists to contain). No
# image answering either half existed anywhere in this repo before this file — confirmed
# by grepping compose, both `.env.example` copies, `infrastructure/`, and `docker images`
# on the build host (issue #189's own repro steps, re-run in this session with the same
# empty result).
#
# Toolchain choice: matches CI's own signal, not a new pin invented here
# ------------------------------------------------------------------------
# `.github/workflows/ci.yml`'s `cpp-adapter` job runs on `ubuntu-24.04` and prints
# `cc --version` so a drifted runner image is visible rather than silently changing what
# "the toolchain" means between runs — the same discipline this Dockerfile follows.
# ubuntu:24.04 (noble)'s `clang` metapackage resolves to clang-18 (confirmed via
# `apt-cache policy clang` inside the pinned base image, this session): the same major
# distribution family CI already builds C/C++ targets on, so `adapters/cpp/fuzzing.py`'s
# CMake invocation (`-DCMAKE_C_COMPILER=clang`) sees the same `-Wall -Wextra -Wshadow
# -Wconversion` diagnostics family as the gcc build, and there is exactly one new
# toolchain to reason about (Clang 18), not two (Clang here, a different Clang version if
# a laptop's Apple clang were ever pressed into this role instead).
#
# `libclang-rt-18-dev` is the compiler-rt package that ships `libclang_rt.fuzzer-*.a` —
# without it `-fsanitize=fuzzer` fails to link at all. ASan/UBSan runtimes ship in the
# same package family (`libclang-rt-18-dev` also carries `libclang_rt.asan-*.a` /
# `.ubsan_standalone-*.a`), so this one package is both requirements from #189's scope:
# "libFuzzer + the sanitizer toolchain already used by adapters/cpp (ASan/UBSan,
# matching what workers/baseline / orchestrator/verification.py already build against)."
# `demo/repositories/pktcfg/CMakeLists.txt`'s `PKTCFG_SANITIZE`/`PKTCFG_FUZZ` options
# both compile against these same runtime libraries, verified in this session (see the
# PR for the full `cmake --build` + libFuzzer campaign log): AddressSanitizer's
# heap-buffer-overflow report against pktcfg's seeded defect came out of THIS image,
# unmodified, with no separate ASan-only build step.
#
# `--memory` (cgroup) vs `RLIMIT_AS`: this image does NOT need
# MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS-equivalent sizing
# ------------------------------------------------------------------------------------
# `adapters/cpp/variants.py` documents a real, measured trap on the OTHER sandbox
# (`packages/sandbox/jail.py`'s subprocess jail): `RLIMIT_AS` (`ulimit -v`) constrains
# virtual address space, and ASan's shadow-memory reservation needs ~28 TiB of it
# regardless of how much memory the target actually touches — so a "reasonable"
# `RLIMIT_AS` (2 GiB, 16 GiB, 64 GiB) aborts every ASan-instrumented process at startup,
# and only an effectively-unlimited `RLIMIT_AS` clears it.
#
# `ContainerJail` does not use `RLIMIT_AS` at all — `_docker_run_args` passes `--memory`,
# which the kernel's cgroup v2 memory controller enforces against actual RESIDENT
# (charged) memory, not reserved virtual address space. Checked directly in this session,
# not assumed: this exact image, built from this exact Dockerfile, ran pktcfg's
# ASan+UBSan+libFuzzer build to a real heap-buffer-overflow crash under `docker run
# --memory 2g` (a quarter of `ContainerJailPolicy`'s own 8192 MiB default) with no
# allocation failure of any kind — ASan's shadow-memory `mmap` reservation is
# `PROT_NONE`/never-touched over most of its range, so it is never charged against the
# cgroup's resident-memory accounting in the first place. `packages/sandbox/jail.py`'s
# owner (not this image) is the one with the RLIMIT_AS trap; this container path is
# genuinely immune, for a structural reason (cgroup memory != rlimit address-space
# memory), not because nobody hit the input size that would trigger it.
#
# Isolation properties this image must not weaken (D-024, `ContainerJail`)
# ---------------------------------------------------------------------------
# `ContainerJailPolicy` always passes `--user <uid>:<gid>` explicitly (never 0) and
# `--network none`/`--cap-drop ALL`/`--security-opt no-new-privileges`/`--read-only` —
# every one of those is set by the CALLER on every `docker run`, unconditionally, so
# nothing in this Dockerfile can opt back into a broader default even if it wanted to.
# The `USER` line below is for a human running this image directly (`docker run -it
# fuzz-toolchain ...`) and documentation of the uid this image expects its writable
# workspace to be owned/permitted for; `ContainerJail.create()` already `chmod 0o777`s
# the bind-mounted worktree specifically because the container's fixed uid is not the
# host's (see that method's docstring), so no image-side ownership setup is needed or
# attempted here.
#
# Pinning
# -------
# `ubuntu:24.04`, pinned by multi-arch index digest — resolved and pulled in this
# session, same rule as every other base-image pin in this repository (control-api's
# `python@sha256:...`, postgres-tls's `postgres@sha256:...`): a tag is mutable and can be
# repointed at new code with no change on our side.
#
# THIS image itself (not just its base) is also pinned by digest at the point it is
# consumed — `adapters/cpp/toolchain.py::require_pinned` refuses anything but
# `name@sha256:<64 hex>` for `ContainerJailPolicy.image`, and `.` throughout this
# repository's Dockerfiles pins upstream bases only, never a self-built image, because no
# other self-built image here is ever referenced by digest from Python code — this is the
# first one that is. `infrastructure/scripts/build-fuzz-image.sh` builds this Dockerfile
# and resolves the digest to hand to `SANDBOX_FUZZ_IMAGE`; see that script's header for
# how (and its documented caveat about storage-driver dependence).
FROM ubuntu@sha256:561618e2c15bf2397621dd04f96926663a3b5616c189cf7e38db7e82f5c538ea

ENV DEBIAN_FRONTEND=noninteractive

# clang            LLVM C/C++ compiler driver (resolves to clang-18 on noble).
# cmake            demo/repositories/pktcfg's build system (CMakeLists.txt, PKTCFG_FUZZ).
# make             CMake's default generator on this image is "Unix Makefiles"; without
#                  this package `cmake --build` fails at configure time with "CMake was
#                  unable to find a build program" — hit and fixed in this session.
# libclang-rt-18-dev   libFuzzer + ASan + UBSan runtime archives for clang-18
#                      (libclang_rt.fuzzer-*.a / .asan-*.a / .ubsan_standalone-*.a).
# ca-certificates  Not used for network access (the container runs with --network none
#                  for every real invocation) — kept only so `apt-get install` itself and
#                  any future TLS-touching tool inside the image resolve certs the same
#                  way every other image in this repository does. Harmless, standard.
RUN apt-get update -qq \
 && apt-get install -y --no-install-recommends \
      clang \
      cmake \
      make \
      libclang-rt-18-dev \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Fixed uid/gid 10001, matching `ContainerJailPolicy`'s own default (`uid: int = 10001`,
# `gid: int = 10001` in packages/sandbox/container.py) and control-api.Dockerfile's `app`
# user — same "a fixed high uid/gid, predictable, cannot collide with a real host account"
# reasoning. Functionally moot for `ContainerJail` itself (it always passes `--user
# 10001:10001` explicitly, overriding whatever `USER` this image declares), but this is
# also the image's documented default for a human running it directly.
RUN groupadd --gid 10001 fuzzer \
 && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin fuzzer

USER fuzzer:fuzzer
WORKDIR /workspace
