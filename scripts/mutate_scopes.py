"""Single source of truth for pytest-gremlins mutation scopes.

Each scope entry pairs source-file mutation targets with a test selection
(directories, files, optional ``-k`` filter) and the backend service
containers it needs for the tests to execute. The same definitions feed:

* ``hatch run mutate <scope>`` (via the ``mutate`` shim in
  ``pyproject.toml`` that delegates to ``scripts/run_mutate.py``);
* ``.github/workflows/mutation.yml`` (reads ``--list-scopes`` and
  ``--container-needs <name>`` to populate the matrix and conditional
  container startup steps).

Add or change a scope here only; pyproject and the CI workflow stay
generic.

Conformance scopes
==================

pytest-gremlins re-runs pytest as a subprocess with every collected node
id as argv. A single conformance topic file can exceed the ~32 KiB
Windows command-line limit (WinError 206) when it covers all backends.
Topics that fit run as one scope; topics over the limit are split by
backend group with a ``-k`` filter on the parametrized backend ids (see
``tests/backends/conformance/conftest.py``). Source-file targets in each
split scope match the backends kept by the filter so mutations are
exercised by surviving tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Backend source-file groups
# ---------------------------------------------------------------------------

ALL_BACKEND_SOURCES: list[str] = [
    "src/remote_store/backends/_local.py",
    "src/remote_store/backends/_memory.py",
    "src/remote_store/backends/_sqlalchemy.py",
    "src/remote_store/backends/_http.py",
    "src/remote_store/backends/_http_httpx.py",
    "src/remote_store/backends/_http_requests.py",
    "src/remote_store/backends/_azure.py",
    "src/remote_store/backends/_s3.py",
    "src/remote_store/backends/_s3_base.py",
    "src/remote_store/backends/_s3_pyarrow.py",
    "src/remote_store/backends/_sftp.py",
]

# Backends whose tests run on a developer machine without a Docker container
# matching the production cloud (local files, in-memory, in-process http,
# in-process sqlite, Azurite emulator, in-process Dafny oracle).
LOCAL_STACK_SOURCES: list[str] = [
    "src/remote_store/backends/_local.py",
    "src/remote_store/backends/_memory.py",
    "src/remote_store/backends/_sqlalchemy.py",
    "src/remote_store/backends/_http.py",
    "src/remote_store/backends/_http_httpx.py",
    "src/remote_store/backends/_http_requests.py",
    "src/remote_store/backends/_azure.py",
]

# Backends whose tests need MinIO (S3) or atmoz/sftp containers.
CLOUD_STACK_SOURCES: list[str] = [
    "src/remote_store/backends/_s3.py",
    "src/remote_store/backends/_s3_base.py",
    "src/remote_store/backends/_s3_pyarrow.py",
    "src/remote_store/backends/_sftp.py",
]

# ``-k`` expressions used by the split-topic conformance scopes. ``LOCAL_STACK_FILTER``
# matches ``[azurite]`` in the parametrized id; that fixture needs the Azurite emulator
# even though every other fixture in the local stack runs without a container. The
# corresponding scopes therefore declare ``needs=[AZURITE]`` individually.
LOCAL_STACK_FILTER = "local or memory or sqlblob or http or azurite or dafny"
CLOUD_STACK_FILTER = "s3 or sftp"

# ---------------------------------------------------------------------------
# Container identifiers (must match conditional startup keys in CI)
# ---------------------------------------------------------------------------

MINIO = "minio"
AZURITE = "azurite"
SFTP = "sftp"


# ---------------------------------------------------------------------------
# Scope record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scope:
    """One mutation-test scope.

    ``targets``  files passed to ``--gremlin-targets``
    ``tests``    pytest path/file args (positional)
    ``filter``   optional ``-k`` expression
    ``needs``    container identifiers (``MINIO``/``AZURITE``/``SFTP``) the
                 tests require to run with full coverage. Used by CI to
                 decide which Docker images to start; **advisory only**.
                 Backend fixtures decide internally whether they can run
                 (e.g. ``sftp_inproc`` runs without Docker, ``sftp_docker``
                 ``pytest.skip``s when its container is missing). A
                 Docker-off local run will therefore exercise a subset of
                 the fixtures the scope's ``-k`` filter selects, and a
                 mutation only the real-daemon fixture would catch can
                 survive.
    """

    targets: list[str]
    tests: list[str]
    filter: str | None = None
    needs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scopes
# ---------------------------------------------------------------------------

SCOPES: dict[str, Scope] = {
    # Core / extension scopes (no backend containers required)
    "core-api": Scope(
        targets=[
            "src/remote_store/_store.py",
            "src/remote_store/_proxy.py",
            "src/remote_store/_stream.py",
            "src/remote_store/_glob.py",
            "src/remote_store/_backend.py",
            "src/remote_store/_types.py",
        ],
        tests=[
            "tests/test_store.py",
            "tests/test_store_child.py",
            "tests/test_proxy.py",
            "tests/test_depth_listing.py",
            "tests/test_folder_info_depth.py",
            "tests/test_open_atomic.py",
            "tests/test_ping.py",
            "tests/test_stream.py",
            "tests/test_glob.py",
        ],
    ),
    "core-infra": Scope(
        targets=[
            "src/remote_store/_capabilities.py",
            "src/remote_store/_errors.py",
            "src/remote_store/_config.py",
            "src/remote_store/_models.py",
            "src/remote_store/_path.py",
            "src/remote_store/_resolution.py",
            "src/remote_store/_registry.py",
            "src/remote_store/backends/_memory.py",
            "src/remote_store/backends/_fileinfo.py",
        ],
        tests=[
            "tests/test_capabilities.py",
            "tests/test_errors.py",
            "tests/test_config.py",
            "tests/test_models.py",
            "tests/test_path.py",
            "tests/test_resolution.py",
            "tests/test_registry.py",
            "tests/test_memory_coverage.py",
        ],
    ),
    "ext-proxy": Scope(
        targets=[
            "src/remote_store/ext/arrow.py",
            "src/remote_store/ext/batch.py",
            "src/remote_store/ext/cache.py",
            "src/remote_store/ext/glob.py",
            "src/remote_store/ext/integrity.py",
            "src/remote_store/ext/observe.py",
            "src/remote_store/ext/otel.py",
            "src/remote_store/ext/partition.py",
            "src/remote_store/ext/streams.py",
            "src/remote_store/ext/transfer.py",
        ],
        tests=[
            "tests/test_arrow.py",
            "tests/test_batch.py",
            "tests/test_cache.py",
            "tests/test_observe.py",
            "tests/test_otel.py",
            "tests/test_partition.py",
            "tests/test_integrity.py",
            "tests/test_transfer.py",
            "tests/test_streams.py",
            "tests/test_glob.py",
        ],
    ),
    "ext-format": Scope(
        targets=[
            "src/remote_store/ext/parquet.py",
            "src/remote_store/ext/yaml.py",
            "src/remote_store/ext/pydantic.py",
            "src/remote_store/ext/dagster.py",
        ],
        tests=[
            "tests/test_ext_parquet.py",
            "tests/test_ext_yaml.py",
            "tests/test_ext_pydantic.py",
            "tests/test_dagster.py",
        ],
    ),
    # Per-backend scopes (legacy axis: per-backend test directory)
    "backends-local": Scope(
        targets=[
            "src/remote_store/backends/_local.py",
            "src/remote_store/backends/_http.py",
            "src/remote_store/backends/_http_httpx.py",
            "src/remote_store/backends/_http_requests.py",
            "src/remote_store/backends/_sqlalchemy.py",
        ],
        tests=[
            "tests/backends/local/",
            "tests/backends/http/",
            "tests/backends/sqlblob/",
            "tests/backends/sqlquery/",
        ],
    ),
    "backends-cloud": Scope(
        targets=CLOUD_STACK_SOURCES + ["src/remote_store/backends/_azure.py"],
        tests=[
            "tests/backends/s3/",
            "tests/backends/sftp/",
            "tests/backends/azure/",
        ],
        needs=[MINIO, AZURITE, SFTP],
    ),
    # Conformance scopes (topic axis): single-file topics
    "conformance-listing": Scope(
        targets=ALL_BACKEND_SOURCES,
        tests=["tests/backends/conformance/test_listing.py"],
        needs=[MINIO, AZURITE, SFTP],
    ),
    "conformance-metadata": Scope(
        targets=ALL_BACKEND_SOURCES,
        tests=["tests/backends/conformance/test_metadata.py"],
        needs=[MINIO, AZURITE, SFTP],
    ),
    "conformance-streaming": Scope(
        targets=ALL_BACKEND_SOURCES,
        tests=["tests/backends/conformance/test_streaming.py"],
        needs=[MINIO, AZURITE, SFTP],
    ),
    "conformance-sync-adapter": Scope(
        targets=ALL_BACKEND_SOURCES,
        tests=["tests/backends/conformance/test_sync_adapter_conformance.py"],
        needs=[MINIO, AZURITE, SFTP],
    ),
    # Conformance scopes (split topics): over-limit, partitioned by backend group
    "conformance-io-local": Scope(
        targets=LOCAL_STACK_SOURCES,
        tests=["tests/backends/conformance/test_io.py"],
        filter=LOCAL_STACK_FILTER,
        needs=[AZURITE],
    ),
    "conformance-io-cloud": Scope(
        targets=CLOUD_STACK_SOURCES,
        tests=["tests/backends/conformance/test_io.py"],
        filter=CLOUD_STACK_FILTER,
        needs=[MINIO, SFTP],
    ),
    "conformance-atomic-local": Scope(
        targets=LOCAL_STACK_SOURCES,
        tests=["tests/backends/conformance/test_atomic.py"],
        filter=LOCAL_STACK_FILTER,
        needs=[AZURITE],
    ),
    "conformance-atomic-cloud": Scope(
        targets=CLOUD_STACK_SOURCES,
        tests=["tests/backends/conformance/test_atomic.py"],
        filter=CLOUD_STACK_FILTER,
        needs=[MINIO, SFTP],
    ),
    "conformance-errors-local": Scope(
        targets=LOCAL_STACK_SOURCES,
        tests=["tests/backends/conformance/test_errors.py"],
        filter=LOCAL_STACK_FILTER,
        needs=[AZURITE],
    ),
    "conformance-errors-cloud": Scope(
        targets=CLOUD_STACK_SOURCES,
        tests=["tests/backends/conformance/test_errors.py"],
        filter=CLOUD_STACK_FILTER,
        needs=[MINIO, SFTP],
    ),
    "conformance-identity-local": Scope(
        targets=LOCAL_STACK_SOURCES,
        tests=["tests/backends/conformance/test_identity.py"],
        filter=LOCAL_STACK_FILTER,
        needs=[AZURITE],
    ),
    "conformance-identity-cloud": Scope(
        targets=CLOUD_STACK_SOURCES,
        tests=["tests/backends/conformance/test_identity.py"],
        filter=CLOUD_STACK_FILTER,
        needs=[MINIO, SFTP],
    ),
    # async-extended runs only on local / memory; one scope per backend
    # keeps the cmdline well under the limit
    "conformance-async-extended-local": Scope(
        targets=["src/remote_store/backends/_local.py"],
        tests=["tests/backends/conformance/test_async_extended.py"],
        filter="local",
    ),
    "conformance-async-extended-memory": Scope(
        targets=["src/remote_store/backends/_memory.py"],
        tests=["tests/backends/conformance/test_async_extended.py"],
        filter="memory",
    ),
}
