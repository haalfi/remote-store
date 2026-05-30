"""``sftp_chroot_inproc`` fixture: SFTPBackend against a chrooted server (ID-212).

Stage 1, real-local. The ``ChrootStubSFTPServer`` started by the
``sftp_chroot_server`` session fixture in ``tests.conftest`` serves a temp
directory but refuses to ``stat`` the ``CHROOT_BOUNDARY`` path and everything
above it, reproducing a chrooted deployment where an ancestor above the chroot
returns ``SSH_FX_PERMISSION_DENIED``.

The backend's ``base_path`` is a unique subdirectory *below* the boundary, so
the boundary is a denied proper ancestor of every backend path. The
file-ancestor walk in ``SFTPBackend._has_file_ancestor`` / ``_ensure_parent_dirs``
starts at ``base_path``: a walk from the absolute SFTP root ``/`` would trip the
denied boundary and mis-classify a genuine file-ancestor case, while the
base_path-relative walk never probes above it. ``strict_only`` keeps this
variant out of the default conformance enumeration — only the file-ancestor
error-fidelity tests (which pass ``include_strict_only=True``) run against it.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures._state import INFRA
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_meta = load_fixture("sftp_chroot_inproc")


def _factory() -> Backend:
    if INFRA.sftp_chroot_port is None:
        pytest.skip("paramiko not installed (in-process SFTP server unavailable)")
    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend
    from tests.backends.sftp._helpers import CHROOT_BOUNDARY

    # Unique root strictly below the denied boundary, so each test is isolated
    # while CHROOT_BOUNDARY stays a denied proper ancestor of base_path.
    #
    # Note: base_path itself is not pre-created. StubSFTPServer.open auto-creates
    # it via os.makedirs on the first write, so this fixture exercises the
    # stat/lstat *denial* above the chroot (what drives the base_path-relative
    # walk) but NOT the "base_path does not pre-exist" case — real OpenSSH does
    # not auto-create the base, and _ensure_parent_dirs short-circuits when
    # parent == base. A future hardening pass against real chroot OpenSSH should
    # add that coverage separately.
    base_path = f"{CHROOT_BOUNDARY}/test_{uuid.uuid4().hex[:8]}"
    return SFTPBackend(
        host="127.0.0.1",
        port=INFRA.sftp_chroot_port,
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
        factory=_factory,
        capabilities=_capabilities(),
        cleanup=_cleanup,
        **_meta.to_kwargs(),
    )
)
