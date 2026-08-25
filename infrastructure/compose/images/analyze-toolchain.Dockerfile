# syntax=docker/dockerfile:1.7
#
# Static-analysis-toolchain image — #22, D-144. Pinned by `packages.sandbox.container.
# ContainerJail`'s `ContainerJailPolicy.image` and consumed by
# `adapters/semgrep/run_semgrep.py::run_semgrep_scan` (the only caller) — this image is
# not a general-purpose build image, it exists to run ONE thing: a headless Semgrep scan
# against a mounted source tree, offline, inside a `--network none`, non-root,
# `--cap-drop ALL` container. See `infrastructure/compose/images/fuzz-toolchain.Dockerfile`
# for the sibling image this one mirrors (same isolation posture, same reasoning), and
# `adapters/semgrep/run_semgrep.py`'s own module docstring for why Semgrep runs against a
# vendored, repo-committed ruleset (`adapters/semgrep/rules/`) rather than
# `--config=p/...` / `--config=auto` — the registry fetch those need cannot reach anywhere
# from a `--network none` container (`docs/03-technical/23-security-plan.md`: "Outbound
# network denied by default"), and D-024's `ContainerJailPolicy.network` hardcodes
# `--network none` unconditionally regardless of what this Dockerfile does.
#
# Semgrep itself needs network only at BUILD time (`pip install`, resolving from PyPI on
# whatever host builds this image) — never at scan time. That is the entire reason this
# can be a real, live Semgrep run inside a network-denied production sandbox: the tool and
# its ruleset are both already present in the image/workspace before the container with
# `--network none` ever starts; nothing it does at scan time needs a live fetch.
#
# Pinning
# -------
# `python@sha256:...` below is the exact same base-image digest
# `infrastructure/compose/images/control-api.Dockerfile` already pins (`python:3.12-slim-
# bookworm`), reused rather than re-resolved so this repository is not tracking two
# independent pins of what is meant to be the same upstream image.
#
# `semgrep==1.173.0` is pinned to an exact PyPI release, not a floating `semgrep` /
# `semgrep>=...` — the same "a tag is mutable, a digest/exact version is not" reasoning
# every other pin in this repository follows. Resolved and installed in this session
# (`docker build` of this exact file); `semgrep --version` inside the built image printed
# `1.173.0`. Bumping this pin is a deliberate, reviewable one-line diff.
#
# THIS image itself (not just its base) is also pinned by digest at the point it is
# consumed — `adapters.semgrep.errors.require_pinned` refuses anything but
# `name@sha256:<64 hex>` for `ContainerJailPolicy.image`, mirroring
# `adapters.cpp.toolchain.require_pinned`'s identical rule for `SANDBOX_FUZZ_IMAGE`.
# `infrastructure/scripts/build-analyze-image.sh` builds this Dockerfile and resolves the
# digest to hand to `SANDBOX_ANALYZE_IMAGE`.
FROM python@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

ARG SEMGREP_VERSION=1.173.0

RUN pip install --no-cache-dir "semgrep==${SEMGREP_VERSION}"

# Fixed uid/gid 10001, matching `ContainerJailPolicy`'s own default (`uid: int = 10001`,
# `gid: int = 10001` in packages/sandbox/container.py) — same "a fixed high uid/gid,
# predictable, cannot collide with a real host account" reasoning as every other image in
# this repository. Functionally moot for `ContainerJail` itself (it always passes
# `--user 10001:10001` explicitly, overriding whatever `USER` this image declares), but
# this is also the image's documented default for a human running it directly.
RUN groupadd --gid 10001 analyzer \
 && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin analyzer

USER analyzer:analyzer
WORKDIR /workspace
