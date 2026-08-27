"""What ``LocalBackend`` does when its root directory is deleted underneath it.

BE-021's absent-container rule says a tolerant delete treats an absent container
as an absent path. On ``LocalBackend`` the container is the root directory, so
the rule applies here as it does everywhere — and this module exists because for
a long time that is *not* what happened.

**The divergence, as it was.** With the root deleted, every operation but
``glob`` and ``check_health`` raised ``InvalidPath("Path escapes root
directory")``. Not ``NotFound``, and not a silent return under ``missing_ok``.
The cause was in ``_within_root``: it walks up from the target to the deepest
lexically-existing ancestor for its symlink-escape check, and once the root was
gone that walk climbed *past* the root, so
``anchor.resolve().relative_to(self._root)`` raised ``ValueError`` and
containment was reported as an escape. Nothing was escaping — the store was
absent — and ``InvalidPath`` was the worst of the three plausible answers, since
it tells the caller their path is malformed when the path is fine.

**Why this module is worth its weight.** The claim that Local already treated an
absent root as an absent path was written into BE-021's rationale and into
BUG-243's trace, as the argument that tolerating "makes flat-namespace agree with
the hierarchical backends". (It was *not* in
``_flat_ns._children_or_absent_container``'s docstring, which an earlier version
of this paragraph asserted; ``git log -S`` finds the phrase in no revision of
that file.) It was false, and it was false in a way reading could not catch:
``delete`` and ``delete_folder`` both look correct in isolation
(``full.exists()`` → ``missing_ok`` → return), because ``_resolve`` raised two
lines earlier. Two readers checked the code and both missed it; running it took
seconds. `sdd/TESTING.md`'s rule that behaviour must be executed rather than
inspected is the whole of the lesson, and it is why the cells below are an
enumeration of the operation surface rather than a sample of it.

**Two guards the fix must not have weakened**, both pinned here: a path that
really does point outside the root is still an escape while the root is gone, and
the root's own spellings still answer BE-029 rather than reporting the store
missing. The first is what makes the containment check worth having; the second
is what ``check_health`` — which does report an absent root, and is the operation
that exists to — is measured against.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from remote_store._errors import InvalidPath, NotFound
from remote_store.backends._local import LocalBackend

if TYPE_CHECKING:
    from collections.abc import Callable

    from remote_store._models import WriteResult

# The behaviour pinned here comes from ``Path.resolve()`` / ``relative_to()``
# semantics in ``_within_root``, which differ most on macOS and Windows — the
# platforms this mark is what runs the file on.
pytestmark = pytest.mark.os_sensitive


@dataclass(frozen=True)
class _SizeOnly:
    """The one field the recreate cell asserts on, for the writer that returns nothing."""

    size: int


def _open_atomic_write(backend: LocalBackend, path: str) -> _SizeOnly:
    """Write one byte through ``open_atomic`` and report the size, like a ``WriteResult``.

    ``open_atomic`` yields a stream and returns nothing, so it cannot be dropped
    into the recreate cell's ``(result, path)`` shape directly. Entering the
    block is the point: the guard under test fires on ``__enter__``, and the
    recreate behaviour only happens inside it.
    """
    with backend.open_atomic(path) as stream:
        stream.write(b"x")
    return _SizeOnly(size=1)


@pytest.fixture
def backend(tmp_path: Path) -> LocalBackend:
    """A ``LocalBackend`` holding one file, whose root is then deleted."""
    root = tmp_path / "store"
    root.mkdir()
    instance = LocalBackend(str(root))
    instance.write("folder/object.txt", b"payload")
    shutil.rmtree(root)
    return instance


@pytest.mark.spec("BE-012", "BE-013", "BE-021")
class TestAbsentRootReadsAsAbsentPath:
    """What BE-021 requires of an absent container, applied to Local's root."""

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt", missing_ok=True)),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True, missing_ok=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_tolerant_delete_returns_cleanly(
        self,
        backend: LocalBackend,
        op_name: str,
        call: Callable[[LocalBackend], None],
    ) -> None:
        assert call(backend) is None, f"{op_name} must tolerate an absent root under missing_ok"

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt")),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_strict_delete_raises_not_found(
        self,
        backend: LocalBackend,
        op_name: str,
        call: Callable[[LocalBackend], None],
    ) -> None:
        with pytest.raises(NotFound) as exc_info:
            call(backend)
        assert exc_info.value.backend == "local"


