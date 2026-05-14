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

import socket
import time
import uuid
from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures._state import INFRA
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_meta = load_fixture("sftp_docker")

# id(backend) -> base_path on the server, used by _cleanup to remove the
# pre-created directory. Keyed by object id so the backend instance itself
# stays free of test-only attributes.
_BASE_PATHS: dict[int, str] = {}


def _wait_for_ssh_banner(host: str, port: int, retries: int = 10, delay: float = 0.5) -> bool:
    """Return True when the SSH banner is readable; False if all retries fail.

    Opens a plain TCP socket (no Paramiko) and reads the first bytes. Under
    heavy xdist parallelism the Docker-Desktop port-forwarding proxy sometimes
    closes the connection before sending the SSH banner, causing Paramiko's
    ``Error reading SSH protocol banner``. Retrying here lets the proxy settle
    without requiring a skip.
    """
    for _ in range(retries):
        try:
            with socket.create_connection((host, port), timeout=2) as sock:
                data = sock.recv(64)
                if data.startswith(b"SSH-"):
                    return True
        except OSError:
            pass
        time.sleep(delay)
    return False


def _factory() -> Backend:
    if INFRA.sftp_docker_port is None:
        pytest.skip("Dockerised SFTP not reachable on 127.0.0.1:2222")
    try:
        import paramiko

        from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend
    except ImportError:
        pytest.skip("paramiko not installed")

    base_path = f"/upload/test_{uuid.uuid4().hex[:8]}"

    # Under heavy xdist parallelism (20 workers) Docker Desktop's port-forward
    # proxy sometimes drops the TCP connection before the SSH banner arrives.
    # Pre-screen the banner via a plain socket so we skip rather than crash
    # with Paramiko's cryptic "Error reading SSH protocol banner".
    if not _wait_for_ssh_banner("127.0.0.1", INFRA.sftp_docker_port):
        pytest.skip("SFTP SSH banner not readable after retries (Docker proxy instability)")

    # SFTPBackend._ensure_parent_dirs early-returns when the parent equals
    # base_path, so the base_path itself must exist on the server before
    # construction. The in-process paramiko server we use elsewhere is
    # forgiving about this; the real openssh-sftp-server in the atmoz/sftp
    # container is not. Pre-create the directory via a short-lived client.
    #
    # Retry up to 3 times: even after _wait_for_ssh_banner returns True,
    # Docker Desktop's NAT layer can drop the very next TCP connection before
    # the SSH banner arrives (observed ~2% of the time with 20 xdist workers).
    for _attempt in range(3):
        transport = paramiko.Transport(("127.0.0.1", INFRA.sftp_docker_port))
        try:
            transport.connect(username="benchuser", password="benchpass")
        except paramiko.SSHException:
            transport.close()
            if _attempt == 2:
                pytest.skip("SFTP SSH banner dropped after 3 attempts (Docker proxy instability)")
            time.sleep(0.5)
            continue
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
        break

    # If SFTPBackend(...) raises after mkdir succeeded (host-key check, network
    # blip, credential mismatch), the orphan directory must still be removed:
    # _BASE_PATHS would never get the registration and _cleanup would have no
    # path to follow. Roll back the mkdir on ctor failure before re-raising.
    try:
        backend = SFTPBackend(
            host="127.0.0.1",
            port=INFRA.sftp_docker_port,
            username="benchuser",
            password="benchpass",
            base_path=base_path,
            host_key_policy=HostKeyPolicy.AUTO_ADD,
            connect_kwargs={"allow_agent": False, "look_for_keys": False},
        )
    except Exception:
        _remove_base_path(base_path)
        raise
    _BASE_PATHS[id(backend)] = base_path
    return backend


def _cleanup(backend: Backend) -> None:
    """Close the backend and remove the pre-created base_path on the server.

    Without this teardown, every conformance iteration would leave an
    orphaned ``/upload/test_<uuid>/`` directory on the atmoz/sftp container.
    """
    backend.close()
    base_path = _BASE_PATHS.pop(id(backend), None)
    if base_path is None:
        return
    _remove_base_path(base_path)


def _remove_base_path(base_path: str) -> None:
    """Best-effort recursive removal of ``base_path`` on the Docker SFTP server.

    Used by both ``_cleanup`` (normal teardown) and ``_factory`` (rollback when
    the SFTPBackend constructor raises after ``mkdir(base_path)`` already
    succeeded). Never raises; a teardown failure must not mask the underlying
    test result. The except clause catches ``Exception`` (not ``OSError``) on
    purpose: ``paramiko.Transport.connect`` raises ``paramiko.SSHException``
    on auth failure or connection refusal, and ``SSHException`` does not
    inherit from ``OSError``.
    """
    if INFRA.sftp_docker_port is None:
        return
    try:
        import paramiko
    except ImportError:
        return
    transport = paramiko.Transport(("127.0.0.1", INFRA.sftp_docker_port))
    try:
        transport.connect(username="benchuser", password="benchpass")
        sftp = paramiko.SFTPClient.from_transport(transport)
        if sftp is None:
            return
        try:
            _rmtree(sftp, base_path)
        finally:
            sftp.close()
    except Exception:  # noqa: BLE001 — best-effort teardown, never fail a test
        pass
    finally:
        transport.close()


def _rmtree(sftp: object, path: str) -> None:
    """Recursively remove ``path`` via the supplied paramiko SFTP client."""
    import contextlib

    import paramiko

    assert isinstance(sftp, paramiko.SFTPClient)
    try:
        entries = sftp.listdir_attr(path)
    except OSError:
        return
    for entry in entries:
        child = f"{path}/{entry.filename}"
        if entry.st_mode is not None and (entry.st_mode & 0o040000):
            _rmtree(sftp, child)
        else:
            with contextlib.suppress(OSError):
                sftp.remove(child)
    with contextlib.suppress(OSError):
        sftp.rmdir(path)


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._sftp import SFTPBackend
    except ImportError:
        return frozenset()
    return frozenset(SFTPBackend.CAPABILITIES)


register(
    BackendFixture(
        factory=_factory,
        capabilities=_capabilities(),
        cleanup=_cleanup,
        marks=(pytest.mark.requires_docker,),
        **_meta.to_kwargs(),
    )
)
