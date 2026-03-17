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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stream(data: bytes) -> io.BytesIO:
    return io.BytesIO(data)


# ---------------------------------------------------------------------------
# STR-001: ProgressReader
# ---------------------------------------------------------------------------


class TestProgressReader:
    @pytest.mark.spec("STR-001")
    def test_fires_callback_on_read(self) -> None:
        chunks: list[int] = []
        stream = ProgressReader(_make_stream(b"hello world"), callback=chunks.append)
        data = stream.read(5)
        assert data == b"hello"
        assert chunks == [5]

    @pytest.mark.spec("STR-001")
    def test_no_callback_on_empty_read(self) -> None:
        chunks: list[int] = []
        stream = ProgressReader(_make_stream(b""), callback=chunks.append)
        data = stream.read()
        assert data == b""
        assert chunks == []

    @pytest.mark.spec("STR-001")
    def test_multiple_reads(self) -> None:
        chunks: list[int] = []
        stream = ProgressReader(_make_stream(b"abcdef"), callback=chunks.append)
        stream.read(3)
        stream.read(3)
        stream.read(1)  # EOF — empty
        assert chunks == [3, 3]

    @pytest.mark.spec("STR-001")
    def test_context_manager(self) -> None:
        inner = _make_stream(b"data")
        with ProgressReader(inner, callback=lambda _: None) as stream:
            assert stream.read() == b"data"
        assert inner.closed

    @pytest.mark.spec("STR-001")
    def test_delegates_attributes(self) -> None:
        inner = _make_stream(b"data")
        stream = ProgressReader(inner, callback=lambda _: None)
        assert stream.seekable() == inner.seekable()


# ---------------------------------------------------------------------------
# STR-002: ProgressWriter
# ---------------------------------------------------------------------------


class TestProgressWriter:
    @pytest.mark.spec("STR-002")
    def test_fires_callback_on_write(self) -> None:
        chunks: list[int] = []
        inner = io.BytesIO()
        writer = ProgressWriter(inner, callback=chunks.append)
        writer.write(b"hello")
        assert chunks == [5]
        assert inner.getvalue() == b"hello"

    @pytest.mark.spec("STR-002")
    def test_no_callback_on_empty_write(self) -> None:
        chunks: list[int] = []
        writer = ProgressWriter(io.BytesIO(), callback=chunks.append)
        writer.write(b"")
        assert chunks == []

    @pytest.mark.spec("STR-002")
    def test_context_manager(self) -> None:
        inner = io.BytesIO()
        with ProgressWriter(inner, callback=lambda _: None) as writer:
            writer.write(b"data")
        assert inner.closed


# ---------------------------------------------------------------------------
# STR-003: ChecksumReader
# ---------------------------------------------------------------------------


class TestChecksumReader:
    @pytest.mark.spec("STR-003")
    def test_computes_sha256(self) -> None:
        data = b"hello world"
        expected = hashlib.sha256(data).hexdigest()
        stream = ChecksumReader(_make_stream(data))
        stream.read()
        assert stream.hexdigest() == expected

    @pytest.mark.spec("STR-003")
    def test_default_algorithm(self) -> None:
        stream = ChecksumReader(_make_stream(b""))
        assert stream.algorithm == "sha256"

    @pytest.mark.spec("STR-003")
    def test_custom_algorithm(self) -> None:
        data = b"test"
        expected = hashlib.md5(data).hexdigest()  # noqa: S324
        stream = ChecksumReader(_make_stream(data), algorithm="md5")
        stream.read()
        assert stream.algorithm == "md5"
        assert stream.hexdigest() == expected

    @pytest.mark.spec("STR-003")
    def test_algorithm_normalized_lowercase(self) -> None:
        stream = ChecksumReader(_make_stream(b""), algorithm="SHA256")
        assert stream.algorithm == "sha256"

    @pytest.mark.spec("STR-003")
    def test_incremental_reads(self) -> None:
        data = b"abcdefghij"
        expected = hashlib.sha256(data).hexdigest()
        stream = ChecksumReader(_make_stream(data))
        stream.read(5)
        stream.read(5)
        assert stream.hexdigest() == expected

    @pytest.mark.spec("STR-003")
    def test_context_manager(self) -> None:
        inner = _make_stream(b"data")
        with ChecksumReader(inner) as stream:
            stream.read()
        assert inner.closed

    @pytest.mark.spec("STR-003")
    def test_delegates_attributes(self) -> None:
        inner = _make_stream(b"data")
        stream = ChecksumReader(inner)
        assert stream.seekable() == inner.seekable()


