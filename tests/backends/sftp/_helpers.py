"""In-process SFTP server for testing, backed by a local temp directory.

Uses paramiko's ServerInterface + SFTPServerInterface to run a real SFTP server
in a background thread. Accepts all authentication for test convenience.
"""

from __future__ import annotations

import contextlib
import errno
import os
import socket
import threading
from pathlib import Path, PurePosixPath

import paramiko
from paramiko import (
    AUTH_SUCCESSFUL,
    OPEN_SUCCEEDED,
    RSAKey,
    ServerInterface,
    SFTPAttributes,
    SFTPHandle,
    SFTPServer,
    SFTPServerInterface,
    Transport,
)

# Chroot boundary for ``ChrootStubSFTPServer`` and the ``sftp_chroot_inproc``
# fixture (ID-212). The server denies ``stat`` on this path and everything
# above it (SSH_FX_PERMISSION_DENIED) while allowing paths strictly below it —
# reproducing a chrooted deployment whose ancestors above the chroot are
# unstattable. The fixture sets the backend's ``base_path`` to a unique
# subdirectory *below* this boundary (e.g. ``/restricted/test_ab12``), so the
# boundary is a proper, denied ancestor of every backend path while each test
# still gets an isolated root.
CHROOT_BOUNDARY = "/restricted"


# region: stub SSH server -- accepts all auth
class StubServer(ServerInterface):
    """Minimal SSH server that accepts all authentication."""

    def check_auth_password(self, username: str, password: str) -> int:
        return AUTH_SUCCESSFUL

    def check_auth_publickey(self, username: str, key: paramiko.PKey) -> int:
        return AUTH_SUCCESSFUL

    def check_channel_request(self, kind: str, chanid: int) -> int:
        return OPEN_SUCCEEDED


# endregion


# region: SFTP handle -- wraps a real file descriptor
class StubSFTPHandle(SFTPHandle):
    """SFTP handle that wraps a real file on the local filesystem."""

    def stat(self) -> SFTPAttributes:
        try:
            return SFTPAttributes.from_stat(os.fstat(self.readfile.fileno()))
        except OSError as exc:
            return SFTPServer.convert_errno(exc.errno)  # type: ignore[return-value]

    def chattr(self, attr: SFTPAttributes) -> int:
        return paramiko.SFTP_OK


# endregion


