"""What ``SFTPBackend`` does when its ``base_path`` does not exist.

BE-021's absent-container rule binds every backend, and this is the SFTP
container: the remote directory every key hangs off. Like `LocalBackend`'s root
it can be absent — a typo in configuration, or a directory removed under a live
backend — so the rule applies here as it does to a missing bucket.

This module exists because the clause claims to bind every backend and, until
it was written, three of them had been *measured* and this one had only been
read. That distinction stopped being academic during the same change:
`LocalBackend` was read as compliant by two independent reviewers and turned out
to raise `InvalidPath` for every operation once its root was deleted, because
the guard that fires sits upstream of the code both readers were looking at.
Reading a hierarchical backend's delete body is demonstrably not enough to know
what it answers, so this one is executed.

Stage 1: the in-process paramiko server, no Docker. The absent container needs
no teardown to arrange — a `base_path` that was never created *is* the case.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("paramiko", reason="paramiko not installed")

from pathlib import Path  # noqa: E402

from remote_store._errors import InvalidPath, NotFound  # noqa: E402
from tests.backends.fixtures._state import INFRA  # noqa: E402
from tests.backends.sftp._helpers import StubSFTPServer  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from remote_store.backends._sftp import SFTPBackend


def _server_side(backend: SFTPBackend) -> Path:
    """The real filesystem path the in-process server serves as ``base_path``.

    The container's state has to be read from the server's own filesystem, not
    through the backend: every root probe answers definitionally (BE-029), so
    ``is_folder("")`` reports ``True`` for a ``base_path`` that is a regular
    file — the precise corruption these cells exist to catch would pass an
    assertion phrased against the backend.
    """
    return Path(StubSFTPServer.ROOT) / backend.native_path("").lstrip("/")


def _open_atomic_write(backend: SFTPBackend, path: str, *, overwrite: bool = False) -> None:
    """Drive ``open_atomic`` to completion; it refuses on ``__enter__``, not at the call."""
    with backend.open_atomic(path, overwrite=overwrite) as handle:
        handle.write(b"x")


@pytest.fixture
def absent_base_path_backend() -> Iterator[SFTPBackend]:
    """An ``SFTPBackend`` whose ``base_path`` was never created on the server."""
    if INFRA.sftp_inproc_port is None:
        pytest.skip("in-process SFTP server unavailable")
    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

    backend = SFTPBackend(
        host="127.0.0.1",
        port=INFRA.sftp_inproc_port,
        username="testuser",
        password="testpass",
        base_path=f"/absent_{uuid.uuid4().hex[:8]}",
        host_key_policy=HostKeyPolicy.AUTO_ADD,
        connect_kwargs={"allow_agent": False, "look_for_keys": False},
    )
    try:
        yield backend
    finally:
        backend.close()


@pytest.mark.spec("BE-012", "BE-013", "BE-021")
class TestAbsentBasePathReadsAsAbsentPath:
    """An absent ``base_path`` is an absent path, on the same terms as a missing bucket."""

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
        absent_base_path_backend: SFTPBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        assert call(absent_base_path_backend) is None, f"{op_name} must tolerate an absent base_path"

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
        absent_base_path_backend: SFTPBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """Both halves, so the tolerance is pinned as belonging to ``missing_ok``."""
        with pytest.raises(NotFound) as exc_info:
            call(absent_base_path_backend)
        assert exc_info.value.backend == "sftp"


_ROOT_WRITES: list = [
    pytest.param(lambda b, p: b.write(p, b"x"), id="write"),
    pytest.param(lambda b, p: b.write(p, b"x", overwrite=True), id="write_overwrite"),
    pytest.param(lambda b, p: b.write_atomic(p, b"x"), id="write_atomic"),
    pytest.param(lambda b, p: b.write_atomic(p, b"x", overwrite=True), id="write_atomic_overwrite"),
    pytest.param(lambda b, p: _open_atomic_write(b, p), id="open_atomic"),
    pytest.param(lambda b, p: _open_atomic_write(b, p, overwrite=True), id="open_atomic_overwrite"),
]
"""Every write-shaped entry point, in both overwrite modes.

