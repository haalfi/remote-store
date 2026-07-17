"""SFTPBackend WriteResult field population -- WR-003 / SFTP-003.

The cross-backend WriteResult contract (``source == "native"``, ``size`` equals
the byte count, populated-field-implies-capability) is owned by
``tests/backends/conformance/test_atomic.py::TestWriteResultConformance``,
which parametrizes over the whole fixture registry. This file pins what is
SFTP-specific and deliberate: SFTP's write path issues **no** ``stat`` after
the upload (BK-313), so ``last_modified`` is ``None`` even though the backend
declares ``WRITE_RESULT_NATIVE``.

The conformance suite records the same fact from the other direction -- a
``strict=True`` entry in its ``_LAST_MODIFIED_XFAIL`` registry, which fails
loud if SFTP ever starts populating the field again. This file states the
intent positively: ``None`` here is the contract, not a gap.
"""

from __future__ import annotations

import io
import uuid
from typing import TYPE_CHECKING

import pytest

# Guard: skip entire module if dependencies are missing
pytest.importorskip("paramiko", reason="paramiko not installed")

from tests.backends.fixtures._state import INFRA  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store.backends._sftp import SFTPBackend


@pytest.fixture
def sftp_backend() -> Iterator[SFTPBackend]:
    """SFTPBackend against the in-process paramiko server (no Docker)."""
    if INFRA.sftp_inproc_port is None:
        pytest.skip("in-process SFTP server unavailable")
    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

    backend = SFTPBackend(
        host="127.0.0.1",
        port=INFRA.sftp_inproc_port,
        username="testuser",
        password="testpass",
        base_path=f"/wr_{uuid.uuid4().hex[:8]}",
        host_key_policy=HostKeyPolicy.AUTO_ADD,
        connect_kwargs={"allow_agent": False, "look_for_keys": False},
    )
    try:
        yield backend
    finally:
        backend.close()


@pytest.mark.spec("WR-003")
@pytest.mark.spec("SFTP-003")
@pytest.mark.parametrize("op", ["write", "write_atomic"])
def test_write_result_last_modified_is_none(sftp_backend: SFTPBackend, op: str) -> None:
    """BK-313: the SFTP write path does not stat, so last_modified stays None.

    SFTP's write response carries no timestamp, and the post-write ``stat``
    that used to supply one cost a round-trip on every write. WR-001a permits
    ``last_modified is None`` when the write response omits it; SFTP is such a
    backend.
    """
    payload = b"bk313-payload"
    result = getattr(sftp_backend, op)(f"{op}-lm.txt", payload)
    assert result.last_modified is None


@pytest.mark.spec("WR-003")
@pytest.mark.parametrize("op", ["write", "write_atomic"])
def test_write_result_size_survives_without_the_stat(sftp_backend: SFTPBackend, op: str) -> None:
    """BK-313: size comes from counting bytes during upload, not from stat().

    Dropping the post-write ``stat`` must not regress ``size`` -- which is what
    keeps ``WRITE_RESULT_NATIVE`` justified on this backend. A non-seekable
    stream forces the counting branch, where a truncated count would otherwise
    go unnoticed.
    """
    payload = b"x" * (64 * 1024 + 7)
    result = getattr(sftp_backend, op)(f"{op}-size.bin", io.BytesIO(payload))
    assert result.size == len(payload)
    assert result.source == "native"
    assert sftp_backend.get_file_info(f"{op}-size.bin").size == len(payload)
