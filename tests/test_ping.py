"""Tests for Store.ping() and Backend.check_health() — spec 026."""

from __future__ import annotations

import contextlib
import errno
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from remote_store._errors import BackendUnavailable, NotFound, PermissionDenied
from remote_store._store import Store
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from remote_store._backend import Backend


# Tracker so an autouse fixture can close() backends made by the helpers below —
# without close, the SFTP/Azure helpers' __del__ emits ResourceWarning at GC.
_BACKENDS: list[Backend] = []


@pytest.fixture(autouse=True)
def _close_tracked_backends() -> Iterator[None]:
    yield
    while _BACKENDS:
        backend = _BACKENDS.pop()
        with contextlib.suppress(Exception):
            backend.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _s3_backend(bucket: str, side_effect: Any = None) -> Any:
    from s3fs import S3FileSystem

    from remote_store.backends._s3 import S3Backend

    s3_mock = MagicMock(spec=S3FileSystem)
    if side_effect is None:
        s3_mock.s3.head_bucket.return_value = {}
    else:
        s3_mock.s3.head_bucket.side_effect = side_effect
    backend = S3Backend(bucket=bucket)
    backend._fs_instance = s3_mock
    return backend, s3_mock


def _sftp_backend(stat_side_effect: Any = None) -> Any:
    from paramiko import SFTPAttributes, SFTPClient, SSHClient

    from remote_store.backends._sftp import SFTPBackend

    sftp_mock = MagicMock(spec=SFTPClient)
    if stat_side_effect is not None:
        sftp_mock.stat.side_effect = stat_side_effect
    else:
        sftp_mock.stat.return_value = MagicMock(spec=SFTPAttributes)
    backend = SFTPBackend(host="example.com", username="user", password="pass")
    backend._sftp_client = sftp_mock
    backend._ssh_client = MagicMock(spec=SSHClient)
    backend._ssh_client.get_transport.return_value.is_active.return_value = True
    _BACKENDS.append(backend)
    return backend, sftp_mock


def _azure_backend(side_effect: Any = None) -> Any:
    from azure.storage.blob import ContainerClient

    from remote_store.backends._azure import AzureBackend

    cc_mock = MagicMock(spec=ContainerClient)
    if side_effect is not None:
        cc_mock.get_container_properties.side_effect = side_effect
    else:
        cc_mock.get_container_properties.return_value = {}
    backend = AzureBackend(
        container="test",
        connection_string="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=dGVzdA==;EndpointSuffix=core.windows.net",
    )
    backend._cc_instance = cc_mock
    backend._hns_enabled = False
    _BACKENDS.append(backend)
    return backend, cc_mock


# ---------------------------------------------------------------------------
# Store.ping() delegation & defaults (PING-001/002/008)
# ---------------------------------------------------------------------------


class TestStorePingAndDefaults:
    @pytest.mark.spec("PING-002")
    def test_default_check_health_is_noop(self) -> None:
        result = MemoryBackend().check_health()
        assert result is None

    @pytest.mark.spec("PING-008")
    def test_memory_backend_always_healthy(self) -> None:
        result = Store(MemoryBackend()).ping()
        assert result is None

    @pytest.mark.spec("PING-001")
    def test_ping_delegates_to_check_health(self) -> None:
        backend = MemoryBackend()
        backend.check_health = MagicMock(spec=MemoryBackend.check_health)  # type: ignore[method-assign]
        result = Store(backend).ping()
        backend.check_health.assert_called_once()
        assert result is None

    @pytest.mark.spec("PING-001")
    def test_ping_propagates_exception(self) -> None:
        backend = MemoryBackend()
        mock_check = MagicMock(spec=MemoryBackend.check_health)
        mock_check.side_effect = BackendUnavailable("down", backend="memory")
        backend.check_health = mock_check  # type: ignore[method-assign]
        with pytest.raises(BackendUnavailable, match="down"):
            Store(backend).ping()

    @pytest.mark.spec("PING-001")
    def test_child_store_ping(self) -> None:
        result = Store(MemoryBackend()).child("subdir").ping()
        assert result is None


# ---------------------------------------------------------------------------
# LocalBackend.check_health() (PING-003)
# ---------------------------------------------------------------------------


