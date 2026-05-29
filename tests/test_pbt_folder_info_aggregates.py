"""Property-based aggregate verification for ``GetFolderInfo`` (ID-187).

Companion to
``tests/backends/conformance/test_metadata.py::TestGetFolderInfoAggregates``,
which spot-checks ``file_count`` / ``total_size`` against two hardcoded
trees. Deterministic fixtures cannot reach the off-by-one paths in the
recursive ``ChildFiles`` / ``SumSizes`` Dafny ghost functions; this module
adds property coverage by generating random file trees and comparing the
Python ``MemoryBackend`` aggregate to the Dafny-compiled oracle's.

The Dafny postcondition is the ground truth (verified by construction in
``sdd/formal/BackendContract.dfy``)::

    IsDir(path) ==>
        r.value.file_count == |ChildFiles(fs, path)|
     && r.value.total_size == SumSizes(fs, ChildFiles(fs, path))

Both backends are seeded from the same ``dict[str, bytes]`` literal — the
oracle is never re-derived by enumerating the backend under test, per the
Safe/Unsafe-pair discipline in ``sdd/formal/README.md``. The seeded-break
self-test at the bottom of this module guards the harness: a divergent
seed must yield divergent aggregates, otherwise the property is vacuously
green.

Hypothesis profiles are loaded from ``tests/conftest.py``
(``dev=50`` / ``ci=100`` / ``nightly=1000``); no inline ``max_examples``
is set (TESTING.md Rule 10). Strategies are module-level constants
(TESTING.md Rule 11).
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from remote_store.backends._memory import MemoryBackend
from tests.backends.dafny import build_oracle

# ---------------------------------------------------------------------------
# Tree-shape strategy
# ---------------------------------------------------------------------------

# Disjoint vocabularies for directory names and filenames make
# file-under-file conflicts (a path being both a file and a directory
# ancestor of another file) structurally impossible — no string can be
# both a ``_DIR_NAMES`` entry and a ``_FILE_NAMES`` entry.
_DIR_NAMES = ("d0", "d1", "d2", "d3", "d4", "d5")
_FILE_NAMES = ("f0.bin", "f1.bin", "f2.bin", "f3.bin", "f4.bin", "f5.bin")

_MAX_DEPTH = 4
_MAX_FILES = 20
_MIN_SIZE = 1
_MAX_SIZE = 10_000


@st.composite
def _file_path(draw: st.DrawFn) -> str:
    depth = draw(st.integers(min_value=0, max_value=_MAX_DEPTH))
    dirs = draw(st.lists(st.sampled_from(_DIR_NAMES), min_size=depth, max_size=depth))
    fname = draw(st.sampled_from(_FILE_NAMES))
    return "/".join([*dirs, fname])


@st.composite
def _file_tree(draw: st.DrawFn) -> dict[str, bytes]:
    paths = draw(st.lists(_file_path(), min_size=1, max_size=_MAX_FILES, unique=True))
    tree: dict[str, bytes] = {}
    for path in paths:
        size = draw(st.integers(min_value=_MIN_SIZE, max_value=_MAX_SIZE))
        tree[path] = bytes(i % 256 for i in range(size))
    return tree


def _dir_prefixes(tree: dict[str, bytes]) -> set[str]:
    """Every directory prefix appearing in the tree, plus root.

    Listing each directory prefix is what reaches the recursive
    ``ChildFiles`` / ``SumSizes`` paths in the Dafny aggregate.
    """
    prefixes = {""}
    for path in tree:
        parts = path.split("/")
        for i in range(1, len(parts)):
            prefixes.add("/".join(parts[:i]))
    return prefixes


# ---------------------------------------------------------------------------
# Property: MemoryBackend aggregates match the Dafny oracle (BE-017, ID-134)
# ---------------------------------------------------------------------------


class TestGetFolderInfoAggregatesOracle:
    """``MemoryBackend.get_folder_info`` aggregates match the Dafny oracle."""

    @pytest.mark.pbt
    @pytest.mark.spec("BE-017")
    @given(tree=_file_tree())
    def test_file_count_and_total_size_match_oracle(self, tree: dict[str, bytes]) -> None:
        oracle = build_oracle(tree)
        backend = MemoryBackend()
        for path, data in tree.items():
            backend.write(path, data)

        for prefix in _dir_prefixes(tree):
            expected = oracle.get_folder_info(prefix)
            actual = backend.get_folder_info(prefix)
            assert actual.file_count == expected.file_count, (
                f"file_count mismatch at {prefix!r}: "
                f"backend={actual.file_count} oracle={expected.file_count} tree={tree!r}"
            )
            assert actual.total_size == expected.total_size, (
                f"total_size mismatch at {prefix!r}: "
                f"backend={actual.total_size} oracle={expected.total_size} tree={tree!r}"
            )


# ---------------------------------------------------------------------------
# Seeded-break harness self-test (Safe/Unsafe-pair discipline)
# ---------------------------------------------------------------------------


class TestSeededBreakHarness:
    """Divergent seeds MUST produce divergent aggregates.

    Guards against a harness bug where ``build_oracle`` silently reuses the
    backend's seed (or vice versa) and makes the property-based test
    vacuously green. See ``sdd/formal/README.md`` § Design decisions —
    Safe/Unsafe pairs.
    """

    def test_divergent_seed_yields_divergent_total_size(self) -> None:
        backend_tree = {"d0/f0.bin": b"hello"}
        oracle_tree = {"d0/f0.bin": b"hi"}  # different size → different SumSizes
        oracle = build_oracle(oracle_tree)
        backend = MemoryBackend()
        for path, data in backend_tree.items():
            backend.write(path, data)

        assert oracle.get_folder_info("d0").total_size != backend.get_folder_info("d0").total_size

    def test_divergent_seed_yields_divergent_file_count(self) -> None:
        backend_tree = {"d0/f0.bin": b"a", "d0/f1.bin": b"b"}
        oracle_tree = {"d0/f0.bin": b"a"}  # one file vs two → different ChildFiles
        oracle = build_oracle(oracle_tree)
        backend = MemoryBackend()
        for path, data in backend_tree.items():
            backend.write(path, data)

        assert oracle.get_folder_info("d0").file_count != backend.get_folder_info("d0").file_count
