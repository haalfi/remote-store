"""LocalBackend concurrency — BUG-220 regression + symlink-escape guard.

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
"""

from __future__ import annotations

import shutil
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
