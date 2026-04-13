"""Tests covering specific uncovered code paths in MemoryBackend (BK-006)."""

from __future__ import annotations

import concurrent.futures
import io

import pytest

from remote_store._errors import DirectoryNotEmpty, InvalidPath, NotFound
from remote_store.backends._memory import MemoryBackend


@pytest.fixture
def mb() -> MemoryBackend:
    return MemoryBackend()


# ---------------------------------------------------------------------------
# _split_path / _traverse / _ensure_parents validation
# ---------------------------------------------------------------------------


@pytest.mark.spec("MEM-DS-005")
@pytest.mark.parametrize(
    ("path", "match"),
    [
        pytest.param("a/\0b", "null byte", id="null_byte"),
        pytest.param("/root/file", "Absolute", id="absolute"),
        pytest.param("a/../b", "\\.\\.", id="dotdot"),
    ],
)
def test_split_path_validation(mb: MemoryBackend, path: str, match: str) -> None:
    with pytest.raises(InvalidPath, match=match):
        mb.exists(path)


@pytest.mark.spec("MEM-DS-005")
@pytest.mark.parametrize(
    "method",
    [
        pytest.param("exists", id="exists"),
        pytest.param("is_file", id="is_file"),
        pytest.param("is_folder", id="is_folder"),
    ],
)
def test_traverse_through_file_returns_false(mb: MemoryBackend, method: str) -> None:
    mb.write("a/b", b"data")
    assert getattr(mb, method)("a/b/c") is False


@pytest.mark.spec("MEM-DS-005")
def test_file_blocks_intermediate_directory(mb: MemoryBackend) -> None:
    mb.write("a/b", b"data")
    with pytest.raises(InvalidPath, match="exists as a file"):
        mb.write("a/b/c/d", b"nested")


# ---------------------------------------------------------------------------
# is_file / write / delete empty/root path rejection
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-005")
@pytest.mark.parametrize("path", ["", "."], ids=["empty", "dot"])
def test_is_file_root(mb: MemoryBackend, path: str) -> None:
    assert mb.is_file(path) is False


@pytest.mark.spec("MEM-012")
@pytest.mark.parametrize(
    "args",
    [pytest.param(("", b"data"), id="empty"), pytest.param((".", b"data"), id="dot")],
)
def test_write_empty_path_rejected(mb: MemoryBackend, args: tuple) -> None:
    with pytest.raises(InvalidPath, match="must not be empty"):
        mb.write(*args)


@pytest.mark.spec("BE-012")
def test_delete_empty_path_rejected(mb: MemoryBackend) -> None:
    with pytest.raises(InvalidPath, match="must not be empty"):
        mb.delete("")


@pytest.mark.spec("MEM-014")
def test_delete_folder_empty_path_rejected(mb: MemoryBackend) -> None:
    with pytest.raises(InvalidPath, match="must not be empty"):
        mb.delete_folder("")


@pytest.mark.spec("MEM-012")
@pytest.mark.parametrize(
    ("label", "data", "expected"),
    [
        pytest.param("directory", b"overwrite-dir", None, id="over_directory"),
        pytest.param("binaryio", io.BytesIO(b"streamed"), b"streamed", id="binaryio"),
    ],
)
def test_write_special_cases(mb: MemoryBackend, label: str, data: bytes, expected: bytes | None) -> None:
    if label == "directory":
        mb.write("a/b/c", b"file-under-b")
        with pytest.raises(InvalidPath, match="exists as a directory"):
            mb.write("a/b", data)
    else:
        mb.write("file.txt", data)
        assert mb.read_bytes("file.txt") == expected


# ---------------------------------------------------------------------------
# delete_folder edge cases
# ---------------------------------------------------------------------------


@pytest.mark.spec("MEM-014")
@pytest.mark.parametrize(
    ("missing_ok", "expect_raise"),
    [
        pytest.param(False, True, id="raises"),
        pytest.param(True, False, id="missing_ok"),
    ],
)
def test_delete_folder_parent_is_file(mb: MemoryBackend, missing_ok: bool, expect_raise: bool) -> None:
    mb.write("a/b", b"data")
    if expect_raise:
        with pytest.raises(NotFound, match="Folder not found"):
            mb.delete_folder("a/b/sub", missing_ok=missing_ok)
    else:
        mb.delete_folder("a/b/sub", missing_ok=missing_ok)


@pytest.mark.spec("MEM-014")
def test_delete_folder_non_recursive_non_empty(mb: MemoryBackend) -> None:
    mb.write("a/b/c", b"data")
    with pytest.raises(DirectoryNotEmpty, match="not empty"):
        mb.delete_folder("a/b", recursive=False)


# ---------------------------------------------------------------------------
# get_file_info / get_folder_info
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-016")
def test_get_file_info_empty_path(mb: MemoryBackend) -> None:
    with pytest.raises(NotFound, match="empty path"):
        mb.get_file_info("")


