#!/usr/bin/env bash
# Load CI service images from the actions/cache tar produced by
# ci_save_images.sh (BK-279). Run by consumer jobs before start-backends.
#
# A missing tar is a no-op (with a warning), not an error: a cache restore-miss
# falls through to start-backends' load-or-pull fallback, which pulls the image
# with retry. This keeps the cache strictly an optimisation.
#
# Usage: ci_load_images.sh <input-dir>
set -euo pipefail

dir="${1:?usage: ci_load_images.sh <input-dir>}"
tar="$dir/images.tar"

if [ -f "$tar" ]; then
  docker load -i "$tar"
else
  echo "::warning::${tar} not found; backends will pull images on demand"
fi
