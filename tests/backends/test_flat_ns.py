"""Unit tests for `remote_store.backends._flat_ns` (ID-211 / BK-324 shared helpers).

The sync helper `_check_no_file_ancestor` is covered transitively by the
ID-211 strict conformance fixtures (`s3_moto_strict`, `sqlblob_strict`,
`azurite_strict`, `s3_pyarrow_moto_strict`). The async sibling
`_acheck_no_file_ancestor` is covered end-to-end by `azurite_async_strict`
(ID-211 review follow-up); these unit tests also exercise its walk body
with a stub `head_one` awaitable so the no-slash early exit and the
first-file-hit short-circuit are pinned independently of the live SDK
closure. Both sync and async helpers share their no-slash early exit and
their first-file-hit short-circuit, so the cases are mirrored.

The BK-324 wrong-type helpers follow the same split. The sync pair is
exercised end-to-end by every flat-NS conformance fixture; the async pair
only by `azurite_async`, which needs a container, so its root carve-out and
probe short-circuit are pinned here against stub awaitables.
"""

from __future__ import annotations

import pytest

from remote_store._errors import InvalidPath
from remote_store.backends._flat_ns import (
    _acheck_no_file_ancestor,
    _awrong_type_if_file,
    _awrong_type_if_folder,
    _check_no_file_ancestor,
    _reject_root_as_file,
    _wrong_type_if_file,
    _wrong_type_if_folder,
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

    def test_invalid_path_preserves_original_input(self) -> None:
        """The raised ``InvalidPath`` carries the caller-supplied input,
        not the post-lstrip normalised form. This lets downstream error
        handlers that grep for the original path still match.
        """

        def head_one(key: str) -> bool:
            return key == "a"

        with pytest.raises(InvalidPath, match=r"//a/b/c/leaf\.txt") as exc_info:
            _check_no_file_ancestor("//a/b/c/leaf.txt", head_one=head_one, backend="stub")

        assert exc_info.value.path == "//a/b/c/leaf.txt"


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

    async def test_invalid_path_preserves_original_input(self) -> None:
        """Async sibling of ``test_invalid_path_preserves_original_input``."""

        async def head_one(key: str) -> bool:
            return key == "a"

        with pytest.raises(InvalidPath, match=r"//a/b/c/leaf\.txt") as exc_info:
            await _acheck_no_file_ancestor("//a/b/c/leaf.txt", head_one=head_one, backend="stub")

        assert exc_info.value.path == "//a/b/c/leaf.txt"


class TestWrongTypeSync:
    """BK-324 facet 2: the error-path reclassification helpers."""

    def test_folder_probe_raises_invalid_path_naming_the_queried_path(self) -> None:
        calls: list[str] = []

        def has_children(key: str) -> bool:
            calls.append(key)
            return True

        with pytest.raises(InvalidPath, match="is a folder, not a file") as exc_info:
            _wrong_type_if_folder("some/dir", has_children=has_children, backend="stub")

        assert calls == ["some/dir"]
        assert exc_info.value.path == "some/dir"
        assert exc_info.value.backend == "stub"

    def test_folder_probe_returns_quietly_when_prefix_is_empty(self) -> None:
        """No children means the miss really was a miss; the caller's error stands."""
        calls: list[str] = []

        def has_children(key: str) -> bool:
            calls.append(key)
            return False

        _wrong_type_if_folder("some/missing", has_children=has_children, backend="stub")

        assert calls == ["some/missing"], "probe must run exactly once, on the queried path"

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_root_is_never_reclassified(self, root: str) -> None:
        """The root is a folder by definition, so it must not even be probed.

        Both spellings, one predicate. A truthiness test (``if path``) exempts
        ``""`` and lets ``"."`` through, where the probe answers about the
        whole store and turns the caller's error into a bogus type verdict.
        """
        calls: list[str] = []

        def has_children(key: str) -> bool:
            calls.append(key)
            return True

        _wrong_type_if_folder(root, has_children=has_children, backend="stub")

        assert calls == []

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_file_probe_skips_both_root_spellings(self, root: str) -> None:
        """Folder-shaped mirror: the root is never an object, so never probed."""
        calls: list[str] = []

        def is_object(key: str) -> bool:
            calls.append(key)
            return True

        _wrong_type_if_file(root, is_object=is_object, backend="stub")

        assert calls == []

    def test_file_probe_raises_invalid_path(self) -> None:
        def is_object(key: str) -> bool:
            return key == "some/file.txt"

        with pytest.raises(InvalidPath, match="is a file, not a folder") as exc_info:
            _wrong_type_if_file("some/file.txt", is_object=is_object, backend="stub")

        assert exc_info.value.path == "some/file.txt"

    def test_file_probe_returns_quietly_when_key_absent(self) -> None:
        calls: list[str] = []

        def is_object(key: str) -> bool:
            calls.append(key)
            return False

        _wrong_type_if_file("some/missing", is_object=is_object, backend="stub")

        assert calls == ["some/missing"]


class TestWrongTypeAsync:
    """Async siblings; only `azurite_async` reaches these end-to-end."""

    async def test_folder_probe_raises_invalid_path(self) -> None:
        calls: list[str] = []

        async def has_children(key: str) -> bool:
            calls.append(key)
            return True

        with pytest.raises(InvalidPath, match="is a folder, not a file") as exc_info:
            await _awrong_type_if_folder("some/dir", has_children=has_children, backend="stub")

        assert calls == ["some/dir"]
        assert exc_info.value.path == "some/dir"

    async def test_folder_probe_returns_quietly_when_prefix_is_empty(self) -> None:
        calls: list[str] = []

        async def has_children(key: str) -> bool:
            calls.append(key)
            return False

        await _awrong_type_if_folder("some/missing", has_children=has_children, backend="stub")

        assert calls == ["some/missing"]

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    async def test_root_is_never_reclassified(self, root: str) -> None:
        calls: list[str] = []

        async def has_children(key: str) -> bool:
            calls.append(key)
            return True

        await _awrong_type_if_folder(root, has_children=has_children, backend="stub")

        assert calls == []

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    async def test_file_probe_skips_both_root_spellings(self, root: str) -> None:
        calls: list[str] = []

        async def is_object(key: str) -> bool:
            calls.append(key)
            return True

        await _awrong_type_if_file(root, is_object=is_object, backend="stub")

        assert calls == []

    async def test_file_probe_raises_invalid_path(self) -> None:
        async def is_object(key: str) -> bool:
            return True

        with pytest.raises(InvalidPath, match="is a file, not a folder") as exc_info:
            await _awrong_type_if_file("some/file.txt", is_object=is_object, backend="stub")

        assert exc_info.value.path == "some/file.txt"

    async def test_file_probe_returns_quietly_when_key_absent(self) -> None:
        calls: list[str] = []

        async def is_object(key: str) -> bool:
            calls.append(key)
            return False

        await _awrong_type_if_file("some/missing", is_object=is_object, backend="stub")

        assert calls == ["some/missing"]


class TestRejectRootAsFile:
    """The pre-check that keeps the root out of file-shaped operations."""

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_both_spellings_raise_invalid_path(self, root: str) -> None:
        with pytest.raises(InvalidPath, match="is a folder, not a file") as exc_info:
            _reject_root_as_file(root, "stub")

        assert exc_info.value.path == root
        assert exc_info.value.backend == "stub"

    @pytest.mark.parametrize("path", ["a.txt", "a/b.txt", "dot.txt", "a/./b"], ids=range(4))
    def test_non_root_paths_pass_through(self, path: str) -> None:
        """Only the root itself is rejected -- an interior dot segment is not root.

        The guard runs ahead of every file-shaped operation, so over-matching
        here would reject ordinary keys before any I/O.
        """
        assert _reject_root_as_file(path, "stub") is None