# region: SFTP server interface -- maps operations to local filesystem
class StubSFTPServer(SFTPServerInterface):
    """SFTP server backed by a local directory tree."""

    ROOT: str = ""  # set by start_sftp_server before accepting connections

    def _realpath(self, path: str) -> str:
        """Map an SFTP path to the local filesystem."""
        # Normalize to POSIX, strip leading /
        posix = str(PurePosixPath(path))
        if posix.startswith("/"):
            posix = posix[1:]
        return str(Path(self.ROOT) / posix)

    def list_folder(self, path: str) -> list[SFTPAttributes]:
        realpath = self._realpath(path)
        try:
            entries = []
            for name in os.listdir(realpath):
                full = os.path.join(realpath, name)
                attr = SFTPAttributes.from_stat(os.stat(full))
                attr.filename = name
                entries.append(attr)
            return entries
        except OSError as exc:
            return SFTPServer.convert_errno(exc.errno)  # type: ignore[return-value]

    def stat(self, path: str) -> SFTPAttributes | int:
        realpath = self._realpath(path)
        try:
            return SFTPAttributes.from_stat(os.stat(realpath))
        except OSError as exc:
            return SFTPServer.convert_errno(exc.errno)  # type: ignore[return-value]

    def lstat(self, path: str) -> SFTPAttributes | int:
        realpath = self._realpath(path)
        try:
            return SFTPAttributes.from_stat(os.lstat(realpath))
        except OSError as exc:
            return SFTPServer.convert_errno(exc.errno)  # type: ignore[return-value]

    def open(self, path: str, flags: int, attr: SFTPAttributes) -> SFTPHandle | int:
        realpath = self._realpath(path)
        try:
            # Ensure parent directory exists
            parent = os.path.dirname(realpath)
            if not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)

            fd = os.open(realpath, flags, 0o644)
        except OSError as exc:
            return SFTPServer.convert_errno(exc.errno)  # type: ignore[return-value]

        if (flags & os.O_CREAT) and attr is not None:
            attr._flags &= ~attr.FLAG_PERMISSIONS  # type: ignore[attr-defined]

        # Determine Python file mode from OS-level flags
        if flags & os.O_WRONLY:
            mode = "wb"
        elif flags & os.O_RDWR:
            mode = "rb+"
        else:
            mode = "rb"
        fobj = os.fdopen(fd, mode)
        handle = StubSFTPHandle(flags)
        handle.filename = realpath
        handle.readfile = fobj  # type: ignore[assignment]
        handle.writefile = fobj  # type: ignore[assignment]
        return handle

    def remove(self, path: str) -> int:
        realpath = self._realpath(path)
        try:
            os.remove(realpath)
            return paramiko.SFTP_OK
        except OSError as exc:
            return SFTPServer.convert_errno(exc.errno)  # type: ignore[return-value]

    def rename(self, oldpath: str, newpath: str) -> int:
        real_old = self._realpath(oldpath)
        real_new = self._realpath(newpath)
        try:
            os.rename(real_old, real_new)
            return paramiko.SFTP_OK
        except OSError as exc:
            return SFTPServer.convert_errno(exc.errno)  # type: ignore[return-value]

    def posix_rename(self, oldpath: str, newpath: str) -> int:
        real_old = self._realpath(oldpath)
        real_new = self._realpath(newpath)
        try:
            os.replace(real_old, real_new)
            return paramiko.SFTP_OK
        except OSError as exc:
            return SFTPServer.convert_errno(exc.errno)  # type: ignore[return-value]

    def mkdir(self, path: str, attr: SFTPAttributes) -> int:
        realpath = self._realpath(path)
        try:
            os.makedirs(realpath, exist_ok=True)
            return paramiko.SFTP_OK
        except OSError as exc:
            return SFTPServer.convert_errno(exc.errno)  # type: ignore[return-value]

    def rmdir(self, path: str) -> int:
        realpath = self._realpath(path)
        try:
            os.rmdir(realpath)
            return paramiko.SFTP_OK
        except OSError as exc:
            return SFTPServer.convert_errno(exc.errno)  # type: ignore[return-value]

    def chattr(self, path: str, attr: SFTPAttributes) -> int:
        return paramiko.SFTP_OK

    def readlink(self, path: str) -> str | int:
        realpath = self._realpath(path)
        try:
            return os.readlink(realpath)
        except OSError as exc:
            return SFTPServer.convert_errno(exc.errno)  # type: ignore[return-value]

    def symlink(self, target_path: str, path: str) -> int:
        return paramiko.SFTP_OP_UNSUPPORTED


# endregion


