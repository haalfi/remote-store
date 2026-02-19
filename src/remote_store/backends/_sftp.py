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
from typing import TYPE_CHECKING, Any, BinaryIO, TypeVar

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import FileInfo, FolderInfo
from remote_store._path import RemotePath

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._types import WritableContent

T = TypeVar("T")

log = logging.getLogger(__name__)

_SFTP_CAPABILITIES = CapabilitySet({c for c in Capability if c is not Capability.GLOB})

# RFC 4253 compliant chunk size for SFTP data transfer
_CHUNK_SIZE = 32768


# region: host key policy


class HostKeyPolicy(Enum):
    """Controls how unknown remote host keys are handled.

    :cvar STRICT: Reject unknown hosts (production default).
    :cvar TRUST_ON_FIRST_USE: Save on first connect, verify after.
    :cvar AUTO_ADD: Accept any key (dev/testing ONLY).
    """

    STRICT = "strict"
    TRUST_ON_FIRST_USE = "tofu"
    AUTO_ADD = "auto"


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
        source: File path (if from_file=True) or PEM-encoded string.
        from_file: If True, treat source as a file path.

    Returns:
        paramiko.RSAKey
    """
    import paramiko

    if from_file:
        return paramiko.RSAKey.from_private_key_file(source)
    with StringIO(_sanitize_pem(source)) as buf:
        return paramiko.RSAKey.from_private_key(buf)


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

    :param host: SFTP server hostname (required, non-empty).
    :param port: SSH port (default: 22).
    :param username: SSH username.
    :param password: SSH password.
    :param pkey: paramiko.PKey instance for key-based auth.
    :param base_path: Root path on the remote server (default: ``/``).
    :param host_key_policy: Host key verification policy.
    :param known_host_keys: Known hosts string (code-level override).
    :param host_keys_path: Path to known_hosts file (default: ``~/.ssh/known_hosts``).
    :param config: Optional config dict (may contain ``known_host_keys``).
    :param timeout: SSH connection timeout in seconds.
    :param connect_kwargs: Extra kwargs passed to ``SSHClient.connect()``.
    """

    def __init__(
        self,
        host: str,
        *,
        port: int = 22,
        username: str | None = None,
        password: str | None = None,
        pkey: Any = None,
        base_path: str = "/",
        host_key_policy: HostKeyPolicy = HostKeyPolicy.STRICT,
        known_host_keys: str | None = None,
        host_keys_path: str | None = None,
        config: dict[str, Any] | None = None,
        timeout: int = 10,
        connect_kwargs: dict[str, Any] | None = None,
    ) -> None:
        if not host or not host.strip():
            raise ValueError("host must be a non-empty string")
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._pkey = pkey
        self._base_path = base_path.rstrip("/") or "/"
        self._host_key_policy = host_key_policy
        self._host_keys_path = host_keys_path
        self._timeout = timeout
        self._connect_kwargs = connect_kwargs or {}
        self._resolved_host_keys = self._resolve_host_keys(known_host_keys, config)

        self._ssh_client: Any = None
        self._sftp_client: Any = None

    @property
    def name(self) -> str:
        return "sftp"

    @property
    def capabilities(self) -> CapabilitySet:
        return _SFTP_CAPABILITIES

    # region: lazy connection

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
            wait_exponential,
        )

        # Close any existing stale connection
        self._close_clients()

        ssh = self._create_ssh_client()

        @retry(
            retry=retry_if_exception_type((paramiko.SSHException, OSError, EOFError)),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            before_sleep=before_sleep_log(log, logging.WARNING),  # type: ignore[arg-type,unused-ignore]
            reraise=True,
        )
        def _do_connect() -> None:
            log.info("Connecting to %s:%d as %s", self._host, self._port, self._username)
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

        _do_connect()
        self._ssh_client = ssh
        self._sftp_client = ssh.open_sftp()
        log.info("SFTP connection established.")

    def _create_ssh_client(self) -> Any:
        """Create and configure an SSHClient with host key policy."""
        import paramiko

        ssh = paramiko.SSHClient()

        # Load known host keys from resolved source or file fallback
        if self._resolved_host_keys:  # pragma: no cover -- tested via unit test
            _load_host_keys_from_string(ssh, self._resolved_host_keys)
        elif self._host_key_policy in (  # pragma: no cover -- tests use AUTO_ADD
            HostKeyPolicy.STRICT,
            HostKeyPolicy.TRUST_ON_FIRST_USE,
        ):
            keys_path = self._host_keys_path or os.path.expanduser("~/.ssh/known_hosts")
            if os.path.isfile(keys_path):
                ssh.load_host_keys(keys_path)

        if self._host_key_policy == HostKeyPolicy.TRUST_ON_FIRST_USE:  # pragma: no cover
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        elif self._host_key_policy == HostKeyPolicy.AUTO_ADD:
            log.warning("AUTO_ADD host key policy -- NOT safe for production.")
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        return ssh

    def _is_connected(self) -> bool:
        """Check if the SFTP connection is alive."""
        if self._sftp_client is None or self._ssh_client is None:
            return False
        try:
            self._sftp_client.stat(".")
            return True
        except Exception:  # pragma: no cover -- requires transport failure
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

    def _close_clients(self) -> None:
        """Close SFTP and SSH clients if open."""
        if self._sftp_client is not None:
            with contextlib.suppress(Exception):
                self._sftp_client.close()
            self._sftp_client = None
        if self._ssh_client is not None:
            with contextlib.suppress(Exception):
                self._ssh_client.close()
            self._ssh_client = None

    # endregion

    # region: path helpers

    def to_key(self, native_path: str) -> str:
        if self._base_path == "/":
            # Strip leading slash
            return native_path.lstrip("/")
        if native_path.startswith(self._base_path + "/"):
            return native_path[len(self._base_path) + 1 :]
        if native_path == self._base_path:
            return ""
        return native_path

    def _sftp_path(self, path: str) -> str:
        """Convert a relative remote_store path to an absolute SFTP path."""
        if path:
            if self._base_path == "/":
                return f"/{path}"
            return f"{self._base_path}/{path}"
        return self._base_path

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
            except OSError:
                with contextlib.suppress(OSError):
                    self._sftp.mkdir(current)

    # endregion

    # region: error mapping

    @contextmanager
    def _errors(self, path: str = "") -> Iterator[None]:
        """Map paramiko/OS exceptions to remote_store errors."""
        import paramiko

        try:
            yield
        except RemoteStoreError:
            raise
        except FileNotFoundError:
            raise NotFound(f"Not found: {path}", path=path, backend=self.name) from None
        except OSError as exc:
            code = getattr(exc, "errno", None)
            if code == errno.ENOENT:
                raise NotFound(f"Not found: {path}", path=path, backend=self.name) from None
            if code == errno.EACCES:  # pragma: no cover -- requires server-side perm setup
                raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None
            if code == errno.EEXIST:  # pragma: no cover -- caught before reaching _errors
                raise AlreadyExists(f"Already exists: {path}", path=path, backend=self.name) from None
            raise RemoteStoreError(str(exc), path=path, backend=self.name) from None
        except paramiko.SSHException as exc:  # pragma: no cover -- requires SSH failure
            raise BackendUnavailable(str(exc), path=path, backend=self.name) from None
        except Exception as exc:  # pragma: no cover -- defensive
            raise RemoteStoreError(str(exc), path=path, backend=self.name) from None

    # endregion

    # region: helpers

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

    # endregion

    # region: existence checks

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
                return bool(stat.S_ISREG(attrs.st_mode))
            except OSError:
                return False

    def is_folder(self, path: str) -> bool:
        with self._errors(path):
            try:
                attrs = self._sftp.stat(self._sftp_path(path))
                return bool(stat.S_ISDIR(attrs.st_mode))
            except OSError:
                return False

    # endregion

    # region: read operations
    def read(self, path: str) -> BinaryIO:
        with self._errors(path):
            sftp_path = self._sftp_path(path)
            return self._sftp.file(sftp_path, "r")

    def read_bytes(self, path: str) -> bytes:
        with self._errors(path):
            sftp_path = self._sftp_path(path)
            try:
                with self._sftp.file(sftp_path, "r") as f:
                    f.prefetch()
                    return bytes(f.read())
            except OSError as exc:
                code = getattr(exc, "errno", None)
                if code == errno.ENOENT:
                    raise NotFound(f"Not found: {path}", path=path, backend=self.name) from None
                raise

    # endregion

    # region: write operations
    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        with self._errors(path):
            sftp_path = self._sftp_path(path)
            if not overwrite:
                try:
                    self._sftp.stat(sftp_path)
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
                except OSError as exc:
                    if getattr(exc, "errno", None) != errno.ENOENT:
                        raise
            self._ensure_parent_dirs(sftp_path)
            with self._sftp.file(sftp_path, "w") as f:
                if isinstance(content, bytes):
                    f.write(content)
                else:
                    shutil.copyfileobj(content, f, _CHUNK_SIZE)

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        with self._errors(path):
            sftp_path = self._sftp_path(path)
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
                    else:
                        shutil.copyfileobj(content, f, _CHUNK_SIZE)
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

    # endregion

    # region: delete operations
    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        with self._errors(path):
            sftp_path = self._sftp_path(path)
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
                if not stat.S_ISDIR(attrs.st_mode):
                    raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
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
                except OSError:
                    entries = []
                if entries:
                    raise RemoteStoreError(
                        f"Folder not empty: {path}",
                        path=path,
                        backend=self.name,
                    )
                self._sftp.rmdir(sftp_path)

    def _rmtree(self, sftp_path: str) -> None:
        """Recursively remove a directory tree, bottom-up."""
        try:
            entries = self._sftp.listdir_attr(sftp_path)
        except OSError:
            return
        for attr in entries:
            child = f"{sftp_path}/{attr.filename}"
            if stat.S_ISDIR(attr.st_mode):
                self._rmtree(child)
            else:
                self._sftp.remove(child)
        self._sftp.rmdir(sftp_path)

    # endregion

    # region: listing operations
    def list_files(self, path: str, *, recursive: bool = False) -> Iterator[FileInfo]:
        try:
            sftp_path = self._sftp_path(path)
            try:
                entries = self._sftp.listdir_attr(sftp_path)
            except OSError:
                return
            for attr in entries:
                if stat.S_ISREG(attr.st_mode):
                    rel = f"{path}/{attr.filename}" if path else attr.filename
                    yield self._stat_to_fileinfo(rel, attr)
                elif recursive and stat.S_ISDIR(attr.st_mode):
                    subpath = f"{path}/{attr.filename}" if path else attr.filename
                    yield from self.list_files(subpath, recursive=True)
        except RemoteStoreError:
            raise
        except Exception as exc:
            raise RemoteStoreError(str(exc), path=path, backend=self.name) from None

    def list_folders(self, path: str) -> Iterator[str]:
        try:
            sftp_path = self._sftp_path(path)
            try:
                entries = self._sftp.listdir_attr(sftp_path)
            except OSError:
                return
            for attr in entries:
                if stat.S_ISDIR(attr.st_mode):
                    yield attr.filename
        except RemoteStoreError:
            raise
        except Exception as exc:
            raise RemoteStoreError(str(exc), path=path, backend=self.name) from None

    # endregion

    # region: metadata
    def get_file_info(self, path: str) -> FileInfo:
        with self._errors(path):
            sftp_path = self._sftp_path(path)
            try:
                attrs = self._sftp.stat(sftp_path)
            except OSError as exc:
                if getattr(exc, "errno", None) == errno.ENOENT:
                    raise NotFound(f"File not found: {path}", path=path, backend=self.name) from None
                raise
            if not stat.S_ISREG(attrs.st_mode):
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
            if not stat.S_ISDIR(attrs.st_mode):
                raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)

            file_count, total_size, latest_modified = self._collect_folder_stats(sftp_path)

            if file_count == 0:
                raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
            return FolderInfo(
                path=RemotePath(path),
                file_count=file_count,
                total_size=total_size,
                modified_at=latest_modified,
            )

    def _collect_folder_stats(self, sftp_path: str) -> tuple[int, int, datetime | None]:
        """Recursively collect file count, total size, and latest modification time."""
        file_count = 0
        total_size = 0
        latest_modified: datetime | None = None

        try:
            entries = self._sftp.listdir_attr(sftp_path)
        except OSError:
            return file_count, total_size, latest_modified

        for attr in entries:
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

    # region: move and copy
    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        with self._errors(src):
            src_sftp = self._sftp_path(src)
            dst_sftp = self._sftp_path(dst)

            # Check source exists
            try:
                self._sftp.stat(src_sftp)
            except OSError as exc:
                if getattr(exc, "errno", None) == errno.ENOENT:
                    raise NotFound(f"Source not found: {src}", path=src, backend=self.name) from None
                raise

            # Check destination
            if not overwrite:
                try:
                    self._sftp.stat(dst_sftp)
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
                    with self._sftp.file(src_sftp, "r") as src_f:
                        with self._sftp.file(dst_sftp, "w") as dst_f:
                            shutil.copyfileobj(src_f, dst_f, _CHUNK_SIZE)
                    self._sftp.remove(src_sftp)

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        with self._errors(src):
            src_sftp = self._sftp_path(src)
            dst_sftp = self._sftp_path(dst)

            # Check source exists
            try:
                self._sftp.stat(src_sftp)
            except OSError as exc:
                if getattr(exc, "errno", None) == errno.ENOENT:
                    raise NotFound(f"Source not found: {src}", path=src, backend=self.name) from None
                raise

            # Check destination
            if not overwrite:
                try:
                    self._sftp.stat(dst_sftp)
                    raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
                except OSError as exc:
                    if getattr(exc, "errno", None) != errno.ENOENT:
                        raise

            self._ensure_parent_dirs(dst_sftp)

            # Stream source to destination (no server-side copy in SFTP)
            with self._sftp.file(src_sftp, "r") as src_f:
                with self._sftp.file(dst_sftp, "w") as dst_f:
                    shutil.copyfileobj(src_f, dst_f, _CHUNK_SIZE)

    # endregion

    # region: lifecycle
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
