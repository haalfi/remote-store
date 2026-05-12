"""SFTP backend using pure paramiko."""

from __future__ import annotations

import contextlib
import errno
import io
import logging
import os
import re
import shutil
import stat
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from io import StringIO
from typing import TYPE_CHECKING, Any, BinaryIO, ClassVar, TypeVar, cast

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import RetryPolicy, Secret, _reveal
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import FileInfo, FolderEntry, FolderInfo, WriteResult
from remote_store._path import RemotePath
from remote_store._stream import _ErrorMappingStream

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from remote_store._resolution import ResolutionPlan
    from remote_store._types import WritableContent

T = TypeVar("T")

log = logging.getLogger(__name__)

_SFTP_CAPABILITIES = CapabilitySet(
    set(Capability) - {Capability.GLOB, Capability.ATOMIC_MOVE, Capability.USER_METADATA}
)

# 256 KiB: reduces round-trips on modern SSH servers; paramiko fragments
# each write internally at the negotiated SSH packet size limit.
_CHUNK_SIZE = 262144


# region: host key policy


class HostKeyPolicy(Enum):
    """Controls how unknown remote host keys are handled.

    Attributes:
        STRICT: Reject unknown hosts (production default).
        TRUST_ON_FIRST_USE: Save on first connect, verify after.
        AUTO_ADD: Accept any key (dev/testing ONLY).

    Accepts the enum-name forms (``"auto_add"``, ``"trust_on_first_use"``,
    ``"STRICT"``) in addition to the canonical value strings (``"auto"``,
    ``"tofu"``, ``"strict"``).
    """

    STRICT = "strict"
    TRUST_ON_FIRST_USE = "tofu"
    AUTO_ADD = "auto"

    @classmethod
    def _missing_(cls, value: object) -> HostKeyPolicy | None:
        # Map enum-name aliases to their canonical members, case-insensitive
        # on the name only (e.g. "auto_add" -> AUTO_ADD). Value-form aliasing
        # (e.g. "AUTO" for value "auto") is intentionally not folded: that
        # contract is locked in by TestSFTPHostKeyPolicyAliases. Returning
        # None falls through to ValueError.
        if not isinstance(value, str):
            return None
        return cls.__members__.get(value.upper())


# endregion

# region: PEM handling

_NON_BASE64_PATTERN = re.compile(r"[^A-Za-z\d+/=]")
_PEM_SEPARATOR = "-----"


def _sanitize_pem(pem_content: str) -> str:
    """Normalize PEM line separators (handles Azure Key Vault blank-vs-newline quirk)."""
    parts = pem_content.split(_PEM_SEPARATOR)
    if len(parts) != 5:
        raise ValueError("Invalid PEM structure (expected 5 parts).")

    payload = parts[2]
    non_base64_chars = list(set(re.findall(_NON_BASE64_PATTERN, payload)))
    if len(non_base64_chars) != 1:
        raise ValueError(f"Unexpected PEM characters: {non_base64_chars}")

    parts[2] = payload.replace(non_base64_chars[0], "\n")
    if len(payload) != len(parts[2]):  # pragma: no cover -- defensive; replace preserves length
        raise ValueError("PEM payload length changed during sanitization.")

    return _PEM_SEPARATOR.join(parts)


def load_private_key(source: str, *, from_file: bool = False) -> Any:  # pragma: no cover
    """Load an RSA private key from a file path or a PEM string.

    Args:
        source: File path (if ``from_file=True``) or PEM-encoded string.
        from_file: If ``True``, treat *source* as a file path.

    Returns:
        ``paramiko.RSAKey``
    """
    import paramiko

    if from_file:
        return paramiko.RSAKey.from_private_key_file(source)
    with StringIO(_sanitize_pem(source)) as buf:
        return paramiko.RSAKey.from_private_key(buf)


def scan_host_keys(host: str, port: int = 22, *, timeout: float = 10.0) -> str:
    """Discover an SFTP server's host key without authenticating.

    Opens a ``paramiko.Transport`` to *host*:*port*, performs key exchange,
    captures the server's offered host key, closes the connection, and
    returns the key as a single ``known_hosts``-formatted line. No
    authentication is attempted; only the SSH key-exchange handshake runs.

    Use this to populate a committed ``host.keys`` file for production
    `STRICT` policy use, without going through a TOFU connect first.

    Args:
        host: Hostname or IP address of the SFTP server.
        port: SSH port (default: 22).
        timeout: Socket and KEX timeout in seconds (default: 10).

    Returns:
        A single ``known_hosts``-format line:
        ``"<host_label> <key_type> <base64_key>"``. Per OpenSSH convention,
        *host_label* is ``"[host]:port"`` when *port* is not 22, and the
        bare hostname otherwise. The trailing newline is not included.

        Returns only the **negotiated** key for one handshake (whichever
        key type paramiko picked: usually one of ed25519, ecdsa, rsa),
        not every key the server offers. ``ssh-keyscan`` returns one line
        per offered type by default; this helper does not. If the server
        offers multiple key types and paramiko later negotiates a
        different one than the pinned line, the connection fails with
        ``BadHostKeyException``. Callers that need full-type coverage
        must call this helper multiple times under different
        ``disabled_algorithms`` settings to force each type in turn.

    Raises:
        paramiko.SSHException: Negotiation failed (e.g. legacy server
            offering only ``ssh-rsa``; call ``enable_ssh_rsa_compat()``
            first if so).
        OSError: Socket-level failure (host unreachable, port refused,
            DNS error, timeout).

    !!! example

        ```python
        from pathlib import Path

        from remote_store.backends import SFTPUtils

        entry = SFTPUtils.scan_host_keys("sftp.example.com")
        Path("host.keys").write_text(entry + "\\n")
        ```
    """
    import socket

    import paramiko

    # Connect the socket ourselves so a refused / unreachable target raises
    # cleanly without leaking a half-bound socket through paramiko's
    # tuple-handling path. The Transport constructor is also guarded so the
    # socket is closed if Transport.__init__ raises before ownership transfers.
    sock = socket.create_connection((host, port), timeout=timeout)
    try:
        transport = paramiko.Transport(sock)
    except Exception:
        sock.close()
        raise
    try:
        transport.banner_timeout = timeout
        transport.start_client(timeout=timeout)
        key = transport.get_remote_server_key()
    finally:
        transport.close()

    return _format_known_hosts_line(host, port, key)


