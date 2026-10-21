#!/bin/bash
# Build the BK-468 key-model proofs in the repo's Lean image.
# Usage: bash sdd/research/bk-468-key-model/lean/build.sh
#
# The project requires sdd/formal/lean by relative path, so both are copied
# into the container with their layout kept; the repo is mounted read-only.
# The image is the one scripts/lean_check.sh builds on its first run.
set -euo pipefail

export MSYS_NO_PATHCONV=1
IMAGE="remote-store-lean:4.34.1"
REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"

if ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
  echo "==> $IMAGE is missing: run 'bash scripts/lean_check.sh' once to build it" >&2
  exit 2
fi

docker run --rm -v "$REPO_ROOT:/work:ro" "$IMAGE" bash -c 'set -e
  for p in sdd/formal/lean sdd/research/bk-468-key-model/lean; do
    mkdir -p "/tmp/r/$p"
    tar -C "/work/$p" --exclude=./.lake -cf - . | tar -C "/tmp/r/$p" -xf -
  done
  cd /tmp/r/sdd/research/bk-468-key-model/lean
  lake build'
