#!/bin/bash
# Build the BK-484 key-model proofs in the repo's Lean image.
# Usage: bash sdd/research/bk-484-key-model/lean/build.sh
#
# The project requires sdd/formal/lean by relative path, so both are copied
# into the container with their layout kept; the repo is mounted read-only.
# This folder is frozen: it pins Lean 4.34.1 here and in lean-toolchain, and is
# deliberately not on scripts/lean_check.sh's bump list. It builds its image
# from scripts/lean.Dockerfile, whose archive checksum is pinned to the repo's
# current Lean version: after a repo-wide bump, a fresh image build here fails
# the checksum unless the image is already cached. The README names the commit
# to check out to reproduce the proofs.
set -euo pipefail

export MSYS_NO_PATHCONV=1
LEAN_VERSION=4.34.1
IMAGE="remote-store-lean:${LEAN_VERSION}"
REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"

if ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
  echo "==> Building $IMAGE (first run only)"
  (cd "$REPO_ROOT/scripts" && docker build --quiet \
    --build-arg "LEAN_VERSION=${LEAN_VERSION}" \
    -t "$IMAGE" \
    -f lean.Dockerfile .)
fi

docker run --rm -v "$REPO_ROOT:/work:ro" "$IMAGE" bash -c 'set -e
  for p in sdd/formal/lean sdd/research/bk-484-key-model/lean; do
    mkdir -p "/tmp/r/$p"
    tar -C "/work/$p" --exclude=./.lake -cf - . | tar -C "/tmp/r/$p" -xf -
  done
  cd /tmp/r/sdd/research/bk-484-key-model/lean
  lake build'