def _format_known_hosts_line(host: str, port: int, key: Any) -> str:
    """Format a paramiko ``PKey`` into a single ``known_hosts``-style line.

    Per OpenSSH convention, the label is ``[host]:port`` when *port* is
    not 22; the bare hostname otherwise.
    """
    host_label = f"[{host}]:{port}" if port != 22 else host
    return f"{host_label} {key.get_name()} {key.get_base64()}"


def enable_ssh_rsa_compat() -> None:
    """Guarantee ``ssh-rsa`` (SHA-1) acceptance across paramiko's four host-key sites.

    Appends ``ssh-rsa`` to four paramiko class attributes if it is
    missing — future-proofing the consumer against eventual removal,
    and restoring state if downstream code has cleared it:

    1. ``paramiko.Transport._preferred_keys`` -- KEX host-key-algorithm
       negotiation.
    2. ``paramiko.Transport._key_info`` -- host-key parsing dispatch.
    3. ``paramiko.rsakey.RSAKey.HASHES`` -- signature-verification hash
       dispatch.
    4. ``paramiko.Transport._preferred_pubkeys`` -- client RSA public-key
       authentication signatures.

    On every paramiko version verified (2.12, 3.0, 3.5, 4.0) all four
    sites contain ``ssh-rsa`` by default, so a freshly-imported
    paramiko already negotiates against an ``ssh-rsa``-only server
    without this helper. The helper is therefore a no-op on a clean
    process and only changes behavior when:

    - downstream code or a transport subclass has stripped ``ssh-rsa``
      from one of the four sites;
    - or a future paramiko major release follows through on removal.

    For KEX / cipher / MAC negotiation failures (e.g.
    ``IncompatiblePeer: no acceptable kex algorithm``), this helper is
    not the right tool — use ``connect_kwargs={"disabled_algorithms":
    ...}`` to widen those instead.

    ``disabled_algorithms`` cannot re-add a default-removed algorithm,
    so class-level patching is the only forward-compatible path. The
    patches are idempotent; calling this multiple times in the same
    process is safe.

    !!! warning "Process-global side effect"

        Every paramiko transport in this process will accept SHA-1 host
        keys for the lifetime of the process. Only call this if the
        consumer connects exclusively to servers under your operational
        control, or if you have explicitly evaluated the tradeoff for
        every server in the process.

        ``ssh-rsa`` is appended (not prepended) to the preferred lists, so
        modern algorithms are still negotiated first when the server
        offers them.

    !!! example

        ```python
        from remote_store.backends import SFTPUtils

        # Call once at process startup, before any SFTPBackend connect.
        SFTPUtils.enable_ssh_rsa_compat()
        ```
    """
    import paramiko
    from cryptography.hazmat.primitives import hashes
    from paramiko.rsakey import RSAKey

    # types-paramiko does not expose these private class attributes that
    # paramiko maintains for algorithm negotiation; mutating them is the
    # only supported path for re-enabling a default-removed algorithm.
    transport_cls: Any = paramiko.Transport
    if "ssh-rsa" not in transport_cls._preferred_keys:
        transport_cls._preferred_keys = (
            *transport_cls._preferred_keys,
            "ssh-rsa",
        )
    if "ssh-rsa" not in transport_cls._key_info:
        transport_cls._key_info["ssh-rsa"] = RSAKey
    if "ssh-rsa" not in RSAKey.HASHES:
        RSAKey.HASHES["ssh-rsa"] = hashes.SHA1
    if "ssh-rsa" not in transport_cls._preferred_pubkeys:
        transport_cls._preferred_pubkeys = (
            *transport_cls._preferred_pubkeys,
            "ssh-rsa",
        )


class SFTPUtils:
    """SFTP setup utilities for key loading and host verification.

    Groups helpers that assist with SFTP backend configuration:

    - ``SFTPUtils.load_private_key(...)`` -- load RSA keys from file or PEM string
    - ``SFTPUtils.HostKeyPolicy`` -- enum controlling unknown host key behavior
    - ``SFTPUtils.scan_host_keys(host, port=22)`` -- preflight host-key
      discovery; returns a ``known_hosts``-formatted line for committing
      into a ``host.keys`` file
    - ``SFTPUtils.enable_ssh_rsa_compat()`` -- restore ``ssh-rsa`` (SHA-1)
      acceptance for legacy SFTP servers (see method docstring for the
      security tradeoff)

    !!! example

        ```python
        from remote_store.backends import SFTPUtils, SFTPBackend

        key = SFTPUtils.load_private_key("~/.ssh/id_rsa", from_file=True)
        backend = SFTPBackend(
            host="sftp.example.com",
            pkey=key,
            host_key_policy=SFTPUtils.HostKeyPolicy.AUTO_ADD,
        )
        ```
    """

    HostKeyPolicy = HostKeyPolicy
    load_private_key = staticmethod(load_private_key)
    enable_ssh_rsa_compat = staticmethod(enable_ssh_rsa_compat)
    scan_host_keys = staticmethod(scan_host_keys)


