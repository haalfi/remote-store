"""Reference model of the OP-01 read stream (spike, step 3).

Built from stream_rows.toml only. Not an implementation: content is held in
memory and the environment is a set of one-shot injections. Category names
(Unavailable, Cancelled) are working names, as in the record.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

OPEN, EXHAUSTED, FAILED, CLOSED = "Open", "Exhausted", "Failed", "Closed"


class Unavailable(Exception):
    """Storage failure category a transfer can surface (D16, D28)."""


class Cancelled(BaseException):
    """Stand-in for asyncio.CancelledError / KeyboardInterrupt (E14)."""


class Env:
    """One-shot environment events, consumed by the next call that meets them."""

    def __init__(self) -> None:
        self.fail = False
        self.cancel = False
        self.release_fail = False

    def take(self, name: str) -> bool:
        hit = getattr(self, name)
        setattr(self, name, False)
        return hit


class Stream:
    def __init__(self, content: bytes, env: Env | None = None) -> None:
        self._content = content
        self._env = env or Env()
        self.pos = 0
        self.state = OPEN if content else EXHAUSTED  # R01, R02
        self._error: Unavailable | None = None
        self.release_log: list[str] = []

    # -- guards shared by every read-family call ---------------------------

    def _check_readable(self) -> None:
        if self.state == CLOSED:
            raise ValueError("I/O operation on closed stream")  # R20, R21
        if self.state == FAILED:
            assert self._error is not None
            raise type(self._error)(*self._error.args)  # R15, R16: same category

    def _transfer(self, m: int) -> bytes:
        """Deliver the next m bytes, or fail / cancel without delivering any."""
        if self._env.take("cancel"):
            self._release()
            self.state = CLOSED  # R23, R24
            raise Cancelled
        if self._env.take("fail"):
            self._error = Unavailable("transport failure")
            self.state = FAILED  # R14
            raise Unavailable("transport failure")
        data = self._content[self.pos : self.pos + m]
        self.pos += m
        if self.pos == len(self._content):
            self.state = EXHAUSTED  # R04, R05
        return data

    def _release(self) -> None:
        if self._env.take("release_fail"):
            self.release_log.append("release failed (swallowed)")  # R25
        else:
            self.release_log.append("released")

    # -- file-object surface -----------------------------------------------

    def read(self, n: int = -1) -> bytes:
        self._check_readable()
        if self.state == EXHAUSTED:
            return b""  # R12
        remaining = len(self._content) - self.pos
        m = remaining if n < 0 else min(n, remaining)
        if m == 0:
            return b""  # R06 (assumed: no transfer)
        return self._transfer(m)

    def readinto(self, buf: bytearray) -> int:
        data = self.read(len(buf))  # R10 (assumed)
        buf[: len(data)] = data
        return len(data)

    def readline(self) -> bytes:
        line = bytearray()  # R11 (assumed io semantics)
        while not line.endswith(b"\n"):
            b = self.read(1)
            if not b:
                break
            line += b
        return bytes(line)

    def chunks(self, size: int) -> Iterator[bytes]:
        if size <= 0:
            raise ValueError("size must be positive")  # R09 (assumed)
        self._check_readable()  # eager: Closed / Failed raise at the call
        return self._iter_chunks(size)

    def _iter_chunks(self, size: int) -> Iterator[bytes]:
        while True:
            chunk = self.read(size)  # shares read's position (D2)
            if not chunk:
                return  # R07, R13
            yield chunk

    def close(self) -> None:
        if self.state == CLOSED:
            return  # R22
        cancel = self._env.take("cancel")
        self._release()
        self.state = CLOSED  # R17-R19, R25
        if cancel:
            raise Cancelled  # R26 (state assumed Closed)

    def collect(self) -> None:
        """Stand-in for garbage collection of the last reference (D17)."""
        if self.state != CLOSED:
            warnings.warn("unclosed stream", ResourceWarning, stacklevel=2)  # R27, R28
            self._release()
            self.state = CLOSED

    def seekable(self) -> bool:
        if self.state == CLOSED:
            raise ValueError("I/O operation on closed stream")
        return False  # D2

    def handle_end(self) -> None:
        raise NotImplementedError("open item OP-01/O5")  # R30
