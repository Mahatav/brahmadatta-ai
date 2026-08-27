# syntax=docker/dockerfile:1.7
#
# BASELINE/VERIFY toolchain image — #181/SEC-57. Pinned by `packages.sandbox.container.
# ContainerJail`'s `ContainerJailPolicy.image` and consumed by `workers/baseline/run.py::
# run_baseline_stage` (via `packages.sandbox.container_runner.ContainerJailRunner`) and
# `orchestrator/verification.py::run_verification` — the two stages SEC-57 wires into a
# container instead of the subprocess-only `packages/sandbox/jail.py::Jail` they used
# before this issue.
#
# Why this is a SEPARATE image from `fuzz-toolchain.Dockerfile`, not a shared one
# -----------------------------------------------------------------------------------
# `fuzz-toolchain.Dockerfile`'s own docstring explains FUZZ needed a different toolchain
# (LLVM clang, for `-fsanitize=fuzzer`) from what `adapters/cpp/pipeline.py`'s subprocess-
# jail path has always built against on this project's CI (`ubuntu-24.04`'s default
# gcc/g++). BASELINE and VERIFY are that gcc/g++ path — `demo/repositories/pktcfg`'s own
# CMakeLists.txt has no compiler preference of its own (`CMAKE_C_COMPILER_ID MATCHES
# "GNU|Clang|AppleClang"` in its warnings block treats all three as first-class), and
# `orchestrator/verification.py`'s own `-DPKTCFG_SANITIZE=ON` default has always run
# against whatever `cmake` found on the host, which is gcc/g++ in every CI run and every
# local dev checkout this project has actually exercised. Pinning THIS image to gcc/g++
# (not clang) keeps BASELINE/VERIFY's toolchain the one every existing green-baseline
# regression test and evidence bundle was already produced against — swapping to clang
# here as well would be a second, unrelated toolchain change riding along with the
# isolation fix this image exists for, and #181 is scoped to isolation, not toolchain
# migration.
#
# `git` is the one package this image needs that `fuzz-toolchain.Dockerfile` does not:
# `orchestrator/verification.py` applies a candidate diff with `git apply` (SEC-47's
# already-landed stdin-avoidance fix — see that module's own docstring — writes the diff
# to a file and passes it as a positional argument instead of piping it in), and D-024's
# `--network none` means a container that lacks a local `git` binary cannot fetch one at
# run time even if it wanted to.
#
# Isolation properties this image must not weaken (D-024, `ContainerJail`)
# ---------------------------------------------------------------------------
# Identical note to `fuzz-toolchain.Dockerfile`: `ContainerJailPolicy` always passes
# `--user <uid>:<gid>` (never 0), `--network none`, `--cap-drop ALL`, `--security-opt
# no-new-privileges`, and `--read-only` on every `docker run` this image is ever started
# under (`packages/sandbox/container.py::_docker_run_args`) — nothing in this Dockerfile
# can opt back into a broader default. The `USER` line below documents the uid a human
# running this image directly should expect, and matches `ContainerJailPolicy`'s own
# `uid: int = 10001`/`gid: int = 10001` defaults; it has no effect on `ContainerJail`
# itself, which always overrides it with an explicit `--user`.
#
# Pinning
# -------
# Same base image digest as `fuzz-toolchain.Dockerfile` (`ubuntu:24.04`/noble, resolved
# via `docker pull` in that PR) — one pinned base for every self-built image in this
# repository, not a second independent resolution. Package versions below are this
# session's real `apt-cache policy` candidates against that exact base, confirmed via a
# real `docker run` in this session (see this PR's handoff for the full output) —
# `infrastructure/scripts/build-baseline-verify-image.sh` builds this file and resolves
# the resulting image's own digest for `SANDBOX_BUILD_IMAGE`; `adapters/cpp/toolchain.py::
# require_pinned` refuses anything but `name@sha256:<64 hex>` for that setting.
FROM ubuntu@sha256:561618e2c15bf2397621dd04f96926663a3b5616c189cf7e38db7e82f5c538ea

ENV DEBIAN_FRONTEND=noninteractive

# gcc/g++          demo/repositories/pktcfg's own default toolchain — every existing
#                  BASELINE/VERIFY regression test and evidence bundle in this repository
#                  was produced against gcc/g++, not clang. Provides libasan/libubsan for
#                  `-DPKTCFG_SANITIZE=ON` (`-fsanitize=address,undefined`).
# cmake / make     demo/repositories/pktcfg's build system + CMake's default generator.
# git              `orchestrator/verification.py`'s `git apply` step (SEC-47).
# ca-certificates  Not used for network access (this image always runs with
#                  `--network none`) — kept only so `apt-get install` itself and any
#                  future TLS-touching tool resolve certs consistently with every other
#                  image in this repository.
#
# Version pins — same SEC-53 discipline `fuzz-toolchain.Dockerfile` follows: without
# these, a rebuild months from now silently pulls whatever noble/noble-updates/
# noble-security happen to carry that day. Resolved against this exact pinned
# `ubuntu@sha256:...` base, this session (`docker run ... apt-cache policy <pkg>` for
# each package below; see this PR's handoff for the full transcript).
ARG GCC_VERSION=4:13.2.0-7ubuntu1
ARG GXX_VERSION=4:13.2.0-7ubuntu1
ARG CMAKE_VERSION=3.28.3-1build7
ARG MAKE_VERSION=4.3-4.1build2
ARG GIT_VERSION=1:2.43.0-1ubuntu7.3
ARG CA_CERTIFICATES_VERSION=20260601~24.04.1

RUN apt-get update -qq \
 && apt-get install -y --no-install-recommends \
      gcc=${GCC_VERSION} \
      g++=${GXX_VERSION} \
      cmake=${CMAKE_VERSION} \
      make=${MAKE_VERSION} \
      git=${GIT_VERSION} \
      ca-certificates=${CA_CERTIFICATES_VERSION} \
 && rm -rf /var/lib/apt/lists/*

# Fixed uid/gid 10001 — same reasoning as `fuzz-toolchain.Dockerfile`'s identical block:
# matches `ContainerJailPolicy`'s own defaults, functionally moot for `ContainerJail`
# itself (always overridden by an explicit `--user`), documented for a human running
# this image directly.
RUN groupadd --gid 10001 builder \
 && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin builder

USER builder:builder
WORKDIR /workspace
