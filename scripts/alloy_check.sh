#!/bin/bash
# Run every command of an Alloy model, natively or via Docker.
# Usage: bash scripts/alloy_check.sh [model.als]
#
# Default target is sdd/formal/alloy/StoreAxioms.als. Every command in the
# model carries an `expect`; Alloy exits non-zero when any outcome differs
# from it, and this script passes that exit code through.
#
# Runner: a native `alloy` on PATH reporting the pinned version (set up per
# sdd/formal/README.md § Running the verifier); otherwise Docker, whose first run
# builds the local image remote-store-alloy:<version> from
# scripts/alloy.Dockerfile. ALLOY_RUNNER=docker forces Docker.
set -euo pipefail

# Disable MSYS/Git-Bash automatic path conversion (mangles Docker -v mounts).
export MSYS_NO_PATHCONV=1

# Bump together with scripts/alloy.Dockerfile, .claude/hooks/session-init.sh,
# the setup block in sdd/formal/README.md and the Local toolchain row.
ALLOY_VERSION=6.2.0
IMAGE="remote-store-alloy:${ALLOY_VERSION}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

MODEL="${1:-sdd/formal/alloy/StoreAxioms.als}"

if [ "${ALLOY_RUNNER:-}" != "docker" ] && command -v alloy > /dev/null 2>&1; then
  NATIVE_VERSION="$(alloy version 2> /dev/null | tail -n 1)"
  if [ "$NATIVE_VERSION" = "$ALLOY_VERSION" ]; then
    echo "==> Running Alloy ${ALLOY_VERSION} (native) on $MODEL"
    OUT="$(mktemp -d)"
    trap 'rm -rf "$OUT"' EXIT
    cd "$REPO_ROOT"
    alloy exec -f -t none -o "$OUT/out" "$MODEL"
    exit $?
  fi
  echo "==> Native alloy reports '${NATIVE_VERSION}', not ${ALLOY_VERSION}; using Docker"
fi

if ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
  echo "==> Building $IMAGE (first run only)"
  (cd "$REPO_ROOT/scripts" && docker build --quiet \
    --build-arg "ALLOY_VERSION=${ALLOY_VERSION}" \
    -t "$IMAGE" \
    -f alloy.Dockerfile .)
fi

echo "==> Running Alloy ${ALLOY_VERSION} (Docker) on $MODEL"
# Solutions go to a scratch directory inside the container; only the summary
# table and any expectation errors reach the console.
docker run --rm \
  -v "$REPO_ROOT:/work:ro" \
  -w /work \
  "$IMAGE" \
  exec -f -t none -o /tmp/alloy-out "$MODEL"
