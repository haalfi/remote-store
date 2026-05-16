"""SFTP backend tests -- covers SFTP-xxx spec items.

Requires: paramiko, tenacity (test dependencies).
All tests are skipped if dependencies are not installed.
"""

from __future__ import annotations

import errno
import io
import os
import shutil
import sys
import tempfile
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

# Guard: skip entire module if dependencies are missing
paramiko = pytest.importorskip("paramiko", reason="paramiko not installed")
pytest.importorskip("tenacity", reason="tenacity not installed")

from remote_store._capabilities import Capability, CapabilitySet  # noqa: E402
from remote_store._config import RetryPolicy  # noqa: E402
from remote_store._errors import (  # noqa: E402
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import FolderInfo  # noqa: E402
from remote_store.backends._sftp import (  # noqa: E402
    HostKeyPolicy,
    SFTPBackend,
    SFTPUtils,
    _load_host_keys_from_string,
    _sanitize_pem,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


@pytest.fixture
def sftp_backend(sftp_server: tuple[int, str]) -> Iterator[Backend]:
    """Create an SFTPBackend against the in-process SFTP server."""
    port, host_key_entry = sftp_server
    base_path = f"/test_{uuid.uuid4().hex[:8]}"
    backend = SFTPBackend(
        host="127.0.0.1",
        port=port,
        username="testuser",
        password="testpass",
        base_path=base_path,
        host_key_policy=HostKeyPolicy.AUTO_ADD,
        connect_kwargs={"allow_agent": False, "look_for_keys": False},
    )
    yield backend
    backend.close()


# region: Dependency surface (BUG-204)
class TestSFTPParamikoVersionSurface:
    """BUG-204: production code relies on paramiko 3.0+ API (channel_timeout)."""

    pytestmark = pytest.mark.spec("BUG-204")

    def test_ssh_client_connect_accepts_channel_timeout(self) -> None:
        """SFTPBackend._connect passes channel_timeout=; guard that the installed
        paramiko exposes the kwarg. Tightens the pyproject.toml lower bound to
        catch a too-loose pin at import time rather than at runtime.
        """
        import inspect

        params = inspect.signature(paramiko.SSHClient.connect).parameters
        assert "channel_timeout" in params


# endregion


# region: Legacy server compatibility (BK-198)


@pytest.fixture
def restore_paramiko_state() -> Iterator[None]:
    """Snapshot paramiko class-attr state and restore after each test.

    Tests that exercise ``SFTPUtils.enable_ssh_rsa_compat`` mutate process-
    global paramiko state. This fixture preserves test isolation.
    """
    from cryptography.hazmat.primitives import hashes  # noqa: F401
    from paramiko.rsakey import RSAKey

    saved_preferred_keys = paramiko.Transport._preferred_keys
    saved_preferred_pubkeys = paramiko.Transport._preferred_pubkeys
    saved_key_info = dict(paramiko.Transport._key_info)
    saved_hashes = dict(RSAKey.HASHES)
    try:
        yield
    finally:
        paramiko.Transport._preferred_keys = saved_preferred_keys
        paramiko.Transport._preferred_pubkeys = saved_preferred_pubkeys
        paramiko.Transport._key_info.clear()
        paramiko.Transport._key_info.update(saved_key_info)
        RSAKey.HASHES.clear()
        RSAKey.HASHES.update(saved_hashes)


class TestSFTPEnableSshRsaCompat:
    """BK-198: SFTPUtils.enable_ssh_rsa_compat ensures ssh-rsa is present at
    the four paramiko sites that govern host-key negotiation.

    # internal: no public observable -- enable_ssh_rsa_compat's contract IS
    # the mutation of paramiko's four private class attributes
    # (Transport._preferred_keys, Transport._preferred_pubkeys,
    # Transport._key_info, RSAKey.HASHES). Paramiko exposes no public API
    # to query "is ssh-rsa in the negotiated set"; mutating these four
    # sites is the only forward-compatible path documented in
    # _sftp.py::enable_ssh_rsa_compat. The helper's docstring names them
    # as the contract. All assertions in this class on those attributes
    # are observing the helper's documented effect, not poking at
    # implementation detail.
    """

    pytestmark = pytest.mark.spec("BK-198")

    def test_helper_adds_ssh_rsa_to_all_four_sites(
        self,
        restore_paramiko_state: None,  # noqa: ARG002
    ) -> None:
        from paramiko.rsakey import RSAKey

        # Strip ssh-rsa from anywhere it might already exist, so we observe
        # the helper's effect, not a no-op.
        paramiko.Transport._preferred_keys = tuple(k for k in paramiko.Transport._preferred_keys if k != "ssh-rsa")
        paramiko.Transport._preferred_pubkeys = tuple(
            k for k in paramiko.Transport._preferred_pubkeys if k != "ssh-rsa"
        )
        paramiko.Transport._key_info.pop("ssh-rsa", None)
        RSAKey.HASHES.pop("ssh-rsa", None)

        SFTPUtils.enable_ssh_rsa_compat()

        assert "ssh-rsa" in paramiko.Transport._preferred_keys
        assert "ssh-rsa" in paramiko.Transport._preferred_pubkeys
        assert paramiko.Transport._key_info.get("ssh-rsa") is RSAKey
        assert "ssh-rsa" in RSAKey.HASHES
        # Security contract: ssh-rsa is appended (not prepended) so modern
        # algorithms remain negotiated first. Locks in the docstring
        # promise at _sftp.py "ssh-rsa is appended (not prepended)...".
        assert paramiko.Transport._preferred_keys[-1] == "ssh-rsa"
        assert paramiko.Transport._preferred_pubkeys[-1] == "ssh-rsa"

    def test_helper_is_idempotent(self, restore_paramiko_state: None) -> None:  # noqa: ARG002
        from paramiko.rsakey import RSAKey

        SFTPUtils.enable_ssh_rsa_compat()
        keys_count_first = paramiko.Transport._preferred_keys.count("ssh-rsa")
        pubkeys_count_first = paramiko.Transport._preferred_pubkeys.count("ssh-rsa")

        SFTPUtils.enable_ssh_rsa_compat()

        assert paramiko.Transport._preferred_keys.count("ssh-rsa") == keys_count_first
        assert paramiko.Transport._preferred_pubkeys.count("ssh-rsa") == pubkeys_count_first
        # Sanity: still present
        assert "ssh-rsa" in paramiko.Transport._key_info
        assert "ssh-rsa" in RSAKey.HASHES


class TestSFTPIncompatiblePeerHint:
    """BK-198: _map_exception annotates IncompatiblePeer with a remediation
    pointer to ``SFTPUtils.enable_ssh_rsa_compat`` only when the underlying
    paramiko message identifies a host-key failure; KEX / cipher / MAC
    variants of IncompatiblePeer pass through with no hint, because the
    helper does not address those."""

    pytestmark = pytest.mark.spec("BK-198")

    def test_incompatible_peer_hint_present_for_host_key(self) -> None:
        """IncompatiblePeer carrying ``host key`` maps to BackendUnavailable
        with a hint carrying all three user-actionable signals: the
        ``[hint:`` framing, ``ssh-rsa``, and ``enable_ssh_rsa_compat``.
        Locks in the documented shape so a refactor that drops any single
        signal does not pass silently.
        """
        backend = SFTPBackend(host="dummy", host_key_policy=HostKeyPolicy.AUTO_ADD)
        exc = paramiko.ssh_exception.IncompatiblePeer("no acceptable host key")
        result = backend._map_exception(exc, "")
        assert isinstance(result, BackendUnavailable)
        message = str(result)
        assert "[hint:" in message
        assert "ssh-rsa" in message
        assert "enable_ssh_rsa_compat" in message

    def test_incompatible_peer_kex_hint_points_at_scan_host_algorithms(self) -> None:
        """IncompatiblePeer for KEX (or cipher / MAC) maps to a
        BackendUnavailable carrying a *different* hint: it points at
        ``scan_host_algorithms`` for diagnosis and at
        ``connect_kwargs={"disabled_algorithms": ...}`` for the remedy.
        ``enable_ssh_rsa_compat`` does not address those failure modes
        and must NOT appear in this hint.
        """
        backend = SFTPBackend(host="dummy", host_key_policy=HostKeyPolicy.AUTO_ADD)
        exc = paramiko.ssh_exception.IncompatiblePeer("no acceptable kex algorithm")
        result = backend._map_exception(exc, "")
        assert isinstance(result, BackendUnavailable)
        message = str(result)
        assert "[hint:" in message
        assert "scan_host_algorithms" in message
        assert "disabled_algorithms" in message
        # The host-key remedy must not bleed into the KEX hint.
        assert "enable_ssh_rsa_compat" not in message
        assert "ssh-rsa" not in message

    def test_other_ssh_exception_unchanged(self) -> None:
        """Non-IncompatiblePeer SSHException keeps the generic mapping (no hint)."""
        backend = SFTPBackend(host="dummy", host_key_policy=HostKeyPolicy.AUTO_ADD)
        exc = paramiko.SSHException("session not active")
        result = backend._map_exception(exc, "")
        assert isinstance(result, BackendUnavailable)
        assert "enable_ssh_rsa_compat" not in str(result)
        assert "scan_host_algorithms" not in str(result)


# endregion


# region: Preflight host-key discovery (BK-199)


class TestSFTPScanHostKeys:
    """BK-199: SFTPUtils.scan_host_keys returns a known_hosts-formatted line
    after performing KEX against the server, without authentication."""

    pytestmark = pytest.mark.spec("BK-199")

    def test_scan_returns_known_hosts_line(self, sftp_server: tuple[int, str]) -> None:
        port, host_key_entry = sftp_server
        result = SFTPUtils.scan_host_keys("127.0.0.1", port=port)
        # Result is a single non-empty line, matching the host_key_entry the
        # fixture publishes (same RSAKey on both sides).
        assert result.strip(), "scan_host_keys returned empty"
        # known_hosts format: <host_label> <key_type> <base64_key>
        parts = result.strip().split(maxsplit=2)
        assert len(parts) == 3
        host_label, key_type, key_b64 = parts
        # Port != 22 -> [host]:port form
        assert host_label == f"[127.0.0.1]:{port}"
        # Same key type and base64 as the fixture-published entry
        _fix_label, fix_type, fix_b64 = host_key_entry.split(maxsplit=2)
        assert key_type == fix_type
        assert key_b64 == fix_b64

    @staticmethod
    def _stub_key() -> object:
        """Minimal paramiko-PKey-shaped stub for formatter unit tests.

        Avoids the ~0.5-1s cost of ``RSAKey.generate(2048)``; the formatter
        only consults ``get_name()`` and ``get_base64()``.
        """
        from unittest.mock import MagicMock

        stub = MagicMock(spec=paramiko.PKey)
        stub.get_name.return_value = "ssh-rsa"
        stub.get_base64.return_value = "AAAA"
        return stub

    def test_format_default_port_omits_brackets(self) -> None:
        """For port 22, ``_format_known_hosts_line`` emits the bare hostname
        (matches OpenSSH known_hosts convention).
        """
        from remote_store.backends._sftp import _format_known_hosts_line

        line = _format_known_hosts_line("example.com", 22, self._stub_key())
        host_label = line.split(maxsplit=1)[0]
        assert host_label == "example.com"

    def test_format_non_default_port_uses_brackets(self) -> None:
        """For non-default ports, the label is ``[host]:port``."""
        from remote_store.backends._sftp import _format_known_hosts_line

        line = _format_known_hosts_line("example.com", 2222, self._stub_key())
        host_label = line.split(maxsplit=1)[0]
        assert host_label == "[example.com]:2222"

    def test_scan_unreachable_raises(self) -> None:
        """Unreachable host propagates a connection error to the caller."""
        # Bind an OS-assigned ephemeral port and immediately close it, then
        # pass that just-released port to scan_host_keys: nothing else can
        # have raced into the same port before the connect attempt, so the
        # connection is deterministically refused. Beats RFC 5737 TEST-NET-1
        # (192.0.2.1) which may be silently dropped by local firewalls and
        # would force us to widen the timeout.
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        unreachable_port = sock.getsockname()[1]
        sock.close()
        # match= covers Linux ("Connection refused" / Errno 111), Windows
        # ("actively refused" / WinError 10061), and connection-reset
        # variants — what we care about is "connect-side OS failure", not
        # any specific message.
        with pytest.raises(
            (OSError, paramiko.SSHException),
            match=r"(?i)refused|reset|timed|timeout|unreachable|10061|10054|10060|connect",
        ):
            SFTPUtils.scan_host_keys("127.0.0.1", port=unreachable_port, timeout=0.5)


# endregion


# region: Preflight algorithm discovery (BK-200)


class TestSFTPScanHostAlgorithms:
    """BK-200: SFTPUtils.scan_host_algorithms parses the server's SSH
    KEXINIT advertisement (RFC 4253 § 7.1) over a raw socket without
    authenticating or completing key exchange.
    """

    pytestmark = pytest.mark.spec("BK-200")

    _EXPECTED_FIELDS = (
        "banner",
        "kex_algorithms",
        "server_host_key_algorithms",
        "encryption_algorithms_ctos",
        "encryption_algorithms_stoc",
        "mac_algorithms_ctos",
        "mac_algorithms_stoc",
        "compression_algorithms_ctos",
        "compression_algorithms_stoc",
        "languages_ctos",
        "languages_stoc",
    )

    def test_scan_returns_kexinit_namelists(self, sftp_server: tuple[int, str]) -> None:
        """Returned dict has all eleven documented entries with the right shapes.

        Drives the helper against the in-process modern SSH fixture
        ``sftp_server`` (atmoz/sftp-style); asserts that the algorithm
        lists are non-empty for the universally-required entries
        (``kex_algorithms``, ``server_host_key_algorithms``,
        encryption / MAC c2s and s2c) and that the banner is a valid SSH
        identification string.
        """
        port, _ = sftp_server
        result = SFTPUtils.scan_host_algorithms("127.0.0.1", port=port)

        assert set(result) == set(self._EXPECTED_FIELDS)
        assert isinstance(result["banner"], str)
        assert result["banner"].startswith("SSH-2.0")
        for required in (
            "kex_algorithms",
            "server_host_key_algorithms",
            "encryption_algorithms_ctos",
            "encryption_algorithms_stoc",
            "mac_algorithms_ctos",
            "mac_algorithms_stoc",
        ):
            value = result[required]
            assert isinstance(value, list), f"{required} should be a list, got {type(value).__name__}"
            assert value, f"{required} should be non-empty, got {value!r}"
            assert all(isinstance(name, str) for name in value), required
            assert all(name for name in value), required

    def test_scan_unreachable_raises(self) -> None:
        """Unreachable host propagates a connection error to the caller.

        Uses the same just-released-ephemeral-port pattern as
        ``scan_host_keys`` so the connection is deterministically refused
        without depending on RFC 5737 reachability behavior.
        """
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        unreachable_port = sock.getsockname()[1]
        sock.close()
        # match= rationale matches scan_host_keys test_scan_unreachable_raises;
        # cross-OS messaging for "connect failed" varies.
        with pytest.raises(
            OSError,
            match=r"(?i)refused|reset|timed|timeout|unreachable|10061|10054|10060|connect",
        ):
            SFTPUtils.scan_host_algorithms("127.0.0.1", port=unreachable_port, timeout=0.5)


# endregion


# region: Construction (SFTP-001 through SFTP-005)
class TestSFTPConstruction:
    """SFTP-001 through SFTP-005: construction and identity."""

    @pytest.mark.spec("SFTP-001")
    def test_constructor_minimal(self, sftp_backend: Backend) -> None:
        """Backend can be constructed with host and credentials."""
        assert sftp_backend is not None

    @pytest.mark.spec("SFTP-002")
    def test_name_is_sftp(self, sftp_backend: Backend) -> None:
        assert sftp_backend.name == "sftp"

    @pytest.mark.spec("SFTP-003")
    def test_declares_all_capabilities(self, sftp_backend: Backend) -> None:
        caps = sftp_backend.capabilities
        assert isinstance(caps, CapabilitySet)
        excluded = {Capability.GLOB, Capability.ATOMIC_MOVE, Capability.USER_METADATA}
        for cap in Capability:
            if cap in excluded:
                assert not caps.supports(cap), f"SFTP must not declare {cap.value}"
            else:
                assert caps.supports(cap), f"Missing capability: {cap.value}"

    @pytest.mark.spec("SFTP-004")
    def test_lazy_connection(self) -> None:
        """Construction must not make network calls."""
        backend = SFTPBackend(
            host="nonexistent.invalid",
            port=99999,
            username="x",
            password="x",
            host_key_policy=HostKeyPolicy.AUTO_ADD,
        )
        # Should succeed -- no connection attempted yet
        assert backend.name == "sftp"

    @pytest.mark.spec("SFTP-005")
    @pytest.mark.parametrize("host", [pytest.param("", id="empty"), pytest.param("   ", id="whitespace")])
    def test_invalid_host_raises(self, host: str) -> None:
        with pytest.raises(ValueError, match="host"):
            SFTPBackend(host=host)


# endregion


# region: Connection (SFTP-006 through SFTP-010)
class TestSFTPConnection:
    """SFTP-006 through SFTP-010: connection and host key handling."""

    @pytest.mark.spec("SFTP-006")
    def test_host_key_policy_enum(self) -> None:
        """HostKeyPolicy enum has expected values."""
        assert HostKeyPolicy.STRICT.value == "strict"
        assert HostKeyPolicy.TRUST_ON_FIRST_USE.value == "tofu"
        assert HostKeyPolicy.AUTO_ADD.value == "auto"

    @pytest.mark.spec("SFTP-009")
    def test_connection_established_on_first_use(self, sftp_backend: Backend) -> None:
        """First operation triggers connection."""
        assert sftp_backend.exists("nonexistent.txt") is False

    @pytest.mark.spec("SFTP-010")
    def test_staleness_reconnect(self, sftp_backend: Backend) -> None:
        """Backend reconnects when connection goes stale."""
        assert isinstance(sftp_backend, SFTPBackend)
        # Force a first connection
        sftp_backend.exists("test.txt")
        # Close the connection manually to simulate staleness
        sftp_backend._close_clients()
        # Next operation should reconnect automatically
        assert sftp_backend.exists("test.txt") is False


# endregion


# region: Filesystem Model (SFTP-011 through SFTP-013)
class TestSFTPFilesystemModel:
    """SFTP-011 through SFTP-013: real directory semantics."""

    @pytest.mark.spec("SFTP-011")
    def test_real_directories(self, sftp_backend: Backend) -> None:
        """SFTP uses real directories, not virtual prefixes."""
        sftp_backend.write("realdir/file.txt", b"content")
        assert sftp_backend.is_folder("realdir") is True

    @pytest.mark.spec("SFTP-012")
    def test_write_creates_intermediate_dirs(self, sftp_backend: Backend) -> None:
        """Writing to nested path creates parent directories."""
        sftp_backend.write("a/b/c/deep.txt", b"deep")
        assert sftp_backend.read_bytes("a/b/c/deep.txt") == b"deep"
        assert sftp_backend.is_folder("a") is True
        assert sftp_backend.is_folder("a/b") is True
        assert sftp_backend.is_folder("a/b/c") is True

    @pytest.mark.spec("SFTP-013")
    def test_empty_folders_persist(self, sftp_backend: Backend) -> None:
        """Empty directories persist after their contents are deleted."""
        sftp_backend.write("persist/only.txt", b"x")
        assert sftp_backend.is_folder("persist") is True
        sftp_backend.delete("persist/only.txt")
        # Unlike S3, the folder should still exist
        assert sftp_backend.is_folder("persist") is True


# endregion


# region: Atomic Write (SFTP-014)
class TestSFTPAtomicWrite:
    """SFTP-014: simulated atomic write — implementation-specific checks.
    Basic write_atomic create/overwrite/already-exists contract is covered by the
    conformance suite (BE-010, BE-011)."""

    @pytest.mark.spec("SFTP-014")
    def test_write_atomic_no_temp_file_left(self, sftp_backend: Backend) -> None:
        """After successful atomic write, no temp files should remain."""
        sftp_backend.write_atomic("clean.txt", b"content")
        # List files -- should only see the target, no .~tmp.* files
        files = list(sftp_backend.list_files(""))
        temp_files = [f for f in files if f.name.startswith(".~tmp.")]
        assert temp_files == []


# endregion


# region: Error Mapping (SFTP-020 through SFTP-024)
class TestSFTPErrorMapping:
    """SFTP-020 through SFTP-024: error mapping."""

    @pytest.mark.spec("SFTP-020")
    def test_read_missing_maps_to_not_found(self, sftp_backend: Backend) -> None:
        with pytest.raises(NotFound) as exc_info:
            sftp_backend.read_bytes("does-not-exist.txt")
        assert exc_info.value.backend == "sftp"

    @pytest.mark.spec("SFTP-020")
    def test_get_file_info_missing(self, sftp_backend: Backend) -> None:
        with pytest.raises(NotFound):
            sftp_backend.get_file_info("nope.txt")

    @pytest.mark.spec("SFTP-020")
    def test_delete_missing(self, sftp_backend: Backend) -> None:
        with pytest.raises(NotFound):
            sftp_backend.delete("nope.txt")

    @pytest.mark.spec("SFTP-021")
    def test_eacces_maps_to_permission_denied(self, sftp_backend: Backend) -> None:
        """OSError with errno.EACCES maps to PermissionDenied."""
        import errno
        from unittest.mock import patch

        assert isinstance(sftp_backend, SFTPBackend)
        # Force connection so _sftp_client is populated
        sftp_backend.exists("warmup.txt")

        eacces = OSError(errno.EACCES, "Permission denied")
        with (
            patch.object(sftp_backend._sftp_client, "file", side_effect=eacces),
            pytest.raises(PermissionDenied) as exc_info,
        ):
            sftp_backend.read_bytes("secret.txt")
        assert exc_info.value.backend == "sftp"

    @pytest.mark.spec("SFTP-021")
    def test_eacces_on_remove_maps_to_permission_denied(self, sftp_backend: Backend) -> None:
        """OSError with errno.EACCES on remove maps to PermissionDenied."""
        import errno
        from unittest.mock import patch

        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("locked.txt", b"data")

        eacces = OSError(errno.EACCES, "Permission denied")
        with (
            patch.object(sftp_backend._sftp_client, "remove", side_effect=eacces),
            pytest.raises(PermissionDenied) as exc_info,
        ):
            sftp_backend.delete("locked.txt")
        assert exc_info.value.backend == "sftp"
        assert exc_info.value.path == "locked.txt"

    @pytest.mark.spec("SFTP-022")
    def test_eexist_maps_to_already_exists(self, sftp_backend: Backend) -> None:
        """OSError with errno.EEXIST maps to AlreadyExists."""
        import errno
        from unittest.mock import patch

        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.exists("warmup.txt")

        eexist = OSError(errno.EEXIST, "File exists")
        with (
            patch.object(sftp_backend._sftp_client, "file", side_effect=eexist),
            pytest.raises(AlreadyExists) as exc_info,
        ):
            sftp_backend.read_bytes("existing.txt")
        assert exc_info.value.backend == "sftp"
        assert exc_info.value.path == "existing.txt"

    @pytest.mark.spec("SFTP-023")
    def test_ssh_exception_maps_to_backend_unavailable(self, sftp_backend: Backend) -> None:
        """paramiko.SSHException maps to BackendUnavailable."""
        from unittest.mock import patch

        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.exists("warmup.txt")

        with (
            patch.object(
                sftp_backend._sftp_client,
                "file",
                side_effect=paramiko.SSHException("SSH session not active"),
            ),
            pytest.raises(BackendUnavailable) as exc_info,
        ):
            sftp_backend.read_bytes("file.txt")
        assert exc_info.value.backend == "sftp"

    @pytest.mark.spec("SFTP-023")
    def test_ssh_exception_on_remove_maps_to_backend_unavailable(self, sftp_backend: Backend) -> None:
        """paramiko.SSHException on remove maps to BackendUnavailable."""
        from unittest.mock import patch

        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("target.txt", b"data")

        with (
            patch.object(
                sftp_backend._sftp_client,
                "remove",
                side_effect=paramiko.SSHException("Connection lost"),
            ),
            pytest.raises(BackendUnavailable) as exc_info,
        ):
            sftp_backend.delete("target.txt")
        assert exc_info.value.backend == "sftp"

    @pytest.mark.spec("SFTP-024")
    def test_no_native_exception_leaks(self, sftp_backend: Backend) -> None:
        """All errors must be RemoteStoreError subtypes."""
        with pytest.raises(RemoteStoreError):
            sftp_backend.read("nonexistent.txt")

    @pytest.mark.spec("SFTP-024")
    def test_error_has_backend_attribute(self, sftp_backend: Backend) -> None:
        with pytest.raises(RemoteStoreError) as exc_info:
            sftp_backend.read("missing.txt")
        assert exc_info.value.backend == "sftp"


# endregion


# region: Lifecycle (SFTP-025 through SFTP-027)
class TestSFTPLifecycle:
    """SFTP-025 through SFTP-027: close and unwrap."""

    @pytest.mark.spec("SFTP-025")
    def test_close_is_callable(self, sftp_backend: Backend) -> None:
        result = sftp_backend.close()
        assert result is None

    @pytest.mark.spec("SFTP-027")
    def test_close_idempotent(self, sftp_backend: Backend) -> None:
        sftp_backend.close()
        result = sftp_backend.close()
        assert result is None

    @pytest.mark.spec("SFTP-026")
    def test_unwrap_sftp_client(self, sftp_backend: Backend) -> None:
        client = sftp_backend.unwrap(paramiko.SFTPClient)
        assert isinstance(client, paramiko.SFTPClient)

    @pytest.mark.spec("SFTP-026")
    def test_unwrap_wrong_type_raises(self, sftp_backend: Backend) -> None:
        with pytest.raises(CapabilityNotSupported):
            sftp_backend.unwrap(str)

    @pytest.mark.spec("BK-143")
    def test_del_emits_resource_warning_and_closes_clients(self) -> None:
        """BK-143 (Error): __del__ emits ResourceWarning and closes open SFTP/SSH clients."""
        from unittest.mock import MagicMock

        backend = SFTPBackend(host="dummy", host_key_policy=HostKeyPolicy.AUTO_ADD)
        mock_sftp = MagicMock(spec=paramiko.SFTPClient)
        mock_ssh = MagicMock(spec=paramiko.SSHClient)
        backend._sftp_client = mock_sftp  # internal: no public observable
        backend._ssh_client = mock_ssh  # internal: no public observable
        with pytest.warns(ResourceWarning, match="Unclosed SFTPBackend"):
            backend.__del__()
        mock_sftp.close.assert_called_once()
        mock_ssh.close.assert_called_once()

    @pytest.mark.spec("BK-143")
    @pytest.mark.parametrize(("set_sftp", "set_ssh"), [(True, False), (False, True)])
    def test_del_closes_partial_clients(self, set_sftp: bool, set_ssh: bool) -> None:
        """__del__ handles the case where only one of the two clients is open."""
        from unittest.mock import MagicMock

        backend = SFTPBackend(host="dummy", host_key_policy=HostKeyPolicy.AUTO_ADD)
        mock_sftp = MagicMock(spec=paramiko.SFTPClient) if set_sftp else None
        mock_ssh = MagicMock(spec=paramiko.SSHClient) if set_ssh else None
        if mock_sftp is not None:
            backend._sftp_client = mock_sftp  # internal: no public observable
        if mock_ssh is not None:
            backend._ssh_client = mock_ssh  # internal: no public observable
        with pytest.warns(ResourceWarning, match="Unclosed SFTPBackend"):
            backend.__del__()
        if mock_sftp is not None:
            mock_sftp.close.assert_called_once()
        if mock_ssh is not None:
            mock_ssh.close.assert_called_once()

    @pytest.mark.spec("BK-143")
    def test_del_continues_closing_after_sftp_exception(self) -> None:
        """__del__ closes SSH client even when SFTP .close() raises."""
        from unittest.mock import MagicMock

        backend = SFTPBackend(host="dummy", host_key_policy=HostKeyPolicy.AUTO_ADD)
        mock_sftp = MagicMock(spec=paramiko.SFTPClient)
        mock_sftp.close.side_effect = RuntimeError("sftp error")
        mock_ssh = MagicMock(spec=paramiko.SSHClient)
        backend._sftp_client = mock_sftp  # internal: no public observable
        backend._ssh_client = mock_ssh  # internal: no public observable
        with pytest.warns(ResourceWarning, match="Unclosed SFTPBackend"):
            backend.__del__()
        mock_ssh.close.assert_called_once()

    @pytest.mark.spec("BK-143")
    def test_del_is_safe_when_no_clients(self) -> None:
        """BK-143 (Error): __del__ does not raise or warn when no clients are open."""
        backend = SFTPBackend(host="dummy", host_key_policy=HostKeyPolicy.AUTO_ADD)
        result = backend.__del__()
        assert result is None


# endregion


# region: PEM Sanitization (SFTP-008)
class TestPEMSanitization:
    """SFTP-008: PEM key sanitization -- unit tests, no server needed."""

    @pytest.mark.spec("SFTP-008")
    def test_sanitize_valid_pem(self) -> None:
        """PEM with spaces as line separators is normalized to newlines."""
        # Build a fake PEM with spaces instead of newlines in payload
        header = "BEGIN RSA PRIVATE KEY"
        footer = "END RSA PRIVATE KEY"
        payload = "AAAA BBBB CCCC DDDD"
        pem = f"-----{header}-----{payload}-----{footer}-----"
        result = _sanitize_pem(pem)
        assert " " not in result.split("-----")[2]
        assert "\n" in result.split("-----")[2]

    @pytest.mark.spec("SFTP-008")
    def test_sanitize_invalid_structure(self) -> None:
        """PEM with wrong number of parts raises ValueError."""
        with pytest.raises(ValueError, match="Invalid PEM"):
            _sanitize_pem("not-a-pem-string")

    @pytest.mark.spec("SFTP-008")
    def test_sanitize_multiple_non_base64_chars(self) -> None:
        """PEM with multiple non-base64 separator types raises ValueError."""
        pem = "-----BEGIN-----A B\tC-----END-----"
        with pytest.raises(ValueError, match="Unexpected PEM"):
            _sanitize_pem(pem)


# endregion


# region: Unit tests for helpers (no server needed)
class TestSFTPHelpers:
    """Unit tests for SFTPBackend helper methods -- no server needed."""

    def test_sftp_path_with_base_path_root(self) -> None:
        """_sftp_path with base_path='/' returns /<path>."""
        backend = SFTPBackend(host="dummy", host_key_policy=HostKeyPolicy.AUTO_ADD)
        assert backend._sftp_path("file.txt") == "/file.txt"
        assert backend._sftp_path("a/b.txt") == "/a/b.txt"
        assert backend._sftp_path("") == "/"

    def test_sftp_path_with_base_path_subdir(self) -> None:
        """_sftp_path with base_path='/data' returns /data/<path>."""
        backend = SFTPBackend(host="dummy", base_path="/data", host_key_policy=HostKeyPolicy.AUTO_ADD)
        assert backend._sftp_path("file.txt") == "/data/file.txt"
        assert backend._sftp_path("") == "/data"

    def test_stat_to_fileinfo_no_mtime(self) -> None:
        """_stat_to_fileinfo handles None mtime."""

        class FakeAttrs:
            st_size = 42
            st_mtime = None

        backend = SFTPBackend(host="dummy", host_key_policy=HostKeyPolicy.AUTO_ADD)
        fi = backend._stat_to_fileinfo("test.txt", FakeAttrs())
        assert fi.name == "test.txt"
        assert fi.size == 42
        assert fi.modified_at is not None

    @pytest.mark.spec("BK-143")
    def test_ensure_known_hosts_file_creates_file(self) -> None:
        """_ensure_known_hosts_file creates the file when absent (all platforms)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "known_hosts")
            SFTPBackend._ensure_known_hosts_file(path)
            assert os.path.isfile(path)

    @pytest.mark.spec("BK-143")
    @pytest.mark.skipif(sys.platform == "win32", reason="NTFS ignores POSIX mode bits")
    def test_ensure_known_hosts_file_creates_with_mode_600(self) -> None:
        """BK-143 (High): known_hosts must be created with mode 0o600, not more permissive.

        Windows: BK-143 mode invariant not enforced — NTFS ignores POSIX mode bits.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "known_hosts")
            SFTPBackend._ensure_known_hosts_file(path)
            mode = os.stat(path).st_mode & 0o777
            assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


# endregion


# region: Metadata (SFTP-specific)
class TestSFTPMetadata:
    """SFTP-specific metadata behavior.
    Generic get_file_info/get_folder_info/exists/is_file/is_folder are covered
    by the conformance suite (BE-004, BE-005, BE-016, BE-017)."""

    def test_get_folder_info_empty_folder(self, sftp_backend: Backend) -> None:
        """SFTP has real directories; empty folder should return FolderInfo with file_count=0."""
        # Create a directory by writing a file then deleting it
        sftp_backend.write("emptydir/tmp.txt", b"x")
        sftp_backend.delete("emptydir/tmp.txt")
        fi = sftp_backend.get_folder_info("emptydir")
        assert isinstance(fi, FolderInfo)
        assert fi.file_count == 0
        assert fi.total_size == 0


# endregion


# region: Coverage gap tests (BK-005)


class TestSFTPHostKeyPolicyCoercion:
    """SEC-005: string-to-enum coercion in constructor (line 167)."""

    pytestmark = pytest.mark.spec("SEC-005")

    @pytest.mark.parametrize(
        ("input_str", "expected"),
        [
            pytest.param("auto", HostKeyPolicy.AUTO_ADD, id="auto"),
            pytest.param("strict", HostKeyPolicy.STRICT, id="strict"),
            pytest.param("tofu", HostKeyPolicy.TRUST_ON_FIRST_USE, id="tofu"),
            pytest.param("invalid", None, id="invalid"),
        ],
    )
    def test_host_key_policy_string_coercion(self, input_str: str, expected: HostKeyPolicy | None) -> None:
        if expected is None:
            with pytest.raises(ValueError, match="invalid"):
                SFTPBackend(host="dummy", host_key_policy=input_str)
        else:
            backend = SFTPBackend(host="dummy", host_key_policy=input_str)
            # internal: no public observable — coercion is constructor
            # normalization; __repr__ does not surface the policy, and the
            # downstream connect-path effect (set_missing_host_key_policy for
            # AUTO_ADD vs TRUST_ON_FIRST_USE vs default-reject for STRICT) is
            # covered behaviorally by TestSFTPInlineHostKeysVerification
            # and TestSFTPTofuPersistence. This assertion pins the
            # string-to-enum equivalence the constructor promises.
            assert backend._host_key_policy is expected

    def test_enum_value_passthrough(self) -> None:
        """An already-typed HostKeyPolicy member is stored unchanged (no coercion path).
        Migrated from tests/test_config.py (BK-216 / BK-191)."""
        backend = SFTPBackend(host="h", host_key_policy=HostKeyPolicy.AUTO_ADD)
        assert backend._host_key_policy is HostKeyPolicy.AUTO_ADD


class TestSFTPHostKeyPolicyAliases:
    """BK-197: HostKeyPolicy accepts enum-name aliases for the values whose
    string forms (``auto``, ``tofu``) diverge from the enum names
    (``AUTO_ADD``, ``TRUST_ON_FIRST_USE``)."""

    pytestmark = pytest.mark.spec("BK-197")

    @pytest.mark.parametrize(
        ("alias", "expected"),
        [
            pytest.param("auto_add", HostKeyPolicy.AUTO_ADD, id="auto_add"),
            pytest.param("AUTO_ADD", HostKeyPolicy.AUTO_ADD, id="AUTO_ADD"),
            pytest.param("trust_on_first_use", HostKeyPolicy.TRUST_ON_FIRST_USE, id="trust_on_first_use"),
            pytest.param("TRUST_ON_FIRST_USE", HostKeyPolicy.TRUST_ON_FIRST_USE, id="TRUST_ON_FIRST_USE"),
            pytest.param("STRICT", HostKeyPolicy.STRICT, id="STRICT-upper-name"),
        ],
    )
    def test_enum_name_aliases_resolve(self, alias: str, expected: HostKeyPolicy) -> None:
        """Enum-name forms (uppercase or lowercase) resolve to the same member."""
        assert HostKeyPolicy(alias) is expected

    def test_invalid_value_still_raises(self) -> None:
        """Unknown values continue to raise ValueError."""
        with pytest.raises(ValueError, match="not a valid HostKeyPolicy"):
            HostKeyPolicy("totally_made_up")

    @pytest.mark.parametrize(
        "value_form",
        [
            # "AUTO" is the uppercase of value "auto", and is NOT an enum
            # name (the name is "AUTO_ADD"); the hook should not resolve it.
            pytest.param("AUTO", id="AUTO-upper-value"),
            # "Tofu" -> "TOFU" is neither value nor name (name is
            # "TRUST_ON_FIRST_USE"); should not resolve.
            pytest.param("Tofu", id="Tofu-mixed-value"),
        ],
    )
    def test_value_form_aliasing_raises(self, value_form: str) -> None:
        """_missing_ only case-folds enum-NAME forms; value-form upper/mixed
        case (e.g. "AUTO" for value "auto", "Tofu" for value "tofu") still
        raises. Locks in the scope of the alias hook so the CHANGELOG
        "case-insensitive on the name" wording stays accurate.

        Caveat: ``"Strict"`` happens to resolve because uppercase yields
        ``"STRICT"``, which IS an enum-name form. That's the same code path
        as ``test_enum_name_aliases_resolve``; not a value-form alias bug.
        """
        with pytest.raises(ValueError, match="not a valid HostKeyPolicy"):
            HostKeyPolicy(value_form)

    def test_constructor_accepts_alias_string(self) -> None:
        """SFTPBackend constructor accepts the alias string form and
        coerces to the canonical enum member.

        The coercion semantics themselves are tested in
        ``test_enum_name_aliases_resolve``; this test adds that the
        SFTPBackend constructor delegates to that coercion rather than
        storing the raw string.
        """
        # internal: no public observable -- SFTPBackend's constructor
        # coercion has no public reflection (no repr surface, no
        # method that returns the policy); asserting on the private
        # attribute is the only way to verify the coerced storage.
        # The coercion logic itself is tested at the enum level above.
        backend = SFTPBackend(host="dummy", host_key_policy="auto_add")
        assert backend._host_key_policy is HostKeyPolicy.AUTO_ADD

    @pytest.mark.parametrize(
        "non_string",
        [
            pytest.param(42, id="int"),
            pytest.param(None, id="None"),
            pytest.param(b"auto", id="bytes"),
        ],
    )
    def test_non_string_input_raises(self, non_string: object) -> None:
        """_missing_ guards with ``isinstance(value, str)``; non-string
        inputs fall through to ValueError rather than crashing on .upper().
        Locks the typing contract so the guard cannot be silently deleted.
        """
        with pytest.raises(ValueError, match="not a valid HostKeyPolicy"):
            HostKeyPolicy(non_string)


class TestSFTPToKey:
    """BK-005: to_key() all branches (lines 324, 326, 328)."""

    @pytest.mark.parametrize(
        ("base_path", "native_path", "expected"),
        [
            pytest.param("/", "/file.txt", "file.txt", id="root-file"),
            pytest.param("/", "/a/b/c.txt", "a/b/c.txt", id="root-nested"),
            pytest.param("/data", "/data/file.txt", "file.txt", id="subdir-file"),
            pytest.param("/data", "/data/sub/file.txt", "sub/file.txt", id="subdir-nested"),
            pytest.param("/data", "/data", "", id="equals-base"),
            pytest.param("/data", "/other/file.txt", "/other/file.txt", id="no-match"),
        ],
    )
    def test_to_key(self, base_path: str, native_path: str, expected: str) -> None:
        backend = SFTPBackend(host="dummy", base_path=base_path, host_key_policy="auto")
        assert backend.to_key(native_path) == expected


class TestSFTPMapException:
    """BK-005: _map_exception edge cases (lines 431, 437, 442)."""

    @staticmethod
    def _oserror_enoent() -> OSError:
        exc = OSError("No such file")
        exc.errno = errno.ENOENT
        return exc

    @pytest.mark.parametrize(
        ("exc_factory", "path", "expected_type", "check"),
        [
            pytest.param(
                lambda: NotFound("test", path="p", backend="sftp"),
                "p",
                NotFound,
                "identity",
                id="passthrough",
            ),
            pytest.param(
                _oserror_enoent.__func__,
                "missing.txt",
                NotFound,
                "path",
                id="oserror-enoent",
            ),
            pytest.param(
                lambda: OSError(errno.EIO, "I/O error"),
                "file.txt",
                RemoteStoreError,
                "not-specific",
                id="generic-oserror",
            ),
            pytest.param(
                lambda: FileNotFoundError("gone"),
                "gone.txt",
                NotFound,
                "type",
                id="file-not-found",
            ),
        ],
    )
    def test_map_exception(self, exc_factory: object, path: str, expected_type: type, check: str) -> None:
        backend = SFTPBackend(host="dummy", host_key_policy="auto")
        exc = exc_factory()
        result = backend._map_exception(exc, path)
        assert isinstance(result, expected_type)
        if check == "identity":
            assert result is exc
        elif check == "path":
            assert result.path == path
        elif check == "not-specific":
            assert not isinstance(result, (NotFound, PermissionDenied, AlreadyExists))


class TestSFTPTypeGuards:
    """BK-005/ID-131: type guards — file/folder confusion raises InvalidPath."""

    def test_get_file_info_on_directory(self, sftp_backend: Backend) -> None:
        """get_file_info on a directory raises InvalidPath."""
        sftp_backend.write("typedir/file.txt", b"x")
        with pytest.raises(InvalidPath):
            sftp_backend.get_file_info("typedir")

    def test_get_folder_info_on_file(self, sftp_backend: Backend) -> None:
        """get_folder_info on a file raises InvalidPath."""
        sftp_backend.write("typefile.txt", b"x")
        with pytest.raises(InvalidPath):
            sftp_backend.get_folder_info("typefile.txt")

    def test_delete_folder_on_file(self, sftp_backend: Backend) -> None:
        """delete_folder on a file raises InvalidPath."""
        sftp_backend.write("notadir.txt", b"x")
        with pytest.raises(InvalidPath):
            sftp_backend.delete_folder("notadir.txt")

    def test_write_atomic_on_directory(self, sftp_backend: Backend) -> None:
        """write_atomic on a directory path raises InvalidPath."""
        sftp_backend.write("wa_dir/file.txt", b"x")
        with pytest.raises(InvalidPath):
            sftp_backend.write_atomic("wa_dir", b"data")

    def test_open_atomic_on_directory(self, sftp_backend: Backend) -> None:
        """open_atomic on a directory path raises InvalidPath."""
        sftp_backend.write("oa_dir/file.txt", b"x")
        with pytest.raises(InvalidPath), sftp_backend.open_atomic("oa_dir") as f:
            f.write(b"data")


class TestSFTPWriteAtomicStream:
    """BK-005: write_atomic with BinaryIO content (line 509)."""

    def test_write_atomic_stream_content(self, sftp_backend: Backend) -> None:
        sftp_backend.write_atomic("stream_atomic.txt", io.BytesIO(b"streamed atomic"))
        assert sftp_backend.read_bytes("stream_atomic.txt") == b"streamed atomic"

    def test_write_atomic_stream_content_overwrite(self, sftp_backend: Backend) -> None:
        sftp_backend.write_atomic("sa_ow.txt", b"first")
        sftp_backend.write_atomic("sa_ow.txt", io.BytesIO(b"second stream"), overwrite=True)
        assert sftp_backend.read_bytes("sa_ow.txt") == b"second stream"


class TestSFTPWriteAtomicCleanup:
    """BK-005: write_atomic failure cleans up temp file (lines 517-521)."""

    def test_write_atomic_cleanup_on_failure(self, sftp_backend: Backend) -> None:
        """Temp file is cleaned up when write_atomic fails mid-write.

        Uses a stream whose read() raises *after* the temp file has been
        opened on the server, so the except block (lines 517-521) must
        actually remove a real temp file.
        """

        class FailingStream(io.BytesIO):
            """Stream that raises on read — simulates I/O failure after temp file is opened."""

            def read(self, size: int = -1) -> bytes:
                raise OSError(errno.EIO, "Disk full")

        with pytest.raises(RemoteStoreError):
            sftp_backend.write_atomic("fail_atomic.txt", FailingStream())

        # Verify no temp files remain — the except block (lines 517-521) must
        # have removed the temp file that was created by file(tmp_path, "w")
        files = list(sftp_backend.list_files(""))
        temp_files = [f for f in files if f.name.startswith(".~tmp.")]
        assert temp_files == []


class TestSFTPCollectFolderStats:
    """BK-005: _collect_folder_stats recursive subdirectory (lines 675-680)."""

    def test_folder_info_nested_subdirectories(self, sftp_backend: Backend) -> None:
        """get_folder_info counts files in nested subdirectories."""
        sftp_backend.write("nested/a.txt", b"aaa")
        sftp_backend.write("nested/sub1/b.txt", b"bb")
        sftp_backend.write("nested/sub1/sub2/c.txt", b"c")
        fi = sftp_backend.get_folder_info("nested")
        assert fi.file_count == 3
        assert fi.total_size == 6
        assert fi.modified_at is not None


class TestSFTPNonEnoentOSErrors:
    """BK-005: non-ENOENT OSError re-raises via mock (lines 480, 497, 550, 630, 643, 698, 707, 737, 746)."""

    def _stat_eio_on_path(self, sftp_backend: SFTPBackend, target_suffix: str) -> object:
        """Return a stat replacement that raises EIO only for a specific file path."""
        original_stat = sftp_backend._sftp_client.stat

        def selective_stat(path: str) -> object:
            if path.endswith(target_suffix):
                raise OSError(errno.EIO, "I/O error")
            return original_stat(path)

        return selective_stat

    @pytest.mark.parametrize(
        ("setup_file", "target_suffix", "method", "args"),
        [
            pytest.param(None, "w_eio.txt", "write", ("w_eio.txt", b"data"), id="write"),
            pytest.param(None, "wa_eio.txt", "write_atomic", ("wa_eio.txt", b"data"), id="write-atomic"),
            pytest.param(None, "df_eio", "delete_folder", ("df_eio",), id="delete-folder"),
            pytest.param(None, "gfi_eio.txt", "get_file_info", ("gfi_eio.txt",), id="get-file-info"),
            pytest.param(None, "gfoi_eio", "get_folder_info", ("gfoi_eio",), id="get-folder-info"),
            pytest.param(None, "m_src_eio.txt", "move", ("m_src_eio.txt", "m_dst.txt"), id="move-src"),
            pytest.param("m_src2.txt", "m_dst2.txt", "move", ("m_src2.txt", "m_dst2.txt"), id="move-dst"),
            pytest.param(None, "c_src_eio.txt", "copy", ("c_src_eio.txt", "c_dst.txt"), id="copy-src"),
            pytest.param("c_src2.txt", "c_dst2.txt", "copy", ("c_src2.txt", "c_dst2.txt"), id="copy-dst"),
        ],
    )
    def test_non_enoent_reraise(
        self,
        sftp_backend: Backend,
        setup_file: str | None,
        target_suffix: str,
        method: str,
        args: tuple[object, ...],
    ) -> None:
        assert isinstance(sftp_backend, SFTPBackend)
        if setup_file:
            sftp_backend.write(setup_file, b"data")
        else:
            sftp_backend.exists("warmup.txt")

        kwargs: dict[str, object] = {}
        if (
            method in ("write", "write_atomic", "move", "copy")
            and len(args) == 2
            and setup_file
            or method in ("write", "write_atomic")
            and not setup_file
        ):
            kwargs["overwrite"] = False

        with (
            patch.object(
                sftp_backend._sftp_client,
                "stat",
                side_effect=self._stat_eio_on_path(sftp_backend, target_suffix),
            ),
            pytest.raises(RemoteStoreError),
        ):
            getattr(sftp_backend, method)(*args, **kwargs)


class TestSFTPListingExceptions:
    """BK-005: generic exception wrapping in list_files/list_folders (lines 599-602, 614-617)."""

    @pytest.mark.parametrize(
        "list_method",
        [
            pytest.param("list_files", id="list-files"),
            pytest.param("list_folders", id="list-folders"),
        ],
    )
    def test_wraps_generic_exception(self, sftp_backend: Backend, list_method: str) -> None:
        """Non-RemoteStoreError during listing wraps to RemoteStoreError."""
        assert isinstance(sftp_backend, SFTPBackend)
        prefix = "lexc" if list_method == "list_files" else "lfexc/sub"
        sftp_backend.write(f"{prefix}/a.txt", b"a")
        folder = "lexc" if list_method == "list_files" else "lfexc"

        original_listdir_attr = sftp_backend._sftp_client.listdir_attr

        def exploding_listdir(path: str) -> list[object]:
            original_listdir_attr(path)
            raise RuntimeError("boom")

        with (
            patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=exploding_listdir),
            pytest.raises(RemoteStoreError, match="boom"),
        ):
            list(getattr(sftp_backend, list_method)(folder))

    @pytest.mark.parametrize(
        "list_method",
        [
            pytest.param("list_files", id="list-files"),
            pytest.param("list_folders", id="list-folders"),
        ],
    )
    def test_reraises_remote_store_error(self, sftp_backend: Backend, list_method: str) -> None:
        """RemoteStoreError during listing is re-raised directly."""
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.exists("warmup.txt")

        with (
            patch.object(
                sftp_backend._sftp_client,
                "listdir_attr",
                side_effect=NotFound("injected", path="x", backend="sftp"),
            ),
            pytest.raises(NotFound, match="injected"),
        ):
            list(getattr(sftp_backend, list_method)("any"))