@pytest.mark.spec("MEM-015")
def test_get_folder_info_with_nested_subdirectories(mb: MemoryBackend) -> None:
    mb.write("a/b/c", b"deep")
    mb.write("a/d", b"shallow")
    info = mb.get_folder_info("a")
    assert info.file_count == 2
    assert info.total_size == len(b"deep") + len(b"shallow")
    assert info.modified_at is not None


# ---------------------------------------------------------------------------
# move/copy empty paths and destination-is-directory
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("op", "src", "dst", "match"),
    [
        pytest.param("move", "", "dst", "Source path must not be empty", id="move_empty_src"),
        pytest.param("move", "src", "", "Destination path must not be empty", id="move_empty_dst"),
        pytest.param("copy", "", "dst", "Source path must not be empty", id="copy_empty_src"),
        pytest.param("copy", "src", "", "Destination path must not be empty", id="copy_empty_dst"),
    ],
)
def test_move_copy_empty_paths(mb: MemoryBackend, op: str, src: str, dst: str, match: str) -> None:
    with pytest.raises(InvalidPath, match=match):
        getattr(mb, op)(src, dst)


@pytest.mark.parametrize("op", [pytest.param("move", id="move"), pytest.param("copy", id="copy")])
def test_dst_is_directory(mb: MemoryBackend, op: str) -> None:
    mb.write("src", b"data")
    mb.write("dst/child", b"nested")
    with pytest.raises(InvalidPath, match="exists as a directory"):
        getattr(mb, op)("src", "dst")


# ---------------------------------------------------------------------------
# move same-path / source parent not DirNode
# ---------------------------------------------------------------------------


@pytest.mark.spec("MEM-016")
def test_move_same_path_exists(mb: MemoryBackend) -> None:
    mb.write("a/b", b"data")
    mb.move("a/b", "a/b")
    assert mb.read_bytes("a/b") == b"data"


@pytest.mark.spec("MEM-016")
def test_move_same_path_not_found(mb: MemoryBackend) -> None:
    with pytest.raises(NotFound, match="Source not found"):
        mb.move("missing", "missing")


@pytest.mark.spec("MEM-016")
def test_move_same_path_directory_raises_invalid_path(mb: MemoryBackend) -> None:
    mb.write("a/b/c", b"data")
    with pytest.raises(InvalidPath, match="Source is a directory"):
        mb.move("a/b", "a/b")


@pytest.mark.spec("MEM-016")
def test_move_source_parent_is_file(mb: MemoryBackend) -> None:
    mb.write("x", b"file")
    with pytest.raises(NotFound, match="Source not found"):
        mb.move("x/child", "dst")


# ---------------------------------------------------------------------------
# BK-123 M-3/M-4/M-5: listing correctness after lock-reduction refactor
# ---------------------------------------------------------------------------


class TestMemoryListingCorrectness:
    """BK-123 M-3/M-4/M-5: listing methods return correct results after refactor."""

    @pytest.mark.spec("BK-123")
    def test_list_files_non_recursive(self, mb: MemoryBackend) -> None:
        mb.write("top.txt", b"t")
        mb.write("sub/nested.txt", b"n")
        files = list(mb.list_files(""))
        names = {f.name for f in files}
        assert names == {"top.txt"}

    @pytest.mark.spec("BK-123")
    def test_list_files_recursive(self, mb: MemoryBackend) -> None:
        mb.write("a/1.txt", b"one")
        mb.write("a/b/2.txt", b"two")
        mb.write("a/b/c/3.txt", b"three")
        files = list(mb.list_files("a", recursive=True))
        names = {f.name for f in files}
        assert names == {"1.txt", "2.txt", "3.txt"}

    @pytest.mark.spec("BK-123")
    def test_list_folders(self, mb: MemoryBackend) -> None:
        mb.write("d1/a.txt", b"a")
        mb.write("d2/b.txt", b"b")
        mb.write("root.txt", b"r")
        folders = list(mb.list_folders(""))
        names = {f.name for f in folders}
        assert names == {"d1", "d2"}

    @pytest.mark.spec("BK-123")
    def test_iter_children_mixed(self, mb: MemoryBackend) -> None:
        mb.write("file.txt", b"f")
        mb.write("dir/child.txt", b"c")
        children = list(mb.iter_children(""))
        names = {c.name for c in children}
        assert names == {"file.txt", "dir"}
        assert len(children) == 2

    @pytest.mark.spec("BK-123")
    def test_list_files_empty_dir(self, mb: MemoryBackend) -> None:
        """Listing a non-existent path yields nothing (no error)."""
        files = list(mb.list_files("nonexistent"))
        assert files == []

    @pytest.mark.spec("BK-006")
    def test_open_atomic_empty_path_raises_invalid_path(self, mb: MemoryBackend) -> None:
        """open_atomic('') raises InvalidPath — empty path is invalid for file ops."""
        with pytest.raises(InvalidPath, match="empty"), mb.open_atomic(""):
            pass

    @pytest.mark.spec("BK-123")
    def test_concurrent_write_and_listing_no_deadlock(self, mb: MemoryBackend) -> None:
        """Concurrent writes + listings must not deadlock."""

        mb.write("init.txt", b"seed")

        errors: list[Exception] = []

        def writer(idx: int) -> None:
            try:
                for i in range(20):
                    mb.write(f"w{idx}_{i}.txt", f"data-{i}".encode(), overwrite=True)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(20):
                    list(mb.list_files("", recursive=True))
                    list(mb.list_folders(""))
                    list(mb.iter_children(""))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(writer, i) for i in range(3)]
            futures += [pool.submit(reader) for _ in range(3)]
            # 10-second timeout to detect deadlocks
            concurrent.futures.wait(futures, timeout=10)
            for f in futures:
                if not f.done():
                    pytest.fail("Deadlock detected: thread did not complete within 10s")
        assert not errors, f"Concurrent operations raised: {errors}"


