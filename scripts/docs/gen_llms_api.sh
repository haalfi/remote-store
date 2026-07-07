#!/usr/bin/env bash
# ID-226 / BUG-226: generate the machine-readable public-API skeleton served at
# ``/llms-api.txt`` on Read the Docs, next to the ``mkdocs-llmstxt`` outputs
# (``llms.txt`` / ``llms-full.txt``), for coding agents that consume
# remote-store.
#
# Runs from ``.readthedocs.yaml``'s ``build.jobs.post_build`` (after ``mkdocs
# build``). This lives in a committed script rather than an inline YAML command
# because RTD executes post_build under ``/bin/sh`` (dash) and a folded YAML
# scalar mis-folds multi-line shell (BUG-226: an over-indented ``| ... bash``
# line became a standalone shell line starting with ``|`` → parse error that
# defeated the inline ``|| echo`` guard and reddened the whole build).
#
# ``lx`` (Go, MIT) turns ``src/`` into a public-only skeleton (signatures +
# docstrings, backends included). RTD is pip-only, so lx is fetched as a pinned
# prebuilt binary rather than added to the toolchain. Install script and binary
# are both pinned to v1.2.2 (the decorated-dataclass skeleton fix; lx <= 1.2.1
# silently dropped public data-model classes) so the whole fetch is
# reproducible with no moving dependency.
#
# ``-u -Y`` = public-only skeleton; ``-e __pycache__`` drops stray bytecode.
#
# Non-fatal by contract: a fetch/run hiccup must never red the canonical docs
# build. lx writes to a temp file that is moved into the served dir only on
# success, so a failed run serves *nothing* (a loud 404 on the discovery links)
# rather than an empty/partial ``llms-api.txt``. This script therefore always
# exits 0; failures are logged and skipped.
set -uo pipefail

LX_VERSION="v1.2.2"
LX_INSTALL_DIR="/tmp/lxbin"
LX_BIN="${LX_INSTALL_DIR}/lx"
TMP_OUT="/tmp/llms-api.txt"
DEST="${READTHEDOCS_OUTPUT:-}/html/llms-api.txt"

skip() {
  echo "BUG-226/ID-226: llms-api.txt skeleton skipped ($1); see build log above" >&2
  exit 0
}

if [ -z "${READTHEDOCS_OUTPUT:-}" ]; then
  skip "READTHEDOCS_OUTPUT unset"
fi

mkdir -p "${LX_INSTALL_DIR}" || skip "mkdir install dir failed"

if ! curl -fsSL "https://raw.githubusercontent.com/rasros/lx/${LX_VERSION}/install.sh" \
    | VERSION="${LX_VERSION}" LX_INSTALL_DIR="${LX_INSTALL_DIR}" bash; then
  skip "lx install failed"
fi

if ! "${LX_BIN}" -e '__pycache__' -u -Y src/remote_store/ > "${TMP_OUT}"; then
  skip "lx run failed"
fi

if [ ! -s "${TMP_OUT}" ]; then
  skip "lx produced empty output"
fi

if ! mv "${TMP_OUT}" "${DEST}"; then
  skip "mv into served dir failed"
fi

echo "BUG-226/ID-226: published llms-api.txt ($(wc -c < "${DEST}") bytes)"
