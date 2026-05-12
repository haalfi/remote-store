"""BK-198: SFTPUtils.enable_ssh_rsa_compat recovery semantics against a real
legacy SSH server (ssh-rsa-only host key).

This is the durable counterpart to the one-off probe in
``sdd/research/research-bk-198-paramiko-ssh-rsa-empirical.md``: that note
ran an out-of-tree matrix across four paramiko versions to characterise
the helper's behaviour. This module locks the result that matters for the
shipping code — namely that the helper recovers the connection when (and
only when) ``ssh-rsa`` has been cleared from paramiko's defaults —
against the currently-installed paramiko, using a Dockerized server.

Requires:
    docker compose -f benchmarks/infra/docker-compose.yml up -d legacy-sftp

Test is skipped when the legacy-sftp container is not reachable on
``127.0.0.1:2223`` (env-overridable: ``E2E_LEGACY_SFTP_PORT`` etc.).
"""

from __future__ import annotations

import pytest

paramiko = pytest.importorskip("paramiko", reason="paramiko not installed")

from remote_store.backends._sftp import SFTPUtils  # noqa: E402
from tests.e2e.conftest import (  # noqa: E402
    LEGACY_SFTP_HOST,
    LEGACY_SFTP_PASS,
    LEGACY_SFTP_PORT,
    LEGACY_SFTP_USER,
    legacy_sftp_skip,
)


def _try_connect() -> tuple[bool, str]:
    """Return (ok, exc_description). Uses paramiko directly so we can
    observe the raw exception type from negotiation."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=LEGACY_SFTP_HOST,
            port=LEGACY_SFTP_PORT,
            username=LEGACY_SFTP_USER,
            password=LEGACY_SFTP_PASS,
            timeout=5,
            banner_timeout=5,
            auth_timeout=5,
            allow_agent=False,
            look_for_keys=False,
        )
        client.close()
        return True, ""
    except Exception as exc:  # noqa: BLE001 -- probe wants the raw type
        return False, f"{type(exc).__name__}: {exc}"


def _clear_ssh_rsa_from_paramiko() -> None:
    """Simulate downstream code that strips ssh-rsa from paramiko's four
    host-key sites — the only state in which the helper meaningfully
    changes behaviour. Restored by the ``restore_paramiko_state`` fixture
    after the test (defined inline below)."""
    from paramiko.rsakey import RSAKey

    t = paramiko.Transport
    t._preferred_keys = tuple(k for k in t._preferred_keys if k != "ssh-rsa")
    t._preferred_pubkeys = tuple(k for k in t._preferred_pubkeys if k != "ssh-rsa")
    t._key_info.pop("ssh-rsa", None)
    RSAKey.HASHES.pop("ssh-rsa", None)


@pytest.fixture
def restore_paramiko_state() -> object:
    """Snapshot paramiko class-attr state and restore after the test.

    Tests in this module mutate process-global paramiko state to simulate
    the cleared-defaults scenario. Without snapshot/restore the
    subsequent test would inherit a corrupted state.
    """
    from paramiko.rsakey import RSAKey

    saved_keys = paramiko.Transport._preferred_keys
    saved_pubkeys = paramiko.Transport._preferred_pubkeys
    saved_key_info = dict(paramiko.Transport._key_info)
    saved_hashes = dict(RSAKey.HASHES)
    yield None
    paramiko.Transport._preferred_keys = saved_keys
    paramiko.Transport._preferred_pubkeys = saved_pubkeys
    paramiko.Transport._key_info.clear()
    paramiko.Transport._key_info.update(saved_key_info)
    RSAKey.HASHES.clear()
    RSAKey.HASHES.update(saved_hashes)


@pytest.mark.integration
@pytest.mark.spec("BK-198")
@legacy_sftp_skip
class TestSFTPLegacyRecovery:
    """End-to-end verification of enable_ssh_rsa_compat's recovery
    semantics against an ssh-rsa-only server.

    Locks the empirical findings recorded in
    ``sdd/research/research-bk-198-paramiko-ssh-rsa-empirical.md``:
    paramiko's defaults already negotiate against the server (S1); the
    helper is a no-op when defaults contain ssh-rsa (S2, asserted
    implicitly by S1 success); the failure reproduces only after
    clearing ssh-rsa (S3); the helper recovers it (S4).
    """

    def test_S1_bare_connect_succeeds_on_defaults(self) -> None:
        """Paramiko defaults already accept ssh-rsa host keys; no helper
        required for the legacy server. Falsifies the original PR claim
        that the helper is *required* for legacy servers."""
        ok, exc_desc = _try_connect()
        assert ok, f"bare connect should succeed on paramiko defaults; got {exc_desc}"

    def test_S3_connect_fails_after_clearing_ssh_rsa(
        self,
        restore_paramiko_state: None,  # noqa: ARG002
    ) -> None:
        """When ssh-rsa is stripped from the four sites, the legacy server
        becomes unreachable and paramiko raises
        ``IncompatiblePeer: ... no acceptable host key``. This is the
        scenario the helper is designed to recover."""
        _clear_ssh_rsa_from_paramiko()
        ok, exc_desc = _try_connect()
        assert not ok, "connect should fail after clearing ssh-rsa from defaults"
        assert "IncompatiblePeer" in exc_desc, exc_desc
        assert "host key" in exc_desc, exc_desc

    def test_S4_helper_recovers_after_clear(
        self,
        restore_paramiko_state: None,  # noqa: ARG002
    ) -> None:
        """After clearing ssh-rsa and then calling
        ``enable_ssh_rsa_compat()``, the connection succeeds again. This
        is the only scenario in which the helper meaningfully changes
        behaviour on a modern paramiko."""
        _clear_ssh_rsa_from_paramiko()
        ok_before, exc_before = _try_connect()
        assert not ok_before, f"cleared state should fail; got {exc_before}"

        SFTPUtils.enable_ssh_rsa_compat()

        ok_after, exc_after = _try_connect()
        assert ok_after, f"helper should recover; got {exc_after}"