class TestSFTPDeleteFolderEdgeCases:
    """BK-005: delete_folder listdir OSError and _rmtree OSError (lines 558-559, 572-573)."""

    def test_delete_folder_non_recursive_listdir_enoent(self, sftp_backend: Backend) -> None:
        """Non-recursive delete_folder treats ENOENT on listdir as empty."""
        assert isinstance(sftp_backend, SFTPBackend)
        # Create an empty folder
        sftp_backend.write("df_oserr/tmp.txt", b"x")
        sftp_backend.delete("df_oserr/tmp.txt")

        def failing_listdir(path: str) -> None:
            raise OSError(errno.ENOENT, "No such file on listdir")

        # With ENOENT on listdir, it assumes empty and tries rmdir — should succeed
        with patch.object(sftp_backend._sftp_client, "listdir", side_effect=failing_listdir):
            sftp_backend.delete_folder("df_oserr", recursive=False)

        assert sftp_backend.is_folder("df_oserr") is False

    def test_delete_folder_non_recursive_listdir_eio_raises(self, sftp_backend: Backend) -> None:
        """BUG-147: Non-recursive delete_folder re-raises non-ENOENT listdir errors."""
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("df_eio/tmp.txt", b"x")
        sftp_backend.delete("df_eio/tmp.txt")

        def failing_listdir(path: str) -> None:
            raise OSError(errno.EIO, "I/O error on listdir")

        with (
            patch.object(sftp_backend._sftp_client, "listdir", side_effect=failing_listdir),
            pytest.raises(RemoteStoreError),
        ):
            sftp_backend.delete_folder("df_eio", recursive=False)

    def test_rmtree_listdir_attr_enoent_returns(self, sftp_backend: Backend) -> None:
        """_rmtree returns silently on ENOENT from listdir_attr."""
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.exists("warmup.txt")

        def enoent_listdir_attr(path: str) -> None:
            raise OSError(errno.ENOENT, "No such file")

        # _rmtree returns early on ENOENT — no error raised
        with patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=enoent_listdir_attr):
            sftp_backend._rmtree("/nonexistent")

    def test_rmtree_listdir_attr_eio_raises(self, sftp_backend: Backend) -> None:
        """_rmtree re-raises non-ENOENT errors from listdir_attr."""
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("rmtree_oserr/a.txt", b"a")

        def failing_listdir_attr(path: str) -> None:
            raise OSError(errno.EIO, "I/O error on listdir_attr")

        with (
            patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=failing_listdir_attr),
            pytest.raises(OSError),
        ):
            sftp_backend._rmtree(sftp_backend._sftp_path("rmtree_oserr"))


