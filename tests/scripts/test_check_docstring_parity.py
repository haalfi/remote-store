"""Tests for scripts/check_docstring_parity.py (BK-297).

Each pure function is tested in isolation:

* ``class_method_docstrings`` -- class scoping (helper classes ignored),
  docstring-less methods omitted, raw value preserved.
* ``compare`` -- identical-match, drift, unclassified, and stale cases.
* ``fix_twin`` -- a sync->async re-sync round-trip on temp files, leaving
  ``divergent`` methods untouched and preserving the sync side's quoting.

A final integration test runs ``compare`` over the live registry -- the same
parity CI enforces.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def mod():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import check_docstring_parity

    return check_docstring_parity


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class TestClassMethodDocstrings:
    def test_scopes_to_named_class_ignoring_helpers(self, mod):
        source = textwrap.dedent(
            '''
            class _Helper:
                def read(self):
                    """Helper read -- must not leak into the twin."""

            class Backend:
                def read(self):
                    """Real read."""
                def write(self):
                    """Real write."""
            '''
        )
        docs = mod.class_method_docstrings(source, "Backend")
        assert docs == {"read": "Real read.", "write": "Real write."}

    def test_omits_methods_without_docstring(self, mod):
        source = textwrap.dedent(
            '''
            class C:
                def documented(self):
                    """Has one."""
                def bare(self):
                    return 1
            '''
        )
        assert mod.class_method_docstrings(source, "C") == {"documented": "Has one."}

    def test_preserves_raw_indentation(self, mod):
        # clean=False: leading whitespace on continuation lines is retained, so
        # an indentation-only difference would register as drift.
        source = 'class C:\n    def m(self):\n        """Line one.\n\n        Line two.\n        """\n'
        docs = mod.class_method_docstrings(source, "C")
        assert "\n\n        Line two." in docs["m"]

    def test_missing_class_yields_empty(self, mod):
        assert mod.class_method_docstrings("x = 1\n", "Nope") == {}


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


def _twin(mod, identical=frozenset(), divergent=frozenset()):
    return mod.Twin(
        sync_path=Path("sync.py"),
        sync_class="Foo",
        async_path=Path("async_.py"),
        async_class="AsyncFoo",
        identical=frozenset(identical),
        divergent=frozenset(divergent),
    )


class TestCompare:
    def test_identical_match_passes(self, mod):
        twin = _twin(mod, identical={"copy"})
        assert compare_clean(mod, twin, {"copy": "Same."}, {"copy": "Same."})

    def test_identical_drift_fails(self, mod):
        twin = _twin(mod, identical={"copy"})
        errors = mod.compare(twin, {"copy": "Sync."}, {"copy": "Async."})
        assert len(errors) == 1
        assert "drift" in errors[0]
        assert "copy" in errors[0]

    def test_divergent_difference_is_allowed(self, mod):
        twin = _twin(mod, divergent={"read"})
        assert compare_clean(mod, twin, {"read": "Stream."}, {"read": "Async iterator."})

    def test_unclassified_shared_method_fails(self, mod):
        twin = _twin(mod, identical={"copy"})
        errors = mod.compare(twin, {"copy": "X", "newish": "Y"}, {"copy": "X", "newish": "Z"})
        assert len(errors) == 1
        assert "unclassified" in errors[0]
        assert "newish" in errors[0]

    def test_stale_registry_entry_fails(self, mod):
        twin = _twin(mod, identical={"copy", "gone"})
        errors = mod.compare(twin, {"copy": "X"}, {"copy": "X"})
        assert len(errors) == 1
        assert "no longer a shared-docstring method" in errors[0]
        assert "gone" in errors[0]

    def test_method_on_only_one_side_is_not_shared(self, mod):
        # ``open_atomic`` exists on sync only -> not shared -> not required to be
        # classified, and not flagged.
        twin = _twin(mod, identical={"copy"})
        assert compare_clean(mod, twin, {"copy": "X", "open_atomic": "Sync only."}, {"copy": "X"})


def compare_clean(mod, twin, sync_docs, async_docs) -> bool:
    return mod.compare(twin, sync_docs, async_docs) == []


# ---------------------------------------------------------------------------
# Fix (round-trip on temp files)
# ---------------------------------------------------------------------------


SYNC_SRC = textwrap.dedent(
    '''\
    class Foo:
        def copy(self):
            """Copy a file.

            Returns:
                Nothing.
            """
        def read(self):
            """Return a readable stream."""
    '''
)

# ``copy`` has drifted (must be re-synced); ``read`` is divergent (left alone).
ASYNC_SRC = textwrap.dedent(
    '''\
    class AsyncFoo:
        def copy(self):
            """Copy a file STALE.
            """
        def read(self):
            """Return an async iterator."""
    '''
)


class TestFixTwin:
    def test_resyncs_identical_leaves_divergent(self, mod, tmp_path):
        sync_p = tmp_path / "sync.py"
        async_p = tmp_path / "async_.py"
        sync_p.write_text(SYNC_SRC, encoding="utf-8")
        async_p.write_text(ASYNC_SRC, encoding="utf-8")
        twin = mod.Twin(
            sync_path=sync_p,
            sync_class="Foo",
            async_path=async_p,
            async_class="AsyncFoo",
            identical=frozenset({"copy"}),
            divergent=frozenset({"read"}),
        )

        fixed = mod.fix_twin(twin)
        assert fixed == ["copy"]

        sync_docs = mod.class_method_docstrings(sync_p.read_text(), "Foo")
        async_docs = mod.class_method_docstrings(async_p.read_text(), "AsyncFoo")
        # copy re-synced byte-for-byte; read untouched.
        assert async_docs["copy"] == sync_docs["copy"]
        assert async_docs["read"] == "Return an async iterator."
        # And the file now passes its own parity check.
        assert mod.compare(twin, sync_docs, async_docs) == []

    def test_fix_is_idempotent(self, mod, tmp_path):
        sync_p = tmp_path / "sync.py"
        async_p = tmp_path / "async_.py"
        sync_p.write_text(SYNC_SRC, encoding="utf-8")
        async_p.write_text(ASYNC_SRC, encoding="utf-8")
        twin = mod.Twin(
            sync_path=sync_p,
            sync_class="Foo",
            async_path=async_p,
            async_class="AsyncFoo",
            identical=frozenset({"copy"}),
            divergent=frozenset({"read"}),
        )
        mod.fix_twin(twin)
        assert mod.fix_twin(twin) == []  # second pass finds nothing to do


# ---------------------------------------------------------------------------
# Integration -- the live registry must hold (mirrors CI)
# ---------------------------------------------------------------------------


class TestLiveRegistry:
    def test_live_parity_holds(self, mod):
        errors: list[str] = []
        for twin in mod.TWINS:
            sync_docs = mod.class_method_docstrings(twin.sync_path.read_text(encoding="utf-8"), twin.sync_class)
            async_docs = mod.class_method_docstrings(twin.async_path.read_text(encoding="utf-8"), twin.async_class)
            errors.extend(mod.compare(twin, sync_docs, async_docs))
        assert errors == [], "\n".join(errors)

    def test_registry_sets_are_disjoint(self, mod):
        for twin in mod.TWINS:
            overlap = twin.identical & twin.divergent
            assert not overlap, f"{twin.label}: {overlap} in both identical and divergent"

    def test_main_returns_zero(self, mod, capsys):
        assert mod.main([]) == 0
