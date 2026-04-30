"""Shared S3 + S3-PyArrow tests -- covers invariants that are identical across
both backends. Each test class is parametrized over ``S3Backend`` and
``S3PyArrowBackend`` with paired spec IDs carried via per-param
``pytest.mark.spec(...)`` marks.

Covers:
- S3-004/005/021/022/025 and S3PA-004/005/022/023 (construction)
- TLS-001/002/004/005/007 (tls_ca_bundle, shared s3fs control path)
- S3-007/008/009 and S3PA-009/010/011 (virtual folder semantics)
- S3-015/S3PA-018, S3-018/S3PA-019 (error mapping: backend attribute)
- S3-019/S3PA-020, S3-020/S3PA-021 (lifecycle: close + unwrap s3fs)
- S3-023/S3PA-017 (ETag in get_file_info)
- S3-024/S3PA-017 (SHA-256 digest in get_file_info)
- RES-051/052 (resolve details)
- BK-123 (paginated listing via _S3Base BFS)
- S3-026/S3PA-026 (retry debug log; s3fs control path only)

Requires: moto[server,s3], s3fs, boto3 (test dependencies).
All tests are skipped if dependencies are not installed.
"""

from __future__ import annotations

import importlib
import uuid
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

pytest.importorskip("moto", reason="moto not installed")
pytest.importorskip("s3fs", reason="s3fs not installed")
boto3 = pytest.importorskip("boto3", reason="boto3 not installed")


if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from remote_store._backend import Backend

REGION = "us-east-1"


def _load_backend_cls(dotted: str) -> type:
    module_path, cls_name = dotted.split(":")
    mod = importlib.import_module(module_path)
    return getattr(mod, cls_name)


# ---------------------------------------------------------------------------
# Parametrize helpers -- paired spec marks per backend.
# ---------------------------------------------------------------------------

S3_CLS = "remote_store.backends._s3:S3Backend"
S3PA_CLS = "remote_store.backends._s3_pyarrow:S3PyArrowBackend"


@pytest.fixture
def s3_any_backend(request: pytest.FixtureRequest, moto_server: str | None) -> Iterator[Backend]:
    """Live backend fixture driven by ``@pytest.mark.parametrize(..., indirect=True)``.

    The parameter value is a ``module:ClassName`` dotted path. Each test
    provides its own list of ``pytest.param(..., marks=pytest.mark.spec(...))``
    values so S3-NNN and S3PA-NNN traceability is preserved per backend.
    """
    backend_cls = _load_backend_cls(request.param)
    bucket = f"shared-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=moto_server,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name=REGION,
    )
    client.create_bucket(Bucket=bucket)
    backend = backend_cls(
        bucket=bucket,
        key="testing",
        secret="testing",
        region_name=REGION,
        endpoint_url=moto_server,
    )
    yield backend
    backend.close()


_LIVE_PARAMS_FOLDER_SIMPLE = [
    pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-007")),
    pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-009")),
]

_LIVE_PARAMS_FOLDER_MARKERS = [
    pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-008")),
    pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-010")),
]

_LIVE_PARAMS_FOLDER_LIFECYCLE = [
    pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-009")),
    pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-011")),
]

_LIVE_PARAMS_RESOLVE = [
    pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("RES-051")),
    pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("RES-052")),
]

_LIVE_PARAMS_PAGINATED = [
    pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("BK-123")),
    pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("BK-123")),
]


# ---------------------------------------------------------------------------
# Construction (S3-004/005/021/022/025 ↔ S3PA-004/005/022/023)
# ---------------------------------------------------------------------------


