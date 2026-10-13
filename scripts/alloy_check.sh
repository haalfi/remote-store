#!/bin/bash
# Run every command of an Alloy model via Docker.
# Usage: bash scripts/alloy_check.sh [model.als]
#
# Default target is sdd/formal/alloy/StoreAxioms.als. Every command in the
# model carries an `expect`; Alloy exits non-zero when any outcome differs
# from it, and this script passes that exit code through.
#
# Requires Docker running. First run builds the local image
# remote-store-alloy:<version> from scripts/alloy.Dockerfile. No local jar,
# no local Java install.
set -euo pipefail

# Disable MSYS/Git-Bash automatic path conversion (mangles Docker -v mounts).
export MSYS_NO_PATHCONV=1

ALLOY_VERSION=6.2.0
IMAGE="remote-store-alloy:${ALLOY_VERSION}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

MODEL="${1:-sdd/formal/alloy/StoreAxioms.als}"

if ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
  echo "==> Building $IMAGE (first run only)"
  (cd "$REPO_ROOT/scripts" && docker build --quiet \
    --build-arg "ALLOY_VERSION=${ALLOY_VERSION}" \
    -t "$IMAGE" \
    -f alloy.Dockerfile .)
fi

echo "==> Running Alloy on $MODEL"
# Solutions go to a scratch directory inside the container; only the summary
# table and any expectation errors reach the console.
docker run --rm \
  -v "$REPO_ROOT:/work:ro" \
  -w /work \
  "$IMAGE" \
  exec -f -t none -o /tmp/alloy-out "$MODEL"
