"""SFTPBackend check_health() probe-identity and error-mapping tests -- PING-006.

The healthy-path assertion (``check_health() is None``) is the universal
ABC contract covered by tests/backends/conformance/test_check_health.py.
This file pins what is SFTP-specific:

- The probe is ``sftp_client.stat(base_path)`` -- a single round-trip to
  the path the backend is rooted at, not a directory listing.
- ``OSError(errno=ENOENT)`` from paramiko maps to ``NotFound`` (PING-009).

Migrated from tests/test_ping.py (BK-217 / BK-191 slice 2/6).
"""

from __future__ import annotations

import contextlib
import errno
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

# Guard: skip entire module if dependencies are missing
pytest.importorskip("paramiko", reason="paramiko not installed")

from remote_store._errors import NotFound  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


# Tracker so an autouse fixture can close() backends made by the helper below —
# without close, SFTPBackend.__del__ emits ResourceWarning at GC.
_BACKENDS: list[Backend] = []


@pytest.fixture(autouse=True)
def _close_tracked_backends() -> Iterator[None]:
    yield
    while _BACKENDS:
        backend = _BACKENDS.pop()
        with contextlib.suppress(Exception):
            backend.close()


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


@pytest.mark.spec("PING-006")
def test_sftp_probe_is_stat_basepath() -> None:
    backend, sftp_mock = _sftp_backend()
    backend.check_health()
    # internal: no public observable — base_path is the SFTP-specific probe target;
    # the assertion pins that stat() was called with it (Rule 3 exception).
    assert any(call.args == (backend._base_path,) for call in sftp_mock.stat.call_args_list)


@pytest.mark.spec("PING-006")
def test_sftp_not_found() -> None:
    err = OSError(errno.ENOENT, "No such file")
    # BK-313: liveness is now a local ``is_active()`` check (mocked True in the
    # helper), so ``check_health``'s base-path ``stat`` is the only round-trip —
    # a single side-effect, not two.
    backend, _ = _sftp_backend(stat_side_effect=[err])
    with pytest.raises(NotFound):
        backend.check_health()


@pytest.mark.spec("SFTP-010")
def test_is_connected_uses_transport_active_not_a_round_trip() -> None:
    """BK-313: liveness reads the transport's active flag, issuing no ``stat``.

    An inactive transport reads as not-connected (so the next ``_sftp`` access
    reconnects), and the check never calls ``stat`` — the round-trip that used
    to be paid on every property access.
    """
    backend, sftp_mock = _sftp_backend()
    assert backend._is_connected() is True
    backend._ssh_client.get_transport.return_value.is_active.return_value = False
    assert backend._is_connected() is False
    # internal: the liveness check must not probe the wire (Rule 3 exception).
    sftp_mock.stat.assert_not_called()
