#!/usr/bin/env bash
# Single source of truth for CI service container image refs (BK-279).
#
# Sourced (`. scripts/ci_service_images.sh`), not executed: it only assigns the
# three backend image refs so that every start site agrees on the exact same
# pin. Consumers:
#   - .github/actions/start-backends/action.yml  (test / test-primary / e2e / pyarrow24-check)
#   - .github/workflows/ci.yml  (the prepare-images cache-priming job)
#   - .github/workflows/publish.yml  (azurite)
#   - .github/workflows/mutation.yml  (minio / azurite / sftp)
#
# Because the ci.yml image cache is keyed on hashFiles() of THIS file, bumping
# any ref here busts the cache so the next run re-pulls and re-saves. Keep the
# refs here and nowhere else — a literal copied into a workflow would silently
# diverge from the cached tar.
MINIO_IMAGE=cgr.dev/chainguard/minio:latest-dev@sha256:2d8f8a3f8da60885794dfd0749c9d49c985b0ee642f1c522e6aa93be59f34a84
AZURITE_IMAGE=mcr.microsoft.com/azure-storage/azurite:3.35.0
SFTP_IMAGE=atmoz/sftp:alpine

# Subset bundled into the actions/cache tar (ci_save_images.sh / ci_load_images.sh).
# Only Azurite (mcr.microsoft.com) and SFTP (Docker Hub) — the two registries that
# intermittently block GitHub-runner egress — are cached. MinIO is deliberately
# EXCLUDED: its ref is digest-pinned, and `docker save`/`docker load` does not
# preserve a digest reference, so a loaded MinIO image cannot be resolved by
# `docker image inspect "$MINIO_IMAGE"` and start-backends pulls it regardless
# (verified empirically on CI). cgr.dev is reliable, so per-job MinIO pulls are the
# pre-existing, non-flaky behavior — caching it would only bloat the cached tar
# (with its layers) for no benefit.
RS_CACHED_IMAGES="$AZURITE_IMAGE $SFTP_IMAGE"
