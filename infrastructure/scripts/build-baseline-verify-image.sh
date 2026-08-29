#!/usr/bin/env bash
# Build the BASELINE/VERIFY toolchain image (#181/SEC-57) and print a pinned
# `name@sha256:...` reference suitable for `SANDBOX_BUILD_IMAGE` /
# `ContainerJailPolicy.image` — `adapters/cpp/toolchain.py::require_pinned` refuses
# anything else.
#
#   infrastructure/scripts/build-baseline-verify-image.sh
#   SANDBOX_BUILD_IMAGE="$(infrastructure/scripts/build-baseline-verify-image.sh)"
#
# Mirrors `build-fuzz-image.sh` line for line — same image-store caveat (a freshly
# built image only has a usable local `RepoDigest` when the docker daemon uses the
# containerd image store; classic overlay2 needs a registry round-trip), same
# `FUZZ_IMAGE_REGISTRY`-shaped escape hatch (`BASELINE_VERIFY_IMAGE_REGISTRY` here).
# See that script's own header for the full explanation, not repeated here.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKERFILE="${REPO_ROOT}/infrastructure/compose/images/build-toolchain.Dockerfile"
BUILD_CONTEXT="${REPO_ROOT}/infrastructure/compose/images"
IMAGE_NAME="${BASELINE_VERIFY_IMAGE_NAME:-brahmadatta-build-toolchain}"
LOCAL_TAG="${IMAGE_NAME}:local"

if ! command -v docker >/dev/null 2>&1; then
  echo "::error:: docker is not on PATH — cannot build the BASELINE/VERIFY toolchain image" >&2
  exit 1
fi

echo "building ${LOCAL_TAG} from ${DOCKERFILE}" >&2
docker build -f "${DOCKERFILE}" -t "${LOCAL_TAG}" "${BUILD_CONTEXT}" >&2

echo "--- toolchain versions in ${LOCAL_TAG} ---" >&2
docker run --rm --user 10001:10001 "${LOCAL_TAG}" sh -c 'gcc --version; cmake --version; git --version' >&2
echo "-------------------------------------------" >&2

repo_digest="$(docker inspect --format='{{index .RepoDigests 0}}' "${LOCAL_TAG}" 2>/dev/null || true)"

if [[ -n "${repo_digest}" ]]; then
  echo "resolved a local RepoDigest (containerd image store) — no registry push needed" >&2
  echo "${repo_digest}"
  exit 0
fi

echo "no local RepoDigest available (classic graphdriver storage) — falling back to a registry push" >&2

if [[ -z "${BASELINE_VERIFY_IMAGE_REGISTRY:-}" ]]; then
  echo "::error:: this docker daemon's image store does not expose a digest for a locally" >&2
  echo "::error:: built image. Set BASELINE_VERIFY_IMAGE_REGISTRY to a registry you can" >&2
  echo "::error:: push to (e.g. a local 'docker run -d -p 5000:5000 registry:3' for" >&2
  echo "::error:: localhost:5000) and re-run." >&2
  exit 1
fi

remote_tag="${BASELINE_VERIFY_IMAGE_REGISTRY}/${IMAGE_NAME}:local"
docker tag "${LOCAL_TAG}" "${remote_tag}" >&2
docker push "${remote_tag}" >&2
pushed_digest="$(docker inspect --format='{{index .RepoDigests 0}}' "${remote_tag}" 2>/dev/null || true)"
if [[ -z "${pushed_digest}" ]]; then
  echo "::error:: pushed to ${remote_tag} but could not resolve a RepoDigest afterward" >&2
  exit 1
fi
echo "${pushed_digest}"
