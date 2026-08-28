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

The BUG-259 root guards are here for a different reason, and it is the one
that most needs stating. `_reject_root_as_write_target` runs on every
write-shaped call on every backend, so its *over-matching* half — the
ordinary keys it must let through — is the half a backend suite cannot
reach cheaply: a predicate matching one character too many would fail
everywhere at once and be diagnosed as anything but a root check. Its
under-matching half has a second reason to live here: the conformance cells
are parametrised over the two canonical spellings only (they assert
`is_root` on the raised path), so the wider spellings the contract requires
are pinned by these cells and by three per-backend modules, and nowhere in
conformance. See ID-251.
"""

from __future__ import annotations

import pytest

from remote_store._errors import InvalidPath
from remote_store._path import is_root
from remote_store.backends._flat_ns import (
    _acheck_no_file_ancestor,
    _achildren_or_absent_container,
    _awrong_type_if_file,
    _awrong_type_if_folder,
    _check_no_file_ancestor,
    _children_or_absent_container,
    _reject_root_as_file,
    _reject_root_as_write_target,
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


@pytest.mark.spec("BE-029", "BE-008")
class TestRejectRootAsWriteTarget:
    """The pre-check that keeps the root out of write-shaped operations.

    The sibling above answers a *read* of the wrong type; this answers a write,
    and the two are deliberately separate helpers with separate wordings. Both
    halves are pinned here rather than only through the backends, because the
    over-matching half is the one a backend suite cannot reach cheaply: every
    ordinary key on every backend runs through this guard, so a predicate that
    matched one character too many would fail everywhere at once and be
    diagnosed as anything but a root check.
    """

    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_both_spellings_raise_invalid_path(self, root: str) -> None:
        with pytest.raises(InvalidPath, match="is the store root") as exc_info:
            _reject_root_as_write_target(root, "stub")

        assert exc_info.value.path == root
        assert exc_info.value.backend == "stub"

    @pytest.mark.parametrize(
        "root",
        ["./", ".//", "./.", "/", "//", "/.", "././"],
        # "dot-dot" would read as "..", which this guard deliberately does NOT
        # refuse -- the bound is the slash-and-dot family, and "_addressable_segments('..')"
        # is [".."]. The ids spell the slashes out so a -v line cannot suggest otherwise.
        ids=[
            "dot-slash",
            "dot-slash-slash",
            "dot-slash-dot",
            "slash",
            "slash-slash",
            "slash-dot",
            "dot-slash-dot-slash",
        ],
    )
    def test_non_canonical_root_spellings_also_raise(self, root: str) -> None:
        """The spellings ``is_root`` does not recognise, which is why this guard normalises.

        ``is_root`` is exactly ``{"", "."}``. Every string here addresses the
        same node and none of them is in that set, so a guard written as
        ``if is_root(path)`` lets all seven through. Measured before the fix
        against a ``LocalBackend`` whose root had been deleted: ``write("./")``
        left the root a regular **file** and raised from above the backend, and
        ``open_atomic("./")`` returned cleanly having done it — the whole defect
        the guard exists for, one character from the spelling it caught.

        The error still echoes the caller's own spelling in ``path`` rather than
        a canonicalised one, so a caller sees the string they passed.
        """
        with pytest.raises(InvalidPath, match="is the store root") as exc_info:
            _reject_root_as_write_target(root, "stub")

        assert exc_info.value.path == root
        assert exc_info.value.backend == "stub"

    def test_the_guard_does_not_defer_to_is_root(self) -> None:
        """Fences the normalisation against a revert to the obvious one-liner.

        Every other cell here would pass with the body rewritten as
        ``if is_root(path)`` **except** the non-canonical class above, and that
        class is easy to read as pedantry about strings nobody types. This cell
        states the dependency outright: the two predicates disagree, and the
        guard is required to follow the wider one.
        """
        assert is_root("./") is False, "is_root recognises './' — this cell's premise is gone"
        with pytest.raises(InvalidPath):
            _reject_root_as_write_target("./", "stub")

    @pytest.mark.parametrize(
        "path",
        ["a.txt", "a/b.txt", "dot.txt", "a/./b", "./a.txt", "..txt", ".hidden"],
        ids=range(7),
    )
    def test_non_root_paths_pass_through(self, path: str) -> None:
        """Ordinary keys are untouched, including the ones that start with a dot.

        ``".hidden"`` and ``"..txt"`` are here because they are what a
        ``startswith(".")`` or a ``strip(".")`` spelling of this predicate would
        swallow — the exact shape that once let ``"."`` through the Graph
        backend's own root check in the opposite direction.
        """
        assert _reject_root_as_write_target(path, "stub") is None

    def test_wording_differs_from_the_read_guard(self) -> None:
        """The two guards must not converge on one message.

        Their separation is the whole reason there are two helpers: a caller
        told "not a file" about a write learns the wrong thing. A future edit
        that unified the wording would pass every backend test, because those
        assert the class and the path, never the sentence.
        """
        with pytest.raises(InvalidPath) as write_exc:
            _reject_root_as_write_target("", "stub")
        with pytest.raises(InvalidPath) as read_exc:
            _reject_root_as_file("", "stub")
        assert str(write_exc.value) != str(read_exc.value)
        assert "Cannot write" in str(write_exc.value)


class _Sentinel(Exception):
    """An exception no ``absent_container`` predicate should ever claim."""


@pytest.mark.spec("BE-012", "BE-013", "BE-021")
class TestChildrenOrAbsentContainerSync:
    """The determinant that reads a container's 404 as "no children".

    Both branches matter and they fail in opposite directions. Swallowing too
    little leaves ``delete_folder`` raising where its sibling returns, which is
    the divergence the helper exists to remove; swallowing too much turns a
    denial or a 503 into "the folder is empty", which is the invented-answer
    class this backend family has already shipped once.
    """

    def test_children_answer_passes_through(self) -> None:
        """No exception, no interpretation: the helper is transparent on success."""
        for answer in (True, False):
            got = _children_or_absent_container(
                "folder",
                has_children=lambda _p, a=answer: a,  # type: ignore[misc]
                absent_container=lambda _e: pytest.fail("predicate consulted without an exception"),
            )
            assert got is answer

    def test_absent_container_reads_as_no_children(self) -> None:
        def has_children(_path: str) -> bool:
            raise _Sentinel

        assert (
            _children_or_absent_container(
                "folder",
                has_children=has_children,
                absent_container=lambda exc: isinstance(exc, _Sentinel),
            )
            is False
        )

    def test_any_other_failure_re_raises_unchanged(self) -> None:
        """The identity of the error is preserved, not just its type.

        A helper that re-raised a *new* exception of the same class would pass a
        type-only assertion while discarding the message, the ``__cause__`` and
        any backend attribution the caller had already attached.
        """
        original = _Sentinel("503 from the service")

        def has_children(_path: str) -> bool:
            raise original

        with pytest.raises(_Sentinel) as exc_info:
            _children_or_absent_container(
                "folder",
                has_children=has_children,
                absent_container=lambda _e: False,
            )
        assert exc_info.value is original


@pytest.mark.spec("ASYNC-012", "ASYNC-013", "BE-021")
class TestAChildrenOrAbsentContainerAsync:
    """The async sibling. Mirrored because the two share no code."""

    async def test_children_answer_passes_through(self) -> None:
        async def has_children(_path: str) -> bool:
            return True

        got = await _achildren_or_absent_container(
            "folder",
            has_children=has_children,
            absent_container=lambda _e: pytest.fail("predicate consulted without an exception"),
        )
        assert got is True

    async def test_absent_container_reads_as_no_children(self) -> None:
        async def has_children(_path: str) -> bool:
            raise _Sentinel

        assert (
            await _achildren_or_absent_container(
                "folder",
                has_children=has_children,
                absent_container=lambda exc: isinstance(exc, _Sentinel),
            )
            is False
        )

    async def test_any_other_failure_re_raises_unchanged(self) -> None:
        original = _Sentinel("503 from the service")

        async def has_children(_path: str) -> bool:
            raise original

        with pytest.raises(_Sentinel) as exc_info:
            await _achildren_or_absent_container(
                "folder",
                has_children=has_children,
                absent_container=lambda _e: False,
            )
        assert exc_info.value is original