@pytest.mark.spec("BE-004", "BE-005")
class TestAbsentRootProbesAnswerFalse:
    """BE-004 / BE-005: the three probes never raise, and an absent path is ``False``."""

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("exists", lambda b: b.exists("folder/object.txt")),
            ("is_file", lambda b: b.is_file("folder/object.txt")),
            ("is_folder", lambda b: b.is_folder("folder")),
        ],
        ids=["exists", "is_file", "is_folder"],
    )
    def test_probe_answers_false(
        self,
        backend: LocalBackend,
        op_name: str,
        call: Callable[[LocalBackend], bool],
    ) -> None:
        assert call(backend) is False, f"{op_name} must answer False for a path in an absent store"


@pytest.mark.spec("BE-006", "BE-017", "BE-021")
class TestAbsentRootReadsRaiseNotFound:
    """Everything BE-021's canonical table sends to ``NotFound`` still does.

    § Reach is explicit that the absent-container clause decides the two
    tolerant deletes and re-decides nothing else: these operations "already had
    an answer for an absent container before this clause, and keep it". That
    answer is the table's existence row, and reaching it requires the
    containment check to stop reporting an escape first.
    """

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("read", lambda b: b.read("folder/object.txt")),
            ("read_bytes", lambda b: b.read_bytes("folder/object.txt")),
            # Not overridden by LocalBackend — the ABC default delegates to
            # read(), so this cell is what makes the inherited path an enumerated
            # member rather than an assumed one.
            ("read_seekable", lambda b: b.read_seekable("folder/object.txt")),
            ("get_file_info", lambda b: b.get_file_info("folder/object.txt")),
            ("get_folder_info", lambda b: b.get_folder_info("folder")),
            ("move_src", lambda b: b.move("folder/object.txt", "folder/other.txt")),
            ("copy_src", lambda b: b.copy("folder/object.txt", "folder/other.txt")),
        ],
        ids=["read", "read_bytes", "read_seekable", "get_file_info", "get_folder_info", "move_src", "copy_src"],
    )
    def test_operation_raises_not_found(
        self,
        backend: LocalBackend,
        op_name: str,
        call: Callable[[LocalBackend], object],
    ) -> None:
        with pytest.raises(NotFound) as exc_info:
            call(backend)
        assert exc_info.value.backend == "local"


@pytest.mark.spec("BE-014", "BE-015", "BE-021", "BE-026")
class TestAbsentRootListingsAreEmpty:
    """An absent container holds nothing, so every listing is empty rather than an error.

    ``glob`` is in the table for parity, not for coverage of its containment
    check. It never went through ``_resolve``, so it answered correctly
    throughout the divergence, and this cell holds it to that answer.

    It does **not** reach ``glob``'s own ``_within_root`` call: with the root
    absent ``self._root.glob(pattern)`` yields nothing, so the loop body that
    filters each item never runs. Measured with a ``sys.settrace`` line counter
    over ``_within_root.__code__`` — 0 calls from this cell — and confirmed by
    deleting the filter outright, which leaves all 70 cells in this module
    green. That check is fenced instead by
    ``test_concurrency.py::TestLocalGlobSymlinkEscape``, the one cell in the
    suite the same deletion does fail.
    """

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("list_files", lambda b: list(b.list_files(""))),
            ("list_files_recursive", lambda b: list(b.list_files("", recursive=True))),
            ("list_files_depth", lambda b: list(b.list_files("", recursive=True, max_depth=1))),
            ("list_folders", lambda b: list(b.list_folders(""))),
            ("iter_children", lambda b: list(b.iter_children(""))),
            ("glob", lambda b: list(b.glob("**/*.txt"))),
        ],
        ids=["list_files", "list_files_recursive", "list_files_depth", "list_folders", "iter_children", "glob"],
    )
    def test_listing_is_empty(
        self,
        backend: LocalBackend,
        op_name: str,
        call: Callable[[LocalBackend], list[object]],
    ) -> None:
        assert call(backend) == [], f"{op_name} must yield nothing when the store is absent"