# ---------------------------------------------------------------------------
# STR-004: ChecksumWriter
# ---------------------------------------------------------------------------


class TestChecksumWriter:
    @pytest.mark.spec("STR-004")
    def test_computes_sha256(self) -> None:
        data = b"hello world"
        expected = hashlib.sha256(data).hexdigest()
        inner = io.BytesIO()
        writer = ChecksumWriter(inner)
        writer.write(data)
        assert writer.hexdigest() == expected
        assert inner.getvalue() == data

    @pytest.mark.spec("STR-004")
    def test_custom_algorithm(self) -> None:
        data = b"test"
        expected = hashlib.md5(data).hexdigest()  # noqa: S324
        writer = ChecksumWriter(io.BytesIO(), algorithm="md5")
        writer.write(data)
        assert writer.algorithm == "md5"
        assert writer.hexdigest() == expected

    @pytest.mark.spec("STR-004")
    def test_incremental_writes(self) -> None:
        expected = hashlib.sha256(b"abcde").hexdigest()
        writer = ChecksumWriter(io.BytesIO())
        writer.write(b"abc")
        writer.write(b"de")
        assert writer.hexdigest() == expected

    @pytest.mark.spec("STR-004")
    def test_context_manager(self) -> None:
        inner = io.BytesIO()
        with ChecksumWriter(inner) as writer:
            writer.write(b"data")
        assert inner.closed


# ---------------------------------------------------------------------------
# STR-005: read_with_progress
# ---------------------------------------------------------------------------


class TestReadWithProgress:
    @pytest.mark.spec("STR-005")
    def test_returns_progress_reader(self, tmp_path: object) -> None:
        from remote_store.backends._memory import MemoryBackend

        backend = MemoryBackend()
        store = Store(backend)
        store.write("test.txt", b"hello world", overwrite=True)

        chunks: list[int] = []
        stream = read_with_progress(store, "test.txt", callback=chunks.append)
        assert isinstance(stream, ProgressReader)
        data = stream.read()
        stream.close()
        assert data == b"hello world"
        assert chunks == [11]


# ---------------------------------------------------------------------------
# STR-006: Composition
# ---------------------------------------------------------------------------


class TestComposition:
    @pytest.mark.spec("STR-006")
    def test_progress_and_checksum_compose(self) -> None:
        data = b"composable streams"
        expected = hashlib.sha256(data).hexdigest()
        chunks: list[int] = []

        stream = ChecksumReader(
            ProgressReader(_make_stream(data), callback=chunks.append),
            algorithm="sha256",
        )
        result = stream.read()
        assert result == data
        assert stream.hexdigest() == expected
        assert chunks == [len(data)]


# ---------------------------------------------------------------------------
# STR-007: Module exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    @pytest.mark.spec("STR-007")
    def test_all_exports(self) -> None:
        from remote_store.ext import streams

        expected = {"ChecksumReader", "ChecksumWriter", "ProgressReader", "ProgressWriter", "read_with_progress"}
        assert set(streams.__all__) == expected

    @pytest.mark.spec("STR-007")
    def test_top_level_import(self) -> None:
        import remote_store

        assert hasattr(remote_store, "ProgressReader")
        assert hasattr(remote_store, "ChecksumReader")
