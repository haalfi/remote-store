"""S3 control-path moto coverage -- covers BK-166, S3-026, S3PA-026, BUG-214.

Wire-level coverage for BUG-178/BUG-185: drives the full backend lifecycle
through the real ``s3fs`` + ``aiobotocore`` stack with ``moto`` standing in
for the S3 endpoint. Nothing in this module patches the production code
path, so a regression in the ``config_kwargs`` routing surfaces as a real
``TypeError: got multiple values for keyword argument 'config'`` on first
I/O.

The unit-level ``TestAiobotocoreCreateClientBoundary`` in
``tests/backends/s3/test_options.py`` patches
``aiobotocore.session.AioSession.create_client`` and asserts on the
captured kwargs; that pins the kwarg shape. This file pins the wire-level
behavior. The companion rejection assertion lives in
``TestConfigKwargsRetryCollision::test_client_kwargs_config_is_rejected``
(unit-level) and is intentionally not duplicated here -- it short-circuits
inside ``_build_s3fs_kwargs`` before any HTTP and gains nothing from a
moto fixture.

Failure-path coverage: ``test_delete_missing_maps_to_notfound`` exercises
the s3fs control path's error pipeline (``_s3fs_errors`` -> real moto 404
-> ``NotFound``) under the tuned ``client_options``. Existing error-mapping
tests in ``test_s3.py`` ``patch.object(s3_backend._s3fs, "cat_file",
side_effect=Exception(...))`` -- they inject fake exceptions and never
exercise the tuned ``config_kwargs`` end-to-end. Conformance tests do, but
only against Docker (not the default suite).

S3-PyArrow scope (S3PA-026): ``_FULL_CLIENT_OPTIONS['config_kwargs']`` is
consumed by the s3fs builder only; ``S3PyArrowBackend`` reads
``endpoint_url`` / ``key`` / ``secret`` / ``region_name`` directly when
constructing its PyArrow ``S3FileSystem`` and does not pass
``client_options`` to the data path. Most ``S3PyArrowBackend`` methods
still touch s3fs for control-path work under the tuned ``config_kwargs``
-- ``write`` calls ``_s3fs.exists`` (overwrite check) and
``_s3fs.call_s3('head_object', ...)`` (post-upload metadata),
``list_files`` / ``exists`` / ``is_file`` / ``is_folder`` / ``delete`` /
``delete_folder`` / ``move`` / ``copy`` all go through s3fs, etc. Only
the actual byte transfers in ``write`` and ``read`` run through PyArrow
at default settings; everything around them still exercises the tuned
``config_kwargs``. That matches S3PA-026's delta against S3-026 (s3fs
control path only).

Why ``moto[server]`` (not ``moto.mock_aws``): ``mock_aws`` patches the
synchronous ``botocore`` stack only. ``aiobotocore`` issues real HTTP
requests, so we need a real moto HTTP server -- pinned in
``pyproject.toml`` as ``moto[server,s3]``. The ``moto_server`` fixture is
the session-scoped one from ``tests/conftest.py``, shared across all
moto-backed tests in the suite.

Why under ``tests/backends/`` (not ``tests/e2e/``): ``tests/e2e/`` is
excluded from ``hatch run test`` / ``hatch run all`` via
``addopts="--ignore=tests/e2e"`` because those tests need Docker. Moto
runs in-process and is fast, so this file must run in the default suite
to actually catch regressions; that was exactly the gap BUG-178 and
BUG-185 fell through.

Why MinIO for S3PyArrowBackend on pyarrow >= 24: pyarrow 24's C++ S3
client rejects moto's CompleteMultipartUpload response shape as
INTERNAL_FAILURE -- even for small payloads, because PyArrow always uses
multipart upload regardless of file size. MinIO returns a conformant
response, so S3PyArrowBackend tests on pyarrow >= 24 use a real MinIO
instance (port 9000) instead of moto.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from tests._helpers import MINIO_KEY as _MINIO_KEY
from tests._helpers import MINIO_SECRET as _MINIO_SECRET
from tests._helpers import FailingContentReader, pyarrow_ge_24

pytest.importorskip("s3fs")
pytest.importorskip("aiobotocore")
pytest.importorskip("moto")
pytest.importorskip("botocore")
pytest.importorskip("boto3")


if TYPE_CHECKING:
    from collections.abc import Iterator


# Mirror the user's MinIO scenario: path-style addressing, proxies cleared
# (so localhost moto isn't sent through any HTTP_PROXY env), tight timeouts.
_FULL_CLIENT_OPTIONS: dict[str, Any] = {
    "config_kwargs": {
        "s3": {"addressing_style": "path"},
        "proxies": {"http": None, "https": None},
        "connect_timeout": 5.0,
        "read_timeout": 5.0,
    },
}


@pytest.fixture(scope="module")
def moto_bucket(moto_server: str | None) -> Iterator[tuple[str, str]]:
    """Create one bucket on the shared moto server for the whole module.

    Module-scoped because tests use unique object keys per parametrize id,
    write with ``overwrite=True``, and clean up their own writes -- a
    fresh bucket per case adds setup with no isolation benefit.
    """
    if moto_server is None:
        pytest.skip("moto / s3fs not available")
    import boto3

    bucket = f"bk166-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=moto_server,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=bucket)
    try:
        yield moto_server, bucket
    finally:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            for obj in page.get("Contents", []):
                client.delete_object(Bucket=bucket, Key=obj["Key"])
        client.delete_bucket(Bucket=bucket)


@pytest.fixture(scope="module")
def minio_bucket(minio_server: str | None) -> Iterator[tuple[str, str] | None]:
    """Create one bucket on MinIO for S3PyArrowBackend tests on pyarrow >= 24.

    Yields ``(endpoint_url, bucket_name)`` when MinIO is reachable, else
    ``None`` (the routing helper will skip the test).
    """
    if minio_server is None:
        yield None
        return
    import boto3

    bucket = f"bk166-minio-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=minio_server,
        aws_access_key_id=_MINIO_KEY,
        aws_secret_access_key=_MINIO_SECRET,
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=bucket)
    try:
        yield minio_server, bucket
    finally:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            for obj in page.get("Contents", []):
                client.delete_object(Bucket=bucket, Key=obj["Key"])
        client.delete_bucket(Bucket=bucket)


def _load(dotted: str) -> type:
    import importlib

    module_path, cls_name = dotted.split(":")
    return getattr(importlib.import_module(module_path), cls_name)


def _resolve_s3_backend(
    backend_cls: str,
    request: pytest.FixtureRequest,
) -> tuple[str, str, str, str]:
    """Return (endpoint, bucket, key, secret) for the backend under test.

    Uses ``request.getfixturevalue`` so only the needed bucket fixture is
    instantiated -- on pyarrow >= 24 the s3-pyarrow variant uses
    ``minio_bucket`` and never creates a moto bucket, avoiding wasted setup.
    """
    cls = _load(backend_cls)
    from remote_store.backends._s3_pyarrow import S3PyArrowBackend as _S3PA

    if cls is _S3PA and pyarrow_ge_24():
        minio: tuple[str, str] | None = request.getfixturevalue("minio_bucket")
        if minio is None:
            pytest.skip("MinIO not reachable; required for S3PyArrowBackend on pyarrow >= 24")
        endpoint, bucket = minio
        return endpoint, bucket, _MINIO_KEY, _MINIO_SECRET
    moto: tuple[str, str] = request.getfixturevalue("moto_bucket")
    endpoint, bucket = moto
    return endpoint, bucket, "testing", "testing"


@pytest.mark.parametrize(
    "backend_cls",
    [
        pytest.param(
            "remote_store.backends._s3:S3Backend",
            id="s3",
            marks=pytest.mark.spec("S3-026"),
        ),
        pytest.param(
            "remote_store.backends._s3_pyarrow:S3PyArrowBackend",
            id="s3-pyarrow",
            marks=pytest.mark.spec("S3PA-026"),
        ),
    ],
)
class TestS3ControlPathMoto:
    """BK-166: drive the full backend lifecycle through real s3fs + aiobotocore."""

    def test_full_lifecycle_with_tuned_client_options(
        self,
        backend_cls: str,
        request: pytest.FixtureRequest,
    ) -> None:
        """write -> list_files -> read -> delete with non-trivial client_options.

        Mirrors the user's MinIO scenario from BUG-185. A pre-fix regression
        raises ``TypeError: got multiple values for keyword argument 'config'``
        from ``aiobotocore.create_client`` on the first I/O call.
        """
        endpoint, bucket, key_cred, secret = _resolve_s3_backend(backend_cls, request)
        cls = _load(backend_cls)
        # Unique key per parametrize id so cases sharing the module-scoped bucket
        # cannot clobber each other if one fails before its own delete.
        key = f"docs/hello-{cls.__name__}.txt"
        backend = cls(
            bucket=bucket,
            endpoint_url=endpoint,
            key=key_cred,
            secret=secret,
            region_name="us-east-1",
            client_options=_FULL_CLIENT_OPTIONS,
        )
        try:
            payload = b"BK-166 wire-level payload"
            result = backend.write(key, payload, overwrite=True)
            assert result.size == len(payload)

            listed = [str(info.path) for info in backend.list_files("docs", recursive=True)]
            assert key in listed

            with backend.read(key) as stream:
                assert stream.read() == payload

            backend.delete(key)
            assert not backend.exists(key)
        finally:
            backend.close()

    def test_lifecycle_with_retry_policy(
        self,
        backend_cls: str,
        request: pytest.FixtureRequest,
    ) -> None:
        """Same lifecycle with ``RetryPolicy`` alongside the tuned client_options.

        ``RetryPolicy`` replaces the ``config_kwargs['retries']`` entry
        wholesale (S3-026); each operation in the round-trip must observe
        the expected effect. Mirrors the four assertions from
        ``test_full_lifecycle_with_tuned_client_options`` so a regression
        in any individual operation under ``RetryPolicy`` surfaces here,
        not just exception-free completion.
        """
        from remote_store._config import RetryPolicy

        endpoint, bucket, key_cred, secret = _resolve_s3_backend(backend_cls, request)
        cls = _load(backend_cls)
        key = f"retry/sample-{cls.__name__}.bin"
        backend = cls(
            bucket=bucket,
            endpoint_url=endpoint,
            key=key_cred,
            secret=secret,
            region_name="us-east-1",
            client_options=_FULL_CLIENT_OPTIONS,
            retry=RetryPolicy(max_attempts=2),
        )
        try:
            payload = b"BK-166 retry payload"
            result = backend.write(key, payload, overwrite=True)
            assert result.size == len(payload)

            listed = [str(info.path) for info in backend.list_files("retry", recursive=True)]
            assert key in listed

            with backend.read(key) as stream:
                assert stream.read() == payload

            backend.delete(key)
            assert not backend.exists(key)
        finally:
            backend.close()

    def test_delete_missing_maps_to_notfound(
        self,
        backend_cls: str,
        request: pytest.FixtureRequest,
    ) -> None:
        """Failure path: ``delete(missing_key)`` under tuned config_kwargs maps to ``NotFound``.

        Real moto returns a 404; the s3fs control path routes it through
        ``_s3fs_errors`` -> ``_classify_error`` -> ``NotFound``. Both
        backends use ``self._s3fs.exists(...)`` inside ``delete``, so the
        ``s3-pyarrow`` parametrize id exercises the same s3fs path -- the
        only place tuned ``config_kwargs`` apply for that backend.

        Existing error-mapping tests in ``test_s3.py`` inject exceptions
        via ``patch.object(_s3fs, "cat_file", side_effect=Exception(...))``;
        no other test in the default suite exercises a real S3 404 with
        ``client_options`` set.
        """
        from remote_store._errors import NotFound

        endpoint, bucket, key_cred, secret = _resolve_s3_backend(backend_cls, request)
        cls = _load(backend_cls)
        key = f"never/written-{cls.__name__}.txt"
        backend = cls(
            bucket=bucket,
            endpoint_url=endpoint,
            key=key_cred,
            secret=secret,
            region_name="us-east-1",
            client_options=_FULL_CLIENT_OPTIONS,
        )
        try:
            with pytest.raises(NotFound, match=key) as exc_info:
                backend.delete(key, missing_ok=False)
            assert exc_info.value.path == key
            assert exc_info.value.backend == backend.name
        finally:
            backend.close()

    @pytest.mark.spec("S3-012")
    def test_delete_folder_non_recursive_non_empty_raises(
        self,
        backend_cls: str,
        request: pytest.FixtureRequest,
    ) -> None:
        """S3-012: non-recursive ``delete_folder`` on a non-empty prefix raises ``DirectoryNotEmpty``.

        The data-safety guard mirrors local ``rmdir`` semantics. The shared
        conformance test (``test_errors.py::...::test_delete_folder_non_recursive_non_empty_raises``)
        skips flat-namespace backends via ``_skip_flat_namespace``, so S3 and
        S3-PyArrow -- both flat-namespace -- never exercise the guard there.
        This pins it for both: the ``s3-pyarrow`` parametrize id drives the
        same s3fs control path (``S3PyArrowBackend.delete_folder`` delegates to
        s3fs, see module docstring). SQLBlob has its own check
        (``SQL-BLOB-025``); this closes the S3/S3PA gap.
        """
        from remote_store._errors import DirectoryNotEmpty

        endpoint, bucket, key_cred, secret = _resolve_s3_backend(backend_cls, request)
        cls = _load(backend_cls)
        prefix = f"dne/{cls.__name__}"
        key = f"{prefix}/child.txt"
        backend = cls(
            bucket=bucket,
            endpoint_url=endpoint,
            key=key_cred,
            secret=secret,
            region_name="us-east-1",
            client_options=_FULL_CLIENT_OPTIONS,
        )
        try:
            backend.write(key, b"keep me", overwrite=True)
            with pytest.raises(DirectoryNotEmpty, match=prefix) as exc_info:
                backend.delete_folder(prefix, recursive=False)
            assert exc_info.value.backend == backend.name
            # The guard must not have deleted the child object.
            assert backend.exists(key)
        finally:
            backend.delete(key, missing_ok=True)
            backend.close()


_MB = 1024 * 1024


@pytest.mark.spec("S3-010")
class TestBug214MidStreamFailure:
    """BUG-214: a mid-stream content failure must not commit a truncated object.

    When the *content source* passed to ``S3Backend.write`` / ``write_atomic``
    raises part-way through, s3fs's ``S3File.__exit__`` -> ``close()`` would
    otherwise flush the buffer (single PUT) or complete the in-flight multipart
    upload, leaving a complete-looking but truncated object -- a violation of
    the ATOMIC_WRITE contract (S3-010 / AW-001). The fix ``discard()``s the
    handle on the exception path instead of committing.

    Both regimes are covered because s3fs only switches to multipart above its
    50 MB default block size: 6 MB exercises the single-PUT path, 55 MB the
    completed-multipart path. ``write_atomic`` delegates to ``write``, so it
    rides the same fix; both are asserted to leave neither an object nor an
    orphaned multipart upload.

    s3fs-only (uses ``moto_bucket`` directly): the s3-pyarrow data path cannot
    run on moto (pyarrow >= 24 needs MinIO) and is covered in ``test_pyarrow``.
    """

    @pytest.mark.parametrize("op", ["write", "write_atomic"])
    @pytest.mark.parametrize(
        ("fill", "regime"),
        [(6 * _MB, "single-put"), (55 * _MB, "multipart")],
    )
    def test_no_truncated_object_on_mid_stream_failure(
        self,
        moto_bucket: tuple[str, str],
        op: str,
        fill: int,
        regime: str,
    ) -> None:
        import boto3

        from remote_store._errors import RemoteStoreError
        from remote_store.backends._s3 import S3Backend

        endpoint, bucket = moto_bucket
        key = f"bug214/{op}-{regime}.bin"
        backend = S3Backend(
            bucket=bucket,
            endpoint_url=endpoint,
            key="testing",
            secret="testing",
            region_name="us-east-1",
        )
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name="us-east-1",
        )
        try:
            # The mid-stream ConnectionResetError surfaces as a typed
            # RemoteStoreError via ``_s3fs_errors`` -> ``_classify_error``.
            with pytest.raises(RemoteStoreError):
                getattr(backend, op)(key, FailingContentReader.buffered(fill), overwrite=True)

            # No truncated object was committed ...
            listed = client.list_objects_v2(Bucket=bucket, Prefix=key).get("Contents", [])
            assert [obj["Key"] for obj in listed if obj["Key"] == key] == []
            # ... and no multipart upload was left orphaned.
            uploads = client.list_multipart_uploads(Bucket=bucket).get("Uploads", [])
            assert [up for up in uploads if up["Key"] == key] == []
        finally:
            backend.close()
            client.close()

    def test_discard_failure_preserves_original_error(self) -> None:
        """A failing ``discard()`` must not mask the content error nor skip ``closed``.

        ``discard()`` makes a live ``AbortMultipartUpload`` call, so it can fail
        on its own (network blip, server error). The cleanup path swallows that
        so the ORIGINAL mid-stream content failure still propagates, and sets
        ``closed`` regardless so a failed abort cannot leave ``__del__`` free to
        re-commit a truncated object (S3-010 / AW-001). Injected s3fs mocks keep
        the test off the wire.
        """
        from unittest.mock import MagicMock

        import s3fs
        from s3fs.core import S3File

        from remote_store._errors import RemoteStoreError
        from remote_store.backends._s3 import S3Backend

        backend = S3Backend(bucket="b", key="testing", secret="testing", region_name="us-east-1")
        fake_file = MagicMock(spec=S3File)
        fake_file.discard.side_effect = RuntimeError("RS214-abort-sentinel: AbortMultipartUpload blew up")
        mock_fs = MagicMock(spec=s3fs.S3FileSystem)
        mock_fs.exists.return_value = False
        mock_fs.open.return_value = fake_file
        backend._fs_instance = mock_fs

        with pytest.raises(RemoteStoreError) as excinfo:
            backend.write("k.bin", FailingContentReader.buffered(10), overwrite=True)

        # The original content failure surfaces, not the abort failure ...
        assert "simulated mid-stream content failure" in str(excinfo.value)
        assert "RS214-abort-sentinel" not in str(excinfo.value)
        # ... the abort was attempted ...
        fake_file.discard.assert_called_once()
        # ... and ``closed`` was set despite ``discard()`` raising, so ``__del__``
        # cannot re-commit.
        assert fake_file.closed is True
