#!/bin/bash
# Verify Dafny formal specs locally via Docker (dotnet/sdk + dafny release).
# Usage: bash scripts/dafny_verify.sh [file.dfy ...]
# No args = verify all four spec files.
#
# Requires Docker Desktop running.  First run pulls the SDK image
# and downloads the Dafny release with bundled Z3.
set -euo pipefail

# Disable MSYS/Git-Bash automatic path conversion (mangles Docker -v mounts).
export MSYS_NO_PATHCONV=1

DAFNY_VERSION=4.9.1
DAFNY_SHA256=697ee703b39414b3904dc8c132e51481982f52205c1658f3374d313a284d43eb
IMAGE=mcr.microsoft.com/dotnet/sdk:8.0
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ $# -eq 0 ]; then
  FILES=(BackendContract.dfy MemoryBackend.dfy DepthCounting.dfy ResourceSafety.dfy)
else
  FILES=("$@")
fi

# Build verify commands: download Dafny release with bundled Z3
CMDS="apt-get update -qq > /dev/null 2>&1"
CMDS="$CMDS && apt-get install -y -qq unzip > /dev/null 2>&1"
CMDS="$CMDS && curl -sSL https://github.com/dafny-lang/dafny/releases/download/v${DAFNY_VERSION}/dafny-${DAFNY_VERSION}-x64-ubuntu-20.04.zip -o /tmp/dafny.zip"
CMDS="$CMDS && echo '${DAFNY_SHA256}  /tmp/dafny.zip' | sha256sum --check --quiet"
CMDS="$CMDS && unzip -q /tmp/dafny.zip -d /opt"
CMDS="$CMDS && chmod +x /opt/dafny/dafny /opt/dafny/z3/bin/z3-*"
for f in "${FILES[@]}"; do
  CMDS="$CMDS && echo '==> Verifying $f' && /opt/dafny/dafny verify /work/$f"
done

docker run --rm \
  -v "$REPO_ROOT/sdd/formal:/work:ro" \
  "$IMAGE" \
  bash -c "$CMDS"
