"""Unit tests for `remote_store.backends._flat_ns` (ID-211 shared helper).

The sync helper `_check_no_file_ancestor` is covered transitively by the
ID-211 strict conformance fixtures (`s3_moto_strict`, `sqlblob_strict`,
`azurite_strict`, `s3_pyarrow_moto_strict`). The async sibling
`_acheck_no_file_ancestor` has no equivalent async strict fixture in the
registry yet (live HNS short-circuits the pre-check via `hdi_isfolder`),
so its walk body is exercised here with a stub `head_one` awaitable.
Both sync and async helpers share their no-slash early exit and their
first-file-hit short-circuit, so the cases are mirrored.
"""

from __future__ import annotations

import pytest

from remote_store._errors import InvalidPath
from remote_store.backends._flat_ns import (
    _acheck_no_file_ancestor,
    _check_no_file_ancestor,
)


class TestCheckNoFileAncestorSync:
    def test_no_slash_path_returns_without_calls(self) -> None:
        calls: list[str] = []

        def head_one(key: str) -> bool:
            calls.append(key)
            return False

        _check_no_file_ancestor("rootfile.txt", head_one=head_one, backend="stub")

        assert calls == []

    def test_all_ancestors_clean_walks_each_then_returns(self) -> None:
        calls: list[str] = []

        def head_one(key: str) -> bool:
            calls.append(key)
            return False

        _check_no_file_ancestor("a/b/c/leaf.txt", head_one=head_one, backend="stub")

        assert calls == ["a", "a/b", "a/b/c"]

    def test_first_ancestor_is_file_raises_invalid_path(self) -> None:
        calls: list[str] = []

        def head_one(key: str) -> bool:
            calls.append(key)
            return key == "a"

        with pytest.raises(InvalidPath, match="'a' is a regular file") as exc_info:
            _check_no_file_ancestor("a/b/c/leaf.txt", head_one=head_one, backend="stub")

        assert calls == ["a"]
        assert exc_info.value.path == "a/b/c/leaf.txt"
        assert exc_info.value.backend == "stub"

    def test_mid_ancestor_is_file_raises_at_that_ancestor(self) -> None:
        calls: list[str] = []

        def head_one(key: str) -> bool:
            calls.append(key)
            return key == "a/b"

        with pytest.raises(InvalidPath, match="'a/b' is a regular file"):
            _check_no_file_ancestor("a/b/c/leaf.txt", head_one=head_one, backend="stub")

        assert calls == ["a", "a/b"]

    def test_leading_slash_is_normalised(self) -> None:
        """`//a/b/c` walks the same `a`, `a/b` ancestors as `a/b/c`.

        Non-canonical inputs that bypass ``Store``-side normalisation would
        otherwise call ``head_one`` on empty / `/a` keys, which return
        404-as-False on every backend and silently miss a real file ancestor.
        """
        calls: list[str] = []

        def head_one(key: str) -> bool:
            calls.append(key)
            return False

        _check_no_file_ancestor("//a/b/c/leaf.txt", head_one=head_one, backend="stub")

        assert calls == ["a", "a/b", "a/b/c"]


class TestACheckNoFileAncestorAsync:
    async def test_no_slash_path_returns_without_calls(self) -> None:
        calls: list[str] = []

        async def head_one(key: str) -> bool:
            calls.append(key)
            return False

        await _acheck_no_file_ancestor("rootfile.txt", head_one=head_one, backend="stub")

        assert calls == []

    async def test_all_ancestors_clean_walks_each_then_returns(self) -> None:
        calls: list[str] = []

        async def head_one(key: str) -> bool:
            calls.append(key)
            return False

        await _acheck_no_file_ancestor("a/b/c/leaf.txt", head_one=head_one, backend="stub")

        assert calls == ["a", "a/b", "a/b/c"]

    async def test_first_ancestor_is_file_raises_invalid_path(self) -> None:
        calls: list[str] = []

        async def head_one(key: str) -> bool:
            calls.append(key)
            return key == "a"

        with pytest.raises(InvalidPath, match="'a' is a regular file") as exc_info:
            await _acheck_no_file_ancestor("a/b/c/leaf.txt", head_one=head_one, backend="stub")

        assert calls == ["a"]
        assert exc_info.value.path == "a/b/c/leaf.txt"
        assert exc_info.value.backend == "stub"

    async def test_mid_ancestor_is_file_raises_at_that_ancestor(self) -> None:
        calls: list[str] = []

        async def head_one(key: str) -> bool:
            calls.append(key)
            return key == "a/b"

        with pytest.raises(InvalidPath, match="'a/b' is a regular file"):
            await _acheck_no_file_ancestor("a/b/c/leaf.txt", head_one=head_one, backend="stub")

        assert calls == ["a", "a/b"]

    async def test_leading_slash_is_normalised(self) -> None:
        """Async sibling of `TestCheckNoFileAncestorSync.test_leading_slash_is_normalised`."""
        calls: list[str] = []

        async def head_one(key: str) -> bool:
            calls.append(key)
            return False

        await _acheck_no_file_ancestor("//a/b/c/leaf.txt", head_one=head_one, backend="stub")

        assert calls == ["a", "a/b", "a/b/c"]
