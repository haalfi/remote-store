"""Does a failing readline() on io.BufferedReader advance the position past undelivered bytes?

Usage (repo root): hatch run python sdd/research/bk-485-op01-stream-spike/freeze-1/readline_loss.py
CPython only, no library code: the content and call sequence of conform.py's T1 divergence.
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


data = b"\xfbP\xf6\xa2ti\xa5"  # 7 bytes, no newline (the conform trace's content)
s = io.BufferedReader(Raw(data, fail_on_call=2))
buf = bytearray(6)
print("readinto(6) ->", s.readinto(buf), bytes(buf), "tell", s.tell())
try:
    s.readline()
except OSError as e:
    print("readline() raised", e)
print("tell after failed readline:", s.tell(), "(bytes delivered: 6)")
print("next read():", s.read())
