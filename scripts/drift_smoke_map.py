"""ID-182: extra -> smoke-test targets for the drift guard.

When ``drift_check.py diff <extra>`` reports drift, the workflow runs the
pytest selections below against the freshly-resolved package set. The
targets are chosen as the surface most likely to break when a transitive
dependency moves under us — modeled on the ``infra/legacy-sftp`` e2e
pattern that catches paramiko algorithm-clearance regressions (BK-198).

For extras whose only "integration surface" is `import ...`, the smoke
is the existing ``tests/ext/`` unit test for the extension. The drift
guard adds no new test files; it just routes existing ones.
"""

from __future__ import annotations

# Each entry is a list of pytest argv fragments. The workflow splices each
# fragment into a single ``pytest`` invocation. Use ``-k`` and ``-m`` as
# needed; the workflow does not add ``-n auto`` (drift smokes run serially
# to avoid masking flakiness as resolution noise).
SMOKE_TARGETS: dict[str, list[str]] = {
    # Backend extras — conformance + per-backend config tests.
    "s3": ["tests/backends/conformance/", "-k", "s3 and not s3_pyarrow"],
    "s3-pyarrow": ["tests/backends/conformance/", "-k", "s3_pyarrow"],
    "azure": ["tests/backends/conformance/", "-k", "azure"],
    # sftp: includes tests/e2e/, which pyproject.toml's addopts excludes by
    # default. `-o addopts=` clears that override (same shape as the `e2e`
    # hatch script) so the legacy-sftp recovery test — the model BK-198
    # baked into the design — actually runs.
    "sftp": [
        "-o",
        "addopts=",
        "tests/backends/conformance/",
        "tests/e2e/test_sftp_legacy_recovery.py",
        "tests/e2e/test_sftp_workflow.py",
        "-k",
        "sftp",
    ],
    # sql: the conformance fixture is registered as ``sqlblob`` (one word,
    # no underscore — see tests/backends/fixtures/sqlblob.py). The per-backend
    # config test lives at tests/backends/sqlblob/.
    "sql": [
        "tests/backends/sqlblob/",
        "tests/backends/conformance/",
        "-k",
        "sqlblob",
    ],
    # sql-query: no conformance fixture exists (SQLQueryBackend is
    # read-only and not in the conformance carve-out). The per-backend
    # config test is the smoke surface.
    "sql-query": ["tests/backends/sqlquery/"],
    # HTTP adapters: backend tests live at tests/backends/http/ (not
    # tests/ext/). Same target for both `requests` and `httpx` since the
    # backend chooses its transport at construction time.
    "requests": ["tests/backends/http/"],
    "httpx": ["tests/backends/http/"],
    # Extension extras — the matching tests/ext/ module is the smoke.
    "arrow": ["tests/ext/test_arrow.py", "tests/ext/test_parquet.py"],
    "otel": ["tests/ext/test_otel.py"],
    "yaml": ["tests/ext/test_yaml.py"],
    "pydantic": ["tests/ext/test_pydantic.py"],
    "dagster": ["tests/ext/test_dagster.py"],
}


def smoke_for(extra: str) -> list[str]:
    """Return the pytest argv for an extra; falls back to an import smoke."""
    if extra in SMOKE_TARGETS:
        return SMOKE_TARGETS[extra]
    # Fallback: just import the package's top-level module. The workflow
    # turns this into `python -c "import remote_store; ..."` rather than a
    # pytest invocation.
    return ["--import-only"]


def backends_needed(extra: str) -> dict[str, bool]:
    """Which docker-compose services the smoke targets need running."""
    backend_extras = {
        "s3": {"minio": True},
        "s3-pyarrow": {"minio": True},
        "azure": {"azurite": True},
        "sftp": {"sftp": True},  # legacy-sftp is built ad-hoc by the workflow
    }
    return backend_extras.get(extra, {})


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print(json.dumps(sorted(SMOKE_TARGETS.keys())))
    else:
        extra = sys.argv[1]
        print(json.dumps({"targets": smoke_for(extra), "backends": backends_needed(extra)}))
