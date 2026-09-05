"""The SFTP rename fallback's overwrite window -- AW-003 / SFTP-014 / SFTP-018.

``_rename_fallback`` and ``_move_fallback`` promote by displacing whatever is at
the destination and renaming onto it, because a server without
``posix-rename@openssh.com`` cannot rename onto an existing path. That window is
where the caller's pre-existing file lives, and this file pins what happens to it
when the promote fails.

The stall half of the window is in ``test_io_timeout.py``, which needs the relay.
Here the promote fails for a **non-dead** reason -- ``EACCES``, ``EIO`` -- which
needs no stall at all: the connection is live throughout, so the backend can both
fail and recover within the same call. That is the case BUG-272 measured, and the
one where the old cleanup destroyed the destination *and* the temp.
"""

from __future__ import annotations

import errno
import uuid
from typing import TYPE_CHECKING, Any

import pytest

# Guard: skip entire module if dependencies are missing
pytest.importorskip("paramiko", reason="paramiko not installed")

from remote_store._errors import PermissionDenied, RemoteStoreError  # noqa: E402
from tests.backends.fixtures._state import INFRA  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store.backends._sftp import SFTPBackend


@pytest.fixture
def sftp_backend() -> Iterator[SFTPBackend]:
    """SFTPBackend against the in-process paramiko server (no Docker)."""
    if INFRA.sftp_inproc_port is None:
        pytest.skip("in-process SFTP server unavailable")
    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

    backend = SFTPBackend(
        host="127.0.0.1",
        port=INFRA.sftp_inproc_port,
        username="testuser",
        password="testpass",
        base_path=f"/fb_{uuid.uuid4().hex[:8]}",
        host_key_policy=HostKeyPolicy.AUTO_ADD,
        connect_kwargs={"allow_agent": False, "look_for_keys": False},
    )
    try:
        yield backend
    finally:
        backend.close()


