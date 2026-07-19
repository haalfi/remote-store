"""Live SFTP correctness-edge checks (BK-316, audit-020 group G4).

The BK-316 edges manifest on error shapes a real OpenSSH server does not emit
(errno-less ``SSH_FX_FAILURE``, mode-less stats), so their *fixed shapes* are
proved by injection in ``tests/backends/sftp/test_config.py``. This module is the
**live** lane the audit's own method used: the OpenSSH-reproducible subset run
against the real ``atmoz/sftp`` container.

Coverage split (kept honest — see the BK-316 trace):

- **L5** (``open_atomic`` temp cleanup on ``GeneratorExit``): genuinely
  reproducible live — an abandoned block on the real server must leave no
  ``.~tmp.*`` orphan.
- **L1 permission path**: a real ``chmod 0o555`` directory yields
  ``PermissionDenied`` end-to-end (the exact classification-stat-``EACCES``
  combination stays injection-only; this proves the permission classification is
  healthy on real OpenSSH).
- **L3** (``delete`` under a file-ancestor): OpenSSH reports ``ENOENT`` so this is
  a **no-regression** check — the map to ``NotFound`` already held and must keep
  holding; the errno-less shape L3 fixes is injection-only.

L2 (mode-less) and L4 (reconnect-during-cleanup) are not reproducible on OpenSSH
and carry no live check here; they are injection-only by nature.

Requires: ``docker compose -f infra/docker-compose.yml up -d``
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from remote_store._errors import NotFound, PermissionDenied
from tests.e2e.conftest import sftp_skip

if TYPE_CHECKING:
    from remote_store import Store


@pytest.mark.integration
@sftp_skip
class TestSFTPCorrectnessEdgesLive:
    """BK-316 edges verified against the real ``atmoz/sftp`` (OpenSSH) container."""

    @pytest.mark.spec("SFTP-014")
    def test_open_atomic_generatorexit_leaves_no_temp_orphan(self, sftp_lake: Store) -> None:
        """L5 live: an abandoned ``open_atomic`` block orphans no temp file.

        The abnormal-exit cleanup used to run only under ``except Exception``, so a
        ``GeneratorExit`` (an abandoned / GC'd ``with`` block) closed the handle but
        left the ``.~tmp.*`` file on the server. Drive it end-to-end on real
        OpenSSH: after the interrupt, the destination directory must hold no temp
        litter and the target must be untouched.
        """
        with pytest.raises(GeneratorExit), sftp_lake.open_atomic("oa_ge.txt") as f:  # noqa: PT012
            f.write(b"partial")
            raise GeneratorExit

        temp_files = [fi for fi in sftp_lake.list_files("") if fi.name.startswith(".~tmp.")]
        assert temp_files == [], f"temp orphaned on GeneratorExit: {temp_files}"
        assert sftp_lake.exists("oa_ge.txt") is False

    @pytest.mark.spec("SFTP-021")
    def test_write_into_readonly_dir_maps_permission_denied(self, sftp_lake: Store) -> None:
        """L1 live: writing under a ``chmod 0o555`` directory yields ``PermissionDenied``.

        Confirms the permission-classification path end-to-end on real OpenSSH (the
        audit reproduced M2 the same way). The narrow L1 case — the *classification
        stat itself* failing ``EACCES`` — is injection-only; this proves a genuine
        server-denied write surfaces the mapped error, not a raw ``PermissionError``.
        """
        import paramiko

        client = sftp_lake.unwrap(paramiko.SFTPClient)
        # sftp_lake roots the backend at the container base_path, so a store-relative
        # path maps straight under it; ``_sftp_path`` gives the on-server absolute
        # path a raw ``chmod`` needs.
        ro_dir = sftp_lake._backend._sftp_path("ro_probe")  # noqa: SLF001 -- e2e needs the raw server path

        sftp_lake.write("ro_probe/keep.txt", b"seed")  # materialise the directory
        client.chmod(ro_dir, 0o555)
        try:
            with pytest.raises(PermissionDenied):
                sftp_lake.write("ro_probe/denied.txt", b"data", overwrite=True)
        finally:
            client.chmod(ro_dir, 0o755)  # restore so fixture teardown can rmtree

    @pytest.mark.spec("SFTP-020")
    def test_delete_under_file_ancestor_maps_not_found(self, sftp_lake: Store) -> None:
        """L3 no-regression: ``delete`` under a regular-file ancestor maps ``NotFound``.

        On OpenSSH the unlink fails ``ENOENT`` and already maps to ``NotFound``;
        L3 only adds the errno-less-server parity (injection-tested). This pins that
        the OpenSSH-visible behaviour the fix leaves untouched stays correct.
        """
        sftp_lake.write("ancestor.txt", b"i am a file")
        with pytest.raises(NotFound):
            sftp_lake.delete("ancestor.txt/child.txt")
