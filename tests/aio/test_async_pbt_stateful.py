"""Stateful property-based test for the async backend API (ID-155).

Drives a Hypothesis ``RuleBasedStateMachine`` against two implementations of
the async backend contract simultaneously:

* ``AsyncMemoryBackend`` — native async (spec ASYNC-001..ASYNC-029).
* ``SyncBackendAdapter(MemoryBackend())`` — sync backend bridged via
  ``asyncio.to_thread()`` (spec ASYNC-030..ASYNC-037).

Each rule executes the same operation on both backends inside a single shared
event loop and asserts they remain in lock-step with a Python ``dict`` model
(plus an explicit ``dirs`` set, mirroring the BUG-183 fix in the sync suite).
Divergence between the two implementations of the same contract — or between
either implementation and the model — fails the test.

Hypothesis 6.x has no ``AsyncRuleBasedStateMachine``; we drive async rules
through a per-instance event loop with ``loop.run_until_complete``. This keeps
``asyncio.Lock`` state and ``asyncio.to_thread`` executor identity stable
across the rule sequence, which is the relevant property under test.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import pytest
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

import remote_store._errors
from remote_store.aio import AsyncMemoryBackend, SyncBackendAdapter
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from typing import TypeVar

    T = TypeVar("T")

# Path segments mirror tests/test_pbt_stateful.py — small alphabet for high
# collision probability (which is what surfaces ordering bugs).
_segment = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_"),
    min_size=1,
    max_size=10,
)
_path = st.lists(_segment, min_size=1, max_size=3).map("/".join)
_content = st.binary(min_size=0, max_size=100)


def _ancestors(path: str) -> list[str]:
    """Ancestor directory paths of *path* (``"a/b/c"`` -> ``["a", "a/b"]``)."""
    parts = path.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


def _can_write(path: str, files: dict[str, bytes], dirs: set[str]) -> bool:
    """Return True if *path* can be written without a file/directory conflict."""
    if path in dirs:
        return False
    return all(a not in files for a in _ancestors(path))


@pytest.mark.spec("ASYNC-001", "ASYNC-008", "ASYNC-012", "ASYNC-013", "ASYNC-018", "ASYNC-019", "ASYNC-030")
class AsyncBackendModel(RuleBasedStateMachine):
    """Both async backends must behave like a dict[str, bytes] + explicit dirs.

    Two backends are driven in lock-step by every rule; the model is the
    arbiter both must agree with. The explicit ``dirs`` set is required for
    the same reason as in the sync suite: ``delete()`` does not auto-prune
    ancestor dir nodes (spec MEM-DS-006 / BUG-183).
    """

    def __init__(self) -> None:
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.native = AsyncMemoryBackend()
        self.adapted = SyncBackendAdapter(MemoryBackend())
        self.model: dict[str, bytes] = {}
        self.dirs: set[str] = set()

    def teardown(self) -> None:
        try:
            self.loop.run_until_complete(self.native.aclose())
            self.loop.run_until_complete(self.adapted.aclose())
        finally:
            self.loop.close()

    def _run(self, coro: Awaitable[T]) -> T:  # type: ignore[type-var]
        return self.loop.run_until_complete(coro)

    @rule(path=_path, data=_content)
    def write_new(self, path: str, data: bytes) -> None:
        """Write to a path that should not exist yet (ASYNC-008)."""
        if path in self.model or not _can_write(path, self.model, self.dirs):
            return
        self._run(self.native.write(path, data))
        self._run(self.adapted.write(path, data))
        self.model[path] = data
        self.dirs.update(_ancestors(path))

    @rule(path=_path, data=_content)
    def write_overwrite(self, path: str, data: bytes) -> None:
        """Write with overwrite=True (ASYNC-008)."""
        if path not in self.model and not _can_write(path, self.model, self.dirs):
            return
        self._run(self.native.write(path, data, overwrite=True))
        self._run(self.adapted.write(path, data, overwrite=True))
        self.model[path] = data
        self.dirs.update(_ancestors(path))

    @rule(path=_path, data=_content)
    def write_atomic(self, path: str, data: bytes) -> None:
        """write_atomic with overwrite=True (ASYNC-010)."""
        if path not in self.model and not _can_write(path, self.model, self.dirs):
            return
        self._run(self.native.write_atomic(path, data, overwrite=True))
        self._run(self.adapted.write_atomic(path, data, overwrite=True))
        self.model[path] = data
        self.dirs.update(_ancestors(path))

    @rule(path=_path)
    def read_bytes(self, path: str) -> None:
        """read_bytes must agree with the model on both backends (ASYNC-007)."""
        if path in self.dirs:
            return  # reading a directory raises InvalidPath, not NotFound
        if path in self.model:
            native_result = self._run(self.native.read_bytes(path))
            adapted_result = self._run(self.adapted.read_bytes(path))
            assert native_result == self.model[path], f"native mismatch for {path!r}"
            assert adapted_result == self.model[path], f"adapted mismatch for {path!r}"
        else:
            with pytest.raises(remote_store._errors.NotFound, match=re.escape(path)):
                self._run(self.native.read_bytes(path))
            with pytest.raises(remote_store._errors.NotFound, match=re.escape(path)):
                self._run(self.adapted.read_bytes(path))

    @rule(path=_path)
    def read_streaming(self, path: str) -> None:
        """Streaming read concatenates to the model bytes (ASYNC-006, ASYNC-020)."""
        if path in self.dirs or path not in self.model:
            return

        async def _drain(backend: object) -> bytes:
            chunks: list[bytes] = []
            async for chunk in backend.read(path):  # type: ignore[attr-defined]
                chunks.append(chunk)
            return b"".join(chunks)

        assert self._run(_drain(self.native)) == self.model[path]
        assert self._run(_drain(self.adapted)) == self.model[path]

    @rule(path=_path)
    def exists(self, path: str) -> None:
        """exists is True for files OR live directories on both backends (ASYNC-004)."""
        is_present = path in self.model or path in self.dirs
        assert self._run(self.native.exists(path)) is is_present
        assert self._run(self.adapted.exists(path)) is is_present

    @rule(path=_path)
    def is_file(self, path: str) -> None:
        """is_file matches the model on both backends (ASYNC-005)."""
        is_file = path in self.model
        assert self._run(self.native.is_file(path)) is is_file
        assert self._run(self.adapted.is_file(path)) is is_file

    @rule(path=_path)
    def delete(self, path: str) -> None:
        """Delete an existing file (ASYNC-012). delete() does not prune dirs."""
        if path not in self.model:
            return
        self._run(self.native.delete(path))
        self._run(self.adapted.delete(path))
        del self.model[path]

    @rule(path=_path)
    def delete_missing_ok(self, path: str) -> None:
        """Delete with missing_ok=True is total on file paths (ASYNC-012)."""
        if path in self.dirs:
            return
        self._run(self.native.delete(path, missing_ok=True))
        self._run(self.adapted.delete(path, missing_ok=True))
        self.model.pop(path, None)

    @rule(path=_path)
    def delete_folder(self, path: str) -> None:
        """Recursively delete a live directory (ASYNC-013)."""
        if path not in self.dirs:
            return
        self._run(self.native.delete_folder(path, recursive=True))
        self._run(self.adapted.delete_folder(path, recursive=True))
        prefix = path + "/"
        self.dirs = {d for d in self.dirs if d != path and not d.startswith(prefix)}
        self.model = {k: v for k, v in self.model.items() if not k.startswith(prefix)}

    @rule(src=_path, dst=_path)
    def move(self, src: str, dst: str) -> None:
        """Move a file (ASYNC-018). Skip cases that depend on backend-specific outcomes."""
        if src not in self.model:
            return
        if src == dst:
            return  # no-op, covered separately
        # Skip if dst conflicts: the spec allows InvalidPath vs AlreadyExists
        # vs success-with-overwrite, but the model can't predict which
        # backend-specific guard fires first without duplicating internals.
        if dst in self.dirs or dst in self.model:
            return
        if not _can_write(dst, self.model, self.dirs):
            return
        self._run(self.native.move(src, dst))
        self._run(self.adapted.move(src, dst))
        self.model[dst] = self.model.pop(src)
        self.dirs.update(_ancestors(dst))

    @rule(src=_path, dst=_path)
    def copy(self, src: str, dst: str) -> None:
        """Copy a file (ASYNC-019)."""
        if src not in self.model:
            return
        if dst in self.dirs or dst in self.model:
            return
        if not _can_write(dst, self.model, self.dirs):
            return
        self._run(self.native.copy(src, dst))
        self._run(self.adapted.copy(src, dst))
        self.model[dst] = self.model[src]
        self.dirs.update(_ancestors(dst))

    @rule(path=_path)
    def list_files_flat(self, path: str) -> None:
        """Non-recursive list_files agrees with the model (ASYNC-014)."""
        prefix = path + "/"
        expected = {k for k in self.model if k.startswith(prefix) and "/" not in k[len(prefix) :]}

        async def _list(backend: object) -> set[str]:
            try:
                return {str(f.path) async for f in backend.list_files(path)}  # type: ignore[attr-defined]
            except remote_store._errors.NotFound:
                return set()

        assert self._run(_list(self.native)) == expected
        assert self._run(_list(self.adapted)) == expected

    @invariant()
    def backends_agree_on_existing_files(self) -> None:
        """Every modelled file is readable from both backends with matching bytes."""
        for path, expected in self.model.items():
            assert self._run(self.native.read_bytes(path)) == expected
            assert self._run(self.adapted.read_bytes(path)) == expected


# Hypothesis discovers and runs this automatically.
TestAsyncBackendModel = AsyncBackendModel.TestCase
TestAsyncBackendModel.__module__ = __name__
TestAsyncBackendModel = pytest.mark.pbt(TestAsyncBackendModel)


@pytest.mark.pbt
@pytest.mark.spec("ASYNC-008", "ASYNC-012")
def test_bug183_empty_dir_persists_after_file_delete_async() -> None:
    """Regression: async model must track empty dir nodes left by ``delete()``.

    Mirrors the sync regression in tests/test_pbt_stateful.py — same dir-node
    persistence semantics apply to AsyncMemoryBackend (it shares ``_DirNode``
    with the sync MemoryBackend) and to the adapted sync backend.
    """
    m = AsyncBackendModel()
    try:
        m.write_new(path="0/0", data=b"")
        m.delete(path="0/0")

        assert m._run(m.native.is_folder("0")), "native should retain the empty dir node"
        assert m._run(m.adapted.is_folder("0")), "adapted should retain the empty dir node"
        assert "0" in m.dirs

        # Must be skipped by the rule guard, not reach the backend.
        m.write_new(path="0", data=b"")
        assert "0" in m.dirs
        assert "0" not in m.model
        assert not m._run(m.native.is_file("0"))
        assert not m._run(m.adapted.is_file("0"))
    finally:
        m.teardown()


@pytest.mark.pbt
@pytest.mark.spec("ASYNC-013")
def test_delete_folder_rule_prunes_dirs_and_descendants_async() -> None:
    """Regression: ``delete_folder`` rule must shrink ``self.dirs`` for both backends."""
    m = AsyncBackendModel()
    try:
        m.write_new(path="a/b/c", data=b"x")
        assert m.dirs == {"a", "a/b"}
        assert m.model == {"a/b/c": b"x"}

        m.delete_folder(path="a")
        assert not m._run(m.native.exists("a"))
        assert not m._run(m.adapted.exists("a"))
        assert m.dirs == set()
        assert m.model == {}

        m.write_new(path="a", data=b"y")
        assert m.model == {"a": b"y"}
        assert m._run(m.native.read_bytes("a")) == b"y"
        assert m._run(m.adapted.read_bytes("a")) == b"y"
    finally:
        m.teardown()
