"""``sftp_inproc`` fixture: SFTPBackend against an in-process paramiko server.

Stage 1, real-local. The paramiko server is started by the
``sftp_server`` session fixture in ``tests.conftest``. It is a real
SFTP service (binary SSH wire protocol) running in a thread of the
test process; no Docker required.

A Stage 2 ``sftp_docker`` fixture (atmoz/sftp on port 2222) is the
companion entry; both register independently so conformance can
exercise the paramiko server on every default run and the Dockerised
service when Docker is up.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._state import INFRA
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend


def _factory() -> Backend:
    if INFRA.sftp_inproc_port is None:
        pytest.skip("paramiko not installed (in-process SFTP server unavailable)")
    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

    base_path = f"/test_{uuid.uuid4().hex[:8]}"
    return SFTPBackend(
        host="127.0.0.1",
        port=INFRA.sftp_inproc_port,
        username="testuser",
        password="testpass",
        base_path=base_path,
        host_key_policy=HostKeyPolicy.AUTO_ADD,
        connect_kwargs={"allow_agent": False, "look_for_keys": False},
    )


def _cleanup(backend: Backend) -> None:
    backend.close()


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._sftp import SFTPBackend
    except ImportError:
        return frozenset()
    return frozenset(SFTPBackend.CAPABILITIES)


register(
    BackendFixture(
        name="sftp_inproc",
        backend="sftp",
        factory=_factory,
        stage=1,
        kind="real-local",
        capabilities=_capabilities(),
        is_async=False,
        cleanup=_cleanup,
    )
)
