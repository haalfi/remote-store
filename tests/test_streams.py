"""Tests for ext.streams — stream-level wrappers for progress and checksums.

Spec: sdd/specs/033-ext-streams.md
"""

from __future__ import annotations

import hashlib
import io

import pytest

from remote_store._store import Store
from remote_store.ext.streams import (
    ChecksumReader,
    ChecksumWriter,
    ProgressReader,
    ProgressWriter,
    read_with_progress,
)


def _src(data: bytes) -> io.BytesIO:
    return io.BytesIO(data)


_H = hashlib.sha256


# ---------------------------------------------------------------------------
# STR-001 / STR-002: Progress wrappers
# ---------------------------------------------------------------------------


class TestProgressCallbacks:
    @pytest.mark.spec("STR-001")
    @pytest.mark.parametrize(
        ("data", "read_sizes", "expected_chunks"),
        [
            pytest.param(b"hello world", [5], [5], id="single-read"),
            pytest.param(b"", [-1], [], id="empty-no-callback"),
            pytest.param(b"abcdef", [3, 3, 1], [3, 3], id="multiple-reads"),
        ],
    )
    def test_reader_callbacks(self, data: bytes, read_sizes: list[int], expected_chunks: list[int]) -> None:
        chunks: list[int] = []
        s = ProgressReader(_src(data), callback=chunks.append)
        for size in read_sizes:
            s.read(size) if size > 0 else s.read()
        assert chunks == expected_chunks

    @pytest.mark.spec("STR-002")
    @pytest.mark.parametrize(
        ("data", "expected_chunks"),
        [
            pytest.param(b"hello", [5], id="write-fires-callback"),
            pytest.param(b"", [], id="empty-no-callback"),
        ],
    )
    def test_writer_callbacks(self, data: bytes, expected_chunks: list[int]) -> None:
        chunks: list[int] = []
        inner = io.BytesIO()
        ProgressWriter(inner, callback=chunks.append).write(data)
        assert chunks == expected_chunks
        if data:
            assert inner.getvalue() == data

    @pytest.mark.spec("STR-001")
    def test_reader_delegates_attributes(self) -> None:
        inner = _src(b"data")
        assert ProgressReader(inner, callback=lambda _: None).seekable() == inner.seekable()


# ---------------------------------------------------------------------------
# STR-003 / STR-004: Checksum wrappers
# ---------------------------------------------------------------------------


class TestChecksumComputation:
    @pytest.mark.spec("STR-003")
    @pytest.mark.parametrize(
        ("data", "chunk_sizes", "label"),
        [
            pytest.param(b"hello world", [-1], "reader-full", id="reader-full"),
            pytest.param(b"abcdefghij", [5, 5], "reader-incremental", id="reader-incremental"),
        ],
    )
    def test_reader_sha256(self, data: bytes, chunk_sizes: list[int], label: str) -> None:
        s = ChecksumReader(_src(data))
        for size in chunk_sizes:
            s.read(size) if size > 0 else s.read()
        assert s.hexdigest() == _H(data).hexdigest()

    @pytest.mark.spec("STR-003")
    def test_reader_default_algorithm(self) -> None:
        assert ChecksumReader(_src(b"")).algorithm == "sha256"

    @pytest.mark.spec("STR-003")
    def test_reader_delegates_attributes(self) -> None:
        inner = _src(b"data")
        assert ChecksumReader(inner).seekable() == inner.seekable()

    @pytest.mark.spec("STR-004")
    @pytest.mark.parametrize(
        ("chunks", "expected"),
        [
            pytest.param([b"hello world"], b"hello world", id="writer-full"),
            pytest.param([b"abc", b"de"], b"abcde", id="writer-incremental"),
        ],
    )
    def test_writer_sha256(self, chunks: list[bytes], expected: bytes) -> None:
        inner = io.BytesIO()
        w = ChecksumWriter(inner)
        for chunk in chunks:
            w.write(chunk)
        assert w.hexdigest() == _H(expected).hexdigest()
        assert inner.getvalue() == expected

    @pytest.mark.parametrize(
        ("cls", "make_inner", "action"),
        [
            pytest.param(ChecksumReader, lambda: _src(b"test"), lambda s: s.read(), id="reader-md5"),
            pytest.param(ChecksumWriter, io.BytesIO, lambda s: s.write(b"test"), id="writer-md5"),
        ],
    )
    def test_custom_algorithm(self, cls, make_inner, action) -> None:
        s = cls(make_inner(), algorithm="md5")
        action(s)
        assert s.algorithm == "md5"
        assert s.hexdigest() == hashlib.md5(b"test").hexdigest()  # noqa: S324

    @pytest.mark.spec("STR-003")
    def test_reader_algorithm_normalized(self) -> None:
        assert ChecksumReader(_src(b""), algorithm="SHA256").algorithm == "sha256"

    @pytest.mark.parametrize(
        ("cls", "inner"),
        [
            pytest.param(ChecksumReader, lambda: _src(b""), id="reader"),
            pytest.param(ChecksumWriter, io.BytesIO, id="writer"),
        ],
    )
    def test_unsupported_algorithm(self, cls, inner) -> None:
        with pytest.raises(ValueError):  # noqa: PT011
            cls(inner(), algorithm="not_a_hash")

    @pytest.mark.spec("STR-003")
    @pytest.mark.parametrize(
        ("data", "action", "extra"),
        [
            pytest.param(b"line1\nline2\n", lambda s: (s.readline(), s.readline()), None, id="readline"),
            pytest.param(b"line1\nline2\nline3\n", lambda s: s.readlines(), lambda r: len(r) == 3, id="readlines"),
            pytest.param(b"abc\ndef", lambda s: (s.readline(), s.read()), None, id="mixed"),
        ],
    )
    def test_read_method_feeds_hash(self, data, action, extra) -> None:
        s = ChecksumReader(_src(data))
        result = action(s)
        assert s.hexdigest() == _H(data).hexdigest()
        if extra:
            assert extra(result)


