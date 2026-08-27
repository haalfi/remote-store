"""Backend I/O conformance: exists, file/folder, read, write, delete, to_key, round-trip.

Most classes apply ``fixture_params(Capability.WRITE)`` at the class
level since their tests overwhelmingly need WRITE. Class-internal
``_require()`` calls remain as defensive guards for tests that need
additional capabilities (DELETE, LIST, ...).
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import AlreadyExists, InvalidPath, NotFound
from remote_store._path import is_root
from tests.backends.conformance._helpers import _fixture_record, _require, _seed
from tests.backends.fixtures import fixture_params

if TYPE_CHECKING:
    from remote_store._backend import Backend


@pytest.mark.parametrize("backend", fixture_params(), indirect=True)
class TestBackendExists:
    """BE-004: exists() behavior."""

    @pytest.mark.spec("BE-004")
    def test_false_for_missing(self, backend: Backend) -> None:
        assert backend.exists("nonexistent.txt") is False

    @pytest.mark.spec("BE-004")
    def test_true_after_write(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("hello.txt", b"hello")
        assert backend.exists("hello.txt") is True


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestBackendFileFolder:
    """BE-005: is_file() / is_folder() distinction."""

    @pytest.mark.spec("BE-005")
    def test_is_file(self, backend: Backend) -> None:
        backend.write("a.txt", b"data")
        assert backend.is_file("a.txt") is True
        assert backend.is_folder("a.txt") is False

    @pytest.mark.spec("BE-005")
    @pytest.mark.spec("AZ-009")
    @pytest.mark.spec("S3-006")
    @pytest.mark.spec("S3PA-008")
    @pytest.mark.spec("MEM-DS-006")
    def test_is_folder(self, backend: Backend) -> None:
        backend.write("dir/a.txt", b"data")
        assert backend.is_folder("dir") is True
        assert backend.is_file("dir") is False

    @pytest.mark.spec("BE-005")
    @pytest.mark.parametrize(
        "method",
        [pytest.param("is_file", id="is_file"), pytest.param("is_folder", id="is_folder")],
    )
    def test_false_for_missing(self, backend: Backend, method: str) -> None:
        assert getattr(backend, method)("nope") is False


_ROOT_FILE_OPS = [
    pytest.param("read", Capability.READ, id="read"),
    pytest.param("read_bytes", Capability.READ, id="read_bytes"),
    pytest.param("read_seekable", Capability.READ, id="read_seekable"),
    pytest.param("get_file_info", Capability.METADATA, id="get_file_info"),
    pytest.param("delete", Capability.DELETE, id="delete"),
    pytest.param("move", Capability.MOVE, id="move_src"),
    pytest.param("copy", Capability.COPY, id="copy_src"),
]
"""The file-shaped surface BE-021's first row governs, as (method, capability).

``read_seekable`` is in the list because it is a read whose *stream* differs,
not a read whose *contract* differs — the ABC default delegates to ``read()``,
so only the two optimised overrides could ever have diverged.
"""

_ROOT_FILE_OP_CALLS = {
    "read": lambda b, p: b.read(p).read(),
    "read_bytes": lambda b, p: b.read_bytes(p),
    "read_seekable": lambda b, p: b.read_seekable(p).read(),
    "get_file_info": lambda b, p: b.get_file_info(p),
    "delete": lambda b, p: b.delete(p),
    "move": lambda b, p: b.move(p, "rootop_dst.txt"),
    "copy": lambda b, p: b.copy(p, "rootop_dst.txt"),
}
"""Invocation per op. ``read``/``read_seekable`` are drained so a backend that
defers its verdict to first byte is not credited with a lazy handle."""


def _open_atomic_write(backend: Backend, path: str, *, overwrite: bool = False) -> None:
    """Drive ``open_atomic`` to completion — it refuses on ``__enter__``, not at the call."""
    with backend.open_atomic(path, overwrite=overwrite) as handle:
        handle.write(b"x")


_ROOT_WRITE_OPS = [
    pytest.param("write", Capability.WRITE, id="write"),
    pytest.param("write_atomic", Capability.ATOMIC_WRITE, id="write_atomic"),
    pytest.param("open_atomic", Capability.ATOMIC_WRITE, id="open_atomic"),
]
"""The write-shaped surface, kept apart from ``_ROOT_FILE_OPS`` above.