def _break_posix_rename(backend: Any) -> None:
    """Make the live client behave like a server without ``posix-rename@openssh.com``.

    The sibling of ``test_io_timeout.py``'s helper of the same name, which
    carries the full reasoning: no fixture server omits the extension, and this
    is the cheap way to stage the fallback -- **not** the only route into it, since
    any non-dead ``posix_rename`` failure reaches it.
    """
    import paramiko

    def unsupported(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("Operation unsupported")

    backend.unwrap(paramiko.SFTPClient).posix_rename = unsupported


def _deny_promote_onto(backend: Any, target: str, code: int) -> None:
    """Fail every ``rename`` onto *target* except one recovering a displaced original.

    Reproduces a server that refuses the promote itself: the fallback's own
    displace (whose destination is the backup name, not *target*) goes through,
    and so does a rename putting a ``.~bak.`` artifact back. Letting the recovery
    through is deliberate -- deny it too and the test measures the harness rather
    than what the backend does when it still can act.
    """
    import paramiko

    client = backend.unwrap(paramiko.SFTPClient)
    original = client.rename

    def denied(src: str, dst: str, *args: Any, **kwargs: Any) -> Any:
        recovering = src.rsplit("/", 1)[-1].startswith(".~bak.")
        if dst.rsplit("/", 1)[-1] == target and not recovering:
            raise OSError(code, "staged promote failure")
        return original(src, dst, *args, **kwargs)

    client.rename = denied


def _strict_rename(backend: Any) -> None:
    """Make ``rename`` refuse an occupied destination, as SFTP v3 requires.

    The fixture server implements ``rename`` with ``os.rename``, which on POSIX
    replaces the destination silently — so on it every rename-onto-existing
    succeeds and the fallback's whole reason for displacing first is invisible.
    A server that lacks ``posix-rename@openssh.com`` is by definition one whose
    ``rename`` follows the v3 rule, so a test about that server class has to
    stage the rule too; without it, a restore that renames onto an occupied path
    passes here and fails in the field.

    Apply before the other staging helpers, so their wrappers sit outside this
    one.
    """
    import paramiko

    client = backend.unwrap(paramiko.SFTPClient)
    original = client.rename

    def strict(src: str, dst: str, *args: Any, **kwargs: Any) -> Any:
        try:
            client.stat(dst)
        except OSError:
            pass
        else:
            raise OSError(errno.EEXIST, "destination exists")
        return original(src, dst, *args, **kwargs)

    client.rename = strict


def _deny_removing(backend: Any, target: str, code: int) -> None:
    """Fail every ``remove`` of *target*, leaving every other unlink alone.

    Ends ``_copy_and_delete`` at its last step, after the destination has been
    written — the cheapest way to stage a copy rung that fails with the
    destination already occupied. The fallback's own cleanup unlinks other names,
    so scoping to *target* is what keeps this a staged server failure rather than
    a blanket one.
    """
    import paramiko

    client = backend.unwrap(paramiko.SFTPClient)
    original = client.remove

    def denied(path: str, *args: Any, **kwargs: Any) -> Any:
        if path.rsplit("/", 1)[-1] == target:
            raise OSError(code, "staged remove failure")
        return original(path, *args, **kwargs)

    client.remove = denied


def _litter(backend: Any) -> list[str]:
    """Names of the fallback's own artifacts left in the store root."""
    return [
        str(entry).rsplit("/", 1)[-1]
        for entry in backend.list_files("")
        if str(entry).rsplit("/", 1)[-1].startswith((".~tmp.", ".~bak."))
    ]


@pytest.mark.spec("AW-003")
@pytest.mark.spec("SFTP-014")
@pytest.mark.parametrize(
    ("code", "expected"),
    [(errno.EACCES, PermissionDenied), (errno.EIO, RemoteStoreError)],
    ids=["eacces", "eio"],
)
@pytest.mark.parametrize("op", ["write_atomic", "open_atomic"])
def test_a_failed_promote_leaves_the_destination_as_it_found_it(
    sftp_backend: SFTPBackend, op: str, code: int, expected: type[Exception]
) -> None:
    """BUG-272: a non-dead promote failure must not cost the caller their file.

    The fallback has to clear the destination before it can rename onto it, so
    between the two calls the caller's file is not at its path. When the rename
    then fails for a reason the connection survives -- the server denies it, the
    store errors -- the backend is still able to act, and what it does with that
    ability is the whole of this test: the destination goes back to the content it
    had, and nothing of the fallback's own is left in the directory.

    Before the fix this measured the opposite, and both runs are recorded because
    the second is what makes the first a defect rather than a quirk: the
    destination was removed outright, the failure then ran the ``write_atomic`` /
    ``open_atomic`` cleanup, which unlinked the temp *because* the connection was
    demonstrably alive -- and neither the old file nor the new payload existed
    anywhere. Run against the pre-fix code this file's four cases fail with
    ``NotFound`` on the read below.

    ``move`` is deliberately absent: its fallback answers the same staged failure
    by copying instead, which the next test pins.
    """
    backend: Any = sftp_backend
    dst = f"dst_{uuid.uuid4().hex[:8]}.bin"
    old, new = b"OLD" * 100, b"NEW" * 100

    backend.write(dst, old)

    _break_posix_rename(backend)
    _deny_promote_onto(backend, dst, code)

    def _run() -> None:
        if op == "open_atomic":
            with backend.open_atomic(dst, overwrite=True) as handle:
                handle.write(new)
        else:
            backend.write_atomic(dst, new, overwrite=True)

    with pytest.raises(expected):
        _run()

    assert backend.read_bytes(dst) == old, (
        "the promote failed on a live connection, so the destination must hold what it "
        "held before the call -- a caller told their write failed has not lost the file "
        "they had"
    )
    assert _litter(backend) == [], "the fallback's temp and backup are its own to clean up"


@pytest.mark.spec("SFTP-018")
@pytest.mark.parametrize("code", [errno.EACCES, errno.EIO], ids=["eacces", "eio"])
def test_move_copies_when_both_renames_fail(sftp_backend: SFTPBackend, code: int) -> None:
    """``move`` has a third rung the atomic paths do not, and it changes the verdict.

    Deny the promote on a live connection and ``_move_fallback`` does not report
    the failure at all: it falls through to ``_copy_and_delete`` and the move
    completes. So the destroyed-destination state BUG-272 measured for
    ``write_atomic`` / ``open_atomic`` is not reachable this way for ``move`` --
    only a *dead* connection, which stops the copy too, leaves its destination
    displaced.

    Pinned because the fallback's ordering has to survive that third rung: the
    copy writes the destination while it stands displaced, so a backup released
    too early would take the new file with it.
    """
    backend: Any = sftp_backend
    tag = uuid.uuid4().hex[:8]
    src, dst = f"src_{tag}.bin", f"dst_{tag}.bin"
    old, new = b"OLD" * 100, b"NEW" * 100

    backend.write(src, new)
    backend.write(dst, old)

    _break_posix_rename(backend)
    _deny_promote_onto(backend, dst, code)

    backend.move(src, dst, overwrite=True)

    assert backend.read_bytes(dst) == new
    assert not backend.exists(src), "a completed move takes the source with it"
    assert _litter(backend) == []


@pytest.mark.spec("SFTP-018")
@pytest.mark.spec("AW-003")
def test_a_failed_copy_rung_still_gives_the_destination_back(sftp_backend: SFTPBackend) -> None:
    """The restore's hard case: the destination is occupied again by the time it runs.

    ``_copy_and_delete`` opens the destination ``"w"`` before it can fail, so any
    failure past that point — here the source unlink that ends it — leaves a copy
    of the payload at the path the backup has to go back to. Renaming onto an
    occupied path is the one operation the servers this fallback exists for
    refuse, so the restore has to clear the target first; without that it fails
    silently and the caller is left with a reported failure, a destination they
    did not ask for, and their old file under a generated name.

    Staged on a live connection throughout, which is what separates this from the
    dead-channel residue in ``test_io_timeout.py``: there the restore is skipped
    by design, here it must run and succeed.
    """
    backend: Any = sftp_backend
    tag = uuid.uuid4().hex[:8]
    src, dst = f"src_{tag}.bin", f"dst_{tag}.bin"
    old, new = b"OLD" * 100, b"NEW" * 100

    backend.write(src, new)
    backend.write(dst, old)

    _break_posix_rename(backend)
    _strict_rename(backend)
    _deny_promote_onto(backend, dst, errno.EACCES)
    _deny_removing(backend, src, errno.EACCES)

    with pytest.raises(PermissionDenied):
        backend.move(src, dst, overwrite=True)

    assert backend.read_bytes(dst) == old, (
        "the move failed, so the destination must hold what it held — the copy rung's "
        "output is this operation's own half-done work, not something to hand the caller"
    )
    assert backend.read_bytes(src) == new, "a failed move leaves its source in place"
    assert _litter(backend) == []


@pytest.mark.spec("AW-003")
@pytest.mark.spec("SFTP-014")
@pytest.mark.parametrize("op", ["write_atomic", "open_atomic"])
def test_the_fallback_still_creates_a_destination_that_was_not_there(sftp_backend: SFTPBackend, op: str) -> None:
    """``overwrite=True`` with nothing at the destination has nothing to displace.

    The guard the fix adds keys on displacing an existing file, so the path where
    there is none must stay a plain promote. Pinned because it is the branch a
    displace-and-restore is most likely to break: the displace fails ``ENOENT``,
    which is not a failure of the write.
    """
    backend: Any = sftp_backend
    dst = f"fresh_{uuid.uuid4().hex[:8]}.bin"
    payload = b"NEW" * 100

    _break_posix_rename(backend)

    if op == "open_atomic":
        with backend.open_atomic(dst, overwrite=True) as handle:
            handle.write(payload)
    else:
        backend.write_atomic(dst, payload, overwrite=True)

    assert backend.read_bytes(dst) == payload
    assert _litter(backend) == []


@pytest.mark.spec("AW-003")
@pytest.mark.spec("SFTP-014")
@pytest.mark.spec("SFTP-018")
@pytest.mark.parametrize("op", ["write_atomic", "open_atomic", "move"])
def test_the_fallback_replaces_an_existing_destination(sftp_backend: SFTPBackend, op: str) -> None:
    """The success path the window exists for, on the same staged server.

    Displacing the destination rather than removing it must not cost the overwrite
    itself: the new content lands, the old file is gone, and the backup does not
    outlive the call it was taken for.

    Staged with the v3 rename rule, which is what makes this an assertion about
    the fallback rather than about the fixture: on the permissive ``os.rename``
    the fixture server implements, a promote onto the occupied destination
    succeeds on its own and the test would pass with the displace deleted
    outright.
    """
    backend: Any = sftp_backend
    tag = uuid.uuid4().hex[:8]
    src, dst = f"src_{tag}.bin", f"dst_{tag}.bin"
    old, new = b"OLD" * 100, b"NEW" * 100

    if op == "move":
        backend.write(src, new)
    backend.write(dst, old)

    _break_posix_rename(backend)
    _strict_rename(backend)

    if op == "move":
        backend.move(src, dst, overwrite=True)
    elif op == "open_atomic":
        with backend.open_atomic(dst, overwrite=True) as handle:
            handle.write(new)
    else:
        backend.write_atomic(dst, new, overwrite=True)

    assert backend.read_bytes(dst) == new
    assert _litter(backend) == []
    if op == "move":
        assert not backend.exists(src), "a completed move takes the source with it"