# endregion

# region: host key helpers

_HOST_KEYS_ENV = "SFTP_KNOWN_HOST_KEYS"


def _load_host_keys_from_string(ssh: Any, keys_content: str) -> None:  # pragma: no cover
    """Parse a known_hosts-formatted string into an SSHClient's host keys."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".known_hosts", delete=True) as tmp:
        tmp.write(keys_content)
        tmp.flush()
        ssh.load_host_keys(tmp.name)


# endregion


class SFTPBackend(Backend):
    """SFTP backend using pure paramiko.

    ``move()`` attempts ``posix_rename`` (atomic on POSIX-compliant servers),
    then falls back to ``rename``, and finally to a stream copy followed by
    a delete.  Because atomicity cannot be guaranteed across all servers,
    ``ATOMIC_MOVE`` is not declared.

    Warning:
        **Not thread-safe for concurrent access.** This backend maintains a
        single SSH/SFTP connection (paramiko ``SFTPClient``), which is not
        safe to call from multiple threads simultaneously. Concurrent calls
        via ``SyncBackendAdapter`` and
        ``asyncio.gather`` will race on the shared socket and may hang or
        corrupt responses. Create one ``SFTPBackend`` instance per thread if
        you need parallel operations.

    Args:
        host: SFTP server hostname (required, non-empty).
        port: SSH port (default: 22).
        username: SSH username.
        password: SSH password.
        pkey: paramiko.PKey instance for key-based auth.
        base_path: Root path on the remote server (default: ``/``).
        host_key_policy: Host key verification policy
            (see ``SFTPUtils.HostKeyPolicy``). Accepts enum value or string.
        known_host_keys: Known hosts string (code-level override).
        host_keys_path: Path to known_hosts file (default: ``~/.ssh/known_hosts``).
        config: Optional config dict (may contain ``known_host_keys``).
        timeout: SSH connection timeout in seconds.
        connect_kwargs: Extra kwargs passed to ``SSHClient.connect()``.
    """

    CAPABILITIES: ClassVar[CapabilitySet] = _SFTP_CAPABILITIES

    def __init__(
        self,
        host: str,
        *,
        port: int = 22,
        username: str | None = None,
        password: str | Secret | None = None,
        pkey: Any = None,
        base_path: str = "/",
        host_key_policy: HostKeyPolicy | str = HostKeyPolicy.STRICT,
        known_host_keys: str | None = None,
        host_keys_path: str | None = None,
        config: dict[str, Any] | None = None,
        timeout: int = 10,
        connect_kwargs: dict[str, Any] | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        if not host or not host.strip():
            raise ValueError("host must be a non-empty string")
        if isinstance(host_key_policy, str):
            host_key_policy = HostKeyPolicy(host_key_policy)
        self._host = host
        self._port = port
        self._username = username
        self._password = _reveal(password)
        self._pkey = pkey
        self._base_path = base_path.rstrip("/") or "/"
        self._host_key_policy = host_key_policy
        self._host_keys_path = host_keys_path
        self._timeout = timeout
        self._connect_kwargs = connect_kwargs or {}
        self._retry = retry
        self._resolved_host_keys = self._resolve_host_keys(known_host_keys, config)

        self._tofu_keys_path: str | None = None
        self._ssh_client: Any = None
        self._sftp_client: Any = None

    # region: properties

    @property
    def name(self) -> str:
        return "sftp"

    @property
    def capabilities(self) -> CapabilitySet:
        return self.CAPABILITIES

    # endregion

    # region: public methods

    def check_health(self) -> None:
        with self._errors():
            self._sftp.stat(self._base_path)

    def to_key(self, native_path: str) -> str:
        if self._base_path == "/":
            # Strip leading slash
            return native_path.lstrip("/")
        if native_path.startswith(self._base_path + "/"):
            return native_path[len(self._base_path) + 1 :]
        if native_path == self._base_path:
            return ""
        return native_path

    def native_path(self, path: str) -> str:
        if path:
            if self._base_path == "/":
                return f"/{path}"
            return f"{self._base_path}/{path}"
        return self._base_path

    def resolve(self, path: str) -> ResolutionPlan:
        """Return a ``ResolutionPlan`` with SFTP-specific details.

        Args:
            path: Backend-relative key.

        Returns:
            Plan with ``kind="sftp"`` and ``details`` containing
            ``host``, ``port``, and ``base_path``.
        """
        from remote_store._resolution import ResolutionPlan as _RP

        return _RP(
            kind="sftp",
            backend=self.name,
            key=path,
            native_path=self.native_path(path),
            details={
                "host": self._host,
                "port": self._port,
                "base_path": self._base_path,
            },
        )

    def exists(self, path: str) -> bool:
        with self._errors(path):
            try:
                self._sftp.stat(self._sftp_path(path))
                return True
            except OSError:
                return False

    def is_file(self, path: str) -> bool:
        with self._errors(path):
            try:
                attrs = self._sftp.stat(self._sftp_path(path))
                return attrs.st_mode is not None and bool(stat.S_ISREG(attrs.st_mode))
            except OSError:
                return False

    def is_folder(self, path: str) -> bool:
        with self._errors(path):
            try:
                attrs = self._sftp.stat(self._sftp_path(path))
                return attrs.st_mode is not None and bool(stat.S_ISDIR(attrs.st_mode))
            except OSError:
                return False

    def read(self, path: str) -> BinaryIO:
        with self._errors(path):
            sftp_path = self._sftp_path(path)
            self._check_not_dir(sftp_path, path)
            f: BinaryIO = self._sftp.file(sftp_path, "r")
            try:
                raw = _ErrorMappingStream(f, self._map_exception, path)
                return io.BufferedReader(cast(io.RawIOBase, raw))  # noqa: TC006
            except Exception:
                f.close()
                raise

    def read_bytes(self, path: str) -> bytes:
        with self._errors(path):
            sftp_path = self._sftp_path(path)
            self._check_not_dir(sftp_path, path)
            try:
                with self._sftp.file(sftp_path, "r") as f:
                    f.prefetch()
                    return bytes(f.read())
            except OSError as exc:
                code = getattr(exc, "errno", None)
                if code == errno.ENOENT:
                    raise NotFound(f"Not found: {path}", path=path, backend=self.name) from None
                raise

    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        with self._errors(path):
            sftp_path = self._sftp_path(path)
            try:
                st = self._sftp.stat(sftp_path)
                if st is not None and st.st_mode is not None and stat.S_ISDIR(st.st_mode):
                    raise InvalidPath(f"Not a file: {path}", path=path, backend=self.name)
                if not overwrite:
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
            except OSError as exc:
                if getattr(exc, "errno", None) != errno.ENOENT:
                    raise
            self._ensure_parent_dirs(sftp_path)
            with self._sftp.file(sftp_path, "w") as f:
                if isinstance(content, bytes):
                    f.write(content)
                    size = len(content)
                else:
                    size = 0
                    while True:
                        chunk = content.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                        size += len(chunk)
            post_stat = self._sftp.stat(sftp_path)
        mtime = post_stat.st_mtime
        last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc) if mtime is not None else None
        return WriteResult(path=RemotePath(path), size=size, source="native", last_modified=last_modified)

    def write_atomic(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        with self._errors(path):
            sftp_path = self._sftp_path(path)
            self._check_not_dir(sftp_path, path)
            if not overwrite:
                try:
                    self._sftp.stat(sftp_path)
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
                except OSError as exc:
                    if getattr(exc, "errno", None) != errno.ENOENT:
                        raise
            self._ensure_parent_dirs(sftp_path)
            # Write to temp file, then rename
            name = sftp_path.rsplit("/", 1)[-1] if "/" in sftp_path else sftp_path
            parent = sftp_path.rsplit("/", 1)[0] if "/" in sftp_path else "."
            tmp_name = f".~tmp.{name}.{uuid.uuid4().hex[:8]}"
            tmp_path = f"{parent}/{tmp_name}"
            try:
                with self._sftp.file(tmp_path, "w") as f:
                    if isinstance(content, bytes):
                        f.write(content)
                        size = len(content)
                    else:
                        size = 0
                        while True:
                            chunk = content.read(_CHUNK_SIZE)
                            if not chunk:
                                break
                            f.write(chunk)
                            size += len(chunk)
                try:
                    self._sftp.posix_rename(tmp_path, sftp_path)
                except OSError:  # pragma: no cover -- fallback for servers without posix_rename
                    if overwrite:
                        with contextlib.suppress(OSError):
                            self._sftp.remove(sftp_path)
                    self._sftp.rename(tmp_path, sftp_path)
            except Exception:
                # Attempt to clean up temp file on failure
                with contextlib.suppress(Exception):
                    self._sftp.remove(tmp_path)
                raise
            post_stat = self._sftp.stat(sftp_path)
        mtime = post_stat.st_mtime
        last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc) if mtime is not None else None
        return WriteResult(path=RemotePath(path), size=size, source="native", last_modified=last_modified)

    @contextmanager
    def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
        # Setup phase: existence check + parent dirs (within error mapping)
        with self._errors(path):
            sftp_path = self._sftp_path(path)
            self._check_not_dir(sftp_path, path)
            if not overwrite:
                try:
                    self._sftp.stat(sftp_path)
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
                except OSError as exc:
                    if getattr(exc, "errno", None) != errno.ENOENT:
                        raise
            self._ensure_parent_dirs(sftp_path)
            name = sftp_path.rsplit("/", 1)[-1] if "/" in sftp_path else sftp_path
            parent = sftp_path.rsplit("/", 1)[0] if "/" in sftp_path else "."
            tmp_name = f".~tmp.{name}.{uuid.uuid4().hex[:8]}"
            tmp_path = f"{parent}/{tmp_name}"
        # Yield phase: outside _errors() so user exceptions propagate cleanly
        try:
            with self._sftp.file(tmp_path, "w") as f:
                yield f
            with self._errors(path):
                try:
                    self._sftp.posix_rename(tmp_path, sftp_path)
                except OSError:  # pragma: no cover -- fallback for servers without posix_rename
                    if overwrite:
                        with contextlib.suppress(OSError):
                            self._sftp.remove(sftp_path)
                    self._sftp.rename(tmp_path, sftp_path)
        except Exception:
            with contextlib.suppress(Exception):
                self._sftp.remove(tmp_path)
            raise

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        with self._errors(path):
            sftp_path = self._sftp_path(path)
            self._check_not_dir(sftp_path, path)
            try:
                self._sftp.remove(sftp_path)
            except OSError as exc:
                if getattr(exc, "errno", None) == errno.ENOENT:
                    if not missing_ok:
                        raise NotFound(f"File not found: {path}", path=path, backend=self.name) from None
                    return
                raise

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        with self._errors(path):
            sftp_path = self._sftp_path(path)
            try:
                attrs = self._sftp.stat(sftp_path)
                if attrs.st_mode is not None and not stat.S_ISDIR(attrs.st_mode):
                    raise InvalidPath(f"Not a folder: {path}", path=path, backend=self.name)
            except OSError as exc:
                if getattr(exc, "errno", None) == errno.ENOENT:
                    if not missing_ok:
                        raise NotFound(f"Folder not found: {path}", path=path, backend=self.name) from None
                    return
                raise

            if recursive:
                self._rmtree(sftp_path)
            else:
                # Non-recursive: fail if folder has contents
                try:
                    entries = self._sftp.listdir(sftp_path)
                except OSError as exc:
                    if getattr(exc, "errno", None) == errno.ENOENT:
                        entries = []
                    else:
                        raise
                if entries:
                    raise DirectoryNotEmpty(
                        f"Folder not empty: {path}",
                        path=path,
                        backend=self.name,
                    )
                self._sftp.rmdir(sftp_path)

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        try:
            yield from self._list_files_depth(path, recursive=recursive, max_depth=max_depth, _depth=0)
        except RemoteStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise RemoteStoreError(str(exc), path=path, backend=self.name) from None

    def _list_files_depth(
        self,
        path: str,
        *,
        recursive: bool,
        max_depth: int | None,
        _depth: int,
    ) -> Iterator[FileInfo]:
        sftp_path = self._sftp_path(path)
        try:
            entries = self._sftp.listdir_attr(sftp_path)
        except OSError as exc:
            if getattr(exc, "errno", None) == errno.ENOENT:
                return
            raise
        for attr in entries:
            if attr.st_mode is None:
                continue
            if stat.S_ISREG(attr.st_mode):
                rel = f"{path}/{attr.filename}" if path else attr.filename
                yield self._stat_to_fileinfo(rel, attr)
            elif recursive and stat.S_ISDIR(attr.st_mode):
                if max_depth is not None and _depth >= max_depth:
                    continue
                subpath = f"{path}/{attr.filename}" if path else attr.filename
                yield from self._list_files_depth(
                    subpath,
                    recursive=True,
                    max_depth=max_depth,
                    _depth=_depth + 1,
                )

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        try:
            sftp_path = self._sftp_path(path)
            try:
                entries = self._sftp.listdir_attr(sftp_path)
            except OSError as exc:
                if getattr(exc, "errno", None) == errno.ENOENT:
                    return
                raise
            for attr in entries:
                if attr.st_mode is None:
                    continue
                if stat.S_ISDIR(attr.st_mode):
                    rel = f"{path}/{attr.filename}" if path else attr.filename
                    yield FolderEntry(path=RemotePath(rel), name=attr.filename)
        except RemoteStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise RemoteStoreError(str(exc), path=path, backend=self.name) from None

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        try:
            sftp_path = self._sftp_path(path)
            try:
                entries = self._sftp.listdir_attr(sftp_path)
            except OSError as exc:
                if getattr(exc, "errno", None) == errno.ENOENT:
                    return
                raise
            for attr in entries:
                if attr.st_mode is None:
                    continue
                if stat.S_ISREG(attr.st_mode):
                    rel = f"{path}/{attr.filename}" if path else attr.filename
                    yield self._stat_to_fileinfo(rel, attr)
                elif stat.S_ISDIR(attr.st_mode):
                    rel = f"{path}/{attr.filename}" if path else attr.filename
                    yield FolderEntry(path=RemotePath(rel), name=attr.filename)
        except RemoteStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise RemoteStoreError(str(exc), path=path, backend=self.name) from None

    def get_file_info(self, path: str) -> FileInfo:
        with self._errors(path):
            sftp_path = self._sftp_path(path)
            try:
                attrs = self._sftp.stat(sftp_path)
            except OSError as exc:
                if getattr(exc, "errno", None) == errno.ENOENT:
                    raise NotFound(f"File not found: {path}", path=path, backend=self.name) from None
                raise
            if attrs.st_mode is not None and stat.S_ISDIR(attrs.st_mode):
                raise InvalidPath(f"Not a file: {path}", path=path, backend=self.name)
            if attrs.st_mode is None or not stat.S_ISREG(attrs.st_mode):
                raise NotFound(f"File not found: {path}", path=path, backend=self.name)
            return self._stat_to_fileinfo(path, attrs)

    def get_folder_info(self, path: str) -> FolderInfo:
        with self._errors(path):
            sftp_path = self._sftp_path(path)
            try:
                attrs = self._sftp.stat(sftp_path)
            except OSError as exc:
                if getattr(exc, "errno", None) == errno.ENOENT:
                    raise NotFound(f"Folder not found: {path}", path=path, backend=self.name) from None
                raise
            if attrs.st_mode is not None and stat.S_ISREG(attrs.st_mode):
                raise InvalidPath(f"Not a folder: {path}", path=path, backend=self.name)
            if attrs.st_mode is None or not stat.S_ISDIR(attrs.st_mode):
                raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)

            file_count, total_size, latest_modified = self._collect_folder_stats(sftp_path)

            return FolderInfo(
                path=RemotePath.from_backend_path(path),
                file_count=file_count,
                total_size=total_size,
                modified_at=latest_modified,
            )

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        with self._errors(src):
            src_sftp = self._sftp_path(src)
            dst_sftp = self._sftp_path(dst)

            # Check source exists and is a file
            try:
                src_attrs = self._sftp.stat(src_sftp)
            except OSError as exc:
                if getattr(exc, "errno", None) == errno.ENOENT:
                    raise NotFound(f"Source not found: {src}", path=src, backend=self.name) from None
                raise
            if src_attrs.st_mode is not None and stat.S_ISDIR(src_attrs.st_mode):
                raise InvalidPath(f"Source is a directory: {src}", path=src, backend=self.name)

            # Self-move is a no-op
            if src_sftp == dst_sftp:
                return

            # Check destination
            try:
                dst_attrs = self._sftp.stat(dst_sftp)
                if dst_attrs.st_mode is not None and stat.S_ISDIR(dst_attrs.st_mode):
                    raise InvalidPath(f"Destination is a directory: {dst}", path=dst, backend=self.name)
                if not overwrite:
                    raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
            except OSError as exc:
                if getattr(exc, "errno", None) != errno.ENOENT:
                    raise

            self._ensure_parent_dirs(dst_sftp)

            # Try posix_rename (atomic), then rename, then copy+delete
            try:
                self._sftp.posix_rename(src_sftp, dst_sftp)
            except OSError:  # pragma: no cover -- fallback for servers without posix_rename
                try:
                    if overwrite:
                        with contextlib.suppress(OSError):
                            self._sftp.remove(dst_sftp)
                    self._sftp.rename(src_sftp, dst_sftp)
                except OSError:
                    # Fallback: stream copy + delete
                    with self._sftp.file(src_sftp, "r") as src_f, self._sftp.file(dst_sftp, "w") as dst_f:
                        shutil.copyfileobj(src_f, dst_f, _CHUNK_SIZE)
                    self._sftp.remove(src_sftp)

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        with self._errors(src):
            src_sftp = self._sftp_path(src)
            dst_sftp = self._sftp_path(dst)

            # Check source exists and is a file
            try:
                src_attrs = self._sftp.stat(src_sftp)
            except OSError as exc:
                if getattr(exc, "errno", None) == errno.ENOENT:
                    raise NotFound(f"Source not found: {src}", path=src, backend=self.name) from None
                raise
            if src_attrs.st_mode is not None and stat.S_ISDIR(src_attrs.st_mode):
                raise InvalidPath(f"Source is a directory: {src}", path=src, backend=self.name)

            # Self-copy is a no-op
            if src_sftp == dst_sftp:
                return

            # Check destination
            try:
                dst_attrs = self._sftp.stat(dst_sftp)
                if dst_attrs.st_mode is not None and stat.S_ISDIR(dst_attrs.st_mode):
                    raise InvalidPath(f"Destination is a directory: {dst}", path=dst, backend=self.name)
                if not overwrite:
                    raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
            except OSError as exc:
                if getattr(exc, "errno", None) != errno.ENOENT:
                    raise

            self._ensure_parent_dirs(dst_sftp)

            # Stream source to destination (no server-side copy in SFTP)
            with self._sftp.file(src_sftp, "r") as src_f, self._sftp.file(dst_sftp, "w") as dst_f:
                shutil.copyfileobj(src_f, dst_f, _CHUNK_SIZE)

    def close(self) -> None:
        self._close_clients()

    def unwrap(self, type_hint: type[T]) -> T:
        import paramiko

        if type_hint is paramiko.SFTPClient:
            return self._sftp  # type: ignore[no-any-return]
        raise CapabilityNotSupported(
            f"Backend 'sftp' does not expose native handle of type {type_hint.__name__}. "
            f"Override unwrap() in your backend to provide native access.",
            capability="unwrap",
            backend=self.name,
        )

    # endregion

    # region: dunder methods

    def __del__(self) -> None:
        # Guard against interpreter shutdown: module globals may be None.
        try:
            if getattr(self, "_sftp_client", None) is None and getattr(self, "_ssh_client", None) is None:
                return
        except Exception:  # noqa: BLE001
            return
        try:  # noqa: SIM105 — cannot use contextlib.suppress during shutdown
            self._del_cleanup()
        except Exception:  # noqa: BLE001
            pass

    def _del_cleanup(self) -> None:
        """Warn and inline-close clients; called by __del__ without contextlib."""
        try:
            import warnings

            warnings.warn(
                f"Unclosed {type(self).__name__}. Call .close() or use a context manager.",
                ResourceWarning,
                stacklevel=2,
            )
        except Exception:  # noqa: BLE001
            pass
        # Inline cleanup — cannot rely on contextlib during shutdown.
        try:
            sftp = getattr(self, "_sftp_client", None)
            if sftp is not None:
                try:  # noqa: SIM105 — cannot use contextlib during shutdown
                    sftp.close()
                except Exception:  # noqa: BLE001
                    pass
                self._sftp_client = None
            ssh = getattr(self, "_ssh_client", None)
            if ssh is not None:
                try:  # noqa: SIM105 — cannot use contextlib during shutdown
                    ssh.close()
                except Exception:  # noqa: BLE001
                    pass
                self._ssh_client = None
        except Exception:  # noqa: BLE001
            pass

    def __repr__(self) -> str:
        return (
            f"SFTPBackend(host={self._host!r}, port={self._port!r}, "
            f"username={self._username!r}, "
            f"password={'***' if self._password is not None else None!r}, "
            f"pkey={'***' if self._pkey is not None else None!r}, "
            f"base_path={self._base_path!r})"
        )

    # endregion

    # region: private helpers

    @property
    def _sftp(self) -> Any:
        """Lazy SFTP client with automatic reconnection on staleness."""
        if not self._is_connected():
            self._connect()
        return self._sftp_client

    def _connect(self) -> None:
        """Establish SSH + SFTP connection with tenacity retry."""
        import paramiko
        from tenacity import (
            before_sleep_log,
            retry,
            retry_if_exception_type,
            stop_after_attempt,
            stop_after_delay,
            wait_exponential,
            wait_random,
        )

        # Close any existing stale connection
        self._close_clients()

        ssh = self._create_ssh_client()

        # Build tenacity parameters from retry policy (or use defaults)
        rp = self._retry
        stop_cond: Any = stop_after_attempt(rp.max_attempts if rp else 3)
        if rp and rp.timeout is not None:
            stop_cond = stop_cond | stop_after_delay(rp.timeout)
        wait_cond: Any = wait_exponential(
            multiplier=1,
            min=rp.backoff_base if rp else 2,
            max=rp.backoff_max if rp else 10,
        )
        if rp and rp.jitter > 0:
            wait_cond = wait_cond + wait_random(0, rp.jitter)

        @retry(
            retry=retry_if_exception_type((paramiko.SSHException, OSError, EOFError)),
            stop=stop_cond,
            wait=wait_cond,
            before_sleep=before_sleep_log(log, logging.WARNING),  # type: ignore[arg-type,unused-ignore]
            reraise=True,
        )
        def _do_connect() -> None:
            log.info(
                "Connecting to %s:%d as %s",
                self._host,
                self._port,
                self._username,
                extra={"op": "connect", "backend": "sftp"},
            )
            ssh.connect(
                hostname=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                pkey=self._pkey,
                timeout=self._timeout,
                banner_timeout=self._timeout,
                auth_timeout=self._timeout,
                channel_timeout=self._timeout,
                **self._connect_kwargs,
            )

        try:
            _do_connect()
        except Exception:
            with contextlib.suppress(Exception):
                ssh.close()
            raise
        self._ssh_client = ssh
        self._sftp_client = ssh.open_sftp()
        log.info("SFTP connection established.", extra={"op": "connect", "backend": "sftp"})

    def _create_ssh_client(self) -> Any:
        """Create and configure an SSHClient with host key policy."""
        import paramiko

        ssh = paramiko.SSHClient()

        # Load known host keys from resolved source or file fallback
        if self._resolved_host_keys:  # pragma: no cover -- tested via unit test
            _load_host_keys_from_string(ssh, self._resolved_host_keys)
            self._tofu_keys_path = None  # inline keys are never persisted
        elif self._host_key_policy == HostKeyPolicy.TRUST_ON_FIRST_USE:
            keys_path = self._host_keys_path or os.path.expanduser("~/.ssh/known_hosts")
            self._ensure_known_hosts_file(keys_path)
            ssh.load_host_keys(keys_path)
            self._tofu_keys_path = keys_path
        elif self._host_key_policy == HostKeyPolicy.STRICT:  # pragma: no cover
            keys_path = self._host_keys_path or os.path.expanduser("~/.ssh/known_hosts")
            if os.path.isfile(keys_path):
                ssh.load_host_keys(keys_path)

        if self._host_key_policy == HostKeyPolicy.TRUST_ON_FIRST_USE:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        elif self._host_key_policy == HostKeyPolicy.AUTO_ADD:
            log.warning(
                "AUTO_ADD host key policy -- NOT safe for production.",
                extra={"op": "connect", "backend": "sftp"},
            )
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        return ssh

    def _is_connected(self) -> bool:
        """Check if the SFTP connection is alive."""
        if self._sftp_client is None or self._ssh_client is None:
            return False
        try:
            self._sftp_client.stat(".")
            return True
        except Exception:  # pragma: no cover -- requires transport failure  # noqa: BLE001
            return False

    def _resolve_host_keys(self, direct: str | None, config: dict[str, Any] | None) -> str | None:
        """Resolve known host keys: code > config > env > file fallback."""
        if direct:
            return direct
        if config and (val := config.get("known_host_keys")):  # pragma: no cover
            return str(val)
        if val_env := os.environ.get(_HOST_KEYS_ENV):  # pragma: no cover
            return val_env
        return None

    @staticmethod
    def _ensure_known_hosts_file(path: str) -> None:
        """Create the known_hosts file and parent directories if absent."""
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, mode=0o700, exist_ok=True)
        if not os.path.isfile(path):
            # mode=0o600 is enforced on Unix; NTFS ignores POSIX mode bits on Windows.
            fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)

    def _close_clients(self) -> None:
        """Close SFTP and SSH clients if open."""
        if self._sftp_client is not None:
            with contextlib.suppress(Exception):
                self._sftp_client.close()
            self._sftp_client = None
        if self._ssh_client is not None:
            if self._tofu_keys_path is not None:
                with contextlib.suppress(Exception):
                    self._ssh_client.save_host_keys(self._tofu_keys_path)
            with contextlib.suppress(Exception):
                self._ssh_client.close()
            self._ssh_client = None

    def _sftp_path(self, path: str) -> str:
        """Convert a relative remote_store path to an absolute SFTP path."""
        if path:
            if self._base_path == "/":
                return f"/{path}"
            return f"{self._base_path}/{path}"
        return self._base_path

    def _check_not_dir(self, sftp_path: str, path: str) -> None:
        """Raise InvalidPath if *sftp_path* is a directory (type-mismatch guard).

        Note: this issues an extra ``stat`` round-trip.  ``write()`` folds
        the check into its existing stat; callers like ``read()`` and
        ``delete()`` pay the extra call for simplicity.
        """
        try:
            st = self._sftp.stat(sftp_path)
            if st is not None and st.st_mode is not None and stat.S_ISDIR(st.st_mode):
                raise InvalidPath(f"Not a file: {path}", path=path, backend=self.name)
        except OSError as exc:
            if getattr(exc, "errno", None) == errno.ENOENT:
                return  # path doesn't exist — let caller handle NotFound
            raise

    def _ensure_parent_dirs(self, sftp_path: str) -> None:
        """Create parent directories for the given SFTP path if they don't exist."""
        parent = sftp_path.rsplit("/", 1)[0] if "/" in sftp_path else ""
        if not parent or parent == self._base_path:
            return
        # Walk from base_path down, creating directories as needed
        parts = parent.split("/")
        current = ""
        for part in parts:
            if not part:
                current = "/"
                continue
            current = f"{current}/{part}" if current and current != "/" else f"/{part}"
            try:
                self._sftp.stat(current)
            except OSError as exc:
                if getattr(exc, "errno", None) != errno.ENOENT:
                    raise
                try:
                    self._sftp.mkdir(current)
                except OSError as mkdir_exc:
                    # Suppress EEXIST (race condition: another client created it)
                    if getattr(mkdir_exc, "errno", None) != errno.EEXIST:
                        raise

    @contextmanager
    def _errors(self, path: str = "") -> Iterator[None]:
        """Map paramiko/OS exceptions to remote_store errors."""
        try:
            yield
        except RemoteStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._map_exception(exc, path) from None

    def _map_exception(self, exc: Exception, path: str) -> RemoteStoreError:
        """Classify an exception into a remote_store error.

        Single source of truth for SFTP error mapping, used by both the
        ``_errors()`` context manager and ``_ErrorMappingStream``.
        """
        import paramiko

        if isinstance(exc, RemoteStoreError):
            return exc
        if isinstance(exc, FileNotFoundError):
            return NotFound(f"Not found: {path}", path=path, backend=self.name)
        if isinstance(exc, OSError):
            code = getattr(exc, "errno", None)
            if code == errno.ENOENT:
                return NotFound(f"Not found: {path}", path=path, backend=self.name)
            if code == errno.EACCES:
                return PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name)
            if code == errno.EEXIST:
                return AlreadyExists(f"Already exists: {path}", path=path, backend=self.name)
            return RemoteStoreError(str(exc), path=path, backend=self.name)
        if isinstance(exc, paramiko.ssh_exception.IncompatiblePeer):
            # IncompatiblePeer wraps host-key / KEX / cipher / MAC negotiation
            # failures; only the host-key variant is addressable by
            # enable_ssh_rsa_compat. Match the paramiko message substring so the
            # hint does not mislead callers hitting KEX/cipher/MAC failures.
            # The literal symbol "enable_ssh_rsa_compat" is asserted by
            # TestSFTPIncompatiblePeerHint; rename the helper and this string
            # plus that test together.
            if "host key" in str(exc):
                return BackendUnavailable(
                    f"{exc} [hint: if ssh-rsa has been cleared from paramiko's "
                    f"defaults (by downstream code or a future paramiko release), "
                    f"call SFTPUtils.enable_ssh_rsa_compat() at process startup "
                    f"to restore it]",
                    path=path,
                    backend=self.name,
                )
            return BackendUnavailable(str(exc), path=path, backend=self.name)
        if isinstance(exc, paramiko.SSHException):
            return BackendUnavailable(str(exc), path=path, backend=self.name)
        return RemoteStoreError(str(exc), path=path, backend=self.name)  # pragma: no cover

    def _stat_to_fileinfo(self, path: str, attrs: Any) -> FileInfo:
        """Convert paramiko SFTPAttributes to a FileInfo."""
        name = path.rsplit("/", 1)[-1] if "/" in path else path
        size = attrs.st_size or 0
        mtime = attrs.st_mtime
        if mtime is not None:
            modified = datetime.fromtimestamp(mtime, tz=timezone.utc)
        else:
            modified = datetime.now(tz=timezone.utc)
        return FileInfo(
            path=RemotePath(path),
            name=name,
            size=int(size),
            modified_at=modified,
        )

    def _rmtree(self, sftp_path: str) -> None:
        """Recursively remove a directory tree, bottom-up."""
        try:
            entries = self._sftp.listdir_attr(sftp_path)
        except OSError as exc:
            if getattr(exc, "errno", None) == errno.ENOENT:
                return
            raise
        for attr in entries:
            child = f"{sftp_path}/{attr.filename}"
            if attr.st_mode is None:
                continue
            if stat.S_ISDIR(attr.st_mode):
                self._rmtree(child)
            else:
                self._sftp.remove(child)
        self._sftp.rmdir(sftp_path)

    def _collect_folder_stats(self, sftp_path: str) -> tuple[int, int, datetime | None]:
        """Recursively collect file count, total size, and latest modification time."""
        file_count = 0
        total_size = 0
        latest_modified: datetime | None = None

        try:
            entries = self._sftp.listdir_attr(sftp_path)
        except OSError as exc:
            if getattr(exc, "errno", None) == errno.ENOENT:
                return file_count, total_size, latest_modified
            raise

        for attr in entries:
            if attr.st_mode is None:
                continue
            if stat.S_ISREG(attr.st_mode):
                file_count += 1
                total_size += attr.st_size or 0
                if attr.st_mtime is not None:
                    modified = datetime.fromtimestamp(attr.st_mtime, tz=timezone.utc)
                    if latest_modified is None or modified > latest_modified:
                        latest_modified = modified
            elif stat.S_ISDIR(attr.st_mode):
                sub_count, sub_size, sub_latest = self._collect_folder_stats(f"{sftp_path}/{attr.filename}")
                file_count += sub_count
                total_size += sub_size
                if sub_latest is not None and (latest_modified is None or sub_latest > latest_modified):
                    latest_modified = sub_latest

        return file_count, total_size, latest_modified

    # endregion