class TestS3SharedConstruction:
    """Construction invariants shared across both backends (unit-level, no moto)."""

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-005")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-005")),
        ],
    )
    @pytest.mark.parametrize(
        "bucket",
        [
            pytest.param("", id="empty"),
            pytest.param("   ", id="whitespace"),
        ],
    )
    def test_invalid_bucket_raises(self, backend_cls: str, bucket: str) -> None:
        cls = _load_backend_cls(backend_cls)
        with pytest.raises(ValueError, match="bucket"):
            cls(bucket=bucket)

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-022")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-024")),
        ],
    )
    def test_credentials_optional(self, backend_cls: str) -> None:
        cls = _load_backend_cls(backend_cls)
        backend = cls(bucket="any-bucket")
        assert backend.name in {"s3", "s3-pyarrow"}

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-004")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-004")),
        ],
    )
    def test_lazy_connection(self, backend_cls: str) -> None:
        cls = _load_backend_cls(backend_cls)
        backend = cls(
            bucket="any-bucket",
            endpoint_url="http://localhost:99999",
            key="k",
            secret="s",
        )
        assert backend.name in {"s3", "s3-pyarrow"}

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-025")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-023")),
        ],
    )
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            pytest.param(None, None, id="none"),
            pytest.param("", None, id="empty"),
            pytest.param("   ", None, id="whitespace"),
            pytest.param("localhost:9000", "https://localhost:9000", id="bare-host-port"),
            pytest.param("my-host.example.com:443", "https://my-host.example.com:443", id="fqdn-port"),
            pytest.param("http://localhost:9000", "http://localhost:9000", id="http-scheme"),
            pytest.param("https://s3.amazonaws.com", "https://s3.amazonaws.com", id="https-scheme"),
            pytest.param("  http://x:9000  ", "http://x:9000", id="whitespace-stripped"),
            pytest.param("HTTP://host:9000", "HTTP://host:9000", id="uppercase-http"),
            pytest.param("HTTPS://host:9000", "HTTPS://host:9000", id="uppercase-https"),
        ],
    )
    def test_endpoint_url_normalization(self, backend_cls: str, raw: str | None, expected: str | None) -> None:
        cls = _load_backend_cls(backend_cls)
        backend = cls(bucket="b", key="k", secret="s", endpoint_url=raw)
        assert backend._endpoint_url == expected

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-021")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-022")),
        ],
    )
    def test_client_options_accepted(self, backend_cls: str) -> None:
        cls = _load_backend_cls(backend_cls)
        backend = cls(
            bucket="any-bucket",
            key="k",
            secret="s",
            client_options={"connect_timeout": 5, "read_timeout": 10},
        )
        assert backend.name in {"s3", "s3-pyarrow"}

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-021")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-022")),
        ],
    )
    def test_client_options_not_mutated(self, backend_cls: str) -> None:
        cls = _load_backend_cls(backend_cls)
        opts: dict = {"client_kwargs": {"timeout": 30}}
        original_inner = dict(opts["client_kwargs"])
        backend = cls(
            bucket="any-bucket",
            key="k",
            secret="s",
            region_name="us-east-1",
            client_options=opts,
        )
        with patch("s3fs.S3FileSystem"):
            _ = backend._s3fs
        assert opts["client_kwargs"] == original_inner


# ---------------------------------------------------------------------------
# TLS CA bundle (shared s3fs control path). PyArrow-specific path stays in
# test_s3_pyarrow.py; env-var fallback (AWS_CA_BUNDLE) stays in test_s3.py.
# ---------------------------------------------------------------------------


