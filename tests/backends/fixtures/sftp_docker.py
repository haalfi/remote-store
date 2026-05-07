"""``sftp_docker`` fixture: SFTPBackend against the atmoz/sftp container.

Stage 2, real-local. The container ships with user ``benchuser`` /
password ``benchpass`` and an upload directory at ``/upload``; it is
defined in ``benchmarks/infra/docker-compose.yml`` and started by the
CI ``test`` and ``e2e`` jobs on port 2222.

This fixture differs from ``sftp_inproc`` only in its transport layer
(real SSH binary protocol against a Linux OpenSSH daemon, vs. an
in-process paramiko server). Both register independently so conformance
exercises both whenever Docker is available.
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
    if INFRA.sftp_docker_port is None:
        pytest.skip("Dockerised SFTP not reachable on 127.0.0.1:2222")
    try:
        import paramiko

        from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend
    except ImportError:
        pytest.skip("paramiko not installed")

    base_path = f"/upload/test_{uuid.uuid4().hex[:8]}"

    # SFTPBackend._ensure_parent_dirs early-returns when the parent equals
    # base_path, so the base_path itself must exist on the server before
    # construction. The in-process paramiko server we use elsewhere is
    # forgiving about this; the real openssh-sftp-server in the atmoz/sftp
    # container is not. Pre-create the directory via a short-lived client.
    transport = paramiko.Transport(("127.0.0.1", INFRA.sftp_docker_port))
    transport.connect(username="benchuser", password="benchpass")
    try:
        sftp = paramiko.SFTPClient.from_transport(transport)
        if sftp is None:
            transport.close()
            pytest.skip("paramiko could not open an SFTP channel")
        try:
            sftp.mkdir(base_path)
        finally:
            sftp.close()
    finally:
        transport.close()

    return SFTPBackend(
        host="127.0.0.1",
        port=INFRA.sftp_docker_port,
        username="benchuser",
        password="benchpass",
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
        name="sftp_docker",
        backend="sftp",
        factory=_factory,
        stage=2,
        kind="real-local",
        capabilities=_capabilities(),
        is_async=False,
        cleanup=_cleanup,
        marks=(pytest.mark.requires_docker,),
    )
)
