"""End-to-end SFTP workflow test.

Typical SFTP flow: check for new files in an inbox, fetch them,
place daily files if they don't already exist.

Requires: ``docker compose -f benchmarks/infra/docker-compose.yml up -d``
"""

from __future__ import annotations

import pytest

from remote_store import Store  # noqa: TC001
from remote_store._errors import AlreadyExists
from tests.e2e.conftest import sftp_skip


@pytest.mark.integration
@pytest.mark.spec("ID-050")
@sftp_skip
class TestSFTPWorkflow:
    """Typical SFTP file-exchange workflow against Docker SFTP."""

    def test_check_fetch_place(self, sftp_lake: Store) -> None:
        """Check for new files, fetch them, place daily files if not exists."""
        inbox = sftp_lake.child("inbox")
        archive = sftp_lake.child("archive")

        # --- Producer drops files into inbox ---
        inbox.write("report-2026-03-01.csv", b"date,value\n2026-03-01,100\n")
        inbox.write("report-2026-03-02.csv", b"date,value\n2026-03-02,200\n")
        inbox.write("report-2026-03-03.csv", b"date,value\n2026-03-03,300\n")

        # --- Consumer: check for new files ---
        new_files = list(inbox.list_files(""))
        names = sorted(str(f.path) for f in new_files)
        assert names == [
            "report-2026-03-01.csv",
            "report-2026-03-02.csv",
            "report-2026-03-03.csv",
        ]

        # --- Consumer: fetch each file ---
        for fi in new_files:
            key = str(fi.path)
            content = inbox.read_bytes(key)
            assert b"date,value" in content

            # Place into archive (if not exists)
            archive.write(key, content)

        # --- Verify archive ---
        archived = sorted(str(f.path) for f in archive.list_files(""))
        assert archived == names

        # --- Re-placing should fail (overwrite=False default) ---
        with pytest.raises(AlreadyExists):
            archive.write("report-2026-03-01.csv", b"duplicate")

        # --- Clean up inbox after processing ---
        for fi in new_files:
            inbox.delete(str(fi.path))

        remaining = list(inbox.list_files(""))
        assert remaining == []

    def test_incremental_pickup(self, sftp_lake: Store) -> None:
        """Only pick up files that aren't already archived."""
        inbox = sftp_lake.child("inbox")
        archive = sftp_lake.child("archive")

        # Pre-existing archived file
        archive.write("day-01.dat", b"already processed")

        # New batch arrives in inbox
        inbox.write("day-01.dat", b"old data (already archived)")
        inbox.write("day-02.dat", b"new data")

        archived_keys = {str(f.path) for f in archive.list_files("")}

        for fi in inbox.list_files(""):
            key = str(fi.path)
            if key not in archived_keys:
                content = inbox.read_bytes(key)
                archive.write(key, content)

        # day-01 unchanged, day-02 added
        assert archive.read_bytes("day-01.dat") == b"already processed"
        assert archive.read_bytes("day-02.dat") == b"new data"

    def test_folder_operations(self, sftp_lake: Store) -> None:
        """Folders created implicitly by writes; list and delete them."""
        # Writing files implicitly creates parent folders
        sftp_lake.write("staging/a.txt", b"a")
        sftp_lake.write("processed/b.txt", b"b")

        folders = set(sftp_lake.list_folders(""))
        assert {"staging", "processed"} <= folders

        # Clean up files, then delete folder
        sftp_lake.delete("staging/a.txt")
        sftp_lake.delete_folder("staging")

        folders_after = set(sftp_lake.list_folders(""))
        assert "staging" not in folders_after

        # Clean up processed too
        sftp_lake.delete("processed/b.txt")
        sftp_lake.delete_folder("processed")

    def test_atomic_write(self, sftp_lake: Store) -> None:
        """open_atomic() on SFTP uses temp file + posix_rename."""
        with sftp_lake.open_atomic("atomic.txt") as f:
            f.write(b"committed content")

        assert sftp_lake.read_bytes("atomic.txt") == b"committed content"
        sftp_lake.delete("atomic.txt")

    def test_overwrite_existing(self, sftp_lake: Store) -> None:
        """Overwrite an existing file with overwrite=True."""
        sftp_lake.write("update-me.txt", b"v1")
        assert sftp_lake.read_bytes("update-me.txt") == b"v1"

        sftp_lake.write("update-me.txt", b"v2", overwrite=True)
        assert sftp_lake.read_bytes("update-me.txt") == b"v2"

        sftp_lake.delete("update-me.txt")