class TestSFTPCollectFolderStatsOSError:
    """BK-005: _collect_folder_stats OSError on listdir_attr (lines 664-665)."""

    def test_collect_folder_stats_listdir_enoent_returns_zeros(self, sftp_backend: Backend) -> None:
        """_collect_folder_stats returns zeros on ENOENT from listdir_attr."""
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.exists("warmup.txt")

        def enoent_listdir_attr(path: str) -> None:
            raise OSError(errno.ENOENT, "No such file")

        with patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=enoent_listdir_attr):
            count, size, latest = sftp_backend._collect_folder_stats("/nonexistent")

        assert count == 0
        assert size == 0
        assert latest is None

    def test_collect_folder_stats_listdir_eio_raises(self, sftp_backend: Backend) -> None:
        """_collect_folder_stats re-raises non-ENOENT errors from listdir_attr."""
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("cfs_oserr/a.txt", b"a")

        def failing_listdir_attr(path: str) -> None:
            raise OSError(errno.EIO, "I/O error")

        with (
            patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=failing_listdir_attr),
            pytest.raises(OSError),
        ):
            sftp_backend._collect_folder_stats(sftp_backend._sftp_path("cfs_oserr"))


# endregion


# region: Bug fixes (BUG-142 through BUG-147)


class TestSFTPBug146ListingEioRaises:
    """BUG-146: listing methods must re-raise non-ENOENT errors from listdir_attr."""

    @pytest.mark.parametrize(
        "method",
        [
            pytest.param("list_files", id="list-files"),
            pytest.param("list_folders", id="list-folders"),
            pytest.param("iter_children", id="iter-children"),
        ],
    )
    def test_listdir_attr_eio_raises(self, sftp_backend: Backend, method: str) -> None:
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("eio_dir/a.txt", b"a")

        def failing_listdir_attr(path: str) -> None:
            raise OSError(errno.EIO, "I/O error")

        with (
            patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=failing_listdir_attr),
            pytest.raises(RemoteStoreError),
        ):
            list(getattr(sftp_backend, method)("eio_dir"))

    @pytest.mark.parametrize(
        "method",
        [
            pytest.param("list_files", id="list-files"),
            pytest.param("list_folders", id="list-folders"),
            pytest.param("iter_children", id="iter-children"),
        ],
    )
    def test_listdir_attr_enoent_returns_empty(self, sftp_backend: Backend, method: str) -> None:
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.exists("warmup.txt")

        def enoent_listdir_attr(path: str) -> None:
            raise OSError(errno.ENOENT, "No such file")

        with patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=enoent_listdir_attr):
            result = list(getattr(sftp_backend, method)("nonexistent"))

        assert result == []