Both modes, because they take different routes to the same open: ``write`` and
``write_atomic`` skip their existence stat entirely when ``overwrite=True``, so
a guard placed on the ``overwrite=False`` branch alone would leave half the
surface corrupting. ``open_atomic`` stats eagerly in both modes and is here for
the opposite reason — it is the one that returned *cleanly* while doing it.
"""


@pytest.mark.spec("BE-029", "BE-021")
class TestWritingToTheRootNeverOccupiesTheContainer:
    """A write *to* the store root is refused before the transport is touched.

    BUG-259. With ``base_path`` absent, every writer ran to completion against
    the container path itself: ``_ensure_parent_dirs`` created the tree, the
    bytes landed at ``base_path``, and the store's container was left a regular
    **file**. ``write`` / ``write_atomic`` did raise afterwards, but from the
    ``RemotePath`` layer *after* the write and with no ``backend=`` attribute;
    ``open_atomic`` returned cleanly having done it.

    The backend's own guard was the observational ``stat`` — the container is a
    directory, so ``_classify_existing_target`` fires — and that check answers
    "absent" once the container is gone, which is the state in which it has to
    hold. So the rejection is definitional, like every other root answer.

    This is ``LocalBackend``'s defect on the other hierarchical backend
    (BUG-247), found by that work's measuring pass rather than by reading.
    """

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    @pytest.mark.parametrize("call", _ROOT_WRITES)
    def test_write_to_the_root_leaves_no_file_at_base_path(
        self,
        absent_base_path_backend: SFTPBackend,
        root: str,
        call: Callable[[SFTPBackend, str], object],
    ) -> None:
        """The assertion is on the server's filesystem, not on the error class.

        An error was already raised on four of these six cells before the fix
        and the container was corrupt anyway, so asserting the raise alone
        reproduces nothing. ``_server_side`` says why the backend cannot be
        asked instead.
        """
        on_disk = _server_side(absent_base_path_backend)
        with pytest.raises(InvalidPath) as exc_info:
            call(absent_base_path_backend, root)
        assert not on_disk.is_file(), "the write left a regular file at base_path"
        assert exc_info.value.backend == "sftp", "the refusal came from above the backend, not from it"

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    @pytest.mark.parametrize("call", _ROOT_WRITES)
    def test_write_to_the_root_does_not_create_the_container(
        self,
        absent_base_path_backend: SFTPBackend,
        root: str,
        call: Callable[[SFTPBackend, str], object],
    ) -> None:
        """Refused *before* the transport, so not even the parent tree is made.

        Separate from the sibling because "no file there" and "nothing there"
        are different claims, and only the second one fences the guard's
        position: a guard placed after ``_ensure_parent_dirs`` would satisfy the
        sibling while still creating the container as a side effect of a call
        that failed.
        """
        on_disk = _server_side(absent_base_path_backend)
        with pytest.raises(InvalidPath):
            call(absent_base_path_backend, root)
        assert not on_disk.exists(), "a refused root write still created base_path"

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_write_under_the_root_still_creates_the_container(
        self, absent_base_path_backend: SFTPBackend, root: str
    ) -> None:
        """The guard refuses the root key, never a key beneath it.

        SFTP creates ``base_path`` lazily on first write and that is the
        documented behaviour, so this is the control for the refusal cells
        above: a guard that over-matched — by prefix, or by running on the
        resolved native path rather than the key — would break the ordinary
        write, and this is the only cell that would notice.

        Both spellings are exercised because ``"./nested/file.txt"`` and
        ``"nested/file.txt"`` reach the guard as different strings and both must
        pass it. Under-matching is **not** what this cell catches: a guard that
        let the dot spelling through would make a success-asserting cell succeed.
        That direction is the refusal cells' job, and they are parametrised over
        both spellings for it.
        """
        key = f"{root}/nested/file.txt" if root == "." else "nested/file.txt"
        result = absent_base_path_backend.write(key, b"x")
        assert result.size == 1
        assert _server_side(absent_base_path_backend).is_dir(), "the container was not created"
        assert absent_base_path_backend.read_bytes("nested/file.txt") == b"x"

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("move", lambda b, p: b.move("a.txt", p)),
            ("copy", lambda b, p: b.copy("a.txt", p)),
        ],
        ids=["move", "copy"],
    )
    def test_move_and_copy_destination_cannot_reach_the_corruption(
        self,
        absent_base_path_backend: SFTPBackend,
        root: str,
        op_name: str,
        call: Callable[[SFTPBackend, str], object],
    ) -> None:
        """The root destination is refused before the source is looked for.

        This cell used to assert ``NotFound`` on the source, and read that as
        proof the destination needed no guard of its own: with ``base_path``
        absent nothing can exist beneath it, so the source stat fails first.
        The premise was true and the conclusion did not travel — measured on a
        flat namespace, the same shape returned cleanly and deleted the source.

        With the destination guarded the order inverts, and the new order is the
        one the contract asks for: the root destination is a permanent, key-
        decidable error, so it is refused at precondition step (0), before the
        round trip that would report the source missing. A caller who names the
        root as a destination hears about *that*, whether or not their source
        happens to exist.
        """
        on_disk = _server_side(absent_base_path_backend)
        with pytest.raises(InvalidPath) as exc_info:
            call(absent_base_path_backend, root)
        assert exc_info.value.path == root, f"{op_name} named {exc_info.value.path!r}, not the destination"
        assert exc_info.value.backend == "sftp"
        assert not on_disk.exists(), f"{op_name} created base_path before failing"