class TestS3SharedTlsCaBundle:
    """tls_ca_bundle accepted + s3fs verify wiring across both backends."""

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("TLS-001")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("TLS-002")),
        ],
    )
    def test_tls_ca_bundle_accepted(self, backend_cls: str, tmp_path: Path) -> None:
        cls = _load_backend_cls(backend_cls)
        cert = tmp_path / "ca.pem"
        cert.write_text("fake cert")
        backend = cls(bucket="b", key="k", secret="s", tls_ca_bundle=str(cert))
        assert backend._tls_ca_bundle == str(cert)

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("TLS-004")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("TLS-004")),
        ],
    )
    def test_tls_ca_bundle_missing_file_raises(self, backend_cls: str) -> None:
        cls = _load_backend_cls(backend_cls)
        with pytest.raises(ValueError, match="does not exist or is not a file"):
            cls(bucket="b", key="k", secret="s", tls_ca_bundle="/no/such/file.pem")

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("TLS-004")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("TLS-004")),
        ],
    )
    def test_tls_ca_bundle_directory_raises(self, backend_cls: str, tmp_path: Path) -> None:
        cls = _load_backend_cls(backend_cls)
        with pytest.raises(ValueError, match="does not exist or is not a file"):
            cls(bucket="b", key="k", secret="s", tls_ca_bundle=str(tmp_path))

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("TLS-001")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("TLS-002")),
        ],
    )
    def test_tls_ca_bundle_none_default(self, backend_cls: str) -> None:
        from remote_store.backends._s3_base import _S3_CA_ENV_VARS

        cls = _load_backend_cls(backend_cls)
        with patch.dict("os.environ", {v: "" for v in _S3_CA_ENV_VARS}, clear=False):
            backend = cls(bucket="b", key="k", secret="s")
        assert backend._tls_ca_bundle is None

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("TLS-005")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("TLS-007")),
        ],
    )
    def test_tls_ca_bundle_sets_verify_on_s3fs(self, backend_cls: str, tmp_path: Path) -> None:
        cls = _load_backend_cls(backend_cls)
        cert = tmp_path / "ca.pem"
        cert.write_text("fake cert")
        backend = cls(bucket="b", key="k", secret="s", tls_ca_bundle=str(cert))
        with patch("s3fs.S3FileSystem") as mock_s3fs_cls:
            _ = backend._s3fs
            call_kwargs = mock_s3fs_cls.call_args[1]
            assert call_kwargs["client_kwargs"]["verify"] == str(cert)

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("TLS-005")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("TLS-007")),
        ],
    )
    def test_tls_ca_bundle_does_not_override_explicit_verify(self, backend_cls: str, tmp_path: Path) -> None:
        cls = _load_backend_cls(backend_cls)
        cert = tmp_path / "ca.pem"
        cert.write_text("fake cert")
        backend = cls(
            bucket="b",
            key="k",
            secret="s",
            tls_ca_bundle=str(cert),
            client_options={"client_kwargs": {"verify": "/other/ca.pem"}},
        )
        with patch("s3fs.S3FileSystem") as mock_s3fs_cls:
            _ = backend._s3fs
            call_kwargs = mock_s3fs_cls.call_args[1]
            assert call_kwargs["client_kwargs"]["verify"] == "/other/ca.pem"


# ---------------------------------------------------------------------------
# Virtual folder semantics (S3-007/008/009 ↔ S3PA-009/010/011)
# ---------------------------------------------------------------------------


class TestS3SharedFolderSemantics:
    """S3 object model: no folder markers, folders vanish when empty."""

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_FOLDER_SIMPLE, indirect=True)
    @pytest.mark.parametrize(
        ("setup_path", "folder", "expected"),
        [
            pytest.param("data/file.txt", "data", True, id="with_objects"),
            pytest.param(None, "nonexistent", False, id="empty_prefix"),
        ],
    )
    def test_is_folder_simple(
        self,
        s3_any_backend: Backend,
        setup_path: str | None,
        folder: str,
        expected: bool,
    ) -> None:
        if setup_path:
            s3_any_backend.write(setup_path, b"x")
        assert s3_any_backend.is_folder(folder) is expected

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_FOLDER_SIMPLE, indirect=True)
    def test_is_folder_nested(self, s3_any_backend: Backend) -> None:
        s3_any_backend.write("a/b/c.txt", b"x")
        assert s3_any_backend.is_folder("a") is True
        assert s3_any_backend.is_folder("a/b") is True
        assert s3_any_backend.is_folder("a/b/c") is False

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_FOLDER_MARKERS, indirect=True)
    def test_write_does_not_create_folder_markers(self, s3_any_backend: Backend) -> None:
        s3_any_backend.write("x/y/z.txt", b"data")
        assert s3_any_backend.is_file("x/y/z.txt") is True
        assert s3_any_backend.is_file("x/") is False
        assert s3_any_backend.is_file("x/y/") is False

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_FOLDER_LIFECYCLE, indirect=True)
    def test_folder_vanishes_when_empty(self, s3_any_backend: Backend) -> None:
        s3_any_backend.write("ephemeral/only.txt", b"x")
        assert s3_any_backend.is_folder("ephemeral") is True
        s3_any_backend.delete("ephemeral/only.txt")
        assert s3_any_backend.is_folder("ephemeral") is False

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_FOLDER_LIFECYCLE, indirect=True)
    def test_folder_persists_with_remaining_files(self, s3_any_backend: Backend) -> None:
        s3_any_backend.write("keep/a.txt", b"a")
        s3_any_backend.write("keep/b.txt", b"b")
        s3_any_backend.delete("keep/a.txt")
        assert s3_any_backend.is_folder("keep") is True


