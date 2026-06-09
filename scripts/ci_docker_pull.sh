#!/usr/bin/env bash
# Retry `docker pull` with exponential backoff (BK-278).
#
# CI service images (Azurite from mcr.microsoft.com, MinIO from cgr.dev, SFTP
# from Docker Hub) are pulled from registries that intermittently reject GitHub
# runner egress — a Microsoft edge/WAF "request is blocked" page, Docker Hub
# anonymous rate limits, or blob-store "reduce your rate of simultaneous reads"
# throttling. A bare `docker run` fails the job on the first such hiccup; pulling
# with backoff first rides out the transient block, after which `docker run`
# uses the now-local image.
#
# Usage: ci_docker_pull.sh <image-ref> [attempts]
set -euo pipefail

image="${1:?usage: ci_docker_pull.sh <image-ref> [attempts]}"
attempts="${2:-5}"
delay=5

for attempt in $(seq 1 "$attempts"); do
  if docker pull "$image"; then
    exit 0
  fi
  if [ "$attempt" -lt "$attempts" ]; then
    echo "::warning::docker pull ${image} failed (attempt ${attempt}/${attempts}); retrying in ${delay}s"
    sleep "$delay"
    delay=$((delay * 2))
  fi
done

echo "::error::docker pull ${image} failed after ${attempts} attempts"
exit 1
