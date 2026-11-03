"""Does a failing readline() on io.BufferedReader lose bytes it had buffered but not delivered?

Usage (repo root): hatch run python sdd/research/bk-485-op01-stream-spike/freeze-1/readline_loss.py
CPython only, no library code. Case 1 is the content and call sequence of conform.py's
T1 divergence (7 bytes, all in the first raw read); case 2 is content larger than the
buffer, so the failing raw read is mid-file.
"""

import io


class Raw(io.RawIOBase):
    def __init__(self, data: bytes, fail_on_call: int):
        self.data, self.pos, self.calls, self.fail_on = data, 0, 0, fail_on_call

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, pos, whence=0):
        self.pos = pos if whence == 0 else self.pos + pos
        return self.pos

    def readinto(self, b):
        self.calls += 1
        if self.calls == self.fail_on:
            raise OSError(5, "injected EIO")
        n = min(len(b), len(self.data) - self.pos)
        b[:n] = self.data[self.pos : self.pos + n]
        self.pos += n
        return n


def run(label: str, data: bytes, buffer_size: int) -> None:
    s = io.BufferedReader(Raw(data, fail_on_call=2), buffer_size=buffer_size)
    buf = bytearray(6)
    got = s.readinto(buf)
    try:
        s.readline()
        print(f"{label}: readline() did not raise")
    except OSError as e:
        print(f"{label}: readline() raised {e}")
    pos = s.tell()
    rest = s.read()
    delivered = got + len(rest)
    print(f"  size {len(data)}, buffer {buffer_size}: readinto(6) -> {got}; tell after failed readline: {pos}")
    print(f"  next read() -> {len(rest)} bytes; delivered {delivered} of {len(data)}, lost {len(data) - delivered}")
    if rest:
        start = len(data) - len(rest)
        print(f"  next read() starts at offset {start}: gap of {start - got} bytes after offset {got}")


run("case 1", b"\xfbP\xf6\xa2ti\xa5", 8192)  # 7 bytes, no newline (the conform trace's content)
run("case 2", bytes(range(11, 256)) * 84, 8192)  # 20580 bytes, no newline (byte 10 excluded)
