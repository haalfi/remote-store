"""What ``SFTPBackend`` does when its ``base_path`` does not exist.

BE-021's absent-container rule binds every backend, and this is the SFTP
container: the remote directory every key hangs off. Like `LocalBackend`'s root
it can be absent — a typo in configuration, or a directory removed under a live
backend — so the rule applies here as it does to a missing bucket.

This module exists because the clause claims to bind every backend and, until
it was written, three of them had been *measured* and this one had only been
read. That distinction stopped being academic during the same change:
`LocalBackend` was read as compliant by two independent reviewers and turned out
to raise `InvalidPath` for every operation once its root was deleted, because
the guard that fires sits upstream of the code both readers were looking at.
Reading a hierarchical backend's delete body is demonstrably not enough to know
what it answers, so this one is executed.

Stage 1: the in-process paramiko server, no Docker. The absent container needs
no teardown to arrange — a `base_path` that was never created *is* the case.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("paramiko", reason="paramiko not installed")

from remote_store._errors import NotFound  # noqa: E402
from tests.backends.fixtures._state import INFRA  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store.backends._sftp import SFTPBackend


@pytest.fixture
def absent_base_path_backend() -> Iterator[SFTPBackend]:
    """An ``SFTPBackend`` whose ``base_path`` was never created on the server."""
    if INFRA.sftp_inproc_port is None:
        pytest.skip("in-process SFTP server unavailable")
    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

    backend = SFTPBackend(
        host="127.0.0.1",
        port=INFRA.sftp_inproc_port,
        username="testuser",
        password="testpass",
        base_path=f"/absent_{uuid.uuid4().hex[:8]}",
        host_key_policy=HostKeyPolicy.AUTO_ADD,
        connect_kwargs={"allow_agent": False, "look_for_keys": False},
    )
    try:
        yield backend
    finally:
        backend.close()


@pytest.mark.spec("BE-012", "BE-013", "BE-021")
class TestAbsentBasePathReadsAsAbsentPath:
    """An absent ``base_path`` is an absent path, on the same terms as a missing bucket."""

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt", missing_ok=True)),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True, missing_ok=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_tolerant_delete_returns_cleanly(
        self,
        absent_base_path_backend: SFTPBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        assert call(absent_base_path_backend) is None, f"{op_name} must tolerate an absent base_path"

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt")),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_strict_delete_raises_not_found(
        self,
        absent_base_path_backend: SFTPBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """Both halves, so the tolerance is pinned as belonging to ``missing_ok``."""
        with pytest.raises(NotFound) as exc_info:
            call(absent_base_path_backend)
        assert exc_info.value.backend == "sftp"
