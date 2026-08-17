#!/usr/bin/env bash
# Build the fuzzing-toolchain image (#189) and print a pinned `name@sha256:...` reference
# suitable for `SANDBOX_FUZZ_IMAGE` / `ContainerJailPolicy.image` —
# `adapters/cpp/toolchain.py::require_pinned` refuses anything else.
#
#   infrastructure/scripts/build-fuzz-image.sh
#   SANDBOX_FUZZ_IMAGE="$(infrastructure/scripts/build-fuzz-image.sh)"   # digest only, on stdout
#
# Why this needs a script at all, instead of "just `docker build -t ... `"
# --------------------------------------------------------------------------
# Every OTHER image pin in this repository (postgres@sha256:..., nginx-unprivileged@
# sha256:..., python@sha256:...) pins an UPSTREAM image someone else published to a
# registry — `docker pull` always returns a real manifest digest for those, because a
# registry round-trip is exactly what produced the digest. This is the first image in the
# repository that is built HERE and then has to be referenced by digest from Python code
# (`ContainerJailPolicy.image`) — no prior Dockerfile in infrastructure/compose/images/
# needed its own output pinned that way; control-api/command-center/postgres-tls are all
# referenced by compose service name or `build:` block, never by a Python-side digest
# check.
#
# Whether a local `docker build` alone produces a usable digest depends on the daemon's
# image store, and this is the one thing this script cannot paper over:
#
#   containerd image store (Docker Desktop's default since ~4.x; opt-in on Linux via
#   `dockerd --feature containerd-snapshotter` / daemon.json `"features": {"containerd-
#   snapshotter": true}`) — the image is content-addressed the moment it is built, and
#   `docker inspect --format '{{index .RepoDigests 0}}'` returns a real, immediately
#   `docker run`-able `name@sha256:...` reference with NO push required. Verified directly
#   in this session: built, referenced by that exact digest string, and run with
#   `--network none --cap-drop ALL --user 10001:10001 --read-only` — the full D-024 flag
#   set — with no error.
#
#   classic overlay2 graphdriver (still the default on a plain `apt install docker.io` /
#   most CI runner images, GitHub-hosted `ubuntu-24.04` included as of this writing) — a
#   freshly built image has NO RepoDigest until it is pushed to (and, strictly, pulled
#   back from) a registry. `docker image inspect --format '{{.RepoDigests}}'` prints `[]`.
#
# This script tries the free path first (no registry needed) and tells you plainly, on
# stderr, which path it took — never silently guesses. If you need the classic-graphdriver
# path, set FUZZ_IMAGE_REGISTRY to a registry you can push to
# (e.g. `localhost:5000`, started via `docker run -d -p 5000:5000 registry:3`, or a real
# registry) and re-run; the script pushes and resolves the digest from the push response
# instead.
#
# What this does NOT do: wire the resulting digest into `.env` for you. Pinning is a
# decision an operator makes deliberately (same reasoning as every other digest pin in
# this repository being a literal string in a tracked file, not resolved at container
# start) — this script's whole job is to hand you the string; `SANDBOX_FUZZ_IMAGE=` in
# `.env.example` documents where it goes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKERFILE="${REPO_ROOT}/infrastructure/compose/images/fuzz-toolchain.Dockerfile"
BUILD_CONTEXT="${REPO_ROOT}/infrastructure/compose/images"
IMAGE_NAME="${FUZZ_IMAGE_NAME:-brahmadatta-fuzz-toolchain}"
LOCAL_TAG="${IMAGE_NAME}:local"

if ! command -v docker >/dev/null 2>&1; then
  echo "::error:: docker is not on PATH — cannot build the fuzzing-toolchain image" >&2
  exit 1
fi

echo "building ${LOCAL_TAG} from ${DOCKERFILE}" >&2
docker build -f "${DOCKERFILE}" -t "${LOCAL_TAG}" "${BUILD_CONTEXT}" >&2

# Toolchain versions actually baked into THIS image, printed for the log — the same
# discipline ci.yml's cpp-adapter job follows for the host toolchain ("a drifted runner
# image is visible in the log rather than silently changing what 'the toolchain' means").
echo "--- toolchain versions in ${LOCAL_TAG} ---" >&2
docker run --rm --user 10001:10001 "${LOCAL_TAG}" sh -c 'clang --version; cmake --version' >&2
echo "-------------------------------------------" >&2

repo_digest="$(docker inspect --format='{{index .RepoDigests 0}}' "${LOCAL_TAG}" 2>/dev/null || true)"

if [[ -n "${repo_digest}" ]]; then
  echo "resolved a local RepoDigest (containerd image store) — no registry push needed" >&2
  echo "${repo_digest}"
  exit 0
fi

echo "no local RepoDigest available (classic graphdriver storage) — falling back to a registry push" >&2

if [[ -z "${FUZZ_IMAGE_REGISTRY:-}" ]]; then
  echo "::error:: this docker daemon's image store does not expose a digest for a locally" >&2
  echo "::error:: built image (docker info | grep driver-type would show something other" >&2
  echo "::error:: than io.containerd.snapshotter.v1). Set FUZZ_IMAGE_REGISTRY to a" >&2
  echo "::error:: registry you can push to (e.g. a local 'docker run -d -p 5000:5000" >&2
  echo "::error:: registry:3' for localhost:5000) and re-run." >&2
  exit 1
fi

remote_tag="${FUZZ_IMAGE_REGISTRY}/${IMAGE_NAME}:local"
docker tag "${LOCAL_TAG}" "${remote_tag}" >&2
docker push "${remote_tag}" >&2
pushed_digest="$(docker inspect --format='{{index .RepoDigests 0}}' "${remote_tag}" 2>/dev/null || true)"
if [[ -z "${pushed_digest}" ]]; then
  echo "::error:: pushed to ${remote_tag} but could not resolve a RepoDigest afterward" >&2
  exit 1
fi
echo "${pushed_digest}"
