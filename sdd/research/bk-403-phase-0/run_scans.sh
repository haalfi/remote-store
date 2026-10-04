#!/usr/bin/env bash
# Runtime half of the D5 layer-4 inventory: ONE full Stage-1 run of the
# readscan plugin, bounded parallel as `hatch run test` / `test-isolation`.
# Throwaway research (RFC-0019 Phase 0). Run from the repository root, one
# order at a time: two scans running at once contend for moto ports and temp
# files and hung at 97% on 2026-10-04.
#
#   bash sdd/research/bk-403-phase-0/run_scans.sh default
#   bash sdd/research/bk-403-phase-0/run_scans.sh random-a -p randomly --randomly-seed=20261004
#   bash sdd/research/bk-403-phase-0/run_scans.sh random-b -p randomly --randomly-seed=4031
set -u
label=$1
shift
rm -rf "tmp/readscan/$label"
RS_READSCAN_OUT="tmp/readscan/$label" PYTHONPATH=sdd/research/bk-403-phase-0 \
  hatch run python scripts/run_tests.py -p no:benchmark --stage=1 -p readscan -q -o faulthandler_timeout=240 "$@"
