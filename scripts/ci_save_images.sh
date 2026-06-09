#!/usr/bin/env bash
# Pre-pull every CI service image (with retry) and bundle them into one tar for
# actions/cache reuse (BK-279). Run on cache miss by the prepare-images job.
#
# Best-effort by design: a pull that outlasts ci_docker_pull.sh's retry window
# is logged but does NOT fail the job. The cache is an optimisation, not a gate —
# consumers' load-or-pull fallback (start-backends) retries at use time, and the
# test matrix's `fail-fast: false` stops one block from cancelling siblings. We
# only emit `complete=true` (which gates the cache *save*) when all three images
# bundled, so a partial/empty tar is never persisted under the ref-hash key and
# left to rot until the next ref bump.
#
# The real payoff is cross-run reuse: once the tar is cached, later runs
# `docker load` it with zero upstream pull, immune to registry blocks entirely.
#
# Usage: ci_save_images.sh <output-dir>
set -euo pipefail

dir="${1:?usage: ci_save_images.sh <output-dir>}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci_service_images.sh
. "$here/ci_service_images.sh"

mkdir -p "$dir"

saved=()
for img in "$MINIO_IMAGE" "$AZURITE_IMAGE" "$SFTP_IMAGE"; do
  if bash "$here/ci_docker_pull.sh" "$img"; then
    saved+=("$img")
  else
    echo "::warning::could not pre-pull ${img}; consumers will pull it on demand"
  fi
done

if [ "${#saved[@]}" -eq 3 ]; then
  docker save "${saved[@]}" -o "$dir/images.tar"
  echo "complete=true" >> "${GITHUB_OUTPUT:-/dev/null}"
else
  echo "::warning::pre-pulled ${#saved[@]}/3 images; skipping cache save"
  echo "complete=false" >> "${GITHUB_OUTPUT:-/dev/null}"
fi