# ---------------------------------------------------------------------------
# Context managers for all wrapper types
# ---------------------------------------------------------------------------


class TestContextManagers:
    @staticmethod
    def _check_closes(cls, make_inner, action, **kwargs) -> None:
        inner = make_inner()
        with cls(inner, **kwargs) as s:
            action(s)
        assert inner.closed

    @pytest.mark.spec("STR-001")
    def test_progress_reader_closes(self) -> None:
        self._check_closes(ProgressReader, lambda: _src(b"data"), lambda s: s.read(), callback=lambda _: None)

    @pytest.mark.spec("STR-002")
    def test_progress_writer_closes(self) -> None:
        self._check_closes(ProgressWriter, io.BytesIO, lambda s: s.write(b"data"), callback=lambda _: None)

    @pytest.mark.spec("STR-003")
    def test_checksum_reader_closes(self) -> None:
        self._check_closes(ChecksumReader, lambda: _src(b"data"), lambda s: s.read())

    @pytest.mark.spec("STR-004")
    def test_checksum_writer_closes(self) -> None:
        self._check_closes(ChecksumWriter, io.BytesIO, lambda s: s.write(b"data"))


# ---------------------------------------------------------------------------
# STR-005 / STR-006 / STR-007: Integration and exports
# ---------------------------------------------------------------------------


class TestIntegrationAndExports:
    @pytest.mark.spec("STR-005")
    def test_read_with_progress(self, tmp_path: object) -> None:
        from remote_store.backends._memory import MemoryBackend

        store = Store(MemoryBackend())
        store.write("test.txt", b"hello world", overwrite=True)
        chunks: list[int] = []
        stream = read_with_progress(store, "test.txt", callback=chunks.append)
        assert isinstance(stream, ProgressReader)
        data = stream.read()
        stream.close()
        assert data == b"hello world"
        assert chunks == [11]

    @pytest.mark.spec("STR-006")
    def test_composition(self) -> None:
        data = b"composable streams"
        chunks: list[int] = []
        s = ChecksumReader(ProgressReader(_src(data), callback=chunks.append), algorithm="sha256")
        assert s.read() == data
        assert s.hexdigest() == _H(data).hexdigest()
        assert chunks == [len(data)]

    @pytest.mark.spec("STR-007")
    def test_all_exports(self) -> None:
        from remote_store.ext import streams

        assert set(streams.__all__) == {
            "ChecksumReader",
            "ChecksumWriter",
            "ProgressReader",
            "ProgressWriter",
            "read_with_progress",
        }

    @pytest.mark.spec("STR-007")
    def test_top_level_import(self) -> None:
        import remote_store

        assert hasattr(remote_store, "ProgressReader")
        assert hasattr(remote_store, "ChecksumReader")