# ---------------------------------------------------------------------------
# Lifecycle (S3-019 ↔ S3PA-020): close() is idempotent. The "callable once"
# variant is covered by conformance; the second-close behaviour is not.
# ---------------------------------------------------------------------------


_LIVE_PARAMS_CLOSE = [
    pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-019")),
    pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-020")),
]


class TestS3SharedLifecycle:
    """Second close() must not raise."""

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_CLOSE, indirect=True)
    def test_close_idempotent(self, s3_any_backend: Backend) -> None:
        s3_any_backend.close()
        result = s3_any_backend.close()
        assert result is None


# ---------------------------------------------------------------------------
# Resolve details (RES-051 ↔ RES-052)
# ---------------------------------------------------------------------------


class TestS3SharedResolve:
    """Backend-specific resolve() details: bucket, object_key, endpoint_url."""

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_RESOLVE, indirect=True)
    def test_details_has_bucket(self, s3_any_backend: Backend) -> None:
        plan = s3_any_backend.resolve("file.txt")
        assert "bucket" in plan.details
        assert isinstance(plan.details["bucket"], str)
        assert len(plan.details["bucket"]) > 0

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_RESOLVE, indirect=True)
    def test_details_has_object_key(self, s3_any_backend: Backend) -> None:
        plan = s3_any_backend.resolve("dir/file.txt")
        assert "object_key" in plan.details
        assert plan.details["object_key"] == "dir/file.txt"

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_RESOLVE, indirect=True)
    def test_details_has_endpoint_url(self, s3_any_backend: Backend) -> None:
        plan = s3_any_backend.resolve("file.txt")
        assert "endpoint_url" in plan.details

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("RES-051")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("RES-052")),
        ],
    )
    def test_endpoint_url_strips_userinfo(self, backend_cls: str) -> None:
        cls = _load_backend_cls(backend_cls)
        backend = cls(
            bucket="test-bucket",
            key="k",
            secret="s",
            endpoint_url="http://user:pass@localhost:9000",
        )
        plan = backend.resolve("file.txt")
        assert "user" not in plan.details["endpoint_url"]
        assert "pass" not in plan.details["endpoint_url"]
        assert "localhost:9000" in plan.details["endpoint_url"]


# ---------------------------------------------------------------------------
# Paginated listing (BK-123: _S3Base BFS via ls, not s3fs.find)
# ---------------------------------------------------------------------------


class TestS3SharedPaginatedListing:
    """BK-123: recursive listing uses BFS via ls() instead of s3fs.find()."""

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_PAGINATED, indirect=True)
    def test_list_files_recursive_nested_dirs(self, s3_any_backend: Backend) -> None:
        s3_any_backend.write("a/1.txt", b"one")
        s3_any_backend.write("a/b/2.txt", b"two")
        s3_any_backend.write("a/b/c/3.txt", b"three")
        files = list(s3_any_backend.list_files("a", recursive=True))
        names = {f.name for f in files}
        assert names == {"1.txt", "2.txt", "3.txt"}
        paths = {str(f.path) for f in files}
        assert "a/1.txt" in paths
        assert "a/b/2.txt" in paths
        assert "a/b/c/3.txt" in paths

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_PAGINATED, indirect=True)
    def test_get_folder_info_aggregates_nested(self, s3_any_backend: Backend) -> None:
        s3_any_backend.write("nest/x.txt", b"xx")
        s3_any_backend.write("nest/sub/y.txt", b"yyyy")
        s3_any_backend.write("nest/sub/deep/z.txt", b"zzzzzz")
        info = s3_any_backend.get_folder_info("nest")
        assert info.file_count == 3
        assert info.total_size == 2 + 4 + 6
        assert info.modified_at is not None

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_PAGINATED, indirect=True)
    def test_find_not_called_for_recursive_list(self, s3_any_backend: Backend) -> None:
        s3_any_backend.write("chk/a.txt", b"a")
        s3_any_backend.write("chk/b/c.txt", b"c")
        with patch.object(
            s3_any_backend._s3fs,
            "find",
            side_effect=AssertionError("find() should not be called"),
        ):
            files = list(s3_any_backend.list_files("chk", recursive=True))
        assert len(files) == 2

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_PAGINATED, indirect=True)
    def test_find_not_called_for_get_folder_info(self, s3_any_backend: Backend) -> None:
        s3_any_backend.write("fi2/a.txt", b"aaa")
        with patch.object(
            s3_any_backend._s3fs,
            "find",
            side_effect=AssertionError("find() should not be called"),
        ):
            info = s3_any_backend.get_folder_info("fi2")
        assert info.file_count == 1
        assert info.total_size == 3

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_PAGINATED, indirect=True)
    def test_find_not_called_for_list_folders(self, s3_any_backend: Backend) -> None:
        s3_any_backend.write("lf/sub/a.txt", b"a")
        with patch.object(
            s3_any_backend._s3fs,
            "find",
            side_effect=AssertionError("find() should not be called"),
        ):
            folders = list(s3_any_backend.list_folders("lf"))
        assert len(folders) == 1
        assert folders[0].name == "sub"


