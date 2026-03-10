"""Tests for Store.ping() and Backend.check_health() — spec 026."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from remote_store._errors import BackendUnavailable, NotFound, PermissionDenied
from remote_store._store import Store
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Backend.check_health() default — no-op (PING-002, PING-008)
# ---------------------------------------------------------------------------


class TestBackendCheckHealthDefault:
    """Default check_health() is a no-op — always succeeds."""

    @pytest.mark.spec("PING-002")
    def test_default_check_health_is_noop(self) -> None:
        """Memory backend inherits the default no-op check_health()."""
        backend = MemoryBackend()
        backend.check_health()  # should not raise

    @pytest.mark.spec("PING-008")
    def test_memory_backend_always_healthy(self) -> None:
        store = Store(MemoryBackend())
        store.ping()  # should not raise


# ---------------------------------------------------------------------------
# Store.ping() delegation (PING-001)
# ---------------------------------------------------------------------------


class TestStorePing:
    @pytest.mark.spec("PING-001")
    def test_ping_delegates_to_check_health(self) -> None:
        backend = MemoryBackend()
        backend.check_health = MagicMock()  # type: ignore[method-assign]
        store = Store(backend)
        store.ping()
        backend.check_health.assert_called_once()

    @pytest.mark.spec("PING-001")
    def test_ping_propagates_exception(self) -> None:
        backend = MemoryBackend()
        backend.check_health = MagicMock(  # type: ignore[method-assign]
            side_effect=BackendUnavailable("down", backend="memory"),
        )
        store = Store(backend)
        with pytest.raises(BackendUnavailable, match="down"):
            store.ping()


# ---------------------------------------------------------------------------
# LocalBackend.check_health() (PING-003)
# ---------------------------------------------------------------------------


class TestLocalCheckHealth:
    @pytest.mark.spec("PING-003")
    def test_healthy_local(self, tmp_path: Path) -> None:
        backend = LocalBackend(root=str(tmp_path))
        backend.check_health()  # should not raise

    @pytest.mark.spec("PING-003")
    def test_local_missing_root(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        # LocalBackend.__init__ creates the directory, so we delete it after
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
# S3Backend.check_health() (PING-004) — mocked
# ---------------------------------------------------------------------------


class TestS3CheckHealth:
    @pytest.mark.spec("PING-004")
    def test_s3_healthy(self) -> None:
        s3_mock = MagicMock()
        s3_mock.s3.head_bucket.return_value = {}

        with patch("remote_store.backends._s3.S3Backend._fs", new_callable=lambda: property(lambda self: s3_mock)):
            from remote_store.backends._s3 import S3Backend

            backend = S3Backend(bucket="test-bucket")
            backend._fs_instance = s3_mock
            backend.check_health()
            s3_mock.s3.head_bucket.assert_called_once_with(Bucket="test-bucket")

    @pytest.mark.spec("PING-004")
    def test_s3_bucket_not_found(self) -> None:
        from remote_store.backends._s3 import S3Backend

        s3_mock = MagicMock()
        s3_mock.s3.head_bucket.side_effect = FileNotFoundError("nosuchbucket")

        backend = S3Backend(bucket="bad-bucket")
        backend._fs_instance = s3_mock
        with pytest.raises(NotFound):
            backend.check_health()

    @pytest.mark.spec("PING-004")
    def test_s3_permission_denied(self) -> None:
        from remote_store.backends._s3 import S3Backend

        s3_mock = MagicMock()
        s3_mock.s3.head_bucket.side_effect = Exception("403 AccessDenied")

        backend = S3Backend(bucket="restricted")
        backend._fs_instance = s3_mock
        with pytest.raises(PermissionDenied):
            backend.check_health()

    @pytest.mark.spec("PING-004")
    def test_s3_unavailable(self) -> None:
        from remote_store.backends._s3 import S3Backend

        s3_mock = MagicMock()
        s3_mock.s3.head_bucket.side_effect = Exception("Could not connect to the endpoint URL")

        backend = S3Backend(bucket="unreachable")
        backend._fs_instance = s3_mock
        with pytest.raises(BackendUnavailable):
            backend.check_health()


# ---------------------------------------------------------------------------
# S3PyArrowBackend.check_health() (PING-005) — mocked
# ---------------------------------------------------------------------------


class TestS3PyArrowCheckHealth:
    @pytest.mark.spec("PING-005")
    def test_s3_pyarrow_healthy(self) -> None:
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        pa_mock = MagicMock()
        pa_mock.get_file_info.return_value = MagicMock()

        backend = S3PyArrowBackend(bucket="test-bucket")
        backend._pa_fs_instance = pa_mock
        backend.check_health()
        pa_mock.get_file_info.assert_called_once_with("test-bucket")

    @pytest.mark.spec("PING-005")
    def test_s3_pyarrow_not_found(self) -> None:
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        pa_mock = MagicMock()
        pa_mock.get_file_info.side_effect = FileNotFoundError("not found")

        backend = S3PyArrowBackend(bucket="bad-bucket")
        backend._pa_fs_instance = pa_mock
        with pytest.raises(NotFound):
            backend.check_health()


# ---------------------------------------------------------------------------
# SFTPBackend.check_health() (PING-006) — mocked
# ---------------------------------------------------------------------------


class TestSFTPCheckHealth:
    @pytest.mark.spec("PING-006")
    def test_sftp_healthy(self) -> None:
        from remote_store.backends._sftp import SFTPBackend

        sftp_mock = MagicMock()
        sftp_mock.stat.return_value = MagicMock()

        backend = SFTPBackend(host="example.com", username="user", password="pass")
        backend._sftp_client = sftp_mock
        backend._ssh_client = MagicMock()
        backend._ssh_client.get_transport.return_value.is_active.return_value = True
        backend.check_health()
        # _is_connected() calls stat('.'), then check_health() calls stat(base_path)
        assert any(call.args == (backend._base_path,) for call in sftp_mock.stat.call_args_list)

    @pytest.mark.spec("PING-006")
    def test_sftp_not_found(self) -> None:
        import errno

        from remote_store.backends._sftp import SFTPBackend

        sftp_mock = MagicMock()
        # First call from _is_connected() succeeds, second from check_health() fails
        err = OSError(errno.ENOENT, "No such file")
        sftp_mock.stat.side_effect = [MagicMock(), err]

        backend = SFTPBackend(host="example.com", username="user", password="pass")
        backend._sftp_client = sftp_mock
        backend._ssh_client = MagicMock()
        backend._ssh_client.get_transport.return_value.is_active.return_value = True
        with pytest.raises(NotFound):
            backend.check_health()


# ---------------------------------------------------------------------------
# AzureBackend.check_health() (PING-007) — mocked
# ---------------------------------------------------------------------------


class TestAzureCheckHealth:
    @pytest.mark.spec("PING-007")
    def test_azure_healthy_non_hns(self) -> None:
        from remote_store.backends._azure import AzureBackend

        cc_mock = MagicMock()
        cc_mock.get_container_properties.return_value = {}

        backend = AzureBackend(
            container="test",
            connection_string="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=dGVzdA==;EndpointSuffix=core.windows.net",
        )
        backend._cc_instance = cc_mock
        backend._hns_enabled = False
        backend.check_health()
        cc_mock.get_container_properties.assert_called_once()

    @pytest.mark.spec("PING-007")
    def test_azure_container_not_found(self) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        from remote_store.backends._azure import AzureBackend

        cc_mock = MagicMock()
        cc_mock.get_container_properties.side_effect = ResourceNotFoundError("not found")

        backend = AzureBackend(
            container="bad",
            connection_string="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=dGVzdA==;EndpointSuffix=core.windows.net",
        )
        backend._cc_instance = cc_mock
        backend._hns_enabled = False
        with pytest.raises(NotFound):
            backend.check_health()


# ---------------------------------------------------------------------------
# Observe integration (PING-010)
# ---------------------------------------------------------------------------


class TestPingObserve:
    @pytest.mark.spec("PING-010")
    def test_observe_on_ping_hook(self) -> None:
        from remote_store.ext.observe import observe

        events: list[Any] = []
        store = Store(MemoryBackend())
        observed = observe(store, on_ping=lambda e: events.append(e))
        observed.ping()
        assert len(events) == 1
        assert events[0].operation == "ping"

    @pytest.mark.spec("PING-010")
    def test_observe_on_any_fires_for_ping(self) -> None:
        from remote_store.ext.observe import observe

        events: list[Any] = []
        store = Store(MemoryBackend())
        observed = observe(store, on_any=lambda e: events.append(e))
        observed.ping()
        assert any(e.operation == "ping" for e in events)

    @pytest.mark.spec("PING-010")
    def test_observe_on_error_fires_for_failed_ping(self) -> None:
        from remote_store.ext.observe import observe

        errors: list[Any] = []
        backend = MemoryBackend()
        backend.check_health = MagicMock(  # type: ignore[method-assign]
            side_effect=BackendUnavailable("down", backend="memory"),
        )
        store = Store(backend)
        observed = observe(store, on_error=lambda e: errors.append(e))
        with pytest.raises(BackendUnavailable):
            observed.ping()
        assert len(errors) == 1
        assert errors[0].error is not None


# ---------------------------------------------------------------------------
# Store.ping() via child store (PING-001)
# ---------------------------------------------------------------------------


class TestPingChildStore:
    @pytest.mark.spec("PING-001")
    def test_child_store_ping(self) -> None:
        """Child stores delegate ping to the shared backend."""
        store = Store(MemoryBackend())
        child = store.child("subdir")
        child.ping()  # should not raise
