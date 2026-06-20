"""LocalBackend concurrency — BUG-220 regression + symlink-escape guards.

BUG-220: ``LocalBackend._resolve`` did ``(self._root / path).resolve()`` then
``relative_to(self._root)``. On Windows, ``Path.resolve()`` over a path whose
intermediate directories are being created by sibling threads can transiently
return an 8.3 short-name form (e.g. ``LONGDI~1``) that is not ``relative_to`` the
init-time root, so a legitimate concurrent write to a nested key raised a
spurious ``InvalidPath("Path escapes root directory")``.

The regression test reproduces it with **long (>8 char) path components** — the
ingredient that triggers 8.3 short-name generation; short components never get
one, so the race cannot fire. The symlink-escape test pins the safety property
the fix must preserve: ``_resolve`` still rejects a symlink inside root that
points outside it.

BUG-221: ``glob()`` shares ``_resolve``'s containment check via ``_within_root``.
The race described for ``glob`` was found **not reproducible** — a *listed* file
fully exists, so its anchor walk stops at the item itself and the resolve is
stable (the 8.3 flicker needs a non-existent tail). The
``TestLocalGlob*`` classes guard the two properties that matter: glob never
silently drops an in-root file under concurrent creation, and it still skips an
entry reached through a reparse point that escapes root.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from remote_store._errors import InvalidPath
from remote_store.backends._local import LocalBackend

pytestmark = pytest.mark.os_sensitive

# Fan-out and iteration count tuned so the race fires reliably pre-fix on
# Windows (per-iteration repro rate is volume/8dot3name-dependent; ~0.35 here,
# so 24 barrier-synchronised iterations make a clean pre-fix pass vanishingly
# unlikely). Post-fix the count is irrelevant — the race is gone, every
# iteration passes deterministically.
_N_THREADS = 8
_N_ITERS = 24
# Long (>8 char) so Windows generates 8.3 short names for them.
_NESTED_PREFIX = "longdirectorysegmentone/longdirectorysegmenttwo"


def _run_one_race(backend: LocalBackend, iteration: int) -> list[BaseException]:
    """Release N threads simultaneously to write distinct keys under one new dir."""
    barrier = threading.Barrier(_N_THREADS)
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        key = f"iteration{iteration}/{_NESTED_PREFIX}/leaf_{i}.bin"
        barrier.wait()
        try:
            backend.write(key, f"payload-{i}".encode())
        except BaseException as exc:  # noqa: BLE001 -- capture every failure mode for the invariant
            with lock:
                errors.append(exc)

    with ThreadPoolExecutor(max_workers=_N_THREADS) as pool:
        list(pool.map(worker, range(_N_THREADS)))
    return errors


class TestLocalConcurrentNestedWrites:
    """BUG-220: concurrent writes that race to create a shared nested parent."""

    @pytest.mark.spec("BE-008")
    def test_concurrent_nested_writes_no_spurious_invalidpath(self) -> None:
        root = tempfile.mkdtemp(prefix="bug220_")
        try:
            backend = LocalBackend(root=root)
            all_errors: list[BaseException] = []
            for n in range(_N_ITERS):
                all_errors.extend(_run_one_race(backend, n))
            # Invariant: every concurrent write to a distinct nested key succeeds.
            assert not all_errors, f"{len(all_errors)} spurious write failure(s): {all_errors[:3]}"
            # And every write actually landed.
            for n in range(_N_ITERS):
                for i in range(_N_THREADS):
                    key = f"iteration{n}/{_NESTED_PREFIX}/leaf_{i}.bin"
                    assert backend.read_bytes(key) == f"payload-{i}".encode()
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestLocalResolveSymlinkEscape:
    """The fix must keep `_resolve`'s symlink-escape rejection (read/write path)."""

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="symlink creation requires SeCreateSymbolicLinkPrivilege on Windows",
    )
    @pytest.mark.spec("BE-008")
    def test_read_through_symlink_escaping_root_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as root:
            outside_file = Path(outside) / "secret.txt"
            outside_file.write_bytes(b"secret")
            symlink = Path(root) / "escape.txt"
            try:
                symlink.symlink_to(str(outside_file))
            except OSError:
                pytest.skip("symlink creation not permitted on this platform")
            backend = LocalBackend(root=root)
            # Reaching the outside target through an in-root symlink must be rejected.
            with pytest.raises(InvalidPath, match="escapes root"):
                backend.read_bytes("escape.txt")

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="symlink creation requires SeCreateSymbolicLinkPrivilege on Windows",
    )
    @pytest.mark.spec("BE-008")
    def test_write_through_intermediate_symlink_dir_escaping_root_rejected(self) -> None:
        """Non-existent leaf under an in-root symlink *directory* still rejected.

        This is the branch the fix introduced: the leaf does not exist, so the
        anchor walk steps up to the symlink directory and must resolve+reject it.
        The existing direct-leaf test stops the walk immediately (target exists),
        so it never exercises this path.
        """
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as root:
            symdir = Path(root) / "symdir"
            try:
                symdir.symlink_to(outside, target_is_directory=True)
            except OSError:
                pytest.skip("symlink creation not permitted on this platform")
            backend = LocalBackend(root=root)
            # symdir/ -> existing outside dir; the leaf does not exist yet.
            with pytest.raises(InvalidPath, match="escapes root"):
                backend.write("symdir/newfile.bin", b"x")

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="symlink creation requires SeCreateSymbolicLinkPrivilege on Windows",
    )
    @pytest.mark.spec("BE-008")
    def test_write_through_broken_symlink_dir_escaping_root_rejected(self) -> None:
        """A *broken* in-root symlink (missing target) escaping root is rejected.

        Regression guard for the ``lexists`` (not ``exists``) walk condition:
        ``exists()`` follows the link and reports False for a broken symlink, so
        the walk would step *past* it and miss the escape. ``lexists`` stops at
        the link itself, resolves it, and rejects the out-of-root target.
        """
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as root:
            missing_target = Path(outside) / "not-created-yet"
            symdir = Path(root) / "symdir"
            try:
                symdir.symlink_to(missing_target, target_is_directory=True)
            except OSError:
                pytest.skip("symlink creation not permitted on this platform")
            backend = LocalBackend(root=root)
            with pytest.raises(InvalidPath, match="escapes root"):
                backend.write("symdir/newfile.bin", b"x")

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="directory junctions are a Windows-only reparse point",
    )
    @pytest.mark.spec("BE-008")
    def test_write_through_junction_dir_escaping_root_rejected(self) -> None:
        """Windows proof of the escape boundary via a directory **junction**.

        The symlink guards above skip on Windows (symlinks need
        ``SeCreateSymbolicLinkPrivilege``), leaving the platform this fix targets
        with no escape assertion. A directory junction needs no privilege, is a
        reparse point ``resolve()`` follows, and -- like a symlink dir -- is
        **not** ``is_symlink()`` yet **is** ``os.path.lexists`` True, so it
        exercises the same anchor-walk branch the fix introduced. The leaf does
        not exist, so the walk steps up to the junction and must reject it.
        """
        outside = tempfile.mkdtemp(prefix="bug220_jout_")
        root = tempfile.mkdtemp(prefix="bug220_jroot_")
        junction = Path(root) / "jdir"
        try:
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), outside],
                capture_output=True,
                check=False,
            )
            if created.returncode != 0 or not junction.exists():
                pytest.skip("directory junction creation not permitted on this runner")
            backend = LocalBackend(root=root)
            # jdir/ -> existing outside dir; the leaf does not exist yet.
            with pytest.raises(InvalidPath, match="escapes root"):
                backend.write("jdir/newfile.bin", b"x")
        finally:
            # Unlink the junction reparse point *before* removing the tree, so
            # rmtree cannot traverse into (and delete) the outside target. A
            # bare ``os.rmdir`` removes the junction itself, not its contents.
            if junction.exists():
                os.rmdir(junction)
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(outside, ignore_errors=True)


