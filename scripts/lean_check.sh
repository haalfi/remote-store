#!/bin/bash
# Build a Lean 4 project (check every proof in it), natively or via Docker.
# Usage: bash scripts/lean_check.sh [project-dir]
#
# Default target is sdd/formal/lean, the store model's proofs. The project
# path is resolved from the repo root and must lie inside the repo (Docker
# mounts only the repo). The project's lakefile turns warnings into errors,
# so a `sorry` fails the build, and `lake build` exits non-zero on any error;
# this script passes that exit code through.
#
# Runner: a native `lean` on PATH reporting the pinned version from inside the
# project (with elan, the project's lean-toolchain file selects it; setup in
# sdd/formal/README.md § Running the verifier); otherwise Docker, whose first
# run builds the local image remote-store-lean:<version> from
# scripts/lean.Dockerfile. LEAN_RUNNER=docker forces Docker.
set -euo pipefail

# Disable MSYS/Git-Bash automatic path conversion (mangles Docker -v mounts).
export MSYS_NO_PATHCONV=1

# Bump together with scripts/lean.Dockerfile, the project's lean-toolchain,
# .claude/hooks/session-init.sh, the setup block in sdd/formal/README.md and
# the Local toolchain row.
LEAN_VERSION=4.34.1
IMAGE="remote-store-lean:${LEAN_VERSION}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PROJECT="${1:-sdd/formal/lean}"

if [ "${LEAN_RUNNER:-}" != "docker" ] && command -v lean > /dev/null 2>&1; then
  # A native lean that cannot start, or cannot fetch the pinned toolchain,
  # must fall back, not exit.
  NATIVE_VERSION="$(cd "$REPO_ROOT/$PROJECT" && lean --version 2> /dev/null)" || NATIVE_VERSION="(failed to start)"
  case "$NATIVE_VERSION" in
    "Lean (version ${LEAN_VERSION},"*)
      echo "==> Building $PROJECT with Lean ${LEAN_VERSION} (native)"
      cd "$REPO_ROOT/$PROJECT"
      lake build
      exit $?
      ;;
  esac
  echo "==> Native lean reports '${NATIVE_VERSION}', not ${LEAN_VERSION}; using Docker"
fi

if ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
  echo "==> Building $IMAGE (first run only)"
  (cd "$REPO_ROOT/scripts" && docker build --quiet \
    --build-arg "LEAN_VERSION=${LEAN_VERSION}" \
    -t "$IMAGE" \
    -f lean.Dockerfile .)
fi

echo "==> Building $PROJECT with Lean ${LEAN_VERSION} (Docker)"
# The repo is mounted read-only; the project is copied, without any native
# build directory, to a scratch directory inside the container and built there.
docker run --rm \
  -v "$REPO_ROOT:/work:ro" \
  "$IMAGE" \
  bash -c 'set -e
    mkdir /tmp/project
    tar -C "/work/$1" --exclude=./.lake -cf - . | tar -C /tmp/project -xf -
    cd /tmp/project
    lake build' _ "$PROJECT"
