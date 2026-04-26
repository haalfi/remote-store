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
from typing import TYPE_CHECKING, Any

import pytest
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule

import remote_store._errors
from remote_store.aio import AsyncMemoryBackend, SyncBackendAdapter
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from collections.abc import Coroutine
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


class AsyncBackendModel(RuleBasedStateMachine):
    """Both async backends must behave like a dict[str, bytes] + explicit dirs.

    Two backends are driven in lock-step by every rule; the model is the
    arbiter both must agree with. The explicit ``dirs`` set is required for
    the same reason as in the sync suite: ``delete()`` does not auto-prune
    ancestor dir nodes (spec MEM-DS-006 / BUG-183).

    Scope: this suite covers the **happy path** of each rule's spec ID and
    the lock-step agreement between the two backends. Negative-path
    invariants (``AlreadyExists``, ``NotFound``, ``DirectoryNotEmpty``) are
    exercised by the example-based suites — see ``test_async_memory.py``,
    ``test_sync_adapter_conformance.py``, and ``test_async_backend.py``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.native = AsyncMemoryBackend()
        self.adapted = SyncBackendAdapter(MemoryBackend())
        self.model: dict[str, bytes] = {}
        self.dirs: set[str] = set()

    def teardown(self) -> None:
        # Close each backend independently. Today both aclose() impls are
        # effectively no-op (AsyncMemoryBackend inherits the default; the
        # adapter's aclose just delegates to a no-op MemoryBackend.close()),
        # so the symmetric guard is purely defensive: a future native backend
        # with real resources must not see one close skipped because the other
        # raised first.
        try:
            try:
                self.loop.run_until_complete(self.native.aclose())
            finally:
                self.loop.run_until_complete(self.adapted.aclose())
        finally:
            self.loop.close()

    def _run(self, coro: Coroutine[Any, Any, T]) -> T:
        return self.loop.run_until_complete(coro)

    # Rule bodies live as ``_do_*`` helpers so the regression tests at the
    # bottom can drive the same code path without going through the @rule
    # decorator. The @rule-decorated wrappers below are thin adapters that
    # Hypothesis schedules with generated arguments.

    def _do_write_new(self, path: str, data: bytes) -> None:
        if path in self.model or not _can_write(path, self.model, self.dirs):
            return
        self._run(self.native.write(path, data))
        self._run(self.adapted.write(path, data))
        self.model[path] = data
        self.dirs.update(_ancestors(path))

    def _do_write_overwrite(self, path: str, data: bytes) -> None:
        if path not in self.model and not _can_write(path, self.model, self.dirs):
            return
        self._run(self.native.write(path, data, overwrite=True))
        self._run(self.adapted.write(path, data, overwrite=True))
        self.model[path] = data
        self.dirs.update(_ancestors(path))

    def _do_write_atomic(self, path: str, data: bytes) -> None:
        if path not in self.model and not _can_write(path, self.model, self.dirs):
            return
        self._run(self.native.write_atomic(path, data, overwrite=True))
        self._run(self.adapted.write_atomic(path, data, overwrite=True))
        self.model[path] = data
        self.dirs.update(_ancestors(path))

    def _do_read_bytes(self, path: str) -> None:
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

    def _do_read_streaming(self, path: str) -> None:
        if path in self.dirs or path not in self.model:
            return

        async def _drain(backend: object) -> bytes:
            chunks: list[bytes] = []
            async for chunk in backend.read(path):  # type: ignore[attr-defined]
                chunks.append(chunk)
            return b"".join(chunks)

        expected = self.model[path]
        native_actual = self._run(_drain(self.native))
        adapted_actual = self._run(_drain(self.adapted))
        assert native_actual == expected, f"native streaming read({path!r}): {native_actual!r} != {expected!r}"
        assert adapted_actual == expected, f"adapted streaming read({path!r}): {adapted_actual!r} != {expected!r}"

    def _do_exists(self, path: str) -> None:
        is_present = path in self.model or path in self.dirs
        assert self._run(self.native.exists(path)) is is_present
        assert self._run(self.adapted.exists(path)) is is_present

    def _do_is_file(self, path: str) -> None:
        is_file = path in self.model
        assert self._run(self.native.is_file(path)) is is_file
        assert self._run(self.adapted.is_file(path)) is is_file

    def _do_delete(self, path: str) -> None:
        if path not in self.model:
            return
        self._run(self.native.delete(path))
        self._run(self.adapted.delete(path))
        del self.model[path]

    def _do_delete_missing_ok(self, path: str) -> None:
        # Skip directory paths: this is a known lock-step divergence (BUG-184)
        # — MemoryBackend.delete(dir_path, missing_ok=True) raises InvalidPath
        # while AsyncMemoryBackend.delete(dir_path, missing_ok=True) silently
        # returns. Once BUG-184 is fixed and the spec pins the outcome, drop
        # this guard so Hypothesis exercises the directory-path case.
        if path in self.dirs:
            return
        self._run(self.native.delete(path, missing_ok=True))
        self._run(self.adapted.delete(path, missing_ok=True))
        self.model.pop(path, None)

    def _do_delete_folder(self, path: str) -> None:
        if path not in self.dirs:
            return
        self._run(self.native.delete_folder(path, recursive=True))
        self._run(self.adapted.delete_folder(path, recursive=True))
        prefix = path + "/"
        self.dirs = {d for d in self.dirs if d != path and not d.startswith(prefix)}
        # `k != path` is technically redundant — `_can_write` ensures a path
        # cannot be in both `self.model` and `self.dirs` simultaneously — but
        # the guard makes the dependency explicit, so a future relaxation of
        # `_can_write` cannot silently drift this filter.
        self.model = {k: v for k, v in self.model.items() if k != path and not k.startswith(prefix)}

    def _do_move(self, src: str, dst: str) -> None:
        if src not in self.model:
            return
        if src == dst:
            # Same-path move is spec-defined as a no-op when the source exists
            # (ASYNC-047). Drive both backends and assert content survives —
            # otherwise the suite would silently accept an implementation that
            # raised, deleted, or corrupted on a same-path move.
            self._run(self.native.move(src, src))
            self._run(self.adapted.move(src, src))
            expected = self.model[src]
            assert self._run(self.native.read_bytes(src)) == expected, (
                f"native same-path move({src!r}) corrupted content"
            )
            assert self._run(self.adapted.read_bytes(src)) == expected, (
                f"adapted same-path move({src!r}) corrupted content"
            )
            return
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

    def _do_copy(self, src: str, dst: str) -> None:
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

    def _do_list_files_flat(self, path: str) -> None:
        prefix = path + "/"
        expected = {k for k in self.model if k.startswith(prefix) and "/" not in k[len(prefix) :]}

        async def _list(backend: object) -> set[str]:
            try:
                return {str(f.path) async for f in backend.list_files(path)}  # type: ignore[attr-defined]
            except remote_store._errors.NotFound:
                return set()

        native_actual = self._run(_list(self.native))
        adapted_actual = self._run(_list(self.adapted))
        assert native_actual == expected, f"native list_files({path!r}): {native_actual} != {expected}"
        assert adapted_actual == expected, f"adapted list_files({path!r}): {adapted_actual} != {expected}"

    @rule(path=_path, data=_content)
    def write_new(self, path: str, data: bytes) -> None:
        """Write to a path that should not exist yet (ASYNC-008 happy path)."""
        self._do_write_new(path, data)

    @rule(path=_path, data=_content)
    def write_overwrite(self, path: str, data: bytes) -> None:
        """Write with overwrite=True (ASYNC-008 happy path)."""
        self._do_write_overwrite(path, data)

    @rule(path=_path, data=_content)
    def write_atomic(self, path: str, data: bytes) -> None:
        """write_atomic with overwrite=True (ASYNC-010 happy path)."""
        self._do_write_atomic(path, data)

    @rule(path=_path)
    def read_bytes(self, path: str) -> None:
        """read_bytes hits both content-equality and NotFound paths (ASYNC-007)."""
        self._do_read_bytes(path)

    @rule(path=_path)
    def read_streaming(self, path: str) -> None:
        """Streaming read concatenates to the model bytes (ASYNC-006, ASYNC-020).

        Content is capped at 100 bytes (`_content`), and `AsyncMemoryBackend.read`
        emits a single chunk by design — so this rule does not exercise the
        multi-chunk shape of `SyncBackendAdapter.read` (ASYNC-033, 65 KiB
        chunks). Multi-chunk drains are covered by
        `tests/aio/test_sync_adapter_conformance.py` and
        `tests/aio/test_async_to_sync_adapter.py`. The value here is asserting
        that the streaming entry point on both backends remains content-correct
        under arbitrary stateful sequences generated by Hypothesis.
        """
        self._do_read_streaming(path)

    @rule(path=_path)
    def exists(self, path: str) -> None:
        """exists is True for files OR live directories on both backends (ASYNC-004)."""
        self._do_exists(path)

    @rule(path=_path)
    def is_file(self, path: str) -> None:
        """is_file matches the model on both backends (ASYNC-005)."""
        self._do_is_file(path)

    @rule(path=_path)
    def delete(self, path: str) -> None:
        """Delete an existing file (ASYNC-012 happy path). Does not prune dirs."""
        self._do_delete(path)

    @rule(path=_path)
    def delete_missing_ok(self, path: str) -> None:
        """Delete with missing_ok=True is total on file paths (ASYNC-012)."""
        self._do_delete_missing_ok(path)

    @rule(path=_path)
    def delete_folder(self, path: str) -> None:
        """Recursively delete a live directory (ASYNC-013 happy path, recursive=True)."""
        self._do_delete_folder(path)

    @rule(src=_path, dst=_path)
    def move(self, src: str, dst: str) -> None:
        """Move a file (ASYNC-018 happy path; ASYNC-047 same-path no-op). Skip dst-conflict cases."""
        self._do_move(src, dst)

    @rule(src=_path, dst=_path)
    def copy(self, src: str, dst: str) -> None:
        """Copy a file (ASYNC-019 happy path). Skip dst-conflict cases."""
        self._do_copy(src, dst)

    @rule(path=_path)
    def list_files_flat(self, path: str) -> None:
        """Non-recursive list_files agrees with the model (ASYNC-014)."""
        self._do_list_files_flat(path)


# Hypothesis discovers and runs this automatically. Markers are applied to
# the dynamically generated ``TestCase`` (not to ``AsyncBackendModel``) — the
# TestCase does not subclass the state machine, so a marker on the state
# machine would be silently dropped by pytest's collection.
TestAsyncBackendModel = AsyncBackendModel.TestCase
TestAsyncBackendModel.__module__ = __name__
TestAsyncBackendModel = pytest.mark.pbt(TestAsyncBackendModel)
TestAsyncBackendModel = pytest.mark.spec(
    "ASYNC-004",
    "ASYNC-005",
    "ASYNC-006",
    "ASYNC-007",
    "ASYNC-008",
    "ASYNC-009",
    "ASYNC-010",
    "ASYNC-012",
    "ASYNC-013",
    "ASYNC-014",
    "ASYNC-018",
    "ASYNC-019",
    "ASYNC-020",
    "ASYNC-030",
    "ASYNC-047",
)(TestAsyncBackendModel)


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
        m._do_write_new("0/0", b"")
        m._do_delete("0/0")

        assert m._run(m.native.is_folder("0")), "native should retain the empty dir node"
        assert m._run(m.adapted.is_folder("0")), "adapted should retain the empty dir node"
        assert "0" in m.dirs

        # Must be skipped by the rule guard, not reach the backend.
        m._do_write_new("0", b"")
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
        m._do_write_new("a/b/c", b"x")
        assert m.dirs == {"a", "a/b"}
        assert m.model == {"a/b/c": b"x"}

        m._do_delete_folder("a")
        assert not m._run(m.native.exists("a"))
        assert not m._run(m.adapted.exists("a"))
        assert m.dirs == set()
        assert m.model == {}

        m._do_write_new("a", b"y")
        assert m.model == {"a": b"y"}
        assert m._run(m.native.read_bytes("a")) == b"y"
        assert m._run(m.adapted.read_bytes("a")) == b"y"
    finally:
        m.teardown()
