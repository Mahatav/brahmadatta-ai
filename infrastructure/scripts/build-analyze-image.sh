#!/usr/bin/env bash
# Build the static-analysis-toolchain image (#22, D-144) and print a pinned
# `name@sha256:...` reference suitable for `SANDBOX_ANALYZE_IMAGE` /
# `ContainerJailPolicy.image` — `adapters/semgrep/errors.py::require_pinned` refuses
# anything else.
#
#   infrastructure/scripts/build-analyze-image.sh
#   SANDBOX_ANALYZE_IMAGE="$(infrastructure/scripts/build-analyze-image.sh)"   # digest only, on stdout
#
# Mirrors `build-fuzz-image.sh` byte-for-byte in structure and reasoning — see that
# script's own header for the full explanation of the two docker-image-store paths
# (containerd snapshotter vs. classic overlay2 graphdriver) this one also has to
# handle. Not re-derived here to avoid two copies of the same reasoning drifting
# apart; only the image name/Dockerfile/version-probe command differ.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKERFILE="${REPO_ROOT}/infrastructure/compose/images/analyze-toolchain.Dockerfile"
BUILD_CONTEXT="${REPO_ROOT}/infrastructure/compose/images"
IMAGE_NAME="${ANALYZE_IMAGE_NAME:-brahmadatta-analyze-toolchain}"
LOCAL_TAG="${IMAGE_NAME}:local"

if ! command -v docker >/dev/null 2>&1; then
  echo "::error:: docker is not on PATH — cannot build the analyze-toolchain image" >&2
  exit 1
fi

image_store="$(docker info --format '{{.DriverStatus}}' 2>/dev/null | grep -o 'driver-type[^]]*' || true)"
if [[ "${image_store}" == *io.containerd.snapshotter.v1* ]]; then
  echo "docker image store: containerd snapshotter detected — a local build should resolve a usable digest with no registry push" >&2
else
  echo "docker image store: containerd snapshotter NOT detected (classic overlay2 graphdriver, or undetermined) — expect this script to need ANALYZE_IMAGE_REGISTRY; see build-fuzz-image.sh's header for the same fallback shape" >&2
fi

echo "building ${LOCAL_TAG} from ${DOCKERFILE}" >&2
docker build -f "${DOCKERFILE}" -t "${LOCAL_TAG}" "${BUILD_CONTEXT}" >&2

echo "--- toolchain versions in ${LOCAL_TAG} ---" >&2
docker run --rm --user 10001:10001 "${LOCAL_TAG}" semgrep --version >&2
echo "-------------------------------------------" >&2

repo_digest="$(docker inspect --format='{{index .RepoDigests 0}}' "${LOCAL_TAG}" 2>/dev/null || true)"

if [[ -n "${repo_digest}" ]]; then
  echo "resolved a local RepoDigest (containerd image store) — no registry push needed" >&2
  echo "${repo_digest}"
  exit 0
fi

echo "no local RepoDigest available (classic graphdriver storage) — falling back to a registry push" >&2

if [[ -z "${ANALYZE_IMAGE_REGISTRY:-}" ]]; then
  echo "::error:: this docker daemon's image store does not expose a digest for a locally" >&2
  echo "::error:: built image (docker info | grep driver-type would show something other" >&2
  echo "::error:: than io.containerd.snapshotter.v1). Set ANALYZE_IMAGE_REGISTRY to a" >&2
  echo "::error:: registry you can push to (e.g. a local 'docker run -d -p 5000:5000" >&2
  echo "::error:: registry:3' for localhost:5000) and re-run." >&2
  exit 1
fi

remote_tag="${ANALYZE_IMAGE_REGISTRY}/${IMAGE_NAME}:local"
docker tag "${LOCAL_TAG}" "${remote_tag}" >&2
docker push "${remote_tag}" >&2
pushed_digest="$(docker inspect --format='{{index .RepoDigests 0}}' "${remote_tag}" 2>/dev/null || true)"
if [[ -z "${pushed_digest}" ]]; then
  echo "::error:: pushed to ${remote_tag} but could not resolve a RepoDigest afterward" >&2
  exit 1
fi
echo "${pushed_digest}"