class TestSFTPBug145EnsureParentDirsEio:
    """BUG-145: _ensure_parent_dirs must re-raise non-ENOENT stat errors."""

    def test_stat_eio_on_intermediate_dir_raises(self, sftp_backend: Backend) -> None:
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.exists("warmup.txt")

        original_stat = sftp_backend._sftp_client.stat

        def eio_stat(path: str) -> object:
            # Fail with EIO on any path that ends with a specific marker
            if path.endswith("/eio_parent"):
                raise OSError(errno.EIO, "I/O error")
            return original_stat(path)

        with (
            patch.object(sftp_backend._sftp_client, "stat", side_effect=eio_stat),
            pytest.raises(RemoteStoreError),
        ):
            sftp_backend.write("eio_parent/child.txt", b"data")


class TestSFTPBug144SshClientLeak:
    """BUG-144: SSHClient is closed when _do_connect exhausts retries."""

    def test_ssh_client_closed_on_connect_failure(self) -> None:
        # internal: no public observable — resource cleanup after failed connect
        # has no behavioral signal; tracking SSHClient.close() is the only option
        import paramiko

        close_called = False
        original_close = paramiko.SSHClient.close

        def tracking_close(self_ssh: Any) -> None:
            nonlocal close_called
            close_called = True
            return original_close(self_ssh)

        backend = SFTPBackend(
            host="127.0.0.1",
            port=1,  # unreachable
            username="x",
            password="x",
            host_key_policy=HostKeyPolicy.AUTO_ADD,
            retry=RetryPolicy(max_attempts=1, backoff_base=0, backoff_max=0),
        )
        with (
            patch.object(paramiko.SSHClient, "close", tracking_close),
            pytest.raises((BackendUnavailable, RemoteStoreError, OSError)),
        ):
            backend._connect()

        assert close_called, "SSHClient was not closed after connection failure"


