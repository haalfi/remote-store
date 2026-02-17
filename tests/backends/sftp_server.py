"""In-process SFTP server for testing, backed by a local temp directory.

Uses paramiko's ServerInterface + SFTPServerInterface to run a real SFTP server
in a background thread. Accepts all authentication for test convenience.
"""

from __future__ import annotations

import contextlib
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

# ---------------------------------------------------------------------------
# Stub SSH server -- accepts all auth
# ---------------------------------------------------------------------------


class StubServer(ServerInterface):
    """Minimal SSH server that accepts all authentication."""

    def check_auth_password(self, username: str, password: str) -> int:
        return AUTH_SUCCESSFUL

    def check_auth_publickey(self, username: str, key: paramiko.PKey) -> int:
        return AUTH_SUCCESSFUL

    def check_channel_request(self, kind: str, chanid: int) -> int:
        return OPEN_SUCCEEDED


# ---------------------------------------------------------------------------
# SFTP handle -- wraps a real file descriptor
# ---------------------------------------------------------------------------


class StubSFTPHandle(SFTPHandle):
    """SFTP handle that wraps a real file on the local filesystem."""

    def stat(self) -> SFTPAttributes:
        try:
            return SFTPAttributes.from_stat(os.fstat(self.readfile.fileno()))
        except OSError as exc:
            return SFTPServer.convert_errno(exc.errno)  # type: ignore[return-value]

    def chattr(self, attr: SFTPAttributes) -> int:
        return paramiko.SFTP_OK


# ---------------------------------------------------------------------------
# SFTP server interface -- maps operations to local filesystem
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


def _accept_connections(
    server_socket: socket.socket,
    host_key: RSAKey,
    root: str,
    stop_event: threading.Event,
) -> None:
    """Accept SSH connections in a loop until stop_event is set."""
    server_socket.settimeout(0.5)
    StubSFTPServer.ROOT = root

    while not stop_event.is_set():
        try:
            conn, _addr = server_socket.accept()
        except TimeoutError:
            continue
        except OSError:
            break

        transport = Transport(conn)
        transport.add_server_key(host_key)
        transport.set_subsystem_handler("sftp", SFTPServer, StubSFTPServer)

        server = StubServer()
        try:
            transport.start_server(server=server)
        except Exception:
            transport.close()
            continue

        # Let the transport handle the SFTP subsystem in its own thread;
        # we just need to keep accepting new connections.
        # The transport thread is daemonic by default in paramiko.


def start_sftp_server(
    root: str,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[threading.Thread, int, RSAKey, threading.Event, socket.socket]:
    """Start an in-process SFTP server in a background thread.

    Args:
        root: Local directory to serve as the SFTP root.
        host: Bind address (default: localhost).
        port: Bind port (default: 0 = OS-assigned free port).

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
        args=(server_socket, host_key, root, stop_event),
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
