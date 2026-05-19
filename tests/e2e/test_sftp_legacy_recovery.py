"""BK-198: SFTPUtils.enable_ssh_rsa_compat recovery semantics against a real
legacy SSH server (ssh-rsa-only host key).

This is the durable counterpart to the one-off probe matrix in
``sdd/research/research-bk-198-paramiko-ssh-rsa-empirical.md``: that note
ran an out-of-tree matrix across paramiko 2.12 / 3.0 / 3.5 / 4.0 / 5.0 to
characterise the helper's behaviour. This module locks the two results
that matter for the shipping code against the currently-installed
paramiko, using a Dockerized server:

- on paramiko < 5, ``ssh-rsa`` ships in defaults so bare connect works
  and the helper is a no-op;
- on paramiko >= 5, ``ssh-rsa`` was cleared from defaults so bare connect
  fails with ``IncompatiblePeer: no acceptable host key`` and the helper
  re-adds the four entries to restore the connection.

Requires:
    docker compose -f infra/docker-compose.yml up -d legacy-sftp

Test is skipped when the legacy-sftp container is not reachable on
``127.0.0.1:2223`` (env-overridable: ``E2E_LEGACY_SFTP_PORT`` etc.).
"""

from __future__ import annotations

import pytest

paramiko = pytest.importorskip("paramiko", reason="paramiko not installed")

from infra._settings import (  # noqa: E402
    LEGACY_SFTP_HOST,
    LEGACY_SFTP_PASS,
    LEGACY_SFTP_PORT,
    LEGACY_SFTP_USER,
)
from remote_store.backends._sftp import SFTPUtils  # noqa: E402
from tests.e2e.conftest import legacy_sftp_skip  # noqa: E402

_PARAMIKO_MAJOR = int(paramiko.__version__.split(".", 1)[0])
_SSH_RSA_IN_DEFAULTS = _PARAMIKO_MAJOR < 5

_skip_unless_pre5 = pytest.mark.skipif(
    not _SSH_RSA_IN_DEFAULTS,
    reason=(
        f"paramiko {paramiko.__version__} >= 5: ssh-rsa removed from defaults; "
        "bare-connect-succeeds invariant only holds on paramiko < 5"
    ),
)
_skip_unless_5plus = pytest.mark.skipif(
    _SSH_RSA_IN_DEFAULTS,
    reason=(
        f"paramiko {paramiko.__version__} < 5: ssh-rsa in defaults; "
        "bare-connect-fails invariant only holds on paramiko >= 5"
    ),
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
    ``sdd/research/research-bk-198-paramiko-ssh-rsa-empirical.md``.
    S1 is split into two version-skipif'd siblings (S1a / S1b) so each
    test has a single straight-line assertion path:

    - **S1a** (paramiko < 5): ssh-rsa is in defaults; bare connect
      succeeds. S2 helper is a no-op (asserted implicitly by S1a success).
    - **S1b** (paramiko >= 5): ssh-rsa was cleared from defaults; bare
      connect fails with ``IncompatiblePeer: no acceptable host key`` --
      the exact failure mode the helper exists to repair.
    - **S3 / S4** (both ranges): clearing ssh-rsa from a paramiko < 5
      process (S3) reproduces the paramiko 5 failure, and the helper
      recovers it (S4).
    """

    @_skip_unless_pre5
    def test_S1a_bare_connect_succeeds_on_paramiko_lt5(self) -> None:
        """On paramiko < 5, ssh-rsa is in defaults at all four sites and
        the legacy server connects out of the box -- no helper required.

        Skipped on paramiko >= 5 where this invariant does not hold (see
        the sibling test_S1b for that branch).
        """
        ok, exc_desc = _try_connect()
        assert ok, (
            f"paramiko {paramiko.__version__}: bare connect should succeed "
            f"(ssh-rsa is in defaults on paramiko < 5); got {exc_desc}"
        )

    @_skip_unless_5plus
    def test_S1b_bare_connect_fails_on_paramiko_ge5(self) -> None:
        """On paramiko >= 5, ssh-rsa was removed from all four host-key
        sites and the bare connect fails immediately in
        ``Transport._parse_kex_init`` with ``IncompatiblePeer: no
        acceptable host key`` -- the exact failure mode the helper
        exists to repair.

        Skipped on paramiko < 5 where defaults already include ssh-rsa
        (see the sibling test_S1a for that branch).
        """
        ok, exc_desc = _try_connect()
        assert not ok, (
            f"paramiko {paramiko.__version__}: bare connect should fail "
            f"(ssh-rsa was removed from defaults on paramiko >= 5)"
        )
        assert "IncompatiblePeer" in exc_desc, exc_desc
        assert "host key" in exc_desc, exc_desc

    def test_S3_connect_fails_after_clearing_ssh_rsa(
        self,
        restore_paramiko_state: None,  # noqa: ARG002
    ) -> None:
        """When ssh-rsa is stripped from the four sites, the legacy server
        becomes unreachable and paramiko raises
        ``IncompatiblePeer: ... no acceptable host key``. This is the
        scenario the helper is designed to recover. On paramiko >= 5 the
        defaults are already cleared so the explicit clear is a no-op.
        """
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
        is the scenario in which the helper meaningfully changes
        behaviour: paramiko < 5 with explicitly-cleared defaults, or
        paramiko >= 5 where the defaults already lack ssh-rsa.
        """
        _clear_ssh_rsa_from_paramiko()
        ok_before, exc_before = _try_connect()
        assert not ok_before, f"cleared state should fail; got {exc_before}"

        SFTPUtils.enable_ssh_rsa_compat()

        ok_after, exc_after = _try_connect()
        assert ok_after, f"helper should recover; got {exc_after}"


@pytest.mark.integration
@pytest.mark.spec("BK-200")
@legacy_sftp_skip
class TestSFTPScanHostAlgorithmsLegacy:
    """End-to-end verification that scan_host_algorithms identifies the
    legacy-server failure shape -- the exact diagnostic that motivated
    the helper. Against the legacy-sftp container, the server's
    advertised host-key algorithm list is exactly ``["ssh-rsa"]``.
    """

    def test_scan_identifies_ssh_rsa_only_server(self) -> None:
        result = SFTPUtils.scan_host_algorithms(LEGACY_SFTP_HOST, port=LEGACY_SFTP_PORT)
        assert isinstance(result["banner"], str)
        assert result["banner"].startswith("SSH-2.0")
        host_key_algos = result["server_host_key_algorithms"]
        assert host_key_algos == ["ssh-rsa"], (
            f"legacy-sftp container should advertise only ssh-rsa; got {host_key_algos}"
        )
        # kex / cipher / mac lists should still be non-empty (only the
        # host-key list is forced narrow on this container).
        kex = result["kex_algorithms"]
        assert isinstance(kex, list)
        assert kex, f"kex_algorithms should be non-empty; got {kex!r}"
        ciphers = result["encryption_algorithms_stoc"]
        assert isinstance(ciphers, list)
        assert ciphers, f"encryption_algorithms_stoc should be non-empty; got {ciphers!r}"