class TestSFTPBug143StModeNone:
    """BUG-143: entries with st_mode=None are skipped instead of raising TypeError."""

    def test_list_files_skips_none_st_mode(self, sftp_backend: Backend) -> None:
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("mode_dir/ok.txt", b"data")

        original_listdir_attr = sftp_backend._sftp_client.listdir_attr

        def patched_listdir_attr(path: str) -> list[object]:
            results = original_listdir_attr(path)
            # Inject a fake entry with st_mode=None
            fake = type("FakeAttrs", (), {"st_mode": None, "filename": "ghost.txt", "st_size": 0, "st_mtime": None})()
            results.append(fake)
            return results

        with patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=patched_listdir_attr):
            files = list(sftp_backend.list_files("mode_dir"))

        names = {f.name for f in files}
        assert "ok.txt" in names
        assert "ghost.txt" not in names

    def test_list_folders_skips_none_st_mode(self, sftp_backend: Backend) -> None:
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("lf_dir/sub/a.txt", b"data")

        original_listdir_attr = sftp_backend._sftp_client.listdir_attr

        def patched_listdir_attr(path: str) -> list[object]:
            results = original_listdir_attr(path)
            fake = type("FakeAttrs", (), {"st_mode": None, "filename": "ghost_dir", "st_size": 0, "st_mtime": None})()
            results.append(fake)
            return results

        with patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=patched_listdir_attr):
            folders = list(sftp_backend.list_folders("lf_dir"))

        names = {f.name for f in folders}
        assert "sub" in names
        assert "ghost_dir" not in names

    def test_rmtree_skips_none_st_mode(self, sftp_backend: Backend) -> None:
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("rm_dir/ok.txt", b"data")

        original_listdir_attr = sftp_backend._sftp_client.listdir_attr

        def patched_listdir_attr(path: str) -> list[object]:
            results = original_listdir_attr(path)
            fake = type("FakeAttrs", (), {"st_mode": None, "filename": "ghost", "st_size": 0, "st_mtime": None})()
            results.append(fake)
            return results

        # _rmtree should skip the None-st_mode entry and successfully remove
        # the rest; no TypeError should be raised
        with patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=patched_listdir_attr):
            sftp_backend._rmtree(sftp_backend._sftp_path("rm_dir"))

    def test_iter_children_skips_none_st_mode(self, sftp_backend: Backend) -> None:
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("ic_dir/ok.txt", b"data")

        original_listdir_attr = sftp_backend._sftp_client.listdir_attr

        def patched_listdir_attr(path: str) -> list[object]:
            results = original_listdir_attr(path)
            fake = type("FakeAttrs", (), {"st_mode": None, "filename": "ghost", "st_size": 0, "st_mtime": None})()
            results.append(fake)
            return results

        with patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=patched_listdir_attr):
            children = list(sftp_backend.iter_children("ic_dir"))

        names = {c.name for c in children}
        assert "ok.txt" in names
        assert "ghost" not in names

    def test_collect_folder_stats_skips_none_st_mode(self, sftp_backend: Backend) -> None:
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("cfs_dir/ok.txt", b"data")

        original_listdir_attr = sftp_backend._sftp_client.listdir_attr

        def patched_listdir_attr(path: str) -> list[object]:
            results = original_listdir_attr(path)
            fake = type("FakeAttrs", (), {"st_mode": None, "filename": "ghost.txt", "st_size": 999, "st_mtime": None})()
            results.append(fake)
            return results

        with patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=patched_listdir_attr):
            count, size, _ = sftp_backend._collect_folder_stats(sftp_backend._sftp_path("cfs_dir"))

        assert count == 1
        assert size == 4  # "data" = 4 bytes, not 4 + 999