A separate roster because it is a separate rule: ``_ROOT_FILE_OPS`` is BE-021's
type-mismatch row — a *read*-shaped operation handed a folder — while these owe
not merely an error class but the absence of a side effect, which no member of
the other roster asserts.

**Paired with a capability each, exactly as that roster is**, and the pairing is
not decorative: ``write_atomic`` and ``open_atomic`` are gated on
``ATOMIC_WRITE``, not ``WRITE`` (`_GATING` in ``_store.py``, `_BACKEND_GATING` in
``gen_graph.py``). Requiring ``WRITE`` for all three would call two operations a
backend never declared on any backend that ever ships ``WRITE`` without
``ATOMIC_WRITE`` — no registered fixture is in that state today, which is
precisely why it would have gone unnoticed.
"""

_ROOT_WRITE_OP_CALLS = {
    "write": lambda b, p, ow: b.write(p, b"x", overwrite=ow),
    "write_atomic": lambda b, p, ow: b.write_atomic(p, b"x", overwrite=ow),
    "open_atomic": lambda b, p, ow: _open_atomic_write(b, p, overwrite=ow),
}

_OVERWRITE_MODES = [pytest.param(False, id="no_overwrite"), pytest.param(True, id="overwrite")]
"""Both modes, because the clause binds both and they take different routes.

``write`` and ``write_atomic`` skip their existence probe entirely when
``overwrite=True`` — a guard placed on the ``overwrite=False`` branch alone would
leave half the surface unguarded, which is not hypothetical: the reproduction
that scoped BUG-259 found the ``overwrite=True`` cells corrupting on their own.
Until this parameter existed the only cells covering the mode were one backend's,
so a normative "in both overwrite modes" was falsifiable on one of eleven bound
classes. The guard is a pre-check, so the cost of the second mode is collection
count and no round trips.
"""

_ROOT_WRITE_DST_OPS = [
    pytest.param("move", Capability.MOVE, id="move_dst"),
    pytest.param("copy", Capability.COPY, id="copy_dst"),
]
"""The other two ways to write, keyed on the destination.