@pytest.mark.spec("BE-029")
class TestAbsentRootStillAnswersAsTheRoot:
    """BE-029: the root is a folder by definition, not by observation.

    Local passed these cells by observation until now — ``__init__`` mkdirs the
    root, so a stat agreed. With the root deleted the stat disagrees, and BE-029
    is unconditional, so the answers have to come from the key. Parity with
    ``SFTPBackend``, whose ``base_path`` is created lazily and which has
    short-circuited exactly these cells for exactly this reason.

    BE-021's absent-container rule does not reach here: it decides what a path
    *in* the container answers, and the root is the container's own spelling.
    """

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_root_is_still_a_folder(self, backend: LocalBackend, root: str) -> None:
        assert backend.exists(root) is True
        assert backend.is_folder(root) is True
        # Records the full trio, but only the first two lines fence a
        # short-circuit here: with the root absent the observed ``is_file``
        # answer is ``False`` too, so the third line holds either way.
        # Removing the ``is_file`` short-circuit fails no cell in this class —
        # it is fenced by ``test_check_health_reports_a_root_path_that_is_not_
        # a_directory``, the one cell where the root is a regular file and the
        # definitional and observed answers part company.
        assert backend.is_file(root) is False

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_root_folder_info_aggregates_to_zero(self, backend: LocalBackend, root: str) -> None:
        """An absent root aggregates to zero rather than reporting itself missing."""
        info = backend.get_folder_info(root)
        assert info.file_count == 0
        assert info.total_size == 0

    @pytest.mark.spec("BE-021")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("read", lambda b, p: b.read(p)),
            ("read_bytes", lambda b, p: b.read_bytes(p)),
            ("read_seekable", lambda b, p: b.read_seekable(p)),
            ("get_file_info", lambda b, p: b.get_file_info(p)),
            ("delete", lambda b, p: b.delete(p)),
            ("delete_missing_ok", lambda b, p: b.delete(p, missing_ok=True)),
            ("move_src", lambda b, p: b.move(p, "dst.txt")),
            ("copy_src", lambda b, p: b.copy(p, "dst.txt")),
        ],
        ids=[
            "read",
            "read_bytes",
            "read_seekable",
            "get_file_info",
            "delete",
            "delete_missing_ok",
            "move_src",
            "copy_src",
        ],
    )
    def test_file_operation_on_root_is_a_type_error(
        self,
        backend: LocalBackend,
        root: str,
        op_name: str,
        call: Callable[[LocalBackend, str], object],
    ) -> None:
        """``InvalidPath``, not ``NotFound`` — and ``missing_ok`` does not silence it.

        The root is a folder, so BE-021's type-mismatch row governs it. Without
        the pre-check this answers from a stat, which reports ENOENT once the
        root is gone: the operation would call a wrong-typed path missing.
        """
        with pytest.raises(InvalidPath) as exc_info:
            call(backend, root)
        assert exc_info.value.path == root, f"{op_name} must name the root it rejected"

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_folder_shaped_operations_still_accept_the_root(self, backend: LocalBackend, root: str) -> None:
        """The pre-check is a type guard, not a mutation guard.

        ``delete_folder`` and ``get_folder_info`` are folder-shaped and
        legitimately take the root; a pre-check applied to them would turn the
        absent-container tolerance this module opens with back into an error.
        """
        assert backend.delete_folder(root, recursive=True, missing_ok=True) is None

    @pytest.mark.spec("BE-013")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    @pytest.mark.parametrize("recursive", [True, False], ids=["recursive", "nonrecursive"])
    def test_strict_delete_folder_on_the_root_answers_from_the_filesystem(
        self, backend: LocalBackend, root: str, recursive: bool
    ) -> None:
        """The one root cell that answers by observation, pinned with its bound.

        ``delete_folder(root, missing_ok=False)`` raises ``NotFound`` on an
        absent root, while ``exists(root)`` in the sibling above reports the root
        present. The two disagree, and deliberately: BE-029 § Out of scope
        excludes ``delete_folder("")`` from the root rule, `Store` refuses a root
        delete before it reaches a backend (STORE-002), and ``SFTPBackend`` — the
        other hierarchical backend, whose ``base_path`` is likewise absent on an
        untouched store — answers this cell identically from its own stat.

        So this is pinned rather than reconciled: making it definitional would
        put Local alone among the backends, on a call no spec decides and no
        supported caller can reach. What the cell buys is that the disagreement
        is now a recorded answer instead of an unexamined one.
        """
        with pytest.raises(NotFound):
            backend.delete_folder(root, recursive=recursive)


