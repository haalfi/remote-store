"""Extended conformance tests for the async backend contract.

Async sibling of the sync conformance topic files in this directory. The
``async_backend`` fixture is parametrised by the registry-driven hook in
``tests.backends.conformance.conftest`` over every registry entry whose
``is_async=True``.

Flat-namespace backends (S3, Azure Blob, HTTP, SQL-blob) have no real
directory entries and are excluded from error-fidelity tests by
``_skip_flat_namespace``. The current registry holds only hierarchical
async fixtures (``memory_async_native``, ``memory_async_adapted``,
``local_async_adapted``); the helper is preserved for the day a flat-NS
async backend is added.

Spec coverage: ASYNC-004, ASYNC-005, ASYNC-006, ASYNC-007, ASYNC-008,
ASYNC-010, ASYNC-012, ASYNC-013, ASYNC-014, ASYNC-015, ASYNC-016, ASYNC-017,
ASYNC-018, ASYNC-019, ASYNC-020, ASYNC-024 (mirroring BE-004..BE-021 and SIO-001).
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import (
    AlreadyExists,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    RemoteStoreError,
)
from tests.backends.conformance._helpers import _fixture_record

if TYPE_CHECKING:
    from remote_store.aio._async_backend import AsyncBackend


# ---------------------------------------------------------------------------
# Helpers (mirror tests/backends/test_conformance_extended.py)
# ---------------------------------------------------------------------------
#
# ``flat_namespace`` and ``self_op_supported`` come from the per-fixture
# ``BackendFixture`` record (attached by the indirect ``async_backend``
# fixture in ``tests/backends/conformance/conftest.py``). The previous
# file-local identity sets keyed by ``backend.name`` could not
# distinguish the Azurite emulator (flat) from live ADLS Gen2 (HNS) —
# closes BK-185.


def _require(backend: AsyncBackend, *caps: Capability) -> None:
    """Skip the test if the backend lacks any of the given capabilities.

    ``capabilities`` is a sync property on ``AsyncBackend``, so the same
    helper shape as the sync suite works without an ``await``.
    """
    for cap in caps:
        if not backend.capabilities.supports(cap):
            pytest.skip(f"Backend does not support {cap.name}")


async def _seed(backend: AsyncBackend, files: dict[str, bytes]) -> None:
    """Write multiple files into the backend."""
    for path, data in files.items():
        await backend.write(path, data)


def _skip_flat_namespace(backend: AsyncBackend, reason: str = "flat-namespace backend") -> None:
    """Skip test for backends without real directory entries."""
    if _fixture_record(backend).flat_namespace:
        pytest.skip(reason)


async def _do_op(backend: AsyncBackend, op: str, src: str, dst: str, **kw: Any) -> None:
    await getattr(backend, op)(src, dst, **kw)


async def _drain_read(backend: AsyncBackend, path: str) -> bytes:
    """Pull every chunk from ``backend.read(path)`` and return the joined bytes.

    ``read()`` is an async generator: errors from the body (NotFound,
    InvalidPath) surface on the first ``__anext__``, not on the call itself,
    so tests that assert on those errors must drive the iterator.
    """
    chunks: list[bytes] = []
    async for chunk in backend.read(path):
        chunks.append(chunk)
    return b"".join(chunks)


_MOVE_COPY_PARAMS = [
    pytest.param("move", Capability.MOVE, id="move"),
    pytest.param("copy", Capability.COPY, id="copy"),
]

pytestmark = pytest.mark.extended_conformance

# ``async_backend`` is parametrised by the registry-driven hook in
# ``tests/backends/conformance/conftest.py``; the legacy local fixture
# override (native-memory / adapted-memory / adapted-local) is replaced
# by the registry entries memory_async_native, memory_async_adapted, and
# local_async_adapted; see tests/backends/fixtures/{memory_async,
# local_async}.py.


# ===========================================================================
# §1  Error Fidelity: Dafny §6 postconditions on error paths
# ===========================================================================


class TestReadErrorFidelity:
    """ASYNC-006/007 (mirrors BE-006/007): dir->InvalidPath, missing->NotFound."""

    @pytest.mark.spec("ASYNC-006")
    async def test_read_on_directory_raises_error(self, async_backend: AsyncBackend) -> None:
        """Read(dir) ==> InvalidPath. Flat-NS backends have no real dirs."""
        _require(async_backend, Capability.WRITE)
        _skip_flat_namespace(async_backend)
        await async_backend.write("rdir/file.txt", b"x")
        with pytest.raises(InvalidPath, match="rdir"):
            await _drain_read(async_backend, "rdir")

    @pytest.mark.spec("ASYNC-007")
    async def test_read_bytes_on_directory_raises_error(self, async_backend: AsyncBackend) -> None:
        """read_bytes(dir): same contract as read()."""
        _require(async_backend, Capability.WRITE)
        _skip_flat_namespace(async_backend)
        await async_backend.write("rbdir/file.txt", b"x")
        with pytest.raises(InvalidPath, match="rbdir"):
            await async_backend.read_bytes("rbdir")

    @pytest.mark.spec("ASYNC-006")
    async def test_read_missing_raises_not_found(self, async_backend: AsyncBackend) -> None:
        """!PathExists ==> NotFound."""
        with pytest.raises(NotFound, match="ec_missing_read"):
            await _drain_read(async_backend, "ec_missing_read.txt")

    @pytest.mark.spec("ASYNC-007")
    async def test_read_bytes_missing_raises_not_found(self, async_backend: AsyncBackend) -> None:
        with pytest.raises(NotFound, match="ec_missing_rb"):
            await async_backend.read_bytes("ec_missing_rb.txt")


class TestWriteErrorFidelity:
    """ASYNC-008 / ASYNC-010 (mirrors BE-008 / BE-010).

    write(dir) and write_atomic(dir) ==> InvalidPath unconditionally.
    The dir check must fire BEFORE the overwrite check; ``write_atomic``
    shares BE-008 precondition order via BE-010.
    """

    @pytest.mark.parametrize(
        ("method", "overwrite"),
        [
            pytest.param("write", False, id="write-no-overwrite", marks=pytest.mark.spec("ASYNC-008")),
            pytest.param("write", True, id="write-overwrite", marks=pytest.mark.spec("ASYNC-008")),
            pytest.param("write_atomic", False, id="write_atomic-no-overwrite", marks=pytest.mark.spec("ASYNC-010")),
            pytest.param("write_atomic", True, id="write_atomic-overwrite", marks=pytest.mark.spec("ASYNC-010")),
        ],
    )
    async def test_write_on_directory_raises_error(
        self, async_backend: AsyncBackend, method: str, overwrite: bool
    ) -> None:
        """IsDir(path) ==> InvalidPath (NOT AlreadyExists), regardless of ``overwrite``."""
        _require(async_backend, Capability.WRITE)
        if method == "write_atomic":
            _require(async_backend, Capability.ATOMIC_WRITE)
        _skip_flat_namespace(async_backend)
        dir_path = f"wdir_{method}_{int(overwrite)}"
        await async_backend.write(f"{dir_path}/file.txt", b"x")
        with pytest.raises(InvalidPath, match=dir_path):
            await getattr(async_backend, method)(dir_path, b"data", overwrite=overwrite)


@pytest.mark.spec("ASYNC-012")
class TestDeleteErrorFidelity:
    """``delete(dir_path)`` raises ``InvalidPath`` regardless of ``missing_ok``.

    Mirrors ``test_conformance_extended.py::TestDeleteErrorFidelity``.
    The ``missing_ok`` flag tolerates a *missing file*, not a type mismatch.
    A directory path must raise ``InvalidPath`` unconditionally (BE-012,
    Dafny: ``Delete: IsDir -> InvalidPath`` unconditionally).
    """

    async def test_delete_on_directory_raises_invalid_path(self, async_backend: AsyncBackend) -> None:
        _require(async_backend, Capability.DELETE, Capability.WRITE)
        _skip_flat_namespace(async_backend)
        await async_backend.write("ddir/file.txt", b"x")
        with pytest.raises(InvalidPath, match="ddir"):
            await async_backend.delete("ddir")

    async def test_delete_on_directory_missing_ok_still_raises(self, async_backend: AsyncBackend) -> None:
        _require(async_backend, Capability.DELETE, Capability.WRITE)
        _skip_flat_namespace(async_backend)
        await async_backend.write("ddir2/file.txt", b"x")
        with pytest.raises(InvalidPath, match="ddir2"):
            await async_backend.delete("ddir2", missing_ok=True)
        assert await async_backend.exists("ddir2/file.txt"), "child silently deleted"


class TestDeleteFolderErrorFidelity:
    """ASYNC-013 (mirrors BE-013): delete_folder postconditions."""

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_on_file_raises_error(self, async_backend: AsyncBackend) -> None:
        """IsFile(path) ==> InvalidPath."""
        _require(async_backend, Capability.DELETE, Capability.WRITE)
        _skip_flat_namespace(async_backend, "flat-namespace backends cannot distinguish file vs folder")
        await async_backend.write("dffile.txt", b"x")
        with pytest.raises(InvalidPath, match="dffile"):
            await async_backend.delete_folder("dffile.txt")

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_on_file_missing_ok_still_raises(self, async_backend: AsyncBackend) -> None:
        """IsFile(path) && missing_ok ==> InvalidPath (type mismatch is not 'missing')."""
        _require(async_backend, Capability.DELETE, Capability.WRITE)
        _skip_flat_namespace(async_backend, "flat-namespace backends cannot distinguish file vs folder")
        await async_backend.write("dffile_mok.txt", b"x")
        with pytest.raises(InvalidPath, match="dffile_mok"):
            await async_backend.delete_folder("dffile_mok.txt", missing_ok=True)
        assert await async_backend.exists("dffile_mok.txt"), "file silently deleted under missing_ok=True"

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_on_file_no_native_leak(self, async_backend: AsyncBackend) -> None:
        """Flat-namespace backends: delete_folder(file) must not leak native exceptions."""
        _require(async_backend, Capability.DELETE, Capability.WRITE)
        if not _fixture_record(async_backend).flat_namespace:
            pytest.skip("hierarchical backend: covered by test_delete_folder_on_file_raises_error")
        await async_backend.write("dffile_flat.txt", b"x")
        with contextlib.suppress(RemoteStoreError):
            await async_backend.delete_folder("dffile_flat.txt")
        assert True  # explicit: survived without native exception leak

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_missing_raises_not_found(self, async_backend: AsyncBackend) -> None:
        """!PathExists && !missing_ok ==> NotFound."""
        _require(async_backend, Capability.DELETE)
        with pytest.raises(NotFound, match="ec_missing_df"):
            await async_backend.delete_folder("ec_missing_df", missing_ok=False)

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_missing_ok_passes(self, async_backend: AsyncBackend) -> None:
        """!PathExists && missing_ok ==> Ok (no error raised)."""
        _require(async_backend, Capability.DELETE)
        await async_backend.delete_folder("ec_missing_df_ok", missing_ok=True)
        assert not await async_backend.exists("ec_missing_df_ok")

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_non_recursive_non_empty_raises(self, async_backend: AsyncBackend) -> None:
        """IsDir && !recursive && HasChildren ==> DirectoryNotEmpty."""
        _require(async_backend, Capability.DELETE, Capability.WRITE)
        _skip_flat_namespace(async_backend)
        await _seed(async_backend, {"dne/a.txt": b"a"})
        with pytest.raises(DirectoryNotEmpty, match="dne"):
            await async_backend.delete_folder("dne", recursive=False)

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_recursive_removes_all(self, async_backend: AsyncBackend) -> None:
        """IsDir && recursive ==> Ok, all children removed."""
        _require(async_backend, Capability.DELETE, Capability.WRITE)
        await _seed(async_backend, {"dfr/a.txt": b"a", "dfr/sub/b.txt": b"b"})
        await async_backend.delete_folder("dfr", recursive=True)
        assert not await async_backend.exists("dfr/a.txt")
        assert not await async_backend.exists("dfr/sub/b.txt")
        assert not await async_backend.exists("dfr")


class TestGetFileInfoErrorFidelity:
    """ASYNC-016 (mirrors BE-016)."""

    @pytest.mark.spec("ASYNC-016")
    async def test_get_file_info_on_directory_raises_error(self, async_backend: AsyncBackend) -> None:
        """IsDir(path) ==> InvalidPath."""
        _require(async_backend, Capability.WRITE)
        _skip_flat_namespace(async_backend)
        await async_backend.write("gfid/file.txt", b"x")
        with pytest.raises(InvalidPath, match="gfid"):
            await async_backend.get_file_info("gfid")

    @pytest.mark.spec("ASYNC-016")
    async def test_get_file_info_missing_raises_not_found(self, async_backend: AsyncBackend) -> None:
        """!PathExists ==> NotFound."""
        with pytest.raises(NotFound, match="ec_missing_gfi"):
            await async_backend.get_file_info("ec_missing_gfi")


class TestGetFolderInfoErrorFidelity:
    """ASYNC-017 (mirrors BE-017)."""

    @pytest.mark.spec("ASYNC-017")
    async def test_get_folder_info_on_file_raises_error(self, async_backend: AsyncBackend) -> None:
        """IsFile(path) ==> InvalidPath."""
        _require(async_backend, Capability.WRITE)
        _skip_flat_namespace(async_backend)
        await async_backend.write("gfof.txt", b"x")
        with pytest.raises(InvalidPath, match="gfof"):
            await async_backend.get_folder_info("gfof.txt")

    @pytest.mark.spec("ASYNC-017")
    async def test_get_folder_info_missing_raises_not_found(self, async_backend: AsyncBackend) -> None:
        """!PathExists ==> NotFound."""
        with pytest.raises(NotFound, match="ec_missing_gfo"):
            await async_backend.get_folder_info("ec_missing_gfo")


class TestGetFolderInfoAggregates:
    """ASYNC-017 / ID-134: aggregate postconditions.

    Dafny: IsDir(path) ==>
      r.Ok?
      && r.value.file_count == |ChildFiles(fs, path)|
      && r.value.total_size == SumSizes(fs, ChildFiles(fs, path))
    """

    @pytest.mark.spec("ASYNC-017")
    @pytest.mark.spec("ID-134")
    async def test_get_folder_info_file_count_and_total_size(self, async_backend: AsyncBackend) -> None:
        """IsDir ==> file_count == |ChildFiles|, total_size == SumSizes."""
        _require(async_backend, Capability.WRITE)
        await _seed(async_backend, {"gfa/a.txt": b"aaa", "gfa/b.txt": b"bb"})
        fi = await async_backend.get_folder_info("gfa")
        assert fi.file_count == 2
        assert fi.total_size == 5

    @pytest.mark.spec("ASYNC-017")
    @pytest.mark.spec("ID-134")
    async def test_get_folder_info_counts_recursive_children(self, async_backend: AsyncBackend) -> None:
        """ChildFiles is the full recursive set: subdirectory files are counted."""
        _require(async_backend, Capability.WRITE)
        await _seed(async_backend, {"gfr/a.txt": b"aaa", "gfr/sub/b.txt": b"bb"})
        fi = await async_backend.get_folder_info("gfr")
        assert fi.file_count == 2
        assert fi.total_size == 5


# ===========================================================================
# §2  Listing: ASYNC-014 / ASYNC-015 postconditions
# ===========================================================================


class TestListFilesCompleteness:
    """ASYNC-014 (mirrors BE-014): every matching file MUST appear."""

    DEPTH_TREE: dict[str, bytes] = {
        "pc/a.txt": b"a",
        "pc/d1/b.txt": b"b",
        "pc/d1/c.txt": b"c",
        "pc/d1/d2/d.txt": b"d",
        "pc/d1/d2/d3/e.txt": b"e",
    }

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_non_recursive(self, async_backend: AsyncBackend) -> None:
        """recursive=false -> only immediate children (depth 0)."""
        _require(async_backend, Capability.LIST, Capability.WRITE)
        await _seed(async_backend, self.DEPTH_TREE)
        files = [f async for f in async_backend.list_files("pc", recursive=False)]
        assert {f.name for f in files} == {"a.txt"}

    @pytest.mark.spec("ASYNC-014")
    @pytest.mark.parametrize(
        ("max_depth", "expected_names"),
        [
            pytest.param(0, {"a.txt"}, id="depth0"),
            pytest.param(1, {"a.txt", "b.txt", "c.txt"}, id="depth1"),
            pytest.param(2, {"a.txt", "b.txt", "c.txt", "d.txt"}, id="depth2"),
            pytest.param(3, {"a.txt", "b.txt", "c.txt", "d.txt", "e.txt"}, id="depth3"),
        ],
    )
    async def test_list_files_recursive_max_depth(
        self, async_backend: AsyncBackend, max_depth: int, expected_names: set[str]
    ) -> None:
        """Depth filtering is inclusive (Dafny DepthFilterBoundaryInclusive)."""
        _require(async_backend, Capability.LIST, Capability.WRITE)
        await _seed(async_backend, self.DEPTH_TREE)
        files = [f async for f in async_backend.list_files("pc", recursive=True, max_depth=max_depth)]
        assert {f.name for f in files} == expected_names

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_unlimited_depth(self, async_backend: AsyncBackend) -> None:
        """max_depth=None -> all files returned."""
        _require(async_backend, Capability.LIST, Capability.WRITE)
        await _seed(async_backend, self.DEPTH_TREE)
        files = [f async for f in async_backend.list_files("pc", recursive=True)]
        assert {f.name for f in files} == {"a.txt", "b.txt", "c.txt", "d.txt", "e.txt"}

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_missing_path_yields_empty(self, async_backend: AsyncBackend) -> None:
        """Dafny: !PathExists ==> r.value == []. Never raises NotFound."""
        _require(async_backend, Capability.LIST)
        files = [f async for f in async_backend.list_files("ec_nonexistent_listing")]
        assert files == []

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_all_results_are_children(self, async_backend: AsyncBackend) -> None:
        """All returned files must be children of the listed path."""
        _require(async_backend, Capability.LIST, Capability.WRITE)
        await _seed(async_backend, {"lfc/a.txt": b"a", "lfc/sub/b.txt": b"b", "other/c.txt": b"c"})
        files = [f async for f in async_backend.list_files("lfc", recursive=True)]
        for f in files:
            assert str(f.path).startswith("lfc/"), f"Unexpected path: {f.path}"


class TestListFoldersCompleteness:
    """ASYNC-015 (mirrors BE-015): every immediate child dir MUST appear."""

    @pytest.mark.spec("ASYNC-015")
    async def test_list_folders_missing_path_yields_empty(self, async_backend: AsyncBackend) -> None:
        """Dafny: !PathExists ==> r.value == []. Never raises NotFound."""
        _require(async_backend, Capability.LIST)
        folders = [f async for f in async_backend.list_folders("ec_nonexistent_folders")]
        assert folders == []

    @pytest.mark.spec("ASYNC-015")
    async def test_list_folders_completeness(self, async_backend: AsyncBackend) -> None:
        """All immediate child directories appear."""
        _require(async_backend, Capability.LIST, Capability.WRITE)
        await _seed(
            async_backend,
            {
                "lfc2/s1/a.txt": b"a",
                "lfc2/s2/b.txt": b"b",
                "lfc2/s3/c.txt": b"c",
                "lfc2/top.txt": b"t",
            },
        )
        folders = [f async for f in async_backend.list_folders("lfc2")]
        assert {f.name for f in folders} == {"s1", "s2", "s3"}


# ===========================================================================
# §3  Move/Copy: ASYNC-018 / ASYNC-019 postconditions
# ===========================================================================


class TestMoveCopyErrorFidelity:
    """ASYNC-018 / ASYNC-019 (mirrors BE-018 / BE-019)."""

    @pytest.mark.spec("ASYNC-018")
    @pytest.mark.spec("ASYNC-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    async def test_source_is_directory_raises_error(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        """IsDir(src) ==> InvalidPath."""
        _require(async_backend, cap, Capability.WRITE)
        _skip_flat_namespace(async_backend)
        await async_backend.write(f"mcds/{op}/file.txt", b"x")
        with pytest.raises(InvalidPath, match=f"mcds/{op}(?!_dst)"):
            await _do_op(async_backend, op, f"mcds/{op}", f"mcds/{op}_dst.txt")

    @pytest.mark.spec("ASYNC-018")
    @pytest.mark.spec("ASYNC-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    async def test_destination_is_directory_raises_error(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        """IsFile(src) && IsDir(dst) ==> InvalidPath(dst)."""
        _require(async_backend, cap, Capability.WRITE)
        _skip_flat_namespace(async_backend)
        await async_backend.write(f"mcdd/{op}_src.txt", b"src")
        await async_backend.write(f"mcdd/{op}_dstdir/file.txt", b"x")
        # match= pinned to the dst-only fragment so a regression that flipped
        # the error to be about src would not silently pass.
        with pytest.raises(InvalidPath, match=f"mcdd/{op}_dstdir"):
            await _do_op(async_backend, op, f"mcdd/{op}_src.txt", f"mcdd/{op}_dstdir")

    @pytest.mark.spec("ASYNC-018")
    @pytest.mark.spec("ASYNC-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    async def test_source_missing_raises_not_found(self, async_backend: AsyncBackend, op: str, cap: Capability) -> None:
        """!PathExists(src) ==> NotFound(src)."""
        _require(async_backend, cap)
        with pytest.raises(NotFound, match="ec_mc_missing_src"):
            await _do_op(async_backend, op, "ec_mc_missing_src.txt", "ec_mc_dst.txt")


class TestMoveCopyOverwrite:
    """ASYNC-018 / ASYNC-019: overwrite semantics."""

    @pytest.mark.spec("ASYNC-018")
    @pytest.mark.spec("ASYNC-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    async def test_dst_exists_no_overwrite_raises_already_exists(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        """IsFile(dst) && !overwrite && src != dst ==> AlreadyExists(dst)."""
        _require(async_backend, cap, Capability.WRITE)
        await _seed(async_backend, {f"mcow/{op}_s.txt": b"s", f"mcow/{op}_d.txt": b"d"})
        with pytest.raises(AlreadyExists, match=f"mcow/{op}_d"):
            await _do_op(async_backend, op, f"mcow/{op}_s.txt", f"mcow/{op}_d.txt", overwrite=False)

    @pytest.mark.spec("ASYNC-018")
    @pytest.mark.spec("ASYNC-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    async def test_overwrite_replaces_destination(self, async_backend: AsyncBackend, op: str, cap: Capability) -> None:
        """overwrite=True -> dst gets src content."""
        _require(async_backend, cap, Capability.WRITE)
        await _seed(async_backend, {f"mcor/{op}_s.txt": b"new", f"mcor/{op}_d.txt": b"old"})
        await _do_op(async_backend, op, f"mcor/{op}_s.txt", f"mcor/{op}_d.txt", overwrite=True)
        assert await async_backend.read_bytes(f"mcor/{op}_d.txt") == b"new"


class TestMoveCopySelfOperation:
    """ASYNC-047 / BE-018 / BE-019: self-move/self-copy must not lose data."""

    @pytest.mark.spec("ASYNC-018")
    @pytest.mark.spec("ASYNC-019")
    @pytest.mark.spec("ASYNC-047")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    @pytest.mark.parametrize("overwrite", [True, False], ids=["overwrite", "no-overwrite"])
    async def test_self_op_preserves_data(
        self, async_backend: AsyncBackend, op: str, cap: Capability, overwrite: bool
    ) -> None:
        """{move,copy}(src, src, overwrite={True,False}) is a no-op: source content preserved."""
        _require(async_backend, cap, Capability.WRITE)
        if not _fixture_record(async_backend).self_op_supported:
            pytest.skip(f"Backend {async_backend.name!r} does not handle self-{op} yet")
        path = f"self_{op}_ow{overwrite}.txt"
        await async_backend.write(path, b"data")
        await _do_op(async_backend, op, path, path, overwrite=overwrite)
        assert await async_backend.read_bytes(path) == b"data"

    @pytest.mark.spec("ASYNC-018")
    @pytest.mark.spec("ASYNC-019")
    @pytest.mark.spec("ASYNC-047")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    async def test_self_op_missing_raises_not_found(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        """{move,copy}(src, src) where src does not exist raises NotFound."""
        _require(async_backend, cap)
        if not _fixture_record(async_backend).self_op_supported:
            pytest.skip(f"Backend {async_backend.name!r} does not handle self-{op} yet")
        path = f"sm_{op}_missing.txt"
        with pytest.raises(NotFound, match=f"sm_{op}_missing"):
            await _do_op(async_backend, op, path, path)

    @pytest.mark.spec("ASYNC-018")
    @pytest.mark.spec("ASYNC-019")
    @pytest.mark.spec("ASYNC-047")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    async def test_self_op_on_directory_raises_invalid_path(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        """{move,copy}(src, src) where src is a directory raises InvalidPath (BE-021)."""
        _require(async_backend, cap)
        if not _fixture_record(async_backend).self_op_supported:
            pytest.skip(f"Backend {async_backend.name!r} does not handle self-{op} yet")
        _skip_flat_namespace(async_backend, "flat-namespace backends cannot distinguish file vs folder")
        await async_backend.write(f"sd_{op}/file.txt", b"x")
        with pytest.raises(InvalidPath, match=f"sd_{op}"):
            await _do_op(async_backend, op, f"sd_{op}", f"sd_{op}")


class TestMovePostState:
    """ASYNC-018: src removed, dst has src content."""

    @pytest.mark.spec("ASYNC-018")
    async def test_move_removes_source(self, async_backend: AsyncBackend) -> None:
        """src != dst ==> !PathExists(fs, src)."""
        _require(async_backend, Capability.MOVE, Capability.WRITE)
        await async_backend.write("mvps_src.txt", b"data")
        await async_backend.move("mvps_src.txt", "mvps_dst.txt")
        assert not await async_backend.exists("mvps_src.txt")
        assert await async_backend.read_bytes("mvps_dst.txt") == b"data"


class TestCopyPostState:
    """ASYNC-019: src unchanged, dst has src content."""

    @pytest.mark.spec("ASYNC-019")
    async def test_copy_preserves_source(self, async_backend: AsyncBackend) -> None:
        """IsFile(fs, src): source still exists after copy."""
        _require(async_backend, Capability.COPY, Capability.WRITE)
        await async_backend.write("cpps_src.txt", b"data")
        await async_backend.copy("cpps_src.txt", "cpps_dst.txt")
        assert await async_backend.read_bytes("cpps_src.txt") == b"data"
        assert await async_backend.read_bytes("cpps_dst.txt") == b"data"


# ===========================================================================
# §4  Write-Read round-trip: mirrors WriteReadConsistency lemma
# ===========================================================================


class TestWriteReadRoundTrip:
    """Write then read: content must match exactly."""

    @pytest.mark.spec("ASYNC-007")
    @pytest.mark.spec("ASYNC-008")
    @pytest.mark.parametrize(
        "content",
        [
            pytest.param(b"", id="empty"),
            pytest.param(b"\x00\x01\x02\xff", id="binary"),
            pytest.param(b"hello world", id="text"),
            pytest.param(b"x" * 10_000, id="large"),
        ],
    )
    async def test_roundtrip(self, async_backend: AsyncBackend, content: bytes) -> None:
        _require(async_backend, Capability.WRITE)
        await async_backend.write("ec_rt.bin", content, overwrite=True)
        assert await async_backend.read_bytes("ec_rt.bin") == content


# ===========================================================================
# §5  Streaming-read consumption: ASYNC-020 (async analogue of SIO-001)
# ===========================================================================


class TestAsyncReadStream:
    """ASYNC-006 / ASYNC-020: async iterator drains correctly and closes cleanly.

    The sync suite tests ``stream.close()`` / ``with`` / double-close on a
    ``BinaryIO``. The async contract returns ``AsyncIterator[bytes]`` (no
    ``close``/``closed`` protocol); the equivalent invariants are:

    1. The iterator yields the full content joined back to the original bytes.
    2. ``aclose()`` on a partially consumed async generator is safe.
    3. ``contextlib.aclosing()`` wraps the iterator without raising.
    """

    @pytest.mark.spec("ASYNC-006")
    @pytest.mark.spec("ASYNC-020")
    async def test_read_stream_drains_full_content(self, async_backend: AsyncBackend) -> None:
        """``async for`` over ``read()`` reproduces the written bytes."""
        _require(async_backend, Capability.WRITE)
        await async_backend.write("ec_rc.txt", b"data")
        assert await _drain_read(async_backend, "ec_rc.txt") == b"data"

    @pytest.mark.spec("ASYNC-006")
    @pytest.mark.spec("ASYNC-020")
    async def test_read_stream_aclosing_context_manager(self, async_backend: AsyncBackend) -> None:
        """``contextlib.aclosing()`` closes the iterator without raising."""
        _require(async_backend, Capability.WRITE)
        await async_backend.write("ec_rcm.txt", b"data")
        async with contextlib.aclosing(async_backend.read("ec_rcm.txt")) as stream:
            collected = b"".join([chunk async for chunk in stream])
        assert collected == b"data"

    @pytest.mark.spec("ASYNC-006")
    @pytest.mark.spec("ASYNC-020")
    async def test_read_stream_partial_aclose(self, async_backend: AsyncBackend) -> None:
        """Calling ``aclose()`` on a partially-consumed async generator is safe."""
        _require(async_backend, Capability.WRITE)
        await async_backend.write("ec_rdc.txt", b"data")
        stream = async_backend.read("ec_rdc.txt")
        # Pull at least one chunk to enter the generator body, then close.
        first_chunk: bytes | None = None
        async for chunk in stream:
            first_chunk = chunk
            break
        assert first_chunk is not None
        assert len(first_chunk) > 0
        await stream.aclose()
        # Second aclose() is a documented no-op for async generators. Must not raise.
        await stream.aclose()
        # After aclose, further iteration yields nothing (StopAsyncIteration).
        remaining = [chunk async for chunk in stream]
        assert remaining == []


# ===========================================================================
# §6  Operational consistency: ASYNC-004 / ASYNC-008 / ASYNC-012 / ASYNC-014
# ===========================================================================


class TestOperationalConsistency:
    """Cross-cutting operational invariants."""

    @pytest.mark.spec("ASYNC-004")
    @pytest.mark.spec("ASYNC-008")
    async def test_exists_after_write(self, async_backend: AsyncBackend) -> None:
        """exists(path) returns True after successful write."""
        _require(async_backend, Capability.WRITE)
        await async_backend.write("ec_eaw.txt", b"x")
        assert await async_backend.exists("ec_eaw.txt") is True

    @pytest.mark.spec("ASYNC-004")
    @pytest.mark.spec("ASYNC-012")
    async def test_exists_after_delete(self, async_backend: AsyncBackend) -> None:
        """exists(path) returns False after successful delete."""
        _require(async_backend, Capability.DELETE, Capability.WRITE)
        await async_backend.write("ec_ead.txt", b"x")
        await async_backend.delete("ec_ead.txt")
        assert await async_backend.exists("ec_ead.txt") is False

    @pytest.mark.spec("ASYNC-008")
    async def test_write_overwrite_true_replaces(self, async_backend: AsyncBackend) -> None:
        """Write with overwrite=True replaces content."""
        _require(async_backend, Capability.WRITE)
        await async_backend.write("ec_wot.txt", b"first")
        await async_backend.write("ec_wot.txt", b"second", overwrite=True)
        assert await async_backend.read_bytes("ec_wot.txt") == b"second"

    @pytest.mark.spec("ASYNC-008")
    async def test_write_overwrite_false_rejects(self, async_backend: AsyncBackend) -> None:
        """Write with overwrite=False raises AlreadyExists."""
        _require(async_backend, Capability.WRITE)
        await async_backend.write("ec_wof.txt", b"first")
        with pytest.raises(AlreadyExists, match="ec_wof"):
            await async_backend.write("ec_wof.txt", b"second", overwrite=False)

    @pytest.mark.spec("ASYNC-012")
    async def test_delete_preserves_siblings(self, async_backend: AsyncBackend) -> None:
        """Deleting one file must not affect siblings."""
        _require(async_backend, Capability.DELETE, Capability.WRITE)
        await _seed(async_backend, {"ec_sib/a.txt": b"a", "ec_sib/b.txt": b"b"})
        await async_backend.delete("ec_sib/a.txt")
        assert not await async_backend.exists("ec_sib/a.txt")
        assert await async_backend.read_bytes("ec_sib/b.txt") == b"b"

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_returns_fileinfo_with_name(self, async_backend: AsyncBackend) -> None:
        """list_files results have name and path attributes."""
        _require(async_backend, Capability.LIST, Capability.WRITE)
        await async_backend.write("ec_lfi/x.txt", b"x")
        files = [f async for f in async_backend.list_files("ec_lfi")]
        assert len(files) >= 1
        assert files[0].name == "x.txt"
        assert str(files[0].path).endswith("x.txt")

    @pytest.mark.spec("ASYNC-016")
    async def test_get_file_info_size(self, async_backend: AsyncBackend) -> None:
        """get_file_info returns correct size."""
        _require(async_backend, Capability.WRITE)
        data = b"hello world"
        await async_backend.write("ec_gfis.txt", data)
        info = await async_backend.get_file_info("ec_gfis.txt")
        assert info.size == len(data)


class TestBackendQueryMethodsTypeConflicts:
    """ASYNC-004 / ASYNC-005 / ASYNC-024 (mirrors BE-004 / BE-005 / BE-021).

    When a path has an ancestor that is a file (not a directory), the query
    methods exists(), is_file(), and is_folder() return False rather than
    raising InvalidPath. This codifies the "accidental consensus" behavior
    across all backends (ID-129).
    """

    @pytest.mark.spec("ASYNC-004")
    @pytest.mark.spec("ASYNC-005")
    @pytest.mark.spec("ASYNC-024")
    @pytest.mark.parametrize(
        "method",
        [
            pytest.param("exists", id="exists"),
            pytest.param("is_file", id="is_file"),
            pytest.param("is_folder", id="is_folder"),
        ],
    )
    async def test_query_methods_return_false_when_ancestor_is_file(
        self, async_backend: AsyncBackend, method: str
    ) -> None:
        """Query methods return False for paths with file-as-directory-component ancestor."""
        _require(async_backend, Capability.WRITE)
        await async_backend.write("a/b", b"file_content")
        assert await getattr(async_backend, method)("a/b/c") is False
        assert await getattr(async_backend, method)("a/b/c/d") is False

    @pytest.mark.spec("ASYNC-004")
    @pytest.mark.spec("ASYNC-005")
    @pytest.mark.spec("ASYNC-024")
    @pytest.mark.parametrize(
        "method",
        [
            pytest.param("exists", id="exists"),
            pytest.param("is_file", id="is_file"),
            pytest.param("is_folder", id="is_folder"),
        ],
    )
    async def test_all_query_methods_return_false_on_type_conflict(
        self, async_backend: AsyncBackend, method: str
    ) -> None:
        """All three query methods return False consistently for type conflicts."""
        _require(async_backend, Capability.WRITE)
        await async_backend.write("file", b"content")
        assert await getattr(async_backend, method)("file/subpath") is False

    @pytest.mark.spec("ASYNC-024")
    async def test_query_methods_distinct_from_non_existent_paths(self, async_backend: AsyncBackend) -> None:
        """Query methods return False both for non-existent and type-conflict paths."""
        _require(async_backend, Capability.WRITE)
        await async_backend.write("a/b", b"file_content")

        assert await async_backend.exists("a/b/c") is False
        assert await async_backend.is_file("a/b/c") is False
        assert await async_backend.is_folder("a/b/c") is False

        assert await async_backend.exists("x/y/z") is False
        assert await async_backend.is_file("x/y/z") is False
        assert await async_backend.is_folder("x/y/z") is False
