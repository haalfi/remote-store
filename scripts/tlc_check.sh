#!/bin/bash
# Run TLC (TLA+ model checker) on a model via Docker.
# Usage: bash scripts/tlc_check.sh [tla-dir] [config-name]
#
# Example: bash scripts/tlc_check.sh sdd/research/tla-poc MC
# Runs:    java -jar tla2tools.jar -config MC.cfg MC.tla   (inside the image)
#
# Requires Docker Desktop running. First run builds the local image
# remote-store-tlc:<version> from scripts/tlc.Dockerfile. No local jar,
# no local Java install.
set -euo pipefail

# Disable MSYS/Git-Bash automatic path conversion (mangles Docker -v mounts).
export MSYS_NO_PATHCONV=1

TLA_VERSION=1.8.0
IMAGE="remote-store-tlc:${TLA_VERSION}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

TLA_DIR="${1:-sdd/research/tla-poc}"
CONFIG="${2:-MC}"

if ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
  echo "==> Building $IMAGE (first run only)"
  (cd "$REPO_ROOT/scripts" && docker build --quiet \
    --build-arg "TLA_VERSION=${TLA_VERSION}" \
    -t "$IMAGE" \
    -f tlc.Dockerfile .)
fi

echo "==> Running TLC on $TLA_DIR/$CONFIG.tla"
docker run --rm \
  -v "$REPO_ROOT:/work" \
  -w "/work/$TLA_DIR" \
  "$IMAGE" \
  -config "${CONFIG}.cfg" \
  -metadir /tmp/states \
  "${CONFIG}.tla"