@pytest.mark.spec("BE-021")
class TestTheContainmentGuardStillGuards:
    """A real escape is still an escape — with the root gone and with it present.

    ``_within_root`` is the symlink-escape guard (BUG-220, BUG-221). The fix
    stops its ancestor walk at the root, so the case it must not have opened is
    a path that genuinely points outside.
    """

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("exists", lambda b: b.exists("../evil")),
            ("delete", lambda b: b.delete("../evil", missing_ok=True)),
            ("read", lambda b: b.read("../evil")),
        ],
        ids=["exists", "delete", "read"],
    )
    def test_lexical_escape_still_rejected_with_the_root_gone(
        self,
        backend: LocalBackend,
        op_name: str,
        call: Callable[[LocalBackend], object],
    ) -> None:
        with pytest.raises(InvalidPath, match="escapes root"):
            call(backend)

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="symlink creation requires SeCreateSymbolicLinkPrivilege on Windows",
    )
    def test_symlink_escape_still_rejected_with_the_root_present(self, tmp_path: Path) -> None:
        """The guard's original job, unchanged: a symlink out of the root is an escape.

        Held here as well as in ``test_concurrency.py`` because this file is
        where the walk was changed; a fix that silently traded the symlink check
        for the absent-root answer would pass every other cell in this module.
        """
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_bytes(b"secret")
        root = tmp_path / "store"
        root.mkdir()
        (root / "link").symlink_to(outside, target_is_directory=True)

        instance = LocalBackend(str(root))
        with pytest.raises(InvalidPath, match="escapes root"):
            instance.read_bytes("link/secret.txt")

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="symlink creation requires SeCreateSymbolicLinkPrivilege on Windows",
    )
    def test_root_replaced_by_a_symlink_is_an_escape(self, tmp_path: Path) -> None:
        """A root swapped for a symlink is still an escape, not an absence.

        This cell pins the ``anchor.resolve().relative_to(self._root)`` leg of
        the guard: with the root replaced by a symlink out of the tree, the
        answer must stay ``InvalidPath``, not become the absent-root answer the
        rest of this module asserts. Neutralising that resolve leg alone fails
        this cell and its sibling above, and no others in the module.

        **It does not exercise the walk stop, and an earlier version of this
        docstring wrongly claimed it did.** ``self._root`` is resolved once in
        ``__init__``, so after ``rmdir`` + ``symlink_to`` the root path still
        *lexists* — as a symlink. The walk climbs ``missing.txt`` to the root,
        the ``while not os.path.lexists(anchor)`` condition then goes false
        *at* the root, and the loop exits before the body's ``break`` is
        reached. Measured with a ``sys.settrace`` line counter over
        ``_within_root.__code__``: the clamp ``if`` is evaluated once and the
        ``break`` is taken **0** times here, against 1 for the plain-deleted
        root. The earlier claim rested on an ``os.path.lexists`` call count,
        which cannot tell "the body ran" from "the break fired" — the very
        discrimination it was cited for.

        The clamp is fenced instead by the 30 cells that fail when the ``break``
        is deleted; the same 30 are exactly the cells the line counter shows
        executing it. No cell is needed for the hazard the earlier docstring
        imagined — a fix answering "root missing → contained" without resolving
        — because when the clamp fires every component from target to root is
        absent, so there is no symlink left for the walk to follow and
        ``relative_to`` alone decides.

        ``exists`` is in the list and is expected to *raise* here rather than
        answer ``False``. That is not a breach of BE-004's never-raise rule: the
        rule is about missing paths and traversal failures, and the method's own
        ``Raises:`` block has always documented ``InvalidPath`` for a path that
        escapes the root. An escape is a different verdict from an absence, which
        is the whole distinction this fix exists to restore.
        """
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_bytes(b"secret")
        root = tmp_path / "store"
        root.mkdir()

        instance = LocalBackend(str(root))
        root.rmdir()
        root.symlink_to(outside, target_is_directory=True)

        for call in (
            lambda: instance.read_bytes("missing.txt"),
            lambda: instance.delete("missing.txt", missing_ok=True),
            lambda: instance.exists("missing.txt"),
        ):
            with pytest.raises(InvalidPath, match="escapes root"):
                call()