# ---------------------------------------------------------------------------
# Retry debug log (S3-026 ↔ S3PA-026, s3fs control path only). The PyArrow
# data-path retry test stays in test_s3_pyarrow.py.
# ---------------------------------------------------------------------------


class TestS3SharedRetryNonDefaultParams:
    """Non-default RetryPolicy logs a debug message and passes max_attempts only."""

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-026")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-026")),
        ],
    )
    def test_s3fs_non_default_retry_triggers_debug_log(
        self, backend_cls: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging
        from unittest.mock import MagicMock

        import s3fs as _s3fs

        from remote_store._config import RetryPolicy

        cls = _load_backend_cls(backend_cls)
        backend = cls(
            bucket="test-bucket",
            retry=RetryPolicy(max_attempts=3, backoff_base=2.0),
        )
        mock_fs = MagicMock(spec=_s3fs.S3FileSystem)
        with (
            caplog.at_level(logging.DEBUG, logger="remote_store.backends._s3_base"),
            patch("s3fs.S3FileSystem", return_value=mock_fs) as mock_s3fs_cls,
        ):
            _ = backend._s3fs
            # S3-026: retry policy lands as a plain dict in opts["config_kwargs"];
            # botocore.config.Config is no longer constructed by the builder.
            call_kwargs = mock_s3fs_cls.call_args.kwargs
            assert call_kwargs["config_kwargs"]["retries"] == {
                "max_attempts": 3,
                "mode": "standard",
            }
        assert any("only max_attempts is used" in rec.message for rec in caplog.records)

    @pytest.mark.parametrize(
        "backend_cls",
        [
            pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-026")),
            pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-026")),
        ],
    )
    def test_s3fs_client_kwargs_config_with_retry_is_rejected(self, backend_cls: str) -> None:
        """S3-026: caller-supplied ``client_kwargs['config']`` is rejected, even with retry=.

        Pre-fix the builder silently merged the pre-built Config into a
        ``client_kwargs['config']`` of its own, which always collided with
        s3fs's built-in ``config=AioConfig(...)``. The new contract is to
        fail fast with a ``ValueError`` pointing at the supported channel.
        """
        import botocore.config

        from remote_store._config import RetryPolicy

        cls = _load_backend_cls(backend_cls)
        existing_config = botocore.config.Config(max_pool_connections=20)
        backend = cls(
            bucket="test-bucket",
            client_options={"client_kwargs": {"config": existing_config}},
            retry=RetryPolicy(max_attempts=2),
        )
        with pytest.raises(ValueError, match="config_kwargs"):
            _ = backend._s3fs


# ---------------------------------------------------------------------------
# Error mapping (S3-015/S3PA-018, S3-018/S3PA-019): backend attribute on
# NotFound and RemoteStoreError. PermissionDenied and BackendUnavailable
# mapping are S3-specific (S3-016, S3-017) and stay in test_s3.py.
# ---------------------------------------------------------------------------


_LIVE_PARAMS_NOT_FOUND = [
    pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-015")),
    pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-018")),
]

_LIVE_PARAMS_ERROR_ATTR = [
    pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-018")),
    pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-019")),
]


class TestS3SharedErrorMapping:
    """S3-015/S3PA-018, S3-018/S3PA-019: backend attribute on exceptions."""

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_NOT_FOUND, indirect=True)
    def test_not_found_has_backend_attr(self, s3_any_backend: Backend) -> None:
        from remote_store._errors import NotFound

        with pytest.raises(NotFound) as exc_info:
            s3_any_backend.read_bytes("does-not-exist.txt")
        assert exc_info.value.backend == s3_any_backend.name

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_ERROR_ATTR, indirect=True)
    def test_error_has_backend_attribute(self, s3_any_backend: Backend) -> None:
        from remote_store._errors import RemoteStoreError

        with pytest.raises(RemoteStoreError) as exc_info:
            s3_any_backend.read("missing.txt")
        assert exc_info.value.backend == s3_any_backend.name


