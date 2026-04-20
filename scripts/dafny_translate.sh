#!/bin/bash
# Translate Dafny formal specs to Python via Docker (dotnet/sdk + dafny release).
# Usage: bash scripts/dafny_translate.sh [file.dfy ...]
# No args = translate MemoryBackend.dfy (the one with a committed oracle).
#
# For each <stem>.dfy, writes sdd/formal/<stem>-py/ with the compiled oracle
# plus the Dafny Python runtime (_dafny/, System_/), then applies the class
# reorder (see sdd/formal/README.md § Class-ordering fix) so module_.py is
# importable as written.
#
# Proof-only files (DepthCounting.dfy, ResourceSafety.dfy, BackendContract.dfy)
# compile to near-empty packages with no committed oracle downstream — pass
# them explicitly if you want to inspect the output.
#
# Requires Docker Desktop running.  Uses the same SDK image and Dafny release
# as scripts/dafny_verify.sh so the SHA256 pin stays in one place per release.
set -euo pipefail

# Disable MSYS/Git-Bash automatic path conversion (mangles Docker -v mounts).
export MSYS_NO_PATHCONV=1

DAFNY_VERSION=4.11.0
DAFNY_SHA256=a46a9ff7cdd720f7955854c78e95df13f4cfe6b80691b05f8654fe19e8267179
IMAGE=mcr.microsoft.com/dotnet/sdk:8.0
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ $# -eq 0 ]; then
  FILES=(MemoryBackend.dfy)
else
  FILES=("$@")
fi

# Fetch Dafny release, then build each file.  `dafny build` tries to run
# python3 after translation and exits non-zero when Python is missing; we
# filter that noise and check for the output directory instead.
CMDS="apt-get update -qq > /dev/null 2>&1"
CMDS="$CMDS && apt-get install -y -qq unzip > /dev/null 2>&1"
CMDS="$CMDS && curl -sSL https://github.com/dafny-lang/dafny/releases/download/v${DAFNY_VERSION}/dafny-${DAFNY_VERSION}-x64-ubuntu-22.04.zip -o /tmp/dafny.zip"
CMDS="$CMDS && echo '${DAFNY_SHA256}  /tmp/dafny.zip' | sha256sum --check --quiet"
CMDS="$CMDS && unzip -q /tmp/dafny.zip -d /opt"
CMDS="$CMDS && chmod +x /opt/dafny/dafny /opt/dafny/z3/bin/z3-*"
CMDS="$CMDS && mkdir -p /build && cp /work/*.dfy /build/ && cd /build"
for f in "${FILES[@]}"; do
  stem="${f%.dfy}"
  # Clear any stale output first: a mid-build dafny failure with a stale
  # /build/${stem}-py from a previous run would otherwise masquerade as
  # success at the directory-existence gate below.  The `|| true` on the
  # dafny invocation swallows the expected post-translate python3-missing
  # exit, so the stale-dir guard is load-bearing.
  CMDS="$CMDS && rm -rf /build/${stem}-py"
  CMDS="$CMDS && echo '==> Translating $f' && (/opt/dafny/dafny build -t py $f --output:$stem 2>&1 | grep -v 'Unable to start python3' | grep -v 'An error occurred trying to start process' || true)"
  CMDS="$CMDS && if [ -d /build/${stem}-py ]; then rm -rf /out/${stem}-py && cp -r /build/${stem}-py /out/; echo '    wrote /out/${stem}-py'; else echo '    skipped: no compilable output'; fi"
done

docker run --rm \
  -v "$REPO_ROOT/sdd/formal:/work:ro" \
  -v "$REPO_ROOT/sdd/formal:/out" \
  "$IMAGE" \
  bash -c "$CMDS"

# Post-process: class reorder so module_.py is importable (Dafny emits
# MemoryBackend(Backend) before Backend).  Runs on the host.  Use `python3`
# — it's the portable name on Linux/macOS CI runners; Windows resolves it
# via the py launcher.
cd "$REPO_ROOT"
for f in "${FILES[@]}"; do
  stem="${f%.dfy}"
  module="sdd/formal/${stem}-py/module_.py"
  if [ -f "$module" ]; then
    python3 scripts/_dafny_classorder.py "$module"
  fi
done