Ids are explicit for the same reason ``_ROOT_FILE_OPS`` spells its ``move_src`` /
``copy_src`` out: without them pytest derives the id from the ``Capability``
member and the enum repr lands in the test id — which is also the cassette
filename for every replay lane, so an id that changes with an unrelated enum edit
orphans recorded cassettes.
"""


@pytest.mark.parametrize("backend", fixture_params(Capability.LIST), indirect=True)
class TestBackendRootPath:
    """BE-029: the store root is a folder, under both spellings.

    ``Store`` normalises ``"."`` and refuses a root delete before delegating,
    so an application never depends on this. It binds the layer below: anyone
    holding a ``Backend`` directly — the adapter surface, ``unwrap()``
    consumers, the conformance suite itself — must get the same answer
    everywhere. Before BK-324 they did not: one backend raised on
    ``is_file("")`` because its SDK rejects a zero-length key, and the
    ``"."`` spelling disagreed with ``""`` on several.

    **Gated on LIST, not WRITE.** "The root is a folder" presupposes a backend
    that has folders, and ``Capability.LIST`` is how a backend declares it
    does. Gating on WRITE instead was an accident of these cells needing a
    seeded file, and it silently excluded every read-only backend that *does*
    enumerate — which is where the rule still needs to hold. The seeds are now
    confined to the two cells that genuinely need one, behind ``_require``.
    """

    @pytest.mark.spec("BE-029")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_root_is_a_folder(self, backend: Backend, root: str) -> None:
        """exists → True, is_folder → True, is_file → False; never raises.

        No seed, so this is also the empty-store case — the harder one for a
        flat namespace, where there is no object to find and the answer must
        come from the definition rather than a listing. Requiring a written
        file to ask the question is what kept read-only backends out.
        """
        assert backend.exists(root) is True
        assert backend.is_folder(root) is True
        assert backend.is_file(root) is False

    @pytest.mark.spec("BE-029")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_root_is_a_folder_with_content(self, backend: Backend, root: str) -> None:
        """Same three answers once the store is non-empty.

        The sibling above covers the empty store, which is the harder case for
        a flat namespace. This one guards the other direction: a backend that
        answered from a listing would flip once a key exists.
        """
        _require(backend, Capability.WRITE)
        backend.write("rootprobe/a.txt", b"x")
        assert backend.exists(root) is True
        assert backend.is_folder(root) is True
        assert backend.is_file(root) is False

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("BE-017")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_get_folder_info_on_root_aggregates(self, backend: Backend, root: str) -> None:
        """get_folder_info(root) aggregates the store instead of raising.

        Asserting the count (not merely that no error escaped) is what keeps
        this from passing on a backend that answers for some other prefix —
        ``"./"`` is a real, and empty, prefix on a flat namespace.
        """
        _require(backend, Capability.METADATA, Capability.WRITE)
        backend.write("rootinfo/a.txt", b"aa")
        backend.write("rootinfo/b.txt", b"bbb")
        info = backend.get_folder_info(root)
        assert info.file_count == 2
        assert info.total_size == 5

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("BE-017")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_get_folder_info_on_empty_root_does_not_raise(self, backend: Backend, root: str) -> None:
        """The root aggregates to zero rather than reporting itself missing.

        Separate from the seeded sibling because an empty store is where a
        truthiness-based root test shows: ``""`` short-circuits to a
        ``FolderInfo`` while ``"."`` falls through to the not-found branch.
        """
        _require(backend, Capability.METADATA)
        info = backend.get_folder_info(root)
        assert info.file_count == 0

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("BE-021")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    @pytest.mark.parametrize(("op", "cap"), _ROOT_FILE_OPS)
    def test_file_operation_on_root_raises_invalid_path(
        self, backend: Backend, root: str, op: str, cap: Capability
    ) -> None:
        """A file-shaped operation on the root is a type error, not a miss.

        The root is a folder (BE-029), so BE-021's first row applies and the
        answer is ``InvalidPath`` — the same answer these operations give for
        any other folder path. Both spellings must reach it, and by the same
        route: the class of defect this pins is one spelling taking a
        different code path from the other, which produced ``NotFound`` for
        ``""`` and ``InvalidPath`` for ``"."`` on the same backend and call.

        The raised error must be *about the root*: a backend that let the root
        through to its SDK and mapped the resulting zero-length-key rejection
        would name something else, or raise a retryable class for a permanent
        condition. ``is_root`` rather than equality, because a backend may echo
        the root in its own canonical spelling — the verified oracle maps
        ``""`` to ``"."`` at its type boundary by design.
        """
        _require(backend, cap)
        with pytest.raises(InvalidPath) as exc:
            _ROOT_FILE_OP_CALLS[op](backend, root)
        assert is_root(exc.value.path), f"error names {exc.value.path!r}, not the root"

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("BE-012")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_delete_root_with_missing_ok_still_raises(self, backend: Backend, root: str) -> None:
        """``missing_ok`` tolerates a missing path, never a wrong-typed one.

        Without this cell a backend can satisfy the sibling test and still
        silently no-op on ``delete(root, missing_ok=True)`` — which one did,
        returning ``None`` and reporting success for a call that deleted
        nothing.
        """
        _require(backend, Capability.DELETE, Capability.WRITE)
        backend.write("rootmok/a.txt", b"x")
        with pytest.raises(InvalidPath) as exc:
            backend.delete(root, missing_ok=True)
        assert is_root(exc.value.path)
        assert backend.exists("rootmok/a.txt") is True

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("BE-008")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    @pytest.mark.parametrize("overwrite", _OVERWRITE_MODES)
    @pytest.mark.parametrize(("op", "cap"), _ROOT_WRITE_OPS)
    def test_write_to_root_is_refused_and_the_store_survives(
        self, backend: Backend, root: str, overwrite: bool, op: str, cap: Capability
    ) -> None:
        """A write *to* the root is refused, and the store is intact afterwards.

        The error class is the cheap half. The half that matters is the second
        assertion: BUG-259 was a backend that raised ``InvalidPath`` on four of
        its six write cells and had *already occupied its own container* with a
        regular file by the time it did — the refusal arrived from the layer
        above the backend, after the bytes. A cell asserting only the raise
        passes on that.

        So this seeds a file first and reads it back after. It is the strongest
        claim conformance can make from outside a backend: whatever the write
        did, the store still answers as a store.

        Two bounds, both structural. The corruption itself is visible only from
        the storage system's own side, which this suite has no handle on; and it
        needs an **absent container**, which no conformance fixture arranges
        (BK-345 owns that gap). So a backend whose container can go absent also
        pins this against that state in its own per-backend home, where both the
        fixture and the server-side assertion are available.

        **Both overwrite modes**, because they reach the write by different
        routes and the clause binds both — see ``_OVERWRITE_MODES``.
        """
        _require(backend, cap, Capability.WRITE, Capability.READ)
        backend.write("rootwrite/a.txt", b"seed")
        with pytest.raises(InvalidPath) as exc:
            _ROOT_WRITE_OP_CALLS[op](backend, root, overwrite)
        assert is_root(exc.value.path), f"error names {exc.value.path!r}, not the root"
        assert backend.read_bytes("rootwrite/a.txt") == b"seed"
        assert backend.is_folder(root) is True

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("BE-008")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    @pytest.mark.parametrize(("op", "cap"), _ROOT_WRITE_DST_OPS)
    def test_root_as_move_or_copy_destination_is_refused(
        self, backend: Backend, root: str, op: str, cap: Capability
    ) -> None:
        """A ``move``/``copy`` *destination* that is the root is a write to the root.

        The sibling above covers the three writers; this covers the other two
        ways to write. It exists because the reasoning that made it unnecessary
        held on one namespace and not another: a hierarchical backend refuses the
        destination by observation, so this cell only changes the message there,
        while on a flat namespace nothing observes and ``move(src, ".")``
        **returned cleanly having deleted the source**.

        Hence the third assertion. Asserting only the error class would pass on a
        backend that raised after moving the bytes, and asserting the source
        still exists is what separates a refusal from a silent data loss.
        """
        _require(backend, cap, Capability.WRITE, Capability.READ)
        backend.write("rootdst/src.txt", b"seed")
        with pytest.raises(InvalidPath) as exc:
            getattr(backend, op)("rootdst/src.txt", root)
        assert is_root(exc.value.path), f"error names {exc.value.path!r}, not the root"
        assert backend.read_bytes("rootdst/src.txt") == b"seed", f"{op} consumed its source"
        assert backend.is_folder(root) is True


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestBackendRead:
    """BE-006 through BE-007: read operations."""

    @pytest.mark.spec("BE-006")
    def test_read_returns_binary_stream(self, backend: Backend) -> None:
        backend.write("data.bin", b"\x00\x01\x02")
        with backend.read("data.bin") as stream:
            assert stream.read() == b"\x00\x01\x02"

    @pytest.mark.spec("BE-007")
    @pytest.mark.spec("SQL-BLOB-021")
    @pytest.mark.spec("MEM-011")
    def test_read_bytes(self, backend: Backend) -> None:
        backend.write("file.txt", b"content")
        assert backend.read_bytes("file.txt") == b"content"

    @pytest.mark.spec("BE-006")
    @pytest.mark.spec("BE-007")
    @pytest.mark.spec("SIO-004")
    @pytest.mark.parametrize(
        "method",
        [pytest.param("read", id="read_stream"), pytest.param("read_bytes", id="read_bytes")],
    )
    def test_not_found(self, backend: Backend, method: str) -> None:
        with pytest.raises(NotFound):
            getattr(backend, method)("missing.txt")


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestBackendWrite:
    """BE-008 through BE-009: write operations."""

    @pytest.mark.spec("BE-008")
    def test_write_creates_file(self, backend: Backend) -> None:
        backend.write("new.txt", b"hello")
        assert backend.read_bytes("new.txt") == b"hello"

    @pytest.mark.spec("BE-008")
    def test_write_raises_already_exists(self, backend: Backend) -> None:
        backend.write("exists.txt", b"first")
        with pytest.raises(AlreadyExists):
            backend.write("exists.txt", b"second", overwrite=False)

    @pytest.mark.spec("BE-008")
    def test_write_overwrite(self, backend: Backend) -> None:
        backend.write("over.txt", b"first")
        backend.write("over.txt", b"second", overwrite=True)
        assert backend.read_bytes("over.txt") == b"second"

    @pytest.mark.spec("BE-008")
    def test_write_from_binaryio(self, backend: Backend) -> None:
        backend.write("stream.txt", io.BytesIO(b"streamed"))
        assert backend.read_bytes("stream.txt") == b"streamed"

    @pytest.mark.spec("BE-009")
    def test_write_creates_intermediate_dirs(self, backend: Backend) -> None:
        backend.write("a/b/c/deep.txt", b"deep")
        assert backend.read_bytes("a/b/c/deep.txt") == b"deep"


@pytest.mark.parametrize("backend", fixture_params(Capability.DELETE), indirect=True)
class TestBackendDelete:
    """BE-012 through BE-013: delete operations."""

    @pytest.mark.spec("BE-012")
    @pytest.mark.spec("SQL-BLOB-024")
    def test_delete_removes_file(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("del.txt", b"bye")
        backend.delete("del.txt")
        assert backend.exists("del.txt") is False

    @pytest.mark.spec("BE-013")
    def test_delete_folder_empty(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        if _fixture_record(backend).flat_namespace:
            pytest.skip("Virtual folders vanish when last object is deleted (S3-009/AZ-006/SQL-BLOB-flat)")
        backend.write("dir/file.txt", b"x")
        backend.delete("dir/file.txt")
        backend.delete_folder("dir")
        assert backend.exists("dir") is False

    @pytest.mark.spec("BE-013")
    @pytest.mark.spec("SFTP-016")
    @pytest.mark.spec("AZ-015")
    @pytest.mark.spec("S3-011")
    def test_delete_folder_recursive(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        _seed(backend, {"dir2/a.txt": b"a", "dir2/sub/b.txt": b"b"})
        backend.delete_folder("dir2", recursive=True)
        assert backend.exists("dir2") is False

    @pytest.mark.spec("BE-012")
    @pytest.mark.spec("BE-013")
    @pytest.mark.parametrize(
        ("method", "target"),
        [
            pytest.param("delete", "missing.txt", id="file"),
            pytest.param("delete_folder", "nodir", id="folder"),
        ],
    )
    @pytest.mark.parametrize(
        ("missing_ok", "expect_error"),
        [
            pytest.param(False, True, id="not_found_raises"),
            pytest.param(True, False, id="missing_ok_passes"),
        ],
    )
    def test_delete_missing(
        self,
        backend: Backend,
        method: str,
        target: str,
        missing_ok: bool,
        expect_error: bool,
    ) -> None:
        if expect_error:
            with pytest.raises(NotFound):
                getattr(backend, method)(target, missing_ok=missing_ok)
        else:
            getattr(backend, method)(target, missing_ok=missing_ok)


@pytest.mark.parametrize("backend", fixture_params(), indirect=True)
class TestBackendToKey:
    """NPR-003 through NPR-008: to_key reverse path resolution."""

    @pytest.mark.spec("NPR-003")
    def test_to_key_exists(self, backend: Backend) -> None:
        assert hasattr(backend, "to_key")
        assert callable(backend.to_key)

    @pytest.mark.spec("NPR-004")
    def test_to_key_is_deterministic(self, backend: Backend) -> None:
        assert backend.to_key("some/path") == backend.to_key("some/path")

    @pytest.mark.spec("NPR-005")
    @pytest.mark.spec("MEM-017")
    @pytest.mark.spec("BE-023")
    def test_to_key_passthrough_for_relative(self, backend: Backend) -> None:
        """Relative paths with no matching prefix pass through unchanged."""
        assert isinstance(backend.to_key("some/path"), str)

    @pytest.mark.spec("NPR-003")
    def test_to_key_round_trip_with_listing(self, backend: Backend) -> None:
        """Paths from list_files can be converted back via to_key."""
        _require(backend, Capability.LIST, Capability.WRITE)
        backend.write("tk/a.txt", b"a")
        files = list(backend.list_files("tk"))
        assert len(files) == 1
        assert backend.read_bytes(str(files[0].path)) == b"a"


pytestmark_extended = pytest.mark.extended_conformance


@pytest.mark.extended_conformance
@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestWriteReadRoundTrip:
    """Write then read: content must match exactly (Dafny WriteReadConsistency)."""

    @pytest.mark.spec("BE-006")
    @pytest.mark.spec("BE-008")
    @pytest.mark.parametrize(
        "content",
        [
            pytest.param(b"", id="empty"),
            pytest.param(b"\x00\x01\x02\xff", id="binary"),
            pytest.param(b"hello world", id="text"),
            pytest.param(b"x" * 10_000, id="large"),
        ],
    )
    def test_roundtrip(self, backend: Backend, content: bytes) -> None:
        backend.write("ec_rt.bin", content, overwrite=True)
        assert backend.read_bytes("ec_rt.bin") == content


@pytest.mark.extended_conformance
@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestOperationalConsistency:
    """Cross-cutting operational invariants."""

    @pytest.mark.spec("BE-004")
    @pytest.mark.spec("BE-008")
    def test_exists_after_write(self, backend: Backend) -> None:
        backend.write("ec_eaw.txt", b"x")
        assert backend.exists("ec_eaw.txt") is True

    @pytest.mark.spec("BE-004")
    @pytest.mark.spec("BE-012")
    def test_exists_after_delete(self, backend: Backend) -> None:
        _require(backend, Capability.DELETE)
        backend.write("ec_ead.txt", b"x")
        backend.delete("ec_ead.txt")
        assert backend.exists("ec_ead.txt") is False

    @pytest.mark.spec("BE-008")
    def test_write_overwrite_true_replaces(self, backend: Backend) -> None:
        backend.write("ec_wot.txt", b"first")
        backend.write("ec_wot.txt", b"second", overwrite=True)
        assert backend.read_bytes("ec_wot.txt") == b"second"

    @pytest.mark.spec("BE-008")
    def test_write_overwrite_false_rejects(self, backend: Backend) -> None:
        backend.write("ec_wof.txt", b"first")
        with pytest.raises(AlreadyExists, match="ec_wof"):
            backend.write("ec_wof.txt", b"second", overwrite=False)

    @pytest.mark.spec("BE-012")
    def test_delete_preserves_siblings(self, backend: Backend) -> None:
        _require(backend, Capability.DELETE)
        _seed(backend, {"ec_sib/a.txt": b"a", "ec_sib/b.txt": b"b"})
        backend.delete("ec_sib/a.txt")
        assert not backend.exists("ec_sib/a.txt")
        assert backend.read_bytes("ec_sib/b.txt") == b"b"

    @pytest.mark.spec("BE-014")
    def test_list_files_returns_fileinfo_with_name(self, backend: Backend) -> None:
        _require(backend, Capability.LIST)
        backend.write("ec_lfi/x.txt", b"x")
        files = list(backend.list_files("ec_lfi"))
        assert len(files) >= 1
        assert files[0].name == "x.txt"
        assert str(files[0].path).endswith("x.txt")

    @pytest.mark.spec("BE-016")
    def test_get_file_info_size(self, backend: Backend) -> None:
        data = b"hello world"
        backend.write("ec_gfis.txt", data)
        info = backend.get_file_info("ec_gfis.txt")
        assert info.size == len(data)


@pytest.mark.extended_conformance
@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestBackendQueryMethodsTypeConflicts:
    """BE-004, BE-005, BE-021: query-method behaviour under file-as-directory-component."""

    @pytest.mark.spec("BE-004")
    @pytest.mark.spec("BE-005")
    @pytest.mark.spec("BE-021")
    @pytest.mark.parametrize(
        "method",
        [
            pytest.param("exists", id="exists"),
            pytest.param("is_file", id="is_file"),
            pytest.param("is_folder", id="is_folder"),
        ],
    )
    def test_query_methods_return_false_when_ancestor_is_file(self, backend: Backend, method: str) -> None:
        """Query methods return False for paths with file-as-directory-component ancestor."""
        backend.write("a/b", b"file_content")
        assert getattr(backend, method)("a/b/c") is False
        assert getattr(backend, method)("a/b/c/d") is False

    @pytest.mark.spec("BE-004")
    @pytest.mark.spec("BE-005")
    @pytest.mark.spec("BE-021")
    @pytest.mark.parametrize(
        "method",
        [
            pytest.param("exists", id="exists"),
            pytest.param("is_file", id="is_file"),
            pytest.param("is_folder", id="is_folder"),
        ],
    )
    def test_all_query_methods_return_false_on_type_conflict(self, backend: Backend, method: str) -> None:
        """All three query methods return False consistently for type conflicts."""
        backend.write("file", b"content")
        assert getattr(backend, method)("file/subpath") is False

    @pytest.mark.spec("BE-021")
    def test_query_methods_distinct_from_non_existent_paths(self, backend: Backend) -> None:
        """Query methods return False both for non-existent and type-conflict paths."""
        backend.write("a/b", b"file_content")
        assert backend.exists("a/b/c") is False
        assert backend.is_file("a/b/c") is False
        assert backend.is_folder("a/b/c") is False
        assert backend.exists("x/y/z") is False
        assert backend.is_file("x/y/z") is False
        assert backend.is_folder("x/y/z") is False
