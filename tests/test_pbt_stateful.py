"""Stateful property-based test: MemoryBackend matches a dict model (BK-139 P4).

Uses Hypothesis ``RuleBasedStateMachine`` to generate random sequences of
write/read/delete/list/exists operations and verify the real backend matches
a simple Python dict at every step.
"""

from __future__ import annotations

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


class BackendModel(RuleBasedStateMachine):
    """MemoryBackend must behave like a simple dict[str, bytes]."""

    def __init__(self) -> None:
        super().__init__()
        self.backend = MemoryBackend()
        self.model: dict[str, bytes] = {}

    @rule(path=_path, data=_content)
    def write_new(self, path: str, data: bytes) -> None:
        """Write to a path that should not exist yet."""
        if path in self.model:
            return  # skip — already exists, would need overwrite=True
        self.backend.write(path, data)
        self.model[path] = data

    @rule(path=_path, data=_content)
    def write_overwrite(self, path: str, data: bytes) -> None:
        """Overwrite an existing path."""
        self.backend.write(path, data, overwrite=True)
        self.model[path] = data

    @rule(path=_path)
    def read_bytes(self, path: str) -> None:
        """read_bytes must match the model."""
        if path in self.model:
            result = self.backend.read_bytes(path)
            assert result == self.model[path], f"Content mismatch for {path!r}"
        else:
            with pytest.raises(remote_store._errors.NotFound, match=path):
                self.backend.read_bytes(path)

    @rule(path=_path)
    def exists(self, path: str) -> None:
        """exists must match the model."""
        assert self.backend.exists(path) == (path in self.model)

    @rule(path=_path)
    def is_file(self, path: str) -> None:
        """is_file must match the model."""
        assert self.backend.is_file(path) == (path in self.model)

    @rule(path=_path)
    def delete(self, path: str) -> None:
        """Delete a file that exists in the model."""
        if path in self.model:
            self.backend.delete(path)
            del self.model[path]

    @rule(path=_path)
    def delete_missing_ok(self, path: str) -> None:
        """Delete with missing_ok=True never raises."""
        self.backend.delete(path, missing_ok=True)
        self.model.pop(path, None)

    @rule(path=_path)
    def list_files_flat(self, path: str) -> None:
        """Non-recursive list_files for a prefix must match the model."""
        # Collect files directly in this "folder" from the model
        prefix = path + "/"
        expected = {k for k in self.model if k.startswith(prefix) and "/" not in k[len(prefix) :]}
        try:
            actual = {str(f.path) for f in self.backend.list_files(path)}
        except remote_store._errors.NotFound:
            # Folder may not exist — that's fine if we expect no files
            actual = set()
        assert actual == expected, f"list_files({path!r}): {actual} != {expected}"


# Hypothesis discovers and runs this automatically
TestBackendModel = BackendModel.TestCase
TestBackendModel.__module__ = __name__
TestBackendModel = pytest.mark.pbt(TestBackendModel)