class TestLocalCheckHealth:
    @pytest.mark.spec("PING-003")
    def test_healthy_local(self, tmp_path: Path) -> None:
        result = LocalBackend(root=str(tmp_path)).check_health()
        assert result is None

    @pytest.mark.spec("PING-003")
    def test_local_missing_root(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        backend = LocalBackend(root=str(missing))
        missing.rmdir()
        with pytest.raises(NotFound, match="Root directory not found"):
            backend.check_health()

    @pytest.mark.spec("PING-003")
    def test_local_unreadable_root(self, tmp_path: Path) -> None:
        backend = LocalBackend(root=str(tmp_path))
        with patch("os.access", return_value=False), pytest.raises(PermissionDenied, match="not readable"):
            backend.check_health()


# ---------------------------------------------------------------------------
# S3Backend.check_health() (PING-004)
# ---------------------------------------------------------------------------


class TestS3CheckHealth:
    @pytest.mark.spec("PING-004")
    def test_s3_healthy(self) -> None:
        backend, s3_mock = _s3_backend("test-bucket")
        result = backend.check_health()
        s3_mock.s3.head_bucket.assert_called_once_with(Bucket="test-bucket")
        assert result is None

    @pytest.mark.spec("PING-004")
    @pytest.mark.parametrize(
        ("side_effect", "expected"),
        [
            pytest.param(FileNotFoundError("nosuchbucket"), NotFound, id="not-found"),
            pytest.param(Exception("403 AccessDenied"), PermissionDenied, id="permission-denied"),
            pytest.param(Exception("Could not connect to the endpoint URL"), BackendUnavailable, id="unavailable"),
        ],
    )
    def test_s3_errors(self, side_effect: Exception, expected: type[Exception]) -> None:
        backend, _ = _s3_backend("bad-bucket", side_effect=side_effect)
        with pytest.raises(expected):
            backend.check_health()


# ---------------------------------------------------------------------------
# S3PyArrowBackend.check_health() (PING-005)
# ---------------------------------------------------------------------------


@pytest.mark.spec("PING-005")
@pytest.mark.parametrize(
    ("side_effect", "expected"),
    [
        pytest.param(None, None, id="healthy"),
        pytest.param(FileNotFoundError("not found"), NotFound, id="not-found"),
    ],
)
def test_s3_pyarrow_health(side_effect: Exception | None, expected: type[Exception] | None) -> None:
    from pyarrow.fs import FileInfo as PyArrowFileInfo
    from pyarrow.fs import S3FileSystem as PyArrowS3FileSystem

    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    pa_mock = MagicMock(spec=PyArrowS3FileSystem)
    if side_effect:
        pa_mock.get_file_info.side_effect = side_effect
    else:
        pa_mock.get_file_info.return_value = MagicMock(spec=PyArrowFileInfo)
    backend = S3PyArrowBackend(bucket="test-bucket")
    backend._pa_fs_instance = pa_mock
    if expected:
        with pytest.raises(expected):
            backend.check_health()
    else:
        backend.check_health()
        pa_mock.get_file_info.assert_called_once_with("test-bucket")


# ---------------------------------------------------------------------------
# SFTP & Azure check_health (PING-006 / PING-007)
# ---------------------------------------------------------------------------


@pytest.mark.spec("PING-006")
def test_sftp_healthy() -> None:
    backend, sftp_mock = _sftp_backend()
    backend.check_health()
    assert any(call.args == (backend._base_path,) for call in sftp_mock.stat.call_args_list)


@pytest.mark.spec("PING-006")
def test_sftp_not_found() -> None:
    from paramiko import SFTPAttributes

    err = OSError(errno.ENOENT, "No such file")
    backend, _ = _sftp_backend(stat_side_effect=[MagicMock(spec=SFTPAttributes), err])
    with pytest.raises(NotFound):
        backend.check_health()


@pytest.mark.spec("PING-007")
def test_azure_healthy() -> None:
    backend, cc_mock = _azure_backend()
    result = backend.check_health()
    cc_mock.get_container_properties.assert_called_once()
    assert result is None


@pytest.mark.spec("PING-007")
def test_azure_not_found() -> None:
    from azure.core.exceptions import ResourceNotFoundError

    backend, _ = _azure_backend(side_effect=ResourceNotFoundError("not found"))
    with pytest.raises(NotFound):
        backend.check_health()


# ---------------------------------------------------------------------------
# Observe integration (PING-010)
# ---------------------------------------------------------------------------


class TestPingObserve:
    @pytest.mark.spec("PING-010")
    @pytest.mark.parametrize(
        ("hook_kwarg", "check"),
        [
            pytest.param("on_ping", lambda events: events[0].operation == "ping", id="on_ping"),
            pytest.param("on_any", lambda events: any(e.operation == "ping" for e in events), id="on_any"),
        ],
    )
    def test_observe_hook_fires_for_ping(self, hook_kwarg: str, check: Any) -> None:
        from remote_store.ext.observe import observe

        events: list[Any] = []
        observed = observe(Store(MemoryBackend()), **{hook_kwarg: lambda e: events.append(e)})
        observed.ping()
        assert len(events) >= 1
        assert check(events)

    @pytest.mark.spec("PING-010")
    def test_observe_on_error_fires_for_failed_ping(self) -> None:
        from remote_store.ext.observe import observe

        errors: list[Any] = []
        backend = MemoryBackend()
        mock_check = MagicMock(spec=MemoryBackend.check_health)
        mock_check.side_effect = BackendUnavailable("down", backend="memory")
        backend.check_health = mock_check  # type: ignore[method-assign]
        observed = observe(Store(backend), on_error=lambda e: errors.append(e))
        with pytest.raises(BackendUnavailable):
            observed.ping()
        assert len(errors) == 1
        assert errors[0].error is not None
