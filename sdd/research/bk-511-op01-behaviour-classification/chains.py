"""Local's gaps C1 to C7 on the other read() chains, offline, with injected faults.

Usage (repo root): hatch run python sdd/research/bk-511-op01-behaviour-classification/chains.py

Each chain is read()'s production stack around a stand-in for the network:
  S3 boto3  BufferedReader(1 MiB) / _ErrorMappingStream(the backend's classifier) / real _S3RangeReader, fake client
  Azure     BufferedReader / _ErrorMappingStream(stub mapper) / real _AzureBinaryIO over a fake chunk iterator
  SFTP      BufferedReader / _ErrorMappingStream(stub mapper) / a seekable fake standing in for paramiko's SFTPFile
Part 2 runs azure-storage-blob's own _ChunkIterator under Azure's chain with a fake
downloader whose second chunk download raises once. Every fault here is injected.
"""

from __future__ import annotations

import errno
import io

from azure.core.exceptions import ServiceResponseError
from azure.storage.blob._download import _ChunkIterator

from remote_store._errors import BackendUnavailable
from remote_store._stream import _ErrorMappingStream
from remote_store.backends._azure import _AzureBinaryIO
from remote_store.backends._s3_boto3 import _READ_BUFFER_SIZE, S3Boto3Backend, _S3RangeReader

DATA = b"abcdefghij"


class Arm:
    """One armed fault: 'fail' raises OSError(EIO), 'cancel' KeyboardInterrupt, 'close_fail' on close."""

    fault: str | None = None

    def take(self) -> None:
        f = self.fault if self.fault in ("fail", "cancel") else None
        if f:
            self.fault = None
        if f == "fail":
            raise OSError(errno.EIO, "injected")
        if f == "cancel":
            raise KeyboardInterrupt


class FakeS3Client:
    def __init__(self, arm: Arm) -> None:
        self.arm = arm

    def get_object(self, Bucket: str, Key: str, Range: str) -> dict:  # noqa: N803 - boto3's names
        self.arm.take()
        a, b = map(int, Range.removeprefix("bytes=").split("-"))
        return {"Body": io.BytesIO(DATA[a : b + 1])}


class FakeSFTPFile(io.RawIOBase):
    def __init__(self, arm: Arm) -> None:
        self.arm, self.b = arm, io.BytesIO(DATA)

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True  # as paramiko's SFTPFile

    def seek(self, o: int, w: int = 0) -> int:
        return self.b.seek(o, w)

    def tell(self) -> int:
        return self.b.tell()

    def readinto(self, buf) -> int:
        self.arm.take()
        return self.b.readinto(buf)

    def close(self) -> None:
        fail, self.arm.fault = self.arm.fault == "close_fail", None
        super().close()
        if fail:
            raise OSError(errno.EIO, "injected release failure")


def stub_mapper(exc: Exception, path: str) -> BackendUnavailable:
    return BackendUnavailable(str(exc), path=path, backend="stub")


def s3(arm: Arm) -> io.BufferedReader:
    rr = _S3RangeReader(FakeS3Client(arm), "b", "k", len(DATA))
    ems = _ErrorMappingStream(rr, S3Boto3Backend("b")._classify_error, "k")
    return io.BufferedReader(ems, buffer_size=_READ_BUFFER_SIZE)


def azure(arm: Arm) -> io.BufferedReader:
    def chunks():
        for i in range(0, len(DATA), 3):
            arm.take()
            yield DATA[i : i + 3]

    return io.BufferedReader(_ErrorMappingStream(_AzureBinaryIO(chunks()), stub_mapper, "k"))


def sftp(arm: Arm) -> io.BufferedReader:
    return io.BufferedReader(_ErrorMappingStream(FakeSFTPFile(arm), stub_mapper, "k"))


def outcome(fn, *args) -> str:
    try:
        return f"returned {fn(*args)!r}"
    except BaseException as e:  # noqa: BLE001 - the outcome is the datum
        return f"raised {type(e).__name__}"


def part1() -> None:
    for name, make in (("S3 boto3", s3), ("Azure", azure), ("SFTP (fake SFTPFile)", sftp)):
        arm = Arm()
        print(f"== {name}")
        print("  C5 read(-2):", outcome(make(arm).read, -2))
        s = make(arm)
        print("  C6 seekable():", outcome(s.seekable), "| C7 seek(0):", outcome(s.seek, 0))
        s = make(arm)
        arm.fault = "cancel"
        print("  C1 read(2) !cancel:", outcome(s.read, 2), "| closed after:", s.closed)
        s = make(arm)
        arm.fault = "fail"
        print("  C3 read(2) !fail:", outcome(s.read, 2), "| C2 next read(2):", outcome(s.read, 2))
        if make is sftp:  # the only chain here whose inner close can be made to raise
            s = make(arm)
            arm.fault = "close_fail"
            print("  C4 close() !release_fail:", outcome(s.close), "| closed after:", s.closed)


CHUNK = 4
CONTENT = bytes(range(48, 68))  # 20 bytes: the first GET's 4, then 4 chunks of 4


class FakeDownloader:
    def __init__(self, exc: Exception) -> None:
        self.calls, self.exc = 0, exc

    def get_chunk_offsets(self):
        yield from range(CHUNK, len(CONTENT), CHUNK)

    def yield_chunk(self, off: int):
        self.calls += 1
        if self.calls == 2:
            raise self.exc
        return CONTENT[off : off + CHUNK], None


def part2() -> None:
    print("== Azure: a failed chunk download, then read on")
    for exc in (OSError("injected"), ServiceResponseError("injected")):
        it = _ChunkIterator(len(CONTENT), CONTENT[:CHUNK], FakeDownloader(exc), CHUNK)
        s = io.BufferedReader(_ErrorMappingStream(_AzureBinaryIO(it), stub_mapper, "k"), buffer_size=CHUNK)
        out: list = []
        while not out or out[-1] != b"":
            try:
                out.append(s.read(CHUNK))
            except BaseException as e:  # noqa: BLE001
                out.append(type(e).__name__)
        got = b"".join(x for x in out if isinstance(x, bytes))
        print(f"  {type(exc).__name__}: {out}")
        print(f"    delivered {len(got)} of {len(CONTENT)} bytes; a prefix of the content: {CONTENT.startswith(got)}")


if __name__ == "__main__":
    part1()
    part2()
