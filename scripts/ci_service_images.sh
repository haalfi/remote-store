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