# ---------------------------------------------------------------------------
# Lifecycle (S3-020 ↔ S3PA-021): unwrap(s3fs.S3FileSystem). Close idempotency
# (S3-019 ↔ S3PA-020) is in TestS3SharedLifecycle above.
# ---------------------------------------------------------------------------


_LIVE_PARAMS_UNWRAP_S3FS = [
    pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-020")),
    pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-021")),
]


class TestS3SharedUnwrap:
    """S3-020/S3PA-021: both backends expose s3fs.S3FileSystem via unwrap()."""

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_UNWRAP_S3FS, indirect=True)
    def test_unwrap_s3fs(self, s3_any_backend: Backend) -> None:
        import s3fs

        fs = s3_any_backend.unwrap(s3fs.S3FileSystem)
        assert isinstance(fs, s3fs.S3FileSystem)


# ---------------------------------------------------------------------------
# ETag and digest (S3-023/S3PA-017, S3-024/S3PA-017): get_file_info returns
# ETag and SHA-256 ContentDigest. S3-specific digest paths (CRC32,
# _digest_from_head_response unit tests, list_files digest) stay in
# test_s3.py.
# ---------------------------------------------------------------------------


_LIVE_PARAMS_ETAG = [
    pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-023")),
    pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-017")),
]

_LIVE_PARAMS_DIGEST_SHA256 = [
    pytest.param(S3_CLS, id="s3", marks=pytest.mark.spec("S3-024")),
    pytest.param(S3PA_CLS, id="s3-pyarrow", marks=pytest.mark.spec("S3PA-017")),
]


class TestS3SharedETagAndDigest:
    """S3-023/S3PA-017, S3-024/S3PA-017: ETag and ContentDigest in FileInfo."""

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_ETAG, indirect=True)
    def test_get_file_info_has_etag(self, s3_any_backend: Backend) -> None:
        s3_any_backend.write("etag.txt", b"hello")
        fi = s3_any_backend.get_file_info("etag.txt")
        assert fi.etag is not None
        assert isinstance(fi.etag, str)
        assert '"' not in fi.etag
        assert fi.etag == fi.etag.lower()

    @pytest.mark.parametrize("s3_any_backend", _LIVE_PARAMS_DIGEST_SHA256, indirect=True)
    def test_get_file_info_has_digest_sha256(self, s3_any_backend: Backend, moto_server: str) -> None:
        import base64
        import hashlib

        from remote_store._models import ContentDigest

        content = b"hello checksum"
        expected_hex = hashlib.sha256(content).hexdigest()
        b64 = base64.b64encode(hashlib.sha256(content).digest()).decode()

        raw_client = boto3.client(
            "s3",
            endpoint_url=moto_server,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name=REGION,
        )
        raw_client.put_object(
            Bucket=s3_any_backend._bucket,
            Key="sha256_file.txt",
            Body=content,
            ChecksumAlgorithm="SHA256",
            ChecksumSHA256=b64,
        )

        fi = s3_any_backend.get_file_info("sha256_file.txt")
        assert fi.digest is not None
        assert isinstance(fi.digest, ContentDigest)
        assert fi.digest.algorithm == "sha256"
        assert fi.digest.value == expected_hex
