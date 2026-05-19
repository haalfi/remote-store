"""End-to-end cross-backend transfer tests.

Exercises ``ext.transfer.transfer()`` streaming data between different
Docker-backed stores, verifying content integrity, progress tracking,
and overwrite guard semantics.

Requires: ``docker compose -f infra/docker-compose.yml up -d``
"""

from __future__ import annotations

import pytest

from remote_store import Store  # noqa: TC001
from remote_store._errors import AlreadyExists
from remote_store.ext.transfer import transfer
from tests.e2e.conftest import (
    azurite_skip,
    minio_skip,
    sftp_skip,
)

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

SMALL_PAYLOAD = b"Hello from the transfer test!"
LARGE_PAYLOAD = b"X" * (256 * 1024)  # 256 KiB -- exercises chunked streaming


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_transfer(
    src: Store,
    dst: Store,
    payload: bytes,
    *,
    track_progress: bool = False,
) -> None:
    """Write *payload* to src, transfer to dst, verify content matches."""
    src.write("xfer-source.bin", payload)

    progress_bytes: list[int] = []

    def on_progress(n: int) -> None:
        progress_bytes.append(n)

    transfer(
        src,
        "xfer-source.bin",
        dst,
        "xfer-dest.bin",
        overwrite=True,
        on_progress=on_progress if track_progress else None,
    )

    assert dst.exists("xfer-dest.bin")
    assert dst.read_bytes("xfer-dest.bin") == payload

    if track_progress:
        assert sum(progress_bytes) == len(payload)

    # Clean up
    src.delete("xfer-source.bin")
    dst.delete("xfer-dest.bin")


def _assert_overwrite_guard(src: Store, dst: Store) -> None:
    """Verify transfer raises AlreadyExists when overwrite=False."""
    src.write("guard-src.bin", b"data")
    dst.write("guard-dst.bin", b"existing")

    with pytest.raises(AlreadyExists):
        transfer(src, "guard-src.bin", dst, "guard-dst.bin", overwrite=False)

    # Original content preserved
    assert dst.read_bytes("guard-dst.bin") == b"existing"

    # Clean up
    src.delete("guard-src.bin")
    dst.delete("guard-dst.bin")


# ---------------------------------------------------------------------------
# Cross-backend transfer tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.spec("ID-050")
class TestCrossBackendTransfer:
    """Transfer files between different Docker-backed stores."""

    # -- Memory -> Docker backends (baseline) --

    @minio_skip
    def test_memory_to_s3(self, memory_lake: Store, s3_lake: Store) -> None:
        """Transfer from Memory to S3."""
        _assert_transfer(memory_lake, s3_lake, SMALL_PAYLOAD)
        assert not s3_lake.exists("xfer-dest.bin")  # cleaned up

    @sftp_skip
    def test_memory_to_sftp(self, memory_lake: Store, sftp_lake: Store) -> None:
        """Transfer from Memory to SFTP."""
        _assert_transfer(memory_lake, sftp_lake, SMALL_PAYLOAD)
        assert not sftp_lake.exists("xfer-dest.bin")  # cleaned up

    @azurite_skip
    def test_memory_to_azure(self, memory_lake: Store, azurite_lake: Store) -> None:
        """Transfer from Memory to Azure."""
        _assert_transfer(memory_lake, azurite_lake, SMALL_PAYLOAD)
        assert not azurite_lake.exists("xfer-dest.bin")  # cleaned up

    # -- Docker backend -> Docker backend --

    @minio_skip
    @sftp_skip
    def test_s3_to_sftp(self, s3_lake: Store, sftp_lake: Store) -> None:
        """Transfer from S3 to SFTP with progress tracking."""
        _assert_transfer(s3_lake, sftp_lake, LARGE_PAYLOAD, track_progress=True)
        assert not sftp_lake.exists("xfer-dest.bin")  # cleaned up

    @sftp_skip
    @minio_skip
    def test_sftp_to_s3(self, sftp_lake: Store, s3_lake: Store) -> None:
        """Transfer from SFTP to S3."""
        _assert_transfer(sftp_lake, s3_lake, LARGE_PAYLOAD)
        assert not s3_lake.exists("xfer-dest.bin")  # cleaned up

    @azurite_skip
    @sftp_skip
    def test_azure_to_sftp(self, azurite_lake: Store, sftp_lake: Store) -> None:
        """Transfer from Azure to SFTP."""
        _assert_transfer(azurite_lake, sftp_lake, LARGE_PAYLOAD, track_progress=True)
        assert not sftp_lake.exists("xfer-dest.bin")  # cleaned up

    @sftp_skip
    @azurite_skip
    def test_sftp_to_azure(self, sftp_lake: Store, azurite_lake: Store) -> None:
        """Transfer from SFTP to Azure."""
        _assert_transfer(sftp_lake, azurite_lake, LARGE_PAYLOAD)
        assert not azurite_lake.exists("xfer-dest.bin")  # cleaned up

    @minio_skip
    @azurite_skip
    def test_s3_to_azure(self, s3_lake: Store, azurite_lake: Store) -> None:
        """Transfer from S3 to Azure with progress tracking."""
        _assert_transfer(s3_lake, azurite_lake, LARGE_PAYLOAD, track_progress=True)
        assert not azurite_lake.exists("xfer-dest.bin")  # cleaned up

    # -- Overwrite guard --

    @minio_skip
    @sftp_skip
    def test_overwrite_guard_s3_to_sftp(self, s3_lake: Store, sftp_lake: Store) -> None:
        """AlreadyExists raised when destination exists and overwrite=False."""
        _assert_overwrite_guard(s3_lake, sftp_lake)
        assert not sftp_lake.exists("guard-dst.bin")  # cleaned up

    @sftp_skip
    @azurite_skip
    def test_overwrite_guard_sftp_to_azure(self, sftp_lake: Store, azurite_lake: Store) -> None:
        """AlreadyExists raised when destination exists and overwrite=False."""
        _assert_overwrite_guard(sftp_lake, azurite_lake)
        assert not azurite_lake.exists("guard-dst.bin")  # cleaned up