class TestLocalGlobConcurrentCreation:
    """BUG-221: glob() must not silently drop in-root files under concurrent creation.

    The 8.3 flicker that hit ``_resolve`` (a non-existent write tail) cannot fire
    on the listing path — every item glob yields fully exists, so its resolve is
    stable. This deterministic guard pins that property against any future
    reintroduction of a brittle whole-path ``resolve()`` containment check.
    """

    @pytest.mark.spec("GLOB-005")
    def test_glob_returns_every_file_after_concurrent_nested_writes(self) -> None:
        root = tempfile.mkdtemp(prefix="bug221_")
        try:
            backend = LocalBackend(root=root)
            expected: set[str] = set()
            for n in range(_N_ITERS):
                errors = _run_one_race(backend, n)
                assert not errors, f"unexpected write failure(s): {errors[:3]}"
                for i in range(_N_THREADS):
                    expected.add(f"iteration{n}/{_NESTED_PREFIX}/leaf_{i}.bin")
            found = {fi.path.as_posix() for fi in backend.glob("**/*.bin")}
            assert found == expected, f"glob dropped {expected - found}"
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestLocalGlobSymlinkEscape:
    """The shared ``_within_root`` helper must keep glob()'s symlink-escape skip."""

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="symlink creation requires SeCreateSymbolicLinkPrivilege on Windows",
    )
    @pytest.mark.spec("GLOB-005")
    def test_glob_skips_file_reached_through_escaping_symlink_dir(self) -> None:
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as root:
            (Path(outside) / "secret.txt").write_bytes(b"secret")
            symdir = Path(root) / "symdir"
            try:
                symdir.symlink_to(outside, target_is_directory=True)
            except OSError:
                pytest.skip("symlink creation not permitted on this platform")
            backend = LocalBackend(root=root)
            # The explicit pattern descends into the symlink dir; the escaping
            # file it surfaces must be dropped by the containment check.
            assert list(backend.glob("symdir/*.txt")) == []

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="directory junctions are a Windows-only reparse point",
    )
    @pytest.mark.spec("GLOB-005")
    def test_glob_skips_file_reached_through_escaping_junction(self) -> None:
        """Windows proof of the glob escape skip via a directory **junction**.

        Symlink creation needs privilege on Windows, so the POSIX guard skips
        there; a junction needs none, is a reparse point ``resolve()`` follows,
        and ``Path.glob`` descends it. Without the containment check glob would
        yield the out-of-root file (verified: raw traversal does surface it).
        """
        outside = tempfile.mkdtemp(prefix="bug221_jout_")
        root = tempfile.mkdtemp(prefix="bug221_jroot_")
        (Path(outside) / "secret.txt").write_bytes(b"secret")
        junction = Path(root) / "jdir"
        try:
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), outside],
                capture_output=True,
                check=False,
            )
            if created.returncode != 0 or not junction.exists():
                pytest.skip("directory junction creation not permitted on this runner")
            backend = LocalBackend(root=root)
            assert list(backend.glob("jdir/*.txt")) == []
        finally:
            if junction.exists():
                os.rmdir(junction)
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(outside, ignore_errors=True)
