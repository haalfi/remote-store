"""Extended conformance tests for the async backend contract.

Async sibling of the sync conformance topic files in this directory. The
``async_backend`` fixture is parametrised by the registry-driven hook in
``tests.backends.conformance.conftest`` over every registry entry whose
``is_async=True``.

Flat-namespace backends (S3, Azure Blob, HTTP, SQL-blob) have no real
directory entries and are excluded from error-fidelity tests by
``_skip_flat_namespace``. The default async registry comprises the
hierarchical-shaped ``is_async=True`` entries declared in
``tests/backends/fixtures/fixtures.toml`` (single source of truth); the
flat-NS async strict variant (``azurite_async_strict``, ID-211 review
follow-up) is opted into only by the file-ancestor test classes via
``include_strict_only=True``.

Spec coverage: ASYNC-004, ASYNC-005, ASYNC-006, ASYNC-007, ASYNC-008,
ASYNC-010, ASYNC-012, ASYNC-013, ASYNC-014, ASYNC-015, ASYNC-016, ASYNC-017,
ASYNC-018, ASYNC-019, ASYNC-020, ASYNC-024, ASYNC-029, ASYNC-047 (mirroring
BE-004..BE-021, SIO-001, ITER-004/005).
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
from remote_store._models import FileInfo, FolderEntry, WriteResult
from tests.backends.conformance._helpers import _depth, _fixture_record
from tests.backends.conformance.test_atomic import _FIELD_CAPABILITY
from tests.backends.fixtures import fixture_params

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from remote_store.aio._async_backend import AsyncBackend


# ---------------------------------------------------------------------------
# Helpers (mirror the sync conformance topic files in this directory)
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


def _skip_unless_rejects_file_ancestor(
    backend: AsyncBackend,
    reason: str = "fixture does not reject write-under-file-ancestor (ID-211 opt-in off)",
) -> None:
    """Async sibling of ``tests/backends/conformance/_helpers._skip_unless_rejects_file_ancestor``."""
    if not _fixture_record(backend).rejects_write_under_file_ancestor:
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

# (op, cap) for the user-metadata round-trip across move/copy (BK-195 /
# BK-233). Per-param @spec marks differ by op: copy carries BE-019 +
# ASYNC-019, move BE-018 + ASYNC-018; both carry WR-013.
_MOVE_COPY_META_PARAMS = [
    pytest.param(
        "copy",
        Capability.COPY,
        id="copy",
        marks=[pytest.mark.spec("WR-013"), pytest.mark.spec("BE-019"), pytest.mark.spec("ASYNC-019")],
    ),
    pytest.param(
        "move",
        Capability.MOVE,
        id="move",
        marks=[pytest.mark.spec("WR-013"), pytest.mark.spec("BE-018"), pytest.mark.spec("ASYNC-018")],
    ),
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

    @pytest.mark.spec("ASYNC-007")
    @pytest.mark.spec("BE-007")
    async def test_read_bytes_under_file_ancestor_raises_not_found(self, async_backend: AsyncBackend) -> None:
        """ID-209 round-2: file-ancestor read-side path => NotFound (async mirror).

        ``read_bytes`` is ``async def`` returning ``bytes`` (per ASYNC-007);
        awaiting it propagates the access-side error.  The ``read``
        counterpart returns an ``AsyncIterator[bytes]`` (per ASYNC-020),
        which is exercised by the streaming ``read`` conformance class
        rather than here.
        """
        _require(async_backend, Capability.READ, Capability.WRITE)
        _skip_flat_namespace(
            async_backend,
            "flat-namespace backends cannot detect file-ancestor in O(1) (ID-211)",
        )
        await async_backend.write("rufa.txt", b"file-blocking")
        with pytest.raises(NotFound, match="rufa.txt"):
            await async_backend.read_bytes("rufa.txt/child.txt")

    @pytest.mark.spec("ASYNC-006")
    @pytest.mark.spec("BE-006")
    async def test_read_under_file_ancestor_raises_not_found(self, async_backend: AsyncBackend) -> None:
        """ID-209 round-2: ``read`` (async iterator form) for the same case.

        Async ``read`` is an async-generator factory — consuming via
        ``async for`` is the canonical way to trigger backend access.
        Backends that validate eagerly raise on the first ``__anext__``.
        """
        _require(async_backend, Capability.READ, Capability.WRITE)
        _skip_flat_namespace(
            async_backend,
            "flat-namespace backends cannot detect file-ancestor in O(1) (ID-211)",
        )
        await async_backend.write("rufa_stream.txt", b"file-blocking")
        with pytest.raises(NotFound, match="rufa_stream.txt"):
            await _drain_read(async_backend, "rufa_stream.txt/child.txt")


@pytest.mark.parametrize(
    "async_backend",
    fixture_params(Capability.WRITE, is_async=True, include_strict_only=True),
    indirect=True,
)
class TestWriteErrorFidelity:
    """ASYNC-008 / ASYNC-010 (mirrors BE-008 / BE-010).

    write(dir) and write_atomic(dir) ==> InvalidPath unconditionally.
    The dir check must fire BEFORE the overwrite check; ``write_atomic``
    shares BE-008 precondition order via BE-010.

    Class-level parametrize uses ``include_strict_only=True`` (ID-211
    review follow-up) so the async file-ancestor test can exercise the
    ``azurite_async_strict`` fixture. The non-file-ancestor tests in
    this class skip flat-NS via ``_skip_flat_namespace``, so the strict
    variant doesn't expand those test cells; only the file-ancestor
    cell actually runs.
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

    @pytest.mark.parametrize("body_kind", ["bytes", "stream"])
    @pytest.mark.parametrize(
        ("method", "cap"),
        [
            pytest.param("write", Capability.WRITE, id="write", marks=pytest.mark.spec("ASYNC-008")),
            pytest.param(
                "write_atomic",
                Capability.ATOMIC_WRITE,
                id="write_atomic",
                marks=[
                    pytest.mark.spec("ASYNC-010"),
                    pytest.mark.spec("SAW-005"),
                    pytest.mark.spec("SAW-011"),
                ],
            ),
        ],
    )
    @pytest.mark.spec("BE-008")
    async def test_write_under_file_ancestor_raises_invalid_path(
        self, async_backend: AsyncBackend, method: str, cap: Capability, body_kind: str
    ) -> None:
        """ID-209 async sibling: !AllAncestorsTraversable(fs, path) => InvalidPath.

        Mirrors the sync ``TestWriteErrorFidelity::test_write_under_file_
        ancestor_raises_invalid_path`` against the async backend surface,
        parametrised over ``write`` and ``write_atomic`` (ASYNC-008 /
        ASYNC-010).  Flat-namespace backends opt into the gate via the
        ID-211 ``reject_write_under_file_ancestor`` kwarg; default-off
        fixtures skip this test, the ``*_strict`` fixture variants run it.

        BK-244 / SAW-005, SAW-011: also assert no orphan temp survives. The
        async store exposes no ``open_atomic``, so ``write_atomic`` is the
        async analog of the sync ``open_atomic`` cleanup branch: on HNS its
        temp ``upload_data`` under a file parent fails, driving
        ``aio/backends/_azure.py`` ``except Exception`` -> ``tmp_fc.delete_file()``
        -> ``_raise_invalid_if_hns_file_ancestor``. As on the sync side the
        temp is never committed (temp and final share a parent), so the scan
        confirms the no-leak invariant rather than a real orphan removal.

        BK-249: also parametrised over the body type (``bytes`` vs an
        ``AsyncIterable[bytes]``).  Azure HNS ``write_atomic`` takes a separate
        ``except`` block per body type, so only the streaming case reaches the
        ``else:`` branch's file-ancestor remap (``aio/backends/_azure.py``
        ``create_file`` of the temp under a file parent -> 409 ->
        ``_raise_invalid_if_hns_file_ancestor``).  The streaming temp create
        fails before the generator is iterated, so an un-iterated generator is
        sufficient.
        """
        _require(async_backend, cap)
        _skip_unless_rejects_file_ancestor(async_backend)
        seed = f"wufa_{method}.txt"
        nested = f"{seed}/child.txt"
        await async_backend.write(seed, b"file-blocking")

        async def _under_file_stream() -> AsyncIterator[bytes]:
            yield b"under-file"

        body = _under_file_stream() if body_kind == "stream" else b"under-file"
        with pytest.raises(InvalidPath, match=seed):
            await getattr(async_backend, method)(nested, body)
        assert await async_backend.read_bytes(seed) == b"file-blocking"
        remaining = [str(fi.path) async for fi in async_backend.list_files("", recursive=True)]
        assert remaining == [seed], f"orphan temp after async {method} file-ancestor failure: {remaining}"