@pytest.mark.spec("BE-008")
class TestWriteRecreatesTheRoot:
    """``write`` answers an absent root by recreating it, and that is deliberate.

    BE-021 § Reach names ``write`` as the one roster operation the
    absent-container clause declines to decide, leaving it to a backend spec —
    and Local has none. So the answer is the backend's own, pinned here rather
    than left implicit: it is consistent with ``__init__``, which mkdirs the
    root on construction, and with ``SFTPBackend``, whose ``base_path`` is
    created by the first write. A caller who needs "is my store still there?"
    asks ``check_health``, which the last cell of this class holds to the
    opposite answer in the same absent-root state.

    The class also carries the write-refusal cells (including ``open_atomic``,
    which refuses on ``__enter__`` rather than at the call), the ``move``/``copy``
    destination cells, and a second ``check_health`` cell for a root occupied by
    a regular *file*. That last one builds its own store instead of using the
    absent-root fixture, because a root holding the wrong kind of thing is the
    one state the fixture cannot express — and it is the only cell in the module
    that fences the ``is_file`` short-circuit.
    """

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("write", lambda b: (b.write("folder/new.txt", b"x"), "folder/new.txt")),
            ("write_atomic", lambda b: (b.write_atomic("folder/new2.txt", b"x"), "folder/new2.txt")),
            ("open_atomic", lambda b: (_open_atomic_write(b, "folder/new3.txt"), "folder/new3.txt")),
        ],
        ids=["write", "write_atomic", "open_atomic"],
    )
    def test_write_recreates_the_root_and_succeeds(
        self,
        backend: LocalBackend,
        op_name: str,
        call: Callable[[LocalBackend], tuple[WriteResult | _SizeOnly, str]],
    ) -> None:
        result, written = call(backend)
        assert result.size == 1
        assert backend.exists(written), f"{op_name} reported success but {written} is not readable"
        assert backend.read_bytes(written) == b"x"

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("write", lambda b, p: b.write(p, b"x")),
            ("write_atomic", lambda b, p: b.write_atomic(p, b"x")),
            ("write_overwrite", lambda b, p: b.write(p, b"x", overwrite=True)),
        ],
        ids=["write", "write_atomic", "write_overwrite"],
    )
    def test_writing_to_the_root_never_puts_a_file_there(
        self,
        backend: LocalBackend,
        root: str,
        op_name: str,
        call: Callable[[LocalBackend, str], object],
    ) -> None:
        """Writing *to* the root is refused, and refused before anything is written.

        Measured, and it is why the writers carry a definitional root guard
        rather than the ``is_dir()`` check they had. With the root present that
        check fires. With the root gone it answers ``False``, and the write ran
        to completion: ``parent.mkdir`` recreated the tree, the bytes landed at
        the root path, and only then did building the ``WriteResult`` reject the
        empty key — leaving the store root as a regular **file**. The error was
        the least of it.

        So the assertion is on the filesystem, not the error class. It is also
        deliberately not ``backend.is_file(root)``: that answers ``False`` from
        the BE-029 short-circuit without looking at the disk, so it would pass
        on exactly the corruption this cell exists to catch.
        """
        on_disk = Path(backend.native_path(root))
        with pytest.raises(InvalidPath):
            call(backend, root)
        assert not on_disk.is_file(), f"{op_name} left a regular file at the store root"

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_open_atomic_on_the_root_is_refused_on_enter(self, backend: LocalBackend, root: str) -> None:
        """The third writer, which the sibling above cannot reach.

        ``open_atomic`` is a ``@contextmanager``: calling it builds a generator
        and runs no body, so the guard fires on ``__enter__`` rather than at the
        call. A copy of the sibling's ``pytest.raises(...): call(...)`` shape
        would pass without ever entering the block, and would still pass with the
        guard deleted.
        """
        on_disk = Path(backend.native_path(root))
        with pytest.raises(InvalidPath), backend.open_atomic(root) as stream:
            stream.write(b"x")
        assert not on_disk.is_file(), "open_atomic left a regular file at the store root"

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("write", lambda b, p: b.write(p, b"x")),
            ("write_atomic", lambda b, p: b.write_atomic(p, b"x")),
            ("open_atomic", lambda b, p: _open_atomic_write(b, p)),
        ],
        ids=["write", "write_atomic", "open_atomic"],
    )
    def test_writing_to_the_root_is_refused_with_the_root_present_too(
        self,
        tmp_path: Path,
        root: str,
        op_name: str,
        call: Callable[[LocalBackend, str], object],
    ) -> None:
        """The guard is unconditional, so the ordinary state needs a cell as well.

        Every other cell in this class runs against the absent-root fixture, and
        the present root is the overwhelmingly common case — the one where this
        PR changed the answer silently. It used to come from ``full.is_dir()``
        as ``"Cannot write — '' exists as a directory"``; it now comes from the
        pre-check, before the disk is touched. Conformance cannot cover it:
        BE-029 § Out of scope excludes writes *to* the root, so ``_ROOT_FILE_OPS``
        carries no writer.

        Uses its own store rather than the module fixture, because the point is
        precisely that the root is there.
        """
        root_dir = tmp_path / "present"
        root_dir.mkdir()
        instance = LocalBackend(str(root_dir))
        instance.write("keep.txt", b"payload")

        with pytest.raises(InvalidPath, match="store root"):
            call(instance, root)
        assert root_dir.is_dir(), f"{op_name} must leave the root a directory"
        assert instance.read_bytes("keep.txt") == b"payload"

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("move", lambda b, p: b.move("keep.txt", p)),
            ("copy", lambda b, p: b.copy("keep.txt", p)),
        ],
        ids=["move", "copy"],
    )
    def test_the_root_as_a_move_or_copy_destination_never_becomes_a_file(
        self,
        backend: LocalBackend,
        root: str,
        op_name: str,
        call: Callable[[LocalBackend, str], object],
    ) -> None:
        """The two writers that did *not* get the definitional guard, pinned anyway.

        ``_reject_root_as_write_target`` has three call sites, not five: ``move``
        and ``copy`` write too, but only their *source* is guarded. The reason is
        that their destination cannot reach the corruption the guard exists to
        prevent, and that reason is worth a cell rather than only a docstring.
        With the root gone nothing can exist beneath it, so the source check
        fails first and the destination is never examined; with the root present
        ``dst_full.is_dir()`` fires. Either way the answer is an error and the
        root is not left a regular file — which is the assertion that matters,
        as the sibling cells above establish.

        Stated plainly, because this module has thrice shipped a docstring
        claiming coverage it did not have: **this cell fences no guard.** It
        passes with every part of the BUG-247 change reverted, because the
        checks that save it are older than the change. It is a characterisation
        test — it pins an outcome that currently holds for a reason recorded in
        ``_reject_root_as_write_target``, so that adding a ``parent.mkdir`` on
        the destination path, or guarding the source differently, fails here
        instead of silently reintroducing the corruption.
        """
        on_disk = Path(backend.native_path(root))
        with pytest.raises((NotFound, InvalidPath)):
            call(backend, root)
        assert not on_disk.is_file(), f"{op_name} left a regular file at the store root"

    @pytest.mark.spec("PING-002", "PING-003", "BE-029")
    def test_check_health_reports_a_root_path_that_is_not_a_directory(self, tmp_path: Path) -> None:
        """The state only ``check_health`` can see, and the reason it tests ``is_dir()``.

        The BE-029 short-circuits answer the root from the key, so once they
        landed no operation observed what is actually *at* the root path. With
        ``check_health`` testing mere existence, a root replaced by a regular
        **file** reported a healthy, empty store from every probe on the backend
        — the one state where the definitional answers become a lie rather than
        a convention.

        This cell is what makes the ``exists()`` → ``is_dir()`` change
        falsifiable: the absent-root cell below cannot, because ``exists()`` is
        ``False`` there too and passes either way. Asserting the probes
        alongside is deliberate — they are *expected* to keep answering by
        definition, so the trio states which operation is allowed to be
        optimistic and which is not.

        Only two of the three probe lines fence a short-circuit. This is the one
        state where the root path holds something, so ``exists("")`` observes
        ``True`` as well and its line holds either way; it is recorded for the
        contrast, not for coverage. ``is_folder`` and ``is_file`` do carry
        signal here, and this is the only cell in the module that fences the
        ``is_file`` short-circuit at all.
        """
        root = tmp_path / "store"
        root.mkdir()
        instance = LocalBackend(str(root))
        shutil.rmtree(root)
        root.write_bytes(b"not a directory")

        with pytest.raises(NotFound, match="Root directory not found"):
            instance.check_health()
        assert instance.exists("") is True
        assert instance.is_folder("") is True
        assert instance.is_file("") is False

    @pytest.mark.spec("PING-002", "PING-003")
    def test_check_health_still_reports_the_absent_root(self, backend: LocalBackend) -> None:
        """The one operation whose job is to notice, and it still does.

        This is what makes the BE-029 answers above safe: they say the root is a
        folder, not that the store is healthy, and the two questions have
        different operations.
        """
        with pytest.raises(NotFound, match="Root directory not found"):
            backend.check_health()
