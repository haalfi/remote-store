"""Stateful property-based test: MemoryBackend matches a dict model (BK-139 P4).

Uses Hypothesis ``RuleBasedStateMachine`` to generate random sequences of
write/read/delete/list/exists operations and verify the real backend matches
a simple Python dict at every step.
"""

from __future__ import annotations

import re

import pytest
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule

import remote_store._errors
from remote_store.backends._memory import MemoryBackend

# Strategy for valid path segments (no '/', no null, no '..' or '.')
_segment = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_"),
    min_size=1,
    max_size=10,
)

# Strategy for file paths (1-3 segments joined by '/')
_path = st.lists(_segment, min_size=1, max_size=3).map("/".join)

# Strategy for file content
_content = st.binary(min_size=0, max_size=100)


def _ancestors(path: str) -> list[str]:
    """Ancestor directory paths of *path* (``"a/b/c"`` → ``["a", "a/b"]``)."""
    parts = path.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


def _can_write(path: str, files: dict[str, bytes], dirs: set[str]) -> bool:
    """Return True if *path* can be written without a file/directory conflict."""
    if path in dirs:
        return False
    return all(a not in files for a in _ancestors(path))


class BackendModel(RuleBasedStateMachine):
    """MemoryBackend must behave like a dict[str, bytes] + explicit dirs set.

    Live directory nodes are tracked separately from the file map because
    ``MemoryBackend.delete()`` does not auto-prune ancestor ``_DirNode`` entries
    (spec MEM-DS-006): an empty directory persists until ``delete_folder()``.
    Deriving dirs from the live file map would forget that and diverge from the
    backend on a ``write('a/b') → delete('a/b') → write('a')`` sequence
    (BUG-183).
    """

    def __init__(self) -> None:
        super().__init__()
        self.backend = MemoryBackend()
        self.model: dict[str, bytes] = {}
        self.dirs: set[str] = set()

    @rule(path=_path, data=_content)
    def write_new(self, path: str, data: bytes) -> None:
        """Write to a path that should not exist yet."""
        if path in self.model or not _can_write(path, self.model, self.dirs):
            return  # skip — conflict
        self.backend.write(path, data)
        self.model[path] = data
        self.dirs.update(_ancestors(path))

    @rule(path=_path, data=_content)
    def write_overwrite(self, path: str, data: bytes) -> None:
        """Write with overwrite=True (creates or overwrites)."""
        if path not in self.model and not _can_write(path, self.model, self.dirs):
            return  # skip — directory/file conflict
        self.backend.write(path, data, overwrite=True)
        self.model[path] = data
        self.dirs.update(_ancestors(path))

    @rule(path=_path)
    def read_bytes(self, path: str) -> None:
        """read_bytes must match the model."""
        if path in self.dirs:
            return  # skip — reading a directory raises InvalidPath, not NotFound
        if path in self.model:
            result = self.backend.read_bytes(path)
            assert result == self.model[path], f"Content mismatch for {path!r}"
        else:
            with pytest.raises(remote_store._errors.NotFound, match=re.escape(path)):
                self.backend.read_bytes(path)

    @rule(path=_path)
    def exists(self, path: str) -> None:
        """exists returns True for files AND live directories."""
        is_file = path in self.model
        is_dir = path in self.dirs
        assert self.backend.exists(path) == (is_file or is_dir)

    @rule(path=_path)
    def is_file(self, path: str) -> None:
        """is_file must match the model."""
        assert self.backend.is_file(path) == (path in self.model)

    @rule(path=_path)
    def delete(self, path: str) -> None:
        """Delete a file that exists in the model.

        Per MEM-DS-006, ``delete()`` does not prune ancestor dir nodes, so
        ``self.dirs`` is left untouched here.
        """
        if path in self.model:
            self.backend.delete(path)
            del self.model[path]

    @rule(path=_path)
    def delete_missing_ok(self, path: str) -> None:
        """Delete with missing_ok=True never raises."""
        if path in self.dirs:
            return  # skip — deleting a directory path is a different operation
        self.backend.delete(path, missing_ok=True)
        self.model.pop(path, None)

    @rule(path=_path)
    def list_files_flat(self, path: str) -> None:
        """Non-recursive list_files for a prefix must match the model."""
        prefix = path + "/"
        expected = {k for k in self.model if k.startswith(prefix) and "/" not in k[len(prefix) :]}
        try:
            actual = {str(f.path) for f in self.backend.list_files(path)}
        except remote_store._errors.NotFound:
            actual = set()
        assert actual == expected, f"list_files({path!r}): {actual} != {expected}"


# Hypothesis discovers and runs this automatically
TestBackendModel = BackendModel.TestCase
TestBackendModel.__module__ = __name__
TestBackendModel = pytest.mark.pbt(TestBackendModel)


@pytest.mark.pbt
def test_bug183_empty_dir_persists_after_file_delete() -> None:
    """Regression: model must track empty dir nodes left by ``delete()``.

    Before BUG-183, the model derived implicit dirs from the live file map, so
    after ``write('0/0') → delete('0/0')`` the dir node ``'0'`` vanished from
    the model while the backend retained it (spec MEM-DS-006). The next
    ``write_new('0')`` then tripped the backend's file/dir conflict check and
    escaped the rule guard as ``InvalidPath``. The fix tracks dirs in a
    separate set that ``delete()`` deliberately does not touch.
    """
    m = BackendModel()
    m.write_new(path="0/0", data=b"")
    m.delete(path="0/0")

    assert m.backend.is_folder("0"), "backend should retain the empty dir node"
    assert "0" in m.dirs, "model should retain the empty dir node"

    # Must be skipped by the rule guard, not reach the backend and raise.
    m.write_new(path="0", data=b"")
    assert "0" not in m.model
    assert not m.backend.is_file("0")