# ---------------------------------------------------------------------------
# BK-123 M-6: write with stream (double-copy elimination)
# ---------------------------------------------------------------------------


class TestMemoryWriteStream:
    """BK-123 M-6: write with BinaryIO stream produces correct content."""

    @pytest.mark.spec("BK-123")
    def test_write_bytesio_stream(self, mb: MemoryBackend) -> None:
        mb.write("stream.txt", io.BytesIO(b"streamed-content"))
        assert mb.read_bytes("stream.txt") == b"streamed-content"

    @pytest.mark.spec("BK-123")
    def test_write_large_stream_chunked(self, mb: MemoryBackend) -> None:
        """Large stream content is read in chunks and assembled correctly."""
        large_data = b"x" * 200_000
        mb.write("large.bin", io.BytesIO(large_data))
        result = mb.read_bytes("large.bin")
        assert len(result) == 200_000
        assert result == large_data

    @pytest.mark.spec("BK-123")
    def test_overwrite_with_stream(self, mb: MemoryBackend) -> None:
        mb.write("f.txt", b"original")
        mb.write("f.txt", io.BytesIO(b"replaced"), overwrite=True)
        assert mb.read_bytes("f.txt") == b"replaced"

    @pytest.mark.spec("BK-123")
    def test_write_empty_stream(self, mb: MemoryBackend) -> None:
        mb.write("empty.txt", io.BytesIO(b""))
        assert mb.read_bytes("empty.txt") == b""


# ---------------------------------------------------------------------------
# RES-056: MemoryBackend.resolve()
# ---------------------------------------------------------------------------


class TestMemoryBackendResolve:
    """RES-056: MemoryBackend uses default resolve(), kind='memory', empty details."""

    @pytest.mark.spec("RES-056")
    def test_kind_is_memory(self, mb: MemoryBackend) -> None:
        plan = mb.resolve("file.txt")
        assert plan.kind == "memory"

    @pytest.mark.spec("RES-056")
    def test_details_is_empty(self, mb: MemoryBackend) -> None:
        plan = mb.resolve("file.txt")
        assert len(plan.details) == 0


# ---------------------------------------------------------------------------
# MEM-010: concurrent read+write — no torn reads
# ---------------------------------------------------------------------------


class TestMemoryReadConcurrency:
    """MEM-010: read() lock scope covers the full byte-copy; readers see only whole payloads."""

    @pytest.mark.spec("MEM-010")
    def test_concurrent_read_write_no_torn_data(self, mb: MemoryBackend) -> None:
        """Concurrent readers and writers must not produce partial (torn) payloads.

        Writers overwrite the key alternating between two known payloads.
        Every completed read must return exactly one of those two payloads —
        never a mix of bytes from both.
        """
        payload_a = b"A" * 50_000
        payload_b = b"B" * 50_000
        valid = {payload_a, payload_b}

        mb.write("f.bin", payload_a)

        errors: list[Exception] = []
        bad_reads: list[bytes] = []

        def reader() -> None:
            try:
                for _ in range(50):
                    result = mb.read("f.bin").read()
                    if result not in valid:
                        bad_reads.append(result)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def writer() -> None:
            try:
                for i in range(50):
                    payload = payload_a if i % 2 == 0 else payload_b
                    mb.write("f.bin", payload, overwrite=True)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(reader) for _ in range(4)]
            futures += [pool.submit(writer) for _ in range(4)]
            concurrent.futures.wait(futures, timeout=30)
            for f in futures:
                if not f.done():
                    pytest.fail("Deadlock detected: thread did not complete within 30s")

        assert not errors, f"Concurrent operations raised: {errors}"
        assert not bad_reads, (
            f"Torn read detected: {len(bad_reads)} result(s) were neither payload_a nor payload_b. "
            f"First bad result length: {len(bad_reads[0])}"
        )