class TestSFTPBug142ReadHandleLeak:
    """BUG-142: read() closes the paramiko handle if wrapping fails."""

    def test_read_closes_handle_on_wrapping_failure(self, sftp_backend: Backend) -> None:
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("leak_test.txt", b"data")

        # Force connection to populate _sftp_client
        sftp_backend.exists("warmup.txt")

        original_file = sftp_backend._sftp_client.file
        opened_handle = None

        def tracking_file(path: str, mode: str) -> object:
            nonlocal opened_handle
            opened_handle = original_file(path, mode)
            return opened_handle

        # Patch BufferedReader to fail during construction;
        # _errors() will catch and map the RuntimeError to RemoteStoreError
        with (
            patch.object(sftp_backend._sftp_client, "file", side_effect=tracking_file),
            patch("remote_store.backends._sftp.io.BufferedReader", side_effect=RuntimeError("boom")),
            pytest.raises(RemoteStoreError, match="boom"),
        ):
            sftp_backend.read("leak_test.txt")

        # internal: no public observable — paramiko SFTPFile has no public
        # closed property; _closed is the only way to verify resource cleanup
        assert opened_handle is not None
        assert getattr(opened_handle, "_closed", False) is True


# endregion


# region: Inline host-key verification (SFTP-007)


class TestSFTPInlineHostKeysVerification:
    """SFTP-007: ``known_host_keys`` (inline) is consulted for STRICT verification.

    Direct keys passed at construction must be loaded into the SSH client so
    that STRICT policy accepts a matching server key and rejects a mismatched
    one — i.e. the resolution chain's top-priority source is actually wired
    into the connection path, not merely stored on the backend.
    """

    pytestmark = pytest.mark.spec("SFTP-007")

    def test_strict_accepts_matching_inline_key(self, sftp_server: tuple[int, str]) -> None:
        """Correct inline ``known_host_keys`` lets STRICT connect succeed."""
        port, host_key_entry = sftp_server
        backend = SFTPBackend(
            host="127.0.0.1",
            port=port,
            username="testuser",
            password="testpass",
            known_host_keys=host_key_entry,
            host_key_policy=HostKeyPolicy.STRICT,
            connect_kwargs={"allow_agent": False, "look_for_keys": False},
        )
        try:
            assert backend.exists("nonexistent.txt") is False
        finally:
            backend.close()

    def test_strict_rejects_mismatched_inline_key(self, sftp_server: tuple[int, str]) -> None:
        """A wrong inline ``known_host_keys`` causes STRICT to refuse the connection."""
        port, _host_key_entry = sftp_server
        wrong_key = paramiko.RSAKey.generate(2048)
        wrong_entry = f"[127.0.0.1]:{port} ssh-rsa {wrong_key.get_base64()}"
        backend = SFTPBackend(
            host="127.0.0.1",
            port=port,
            username="testuser",
            password="testpass",
            known_host_keys=wrong_entry,
            host_key_policy=HostKeyPolicy.STRICT,
            connect_kwargs={"allow_agent": False, "look_for_keys": False},
            retry=RetryPolicy(max_attempts=1, backoff_base=0, backoff_max=0),
        )
        try:
            # Paramiko raises BadHostKeyException (subclass of SSHException),
            # which _map_exception translates to BackendUnavailable carrying
            # the original "Host key for server ... does not match" text.
            # The match= pins the host-key-mismatch failure path, not any
            # other RemoteStoreError (timeout, auth, transient SSH error).
            with pytest.raises(BackendUnavailable, match=r"(?i)host key"):
                backend.exists("nonexistent.txt")
        finally:
            backend.close()

    def test_load_host_keys_from_string_reopenable(self) -> None:
        """BUG-209: helper must hand paramiko a re-openable file on every OS.

        Regression guard: prior to BUG-209 the helper used
        ``NamedTemporaryFile(delete=True)``, whose Windows ``O_TEMPORARY``
        lock raised ``PermissionError`` from ``load_host_keys``. The error
        was then swallowed by ``exists()``'s ``except OSError``, silently
        bypassing STRICT verification.
        """
        key = paramiko.RSAKey.generate(2048)
        entry = f"[127.0.0.1]:22 ssh-rsa {key.get_base64()}\n"
        ssh = paramiko.SSHClient()
        try:
            _load_host_keys_from_string(ssh, entry)
            loaded = ssh.get_host_keys()
            assert list(loaded.keys()) == ["[127.0.0.1]:22"]
            entry_keys = loaded["[127.0.0.1]:22"]
            assert "ssh-rsa" in entry_keys
            assert entry_keys["ssh-rsa"].get_base64() == key.get_base64()
        finally:
            ssh.close()


