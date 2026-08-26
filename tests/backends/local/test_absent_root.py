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
absent root as an absent path was written into BE-021's rationale, into
``_flat_ns._children_or_absent_container``'s docstring, and into BUG-243's trace,
as the argument that tolerating "makes flat-namespace agree with the hierarchical
backends". It was false, and it was false in a way reading could not catch:
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
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from remote_store._errors import InvalidPath, NotFound
from remote_store.backends._local import LocalBackend

if TYPE_CHECKING:
    from collections.abc import Callable

# The behaviour pinned here comes from ``Path.resolve()`` / ``relative_to()``
# semantics in ``_within_root``, which differ most on macOS and Windows — the
# platforms this mark is what runs the file on.
pytestmark = pytest.mark.os_sensitive


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
            ("get_file_info", lambda b: b.get_file_info("folder/object.txt")),
            ("get_folder_info", lambda b: b.get_folder_info("folder")),
            ("move_src", lambda b: b.move("folder/object.txt", "folder/other.txt")),
            ("copy_src", lambda b: b.copy("folder/object.txt", "folder/other.txt")),
        ],
        ids=["read", "read_bytes", "get_file_info", "get_folder_info", "move_src", "copy_src"],
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


@pytest.mark.spec("BE-014", "BE-015", "BE-021")
class TestAbsentRootListingsAreEmpty:
    """An absent container holds nothing, so every listing is empty rather than an error.

    ``glob`` is in the table because it is the *other* ``_within_root`` caller.
    It never went through ``_resolve``, so it answered correctly throughout the
    divergence — which is exactly why it belongs here: it is the one listing
    whose correctness this fix did not have to produce, and a regression in it
    would otherwise be invisible.
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
            ("get_file_info", lambda b, p: b.get_file_info(p)),
            ("delete", lambda b, p: b.delete(p)),
            ("delete_missing_ok", lambda b, p: b.delete(p, missing_ok=True)),
            ("move_src", lambda b, p: b.move(p, "dst.txt")),
            ("copy_src", lambda b, p: b.copy(p, "dst.txt")),
        ],
        ids=["read", "read_bytes", "get_file_info", "delete", "delete_missing_ok", "move_src", "copy_src"],
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


@pytest.mark.spec("BE-008")
class TestWriteRecreatesTheRoot:
    """``write`` answers an absent root by recreating it, and that is deliberate.

    BE-021 § Reach names ``write`` as the one roster operation the
    absent-container clause declines to decide, leaving it to a backend spec —
    and Local has none. So the answer is the backend's own, pinned here rather
    than left implicit: it is consistent with ``__init__``, which mkdirs the
    root on construction, and with ``SFTPBackend``, whose ``base_path`` is
    created by the first write. A caller who needs "is my store still there?"
    asks ``check_health``, which the cell below holds to the opposite answer in
    the same state.
    """

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("write", lambda b: b.write("folder/new.txt", b"x")),
            ("write_atomic", lambda b: b.write_atomic("folder/new2.txt", b"x")),
        ],
        ids=["write", "write_atomic"],
    )
    def test_write_recreates_the_root_and_succeeds(
        self,
        backend: LocalBackend,
        op_name: str,
        call: Callable[[LocalBackend], object],
    ) -> None:
        result = call(backend)
        assert result.size == 1  # type: ignore[attr-defined]
        assert backend.exists("folder/new.txt") or backend.exists("folder/new2.txt")

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

    @pytest.mark.spec("BE-026")
    def test_check_health_still_reports_the_absent_root(self, backend: LocalBackend) -> None:
        """The one operation whose job is to notice, and it still does.

        This is what makes the BE-029 answers above safe: they say the root is a
        folder, not that the store is healthy, and the two questions have
        different operations.
        """
        with pytest.raises(NotFound, match="Root directory not found"):
            backend.check_health()