# region: chroot SFTP server -- denies stat above a configured boundary
class ChrootStubSFTPServer(StubSFTPServer):
    """SFTP server that refuses to stat the chroot boundary and everything above.

    Simulates a chrooted/partial-permission deployment: ``stat`` / ``lstat``
    on the boundary path ``CHROOT`` or any of its ancestors returns
    ``SSH_FX_PERMISSION_DENIED``, exactly as an OpenSSH server does when a
    directory above the chroot is mode ``700`` and owned by another user.
    Paths strictly *below* the boundary behave like the plain
    ``StubSFTPServer``.

    The backend under test sets ``base_path`` to a subdirectory below
    ``CHROOT``, so ``CHROOT`` is a denied proper ancestor of every backend
    path. A file-ancestor walk that starts from the absolute SFTP root ``/``
    trips the denied boundary and mis-classifies the failure, while a walk
    that starts at ``base_path`` never probes above it (ID-212). This is the
    case the ``sftp_inproc`` fixture cannot reach — it grants unrestricted
    local-FS access.
    """

    CHROOT: str = ""  # set by start_sftp_server before accepting connections

    def _within_chroot(self, path: str) -> bool:
        # Relative paths (notably "." -- paramiko's connection-liveness probe)
        # are not subject to the boundary; only absolute requests are.
        if not path.startswith("/"):
            return True
        boundary = self.CHROOT.rstrip("/")
        # Allowed iff strictly below the boundary; the boundary itself and any
        # ancestor are denied.
        return str(PurePosixPath(path)).startswith(boundary + "/")

    def stat(self, path: str) -> SFTPAttributes | int:
        if not self._within_chroot(path):
            return SFTPServer.convert_errno(errno.EACCES)  # type: ignore[return-value]
        return super().stat(path)

    def lstat(self, path: str) -> SFTPAttributes | int:
        if not self._within_chroot(path):
            return SFTPServer.convert_errno(errno.EACCES)  # type: ignore[return-value]
        return super().lstat(path)


# endregion


# region: server lifecycle
def _accept_connections(
    server_socket: socket.socket,
    host_key: RSAKey,
    root: str,
    stop_event: threading.Event,
    server_class: type[StubSFTPServer] = StubSFTPServer,
    chroot: str | None = None,
) -> None:
    """Accept SSH connections in a loop until stop_event is set.

    ``server_class`` selects the SFTP interface implementation (the plain
    ``StubSFTPServer`` or the ``ChrootStubSFTPServer`` variant). ``ROOT`` and
    ``CHROOT`` are set on that class so concurrently running servers of
    different classes do not clobber each other's attributes.
    """
    server_socket.settimeout(0.5)
    server_class.ROOT = root
    if chroot is not None:
        server_class.CHROOT = chroot  # type: ignore[attr-defined]

    while not stop_event.is_set():
        try:
            conn, _addr = server_socket.accept()
        except TimeoutError:
            continue
        except OSError:
            break

        transport = Transport(conn)
        transport.add_server_key(host_key)
        transport.set_subsystem_handler("sftp", SFTPServer, server_class)

        server = StubServer()
        try:
            transport.start_server(server=server)
        except Exception:  # noqa: BLE001
            transport.close()
            continue

        # Let the transport handle the SFTP subsystem in its own thread;
        # we just need to keep accepting new connections.
        # The transport thread is daemonic by default in paramiko.


def start_sftp_server(
    root: str,
    host: str = "127.0.0.1",
    port: int = 0,
    server_class: type[StubSFTPServer] = StubSFTPServer,
    chroot: str | None = None,
) -> tuple[threading.Thread, int, RSAKey, threading.Event, socket.socket]:
    """Start an in-process SFTP server in a background thread.

    Args:
        root: Local directory to serve as the SFTP root.
        host: Bind address (default: localhost).
        port: Bind port (default: 0 = OS-assigned free port).
        server_class: SFTP interface implementation. Defaults to the plain
            ``StubSFTPServer``; pass ``ChrootStubSFTPServer`` for the
            permission-restricted variant (ID-212).
        chroot: Boundary path for ``ChrootStubSFTPServer``. Ignored by the
            plain server.

    Returns:
        (thread, actual_port, host_key, stop_event, server_socket)
    """
    host_key = RSAKey.generate(2048)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen(5)
    actual_port = server_socket.getsockname()[1]

    stop_event = threading.Event()

    thread = threading.Thread(
        target=_accept_connections,
        args=(server_socket, host_key, root, stop_event, server_class, chroot),
        daemon=True,
    )
    thread.start()

    return thread, actual_port, host_key, stop_event, server_socket


def stop_sftp_server(
    thread: threading.Thread,
    stop_event: threading.Event,
    server_socket: socket.socket,
) -> None:
    """Stop the SFTP server thread and clean up resources."""
    stop_event.set()
    with contextlib.suppress(OSError):
        server_socket.close()
    thread.join(timeout=5)


# endregion