@pytest.mark.spec("ASYNC-012")
class TestDeleteErrorFidelity:
    """``delete(dir_path)`` raises ``InvalidPath`` regardless of ``missing_ok``.

    Mirrors ``test_errors.py::TestDeleteErrorFidelity``.
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

    @pytest.mark.spec("ASYNC-012")
    @pytest.mark.spec("BE-012")
    async def test_delete_under_file_ancestor_raises_not_found(self, async_backend: AsyncBackend) -> None:
        """ID-209 round-2: file-ancestor → NotFound (read-side semantics)."""
        _require(async_backend, Capability.DELETE, Capability.WRITE)
        _skip_flat_namespace(
            async_backend,
            "flat-namespace backends cannot detect file-ancestor in O(1) (ID-211)",
        )
        await async_backend.write("dufa.txt", b"file-blocking")
        with pytest.raises(NotFound, match="dufa.txt"):
            await async_backend.delete("dufa.txt/child.txt")
        # missing_ok=True: file-ancestor is "missing", not "wrong type".
        await async_backend.delete("dufa.txt/child.txt", missing_ok=True)
        assert await async_backend.read_bytes("dufa.txt") == b"file-blocking"


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

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_recursive_no_child_survives(self, async_backend: AsyncBackend) -> None:
        """ID-184 (T-side, async): the Dafny ``forall p | IsChildOf(p, path)
        :: !PathExists(fs, p)`` quantifier — no file under the deleted prefix
        survives the recursive delete. Async mirror of the sync sibling in
        ``test_errors.py``.
        """
        _require(async_backend, Capability.DELETE, Capability.WRITE, Capability.LIST)
        await _seed(async_backend, {"dfrls/a.txt": b"a", "dfrls/sub/b.txt": b"b"})
        await async_backend.delete_folder("dfrls", recursive=True)
        assert [fi async for fi in async_backend.list_files("dfrls", recursive=True)] == []


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

    @pytest.mark.spec("ASYNC-016")
    @pytest.mark.spec("BE-016")
    async def test_get_file_info_under_file_ancestor_raises_not_found(self, async_backend: AsyncBackend) -> None:
        """ID-209 round-2: file-ancestor path => NotFound (read-side semantics)."""
        _require(async_backend, Capability.METADATA, Capability.WRITE)
        _skip_flat_namespace(
            async_backend,
            "flat-namespace backends cannot detect file-ancestor in O(1) (ID-211)",
        )
        await async_backend.write("gfufa.txt", b"file-blocking")
        with pytest.raises(NotFound, match="gfufa.txt"):
            await async_backend.get_file_info("gfufa.txt/child.txt")


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
    async def test_get_folder_info_file_count_and_total_size(self, async_backend: AsyncBackend) -> None:
        """IsDir ==> file_count == |ChildFiles|, total_size == SumSizes."""
        _require(async_backend, Capability.WRITE)
        await _seed(async_backend, {"gfa/a.txt": b"aaa", "gfa/b.txt": b"bb"})
        fi = await async_backend.get_folder_info("gfa")
        assert fi.file_count == 2
        assert fi.total_size == 5

    @pytest.mark.spec("ASYNC-017")
    async def test_get_folder_info_counts_recursive_children(self, async_backend: AsyncBackend) -> None:
        """ChildFiles is the full recursive set: subdirectory files are counted."""
        _require(async_backend, Capability.WRITE)
        await _seed(async_backend, {"gfr/a.txt": b"aaa", "gfr/sub/b.txt": b"bb"})
        fi = await async_backend.get_folder_info("gfr")
        assert fi.file_count == 2
        assert fi.total_size == 5


# ===========================================================================
# §2  Listing: ASYNC-014 / ASYNC-015 / ASYNC-029 postconditions
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
        """Depth filtering is inclusive (Dafny DepthFilterBoundaryInclusive).

        Async sibling of the sync depth-boundary gate in
        ``test_listing.py``. The ``.name``-set check alone does not
        enforce the boundary — see ID-185 for the diagnosis.
        """
        _require(async_backend, Capability.LIST, Capability.WRITE)
        await _seed(async_backend, self.DEPTH_TREE)
        files = [f async for f in async_backend.list_files("pc", recursive=True, max_depth=max_depth)]
        assert {f.name for f in files} == expected_names
        for f in files:
            d = _depth("pc", f.path)
            assert d <= max_depth, f"DEPTH-003 violation: {f.path} at depth {d} > max_depth={max_depth}"

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

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_non_traversable_ancestor_yields_empty(self, async_backend: AsyncBackend) -> None:
        """Async mirror of the file-ancestor adapter gate in
        ``test_listing.py``. See the sync test's docstring for the scope
        caveat — this exercises the `!PathExists` disjunct of the Dafny
        empty-result postcondition under a file-ancestor path shape,
        not the ID-184 `!AllAncestorsTraversable` disjunct directly.
        """
        _require(async_backend, Capability.LIST, Capability.WRITE)
        await _seed(async_backend, {"badanc.txt": b"x"})
        files = [f async for f in async_backend.list_files("badanc.txt/child", recursive=True)]
        assert files == []


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

    @pytest.mark.spec("ASYNC-015")
    async def test_list_folders_non_traversable_ancestor_yields_empty(self, async_backend: AsyncBackend) -> None:
        """Async mirror of the ``list_folders`` file-ancestor adapter
        gate in ``test_listing.py``. See the sync sibling's docstring
        for the scope caveat.
        """
        _require(async_backend, Capability.LIST, Capability.WRITE)
        await _seed(async_backend, {"badanc.txt": b"x"})
        folders = [f async for f in async_backend.list_folders("badanc.txt/child")]
        assert folders == []


class TestAsyncIterChildren:
    """ASYNC-029 (mirrors ITER-004 / ITER-005): iter_children combined listing."""

    @pytest.mark.spec("ASYNC-029")
    async def test_iter_children(self, async_backend: AsyncBackend) -> None:
        _require(async_backend, Capability.LIST, Capability.WRITE)
        await _seed(async_backend, {"ic/a.txt": b"a", "ic/b.txt": b"b", "ic/sub/c.txt": b"c"})
        children = [c async for c in async_backend.iter_children("ic")]
        files = [c for c in children if isinstance(c, FileInfo)]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert {f.name for f in files} == {"a.txt", "b.txt"}
        assert {f.name for f in folders} == {"sub"}
        assert {str(f.path) for f in folders} == {"ic/sub"}

    @pytest.mark.spec("ASYNC-029")
    async def test_iter_children_empty_or_nonexistent(self, async_backend: AsyncBackend) -> None:
        _require(async_backend, Capability.LIST)
        children = [c async for c in async_backend.iter_children("ic_nonexistent")]
        assert children == []

    @pytest.mark.spec("ASYNC-029")
    @pytest.mark.parametrize(
        ("prefix", "file_path", "expect_files", "expect_folders"),
        [
            pytest.param("icf", "icf/x.txt", {"x.txt"}, set(), id="only_files"),
            pytest.param("ico", "ico/sub/y.txt", set(), {"sub"}, id="only_folders"),
        ],
    )
    async def test_iter_children_single_type(
        self,
        async_backend: AsyncBackend,
        prefix: str,
        file_path: str,
        expect_files: set[str],
        expect_folders: set[str],
    ) -> None:
        _require(async_backend, Capability.LIST, Capability.WRITE)
        await async_backend.write(file_path, b"x")
        children = [c async for c in async_backend.iter_children(prefix)]
        files = [c for c in children if isinstance(c, FileInfo)]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert {f.name for f in files} == expect_files
        assert {f.name for f in folders} == expect_folders


# ===========================================================================
# §3  Move/Copy: ASYNC-018 / ASYNC-019 postconditions
# ===========================================================================


@pytest.mark.parametrize(
    "async_backend",
    fixture_params(Capability.WRITE, is_async=True, include_strict_only=True),
    indirect=True,
)
class TestMoveCopyErrorFidelity:
    """ASYNC-018 / ASYNC-019 (mirrors BE-018 / BE-019).

    Class-level parametrize uses ``include_strict_only=True`` (ID-211
    review follow-up) so the async file-ancestor / precondition-order
    tests can exercise the ``azurite_async_strict`` fixture. The
    non-file-ancestor tests in this class skip flat-NS via
    ``_skip_flat_namespace``, so the strict variant doesn't expand
    those test cells; only the file-ancestor and missing-src cells
    actually run.
    """

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

    @pytest.mark.spec("ASYNC-018")
    @pytest.mark.spec("ASYNC-019")
    @pytest.mark.spec("BE-018")
    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    async def test_destination_under_file_ancestor_raises_invalid_path(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        """ID-209 async sibling: !AllAncestorsTraversable(fs, dst) => InvalidPath(dst)."""
        _require(async_backend, cap, Capability.WRITE)
        _skip_unless_rejects_file_ancestor(async_backend)
        await async_backend.write(f"mcua/{op}_blocker.txt", b"file-blocking")
        await async_backend.write(f"mcua/{op}_src.txt", b"srcdata")
        with pytest.raises(InvalidPath, match=f"mcua/{op}_blocker.txt"):
            await _do_op(
                async_backend,
                op,
                f"mcua/{op}_src.txt",
                f"mcua/{op}_blocker.txt/dst.txt",
            )
        assert await async_backend.read_bytes(f"mcua/{op}_blocker.txt") == b"file-blocking"
        assert await async_backend.read_bytes(f"mcua/{op}_src.txt") == b"srcdata"

    @pytest.mark.spec("ASYNC-018")
    @pytest.mark.spec("ASYNC-019")
    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_PARAMS)
    async def test_missing_src_under_blocked_dst_raises_not_found(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        """ASYNC-018/019 precondition order: src-NotFound > dst-file-ancestor (ID-211 review)."""
        _require(async_backend, cap, Capability.WRITE)
        await async_backend.write(f"mcord/{op}_blocker.txt", b"file-blocking")
        with pytest.raises(NotFound, match=f"mcord/{op}_missing"):
            await _do_op(
                async_backend,
                op,
                f"mcord/{op}_missing.txt",
                f"mcord/{op}_blocker.txt/dst.txt",
            )


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
        """{move,copy}(src, src) where src is a directory raises InvalidPath.

        ASYNC-018/019 src-type precondition; ASYNC-047 self-op contract.
        """
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


class TestMoveCopyMetadataPreservation:
    """ASYNC-018 / ASYNC-019: move/copy preserve user metadata (BK-233 / BK-195).

    Async mirror of ``test_atomic.py::TestWriteResultConformance``
    ``::test_metadata_round_trips_through_move_copy`` — the WR-013
    user-metadata round-trip applied to the async move/copy paths.
    """

    @pytest.mark.parametrize(("op", "cap"), _MOVE_COPY_META_PARAMS)
    async def test_metadata_round_trips_through_move_copy(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        """A successful move/copy preserves the source file's user metadata.

        BE-018/BE-019 Metadata invariant: ``get_file_info(dst)`` MUST return
        the same mapping the source carried before the operation.
        """
        _require(async_backend, cap, Capability.USER_METADATA, Capability.METADATA)
        meta = {"author": "carol", "stage": "bronze"}
        src = f"mcmeta/{op}-src.txt"
        dst = f"mcmeta/{op}-dst.txt"
        await async_backend.write(src, b"data", metadata=meta)
        await _do_op(async_backend, op, src, dst)
        info = await async_backend.get_file_info(dst)
        assert info.metadata == meta


# ===========================================================================
# §3b  WriteResult field contract for AsyncBackend (ID-127 GR-CONTRACT)
# ===========================================================================
#
# Async parametrisation of ``test_atomic.py::TestWriteResultConformance``.
# Per the ID-127 plan's "option (a)" decision, the async WriteResult slices
# (WR-001a / 004 / 005 / 012 / 013) land for ``AsyncBackend`` — validated
# against ``AsyncMemory`` / ``AsyncAzure`` — *before* the Graph backend plugs
# in, so its native ``driveItem``-from-response population (GR-018 / GR-019)
# moves onto a contract that already exists.

# (op, cap) carrying each op's async-method spec mark — ASYNC-008 (``write``)
# / ASYNC-010 (``write_atomic``). The WriteResult *field* contract (WR-*) is
# carried per test method below.
_WRITE_OPS = [
    pytest.param("write", Capability.WRITE, id="write", marks=pytest.mark.spec("ASYNC-008")),
    pytest.param("write_atomic", Capability.ATOMIC_WRITE, id="write_atomic", marks=pytest.mark.spec("ASYNC-010")),
]

# name → (reason, strict).  Populate when an async backend temporarily returns
# last_modified=None / disagrees on a rich field from write() (mirrors the sync
# test_atomic.py registries; empty until a real async-backend gap is recorded).
_ASYNC_LAST_MODIFIED_XFAIL: dict[str, tuple[str, bool]] = {}
_ASYNC_RICH_FIELDS_XFAIL: dict[str, tuple[str, bool]] = {}


class TestAsyncWriteResultConformance:
    """WR-001a / WR-004 / WR-005 / WR-012 / WR-013: WriteResult field contract (async)."""

    @pytest.mark.spec("WR-001a")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    async def test_result_is_write_result_with_path_and_size(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        _require(async_backend, cap)
        payload = b"wr001a-payload"
        result = await getattr(async_backend, op)(f"wr/{op}-path-size.txt", payload)
        assert isinstance(result, WriteResult)
        assert str(result.path) == f"wr/{op}-path-size.txt"
        assert result.size == len(payload)

    @pytest.mark.spec("WR-001a")
    @pytest.mark.spec("ASYNC-021")
    async def test_size_matches_written_bytes_for_async_iterator_input(self, async_backend: AsyncBackend) -> None:
        """WR-001a size clause for ``AsyncIterator[bytes]`` input on write_atomic.

        The payload spans many chunks, so a backend that captures size from the
        first chunk rather than the streamed total reports a truncated value —
        the async analogue of the sync ``BytesIO`` BUG-168 guard. The
        ``_count_and_pass`` streaming wrapper (ASYNC-021) must total every chunk.
        """
        _require(async_backend, Capability.ATOMIC_WRITE)
        payload = b"x" * (100 * 1024)

        async def _chunks() -> AsyncIterator[bytes]:
            for i in range(0, len(payload), 16 * 1024):
                yield payload[i : i + 16 * 1024]

        result = await async_backend.write_atomic("wr/streaming-size.bin", _chunks())
        assert result.size == len(payload)

    @pytest.mark.spec("WR-004")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    async def test_source_matches_write_result_native(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        _require(async_backend, cap)
        result = await getattr(async_backend, op)(f"wr/{op}-source.txt", b"data")
        expected = "native" if async_backend.capabilities.supports(Capability.WRITE_RESULT_NATIVE) else "basic"
        assert result.source == expected

    @pytest.mark.spec("WR-005")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    async def test_basic_source_leaves_rich_fields_none(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        _require(async_backend, cap)
        if async_backend.capabilities.supports(Capability.WRITE_RESULT_NATIVE):
            pytest.skip("WR-005 governs basic-source results")
        result = await getattr(async_backend, op)(f"wr/{op}-basic.txt", b"data")
        assert result.source == "basic"
        assert result.digest is None
        assert result.etag is None
        assert result.version_id is None
        assert result.last_modified is None

    @pytest.mark.spec("WR-005")
    @pytest.mark.spec("WR-012")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    async def test_populated_field_implies_declared_capability(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        """BK-239 async: every populated WriteResult field implies its gating capability.

        Generic field↔capability symmetry over the shared ``_FIELD_CAPABILITY``
        map (its completeness guard lives in the sync ``test_atomic.py``). Runs on
        every async WRITE backend, so over-declaration fails regardless of direction.
        """
        _require(async_backend, cap)
        meta = {"author": "symmetry"} if async_backend.capabilities.supports(Capability.USER_METADATA) else None
        result = await getattr(async_backend, op)(f"wr/{op}-symmetry.txt", b"data", metadata=meta)
        for name, required in _FIELD_CAPABILITY.items():
            if required is not None and getattr(result, name) is not None:
                assert async_backend.capabilities.supports(required), (
                    f"{async_backend.name} populated WriteResult.{name} without declaring {required.name}"
                )

    @pytest.mark.spec("WR-001a")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    async def test_native_populates_last_modified(
        self, async_backend: AsyncBackend, op: str, cap: Capability, request: pytest.FixtureRequest
    ) -> None:
        """WR-001a rich-field obligation on declaring async backends."""
        _require(async_backend, cap, Capability.WRITE_RESULT_NATIVE)
        if async_backend.name in _ASYNC_LAST_MODIFIED_XFAIL:
            reason, strict = _ASYNC_LAST_MODIFIED_XFAIL[async_backend.name]
            request.applymarker(pytest.mark.xfail(reason=reason, strict=strict))
        result = await getattr(async_backend, op)(f"wr/{op}-lm.txt", b"data")
        assert result.last_modified is not None

    @pytest.mark.spec("WR-001a")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    async def test_write_result_rich_fields_match_file_info(
        self, async_backend: AsyncBackend, op: str, cap: Capability, request: pytest.FixtureRequest
    ) -> None:
        """WR-001a consistency contract: write() rich fields must match get_file_info()."""
        _require(async_backend, cap, Capability.METADATA)
        if async_backend.name in _ASYNC_RICH_FIELDS_XFAIL:
            reason, strict = _ASYNC_RICH_FIELDS_XFAIL[async_backend.name]
            request.applymarker(pytest.mark.xfail(reason=reason, strict=strict))
        key = f"wr/{op}-rich-fields-match.txt"
        result = await getattr(async_backend, op)(key, b"rich-fields-payload")
        info = await async_backend.get_file_info(key)
        assert result.etag == info.etag
        assert result.digest == info.digest
        if info.modified_at is not None:
            assert result.last_modified == info.modified_at

    @pytest.mark.spec("WR-012")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    async def test_metadata_echoed_when_gate_passes(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        _require(async_backend, cap, Capability.USER_METADATA)
        meta = {"author": "alice", "project": "conformance"}
        result = await getattr(async_backend, op)(f"wr/{op}-meta-echo.txt", b"data", metadata=meta)
        assert result.metadata == meta

    @pytest.mark.spec("WR-012")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    async def test_metadata_is_none_when_not_passed(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        _require(async_backend, cap)
        result = await getattr(async_backend, op)(f"wr/{op}-meta-absent.txt", b"data")
        assert result.metadata is None

    @pytest.mark.spec("WR-013")
    @pytest.mark.parametrize(("op", "cap"), _WRITE_OPS)
    async def test_metadata_round_trips_via_get_file_info(
        self, async_backend: AsyncBackend, op: str, cap: Capability
    ) -> None:
        _require(async_backend, cap, Capability.USER_METADATA, Capability.METADATA)
        meta = {"author": "bob", "version": "v1"}
        key = f"wr/{op}-meta-roundtrip.txt"
        await getattr(async_backend, op)(key, b"data", metadata=meta)
        info = await async_backend.get_file_info(key)
        assert info.metadata == meta

    @pytest.mark.spec("WR-013")
    async def test_file_info_metadata_none_when_capability_absent(self, async_backend: AsyncBackend) -> None:
        _require(async_backend, Capability.METADATA)
        if async_backend.capabilities.supports(Capability.USER_METADATA):
            pytest.skip("WR-013 negative direction targets non-declaring backends")
        await async_backend.write("wr/meta-no-cap.txt", b"data")
        info = await async_backend.get_file_info("wr/meta-no-cap.txt")
        assert info.metadata is None


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


class TestAsyncWriteAtomic:
    """ASYNC-010 / WR-001a (mirrors BE-010): atomic write happy-path round-trip."""

    @pytest.mark.spec("ASYNC-010")
    async def test_write_atomic_creates_file(self, async_backend: AsyncBackend) -> None:
        _require(async_backend, Capability.ATOMIC_WRITE)
        await async_backend.write_atomic("async_atomic.txt", b"atomic content")
        assert await async_backend.read_bytes("async_atomic.txt") == b"atomic content"

    @pytest.mark.spec("ASYNC-010")
    async def test_write_atomic_overwrite(self, async_backend: AsyncBackend) -> None:
        _require(async_backend, Capability.ATOMIC_WRITE)
        await async_backend.write_atomic("async_atomic2.txt", b"first")
        await async_backend.write_atomic("async_atomic2.txt", b"second", overwrite=True)
        assert await async_backend.read_bytes("async_atomic2.txt") == b"second"

    @pytest.mark.spec("ASYNC-010")
    async def test_write_atomic_already_exists(self, async_backend: AsyncBackend) -> None:
        _require(async_backend, Capability.ATOMIC_WRITE)
        await async_backend.write_atomic("async_atomic3.txt", b"first")
        with pytest.raises(AlreadyExists):
            await async_backend.write_atomic("async_atomic3.txt", b"second", overwrite=False)


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