# endregion


# region: TOFU persistence (SFTP-028)


class TestSFTPTofuPersistence:
    """SFTP-028: TOFU host key persistence to disk."""

    @pytest.mark.spec("SFTP-028")
    def test_tofu_creates_and_persists_key(self, sftp_server: tuple[int, str]) -> None:
        """TOFU creates known_hosts file and persists the accepted key."""
        port, _host_key_entry = sftp_server
        tmpdir = tempfile.mkdtemp(prefix="tofu_test_")
        keys_path = os.path.join(tmpdir, "known_hosts")
        try:
            assert not os.path.isfile(keys_path)
            backend = SFTPBackend(
                host="127.0.0.1",
                port=port,
                username="testuser",
                password="testpass",
                base_path="/",
                host_key_policy=HostKeyPolicy.TRUST_ON_FIRST_USE,
                host_keys_path=keys_path,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            backend.exists("nonexistent.txt")
            backend.close()
            assert os.path.isfile(keys_path)
            assert os.path.getsize(keys_path) > 0
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.spec("SFTP-028")
    def test_tofu_persisted_key_verifiable_by_strict(self, sftp_server: tuple[int, str]) -> None:
        """After TOFU persists a key, a STRICT backend can connect using the same file."""
        port, _host_key_entry = sftp_server
        tmpdir = tempfile.mkdtemp(prefix="tofu_test_")
        keys_path = os.path.join(tmpdir, "known_hosts")
        try:
            # First connection: TOFU accepts and persists the key
            tofu_backend = SFTPBackend(
                host="127.0.0.1",
                port=port,
                username="testuser",
                password="testpass",
                base_path="/",
                host_key_policy=HostKeyPolicy.TRUST_ON_FIRST_USE,
                host_keys_path=keys_path,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            tofu_backend.exists("nonexistent.txt")
            tofu_backend.close()

            # Second connection: STRICT should succeed with the persisted key
            strict_backend = SFTPBackend(
                host="127.0.0.1",
                port=port,
                username="testuser",
                password="testpass",
                base_path="/",
                host_key_policy=HostKeyPolicy.STRICT,
                host_keys_path=keys_path,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            result = strict_backend.exists("nonexistent.txt")
            assert result is False  # file doesn't exist; verifiable by strict policy
            strict_backend.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.spec("SFTP-028")
    def test_tofu_creates_parent_directories(self, sftp_server: tuple[int, str]) -> None:
        """TOFU creates nested parent directories for the known_hosts file."""
        port, _host_key_entry = sftp_server
        tmpdir = tempfile.mkdtemp(prefix="tofu_test_")
        keys_path = os.path.join(tmpdir, "a", "b", "known_hosts")
        try:
            backend = SFTPBackend(
                host="127.0.0.1",
                port=port,
                username="testuser",
                password="testpass",
                base_path="/",
                host_key_policy=HostKeyPolicy.TRUST_ON_FIRST_USE,
                host_keys_path=keys_path,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            backend.exists("nonexistent.txt")
            backend.close()
            assert os.path.isfile(keys_path)
            assert os.path.isdir(os.path.join(tmpdir, "a", "b"))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.spec("SFTP-028")
    def test_tofu_reconnect_preserves_keys(self, sftp_server: tuple[int, str]) -> None:
        """Keys survive the close-then-reconnect cycle within one backend lifetime."""
        port, _host_key_entry = sftp_server
        tmpdir = tempfile.mkdtemp(prefix="tofu_test_")
        keys_path = os.path.join(tmpdir, "known_hosts")
        try:
            backend = SFTPBackend(
                host="127.0.0.1",
                port=port,
                username="testuser",
                password="testpass",
                base_path="/",
                host_key_policy=HostKeyPolicy.TRUST_ON_FIRST_USE,
                host_keys_path=keys_path,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            # First operation triggers connection and TOFU key acceptance
            backend.exists("nonexistent.txt")
            # Force disconnect (saves keys) then reconnect (loads them back)
            backend._close_clients()
            backend.exists("nonexistent.txt")
            backend.close()

            # Verify the file still has the persisted key
            assert os.path.isfile(keys_path)
            assert os.path.getsize(keys_path) > 0
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.spec("SFTP-028")
    def test_tofu_inline_keys_not_persisted(self, sftp_server: tuple[int, str]) -> None:
        """Inline known_host_keys with TOFU policy do not trigger file persistence."""
        port, host_key_entry = sftp_server
        tmpdir = tempfile.mkdtemp(prefix="tofu_test_")
        keys_path = os.path.join(tmpdir, "known_hosts")
        try:
            backend = SFTPBackend(
                host="127.0.0.1",
                port=port,
                username="testuser",
                password="testpass",
                base_path="/",
                host_key_policy=HostKeyPolicy.TRUST_ON_FIRST_USE,
                known_host_keys=host_key_entry,
                host_keys_path=keys_path,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            backend.exists("nonexistent.txt")
            backend.close()
            # Observable: with inline keys, the TRUST_ON_FIRST_USE
            # file-load branch is bypassed entirely — _ensure_known_hosts_file
            # is never called and _close_clients does not invoke
            # save_host_keys (because _tofu_keys_path stays None). The
            # public-observable proxy is therefore: the user's
            # host_keys_path file was never created.
            assert not os.path.isfile(keys_path)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.spec("SFTP-028")
    def test_tofu_save_failure_suppressed(self, sftp_server: tuple[int, str]) -> None:
        """Save failure during close does not raise."""
        port, _host_key_entry = sftp_server
        tmpdir = tempfile.mkdtemp(prefix="tofu_test_")
        keys_path = os.path.join(tmpdir, "known_hosts")
        try:
            backend = SFTPBackend(
                host="127.0.0.1",
                port=port,
                username="testuser",
                password="testpass",
                base_path="/",
                host_key_policy=HostKeyPolicy.TRUST_ON_FIRST_USE,
                host_keys_path=keys_path,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            backend.exists("nonexistent.txt")
            # Mock save_host_keys to reliably fail on all platforms
            # (os.chmod is a no-op for owner on Windows)
            with patch.object(backend._ssh_client, "save_host_keys", side_effect=OSError("boom")):
                result = backend.close()
            assert result is None  # save failure suppressed
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# endregion


# region: Resolution (RES-054)
class TestSFTPResolve:
    """RES-054: SFTPBackend.resolve() returns kind='sftp' with host, port, base_path."""

    @pytest.mark.spec("RES-054")
    def test_kind_is_sftp(self) -> None:
        backend = SFTPBackend(
            host="example.com",
            port=22,
            username="u",
            password="p",
            host_key_policy=HostKeyPolicy.AUTO_ADD,
        )
        plan = backend.resolve("file.txt")
        assert plan.kind == "sftp"

    @pytest.mark.spec("RES-054")
    def test_details_has_host(self) -> None:
        backend = SFTPBackend(
            host="example.com",
            port=22,
            username="u",
            password="p",
            host_key_policy=HostKeyPolicy.AUTO_ADD,
        )
        plan = backend.resolve("file.txt")
        assert "host" in plan.details
        assert plan.details["host"] == "example.com"

    @pytest.mark.spec("RES-054")
    def test_details_has_port(self) -> None:
        backend = SFTPBackend(
            host="example.com",
            port=2222,
            username="u",
            password="p",
            host_key_policy=HostKeyPolicy.AUTO_ADD,
        )
        plan = backend.resolve("file.txt")
        assert "port" in plan.details
        assert plan.details["port"] == 2222

    @pytest.mark.spec("RES-054")
    def test_details_has_base_path(self) -> None:
        backend = SFTPBackend(
            host="example.com",
            port=22,
            username="u",
            password="p",
            base_path="/data",
            host_key_policy=HostKeyPolicy.AUTO_ADD,
        )
        plan = backend.resolve("file.txt")
        assert "base_path" in plan.details


# endregion


# region: RetryPolicy acceptance (RET-010) — migrated from tests/test_config.py (BK-216 / BK-191)
@pytest.mark.spec("RET-010")
@pytest.mark.parametrize(
    ("retry_arg", "expect_none"),
    [
        pytest.param(RetryPolicy(max_attempts=5), False, id="with_retry"),
        pytest.param(None, True, id="default_none"),
    ],
)
def test_sftp_retry(retry_arg: RetryPolicy | None, expect_none: bool) -> None:
    backend = SFTPBackend(host="h") if retry_arg is None else SFTPBackend(host="h", retry=retry_arg)
    assert (backend._retry is None) is expect_none


# endregion


# region: Credential masking (AF-008, SEC-004) — migrated from tests/test_coverage_gaps.py (BK-222 / BK-191 slice 6/6)


class TestSFTPCredentialMasking:
    """AF-008: SFTPBackend repr masks sensitive fields and accepts Secret wrappers."""

    def test_masks_set_secrets(self) -> None:
        backend = SFTPBackend(host="h", password="secret123", pkey="keydata")
        r = repr(backend)
        for raw in ("secret123", "keydata"):
            assert raw not in r
        for masked in ("password='***'", "pkey='***'"):
            assert masked in r
        assert "host='h'" in r

    def test_shows_none_for_unset_secrets(self) -> None:
        backend = SFTPBackend(host="h")
        r = repr(backend)
        for expected in ("password=None", "pkey=None"):
            assert expected in r

    @pytest.mark.spec("SEC-004")
    def test_accepts_secret_wrapper(self) -> None:
        from remote_store._config import Secret

        backend = SFTPBackend(host="h", password=Secret("pass123"))
        assert backend._password == "pass123"  # internal: no public observable (repr shows '***' for raw strings too)


# endregion
