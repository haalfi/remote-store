#!/usr/bin/env bash
# Pre-pull the cached CI service images (RS_CACHED_IMAGES, with retry) and bundle
# them into one tar for actions/cache reuse (BK-279). Run on cache miss by the
# prepare-images job.
#
# Best-effort by design: neither a pull that outlasts ci_docker_pull.sh's retry
# window nor a `docker save` error fails the job — both are logged and degrade to
# `complete=false`. The cache is an optimisation, not a gate: consumers' load-or-pull
# fallback (start-backends) retries at use time, and the test matrix's
# `fail-fast: false` stops one block from cancelling siblings. Keeping this step
# unable to hard-fail also shrinks the `needs: prepare-images` cascade surface — a
# save hiccup degrades to per-job pulls instead of skipping the backend lane. We
# only emit `complete=true` (which gates the cache *save*) when every cached image
# (RS_CACHED_IMAGES) bundled, so a partial/empty tar is never persisted under the
# ref-hash key and left to rot until the next ref bump.
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

read -ra want <<< "$RS_CACHED_IMAGES"
saved=()
for img in "${want[@]}"; do
  if bash "$here/ci_docker_pull.sh" "$img"; then
    saved+=("$img")
  else
    echo "::warning::could not pre-pull ${img}; consumers will pull it on demand"
  fi
done

# `docker save` is in the `if` condition so a save error trips the else branch
# (complete=false) under `set -e` instead of failing the job.
if [ "${#saved[@]}" -gt 0 ] && [ "${#saved[@]}" -eq "${#want[@]}" ] \
    && docker save "${saved[@]}" -o "$dir/images.tar"; then
  echo "complete=true" >> "${GITHUB_OUTPUT:-/dev/null}"
else
  echo "::warning::did not bundle all cached images (pulled ${#saved[@]}/${#want[@]}, or docker save failed); skipping cache save"
  echo "complete=false" >> "${GITHUB_OUTPUT:-/dev/null}"
fi
