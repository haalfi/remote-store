"""Unit tests for scripts/check_backend_order.py.

The regression cases below are not invented: each is a real enumeration
that was live in the repo and had to be fixed by hand, and each is a
shape the ``git grep`` this gate replaces could not see. If the gate
stops catching them, it has decayed back into the grep.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_backend_order.py"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("check_backend_order", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_backend_order", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


class TestTokenising:
    """The alias table must resolve the spellings the docs actually use."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            # Longest alias wins: S3-PyArrow is not S3 followed by noise.
            ("S3, S3-PyArrow", ["S3", "S3-PyArrow"]),
            ("S3Backend, S3PyArrowBackend", ["S3", "S3-PyArrow"]),
            # Graph answers to three names.
            ("GraphBackend", ["Graph"]),
            ("OneDrive", ["Graph"]),
            # The abbreviation that hid a whole enumeration from the grep.
            ("SQL", ["SQLBlob"]),
            ("SQL Query", ["SQLQuery"]),
            # A word that merely starts with a backend name is not a backend.
            ("SQLAlchemy pools connections", []),
            ("s3fs and paramiko", []),
            # Lower-case prose is prose, not an enumeration entry.
            ("run it against local files and http endpoints", []),
        ],
    )
    def test_backends_in(self, text: str, expected: list[str]) -> None:
        assert _mod.backends_in(text) == expected

    def test_consecutive_repeats_collapse(self) -> None:
        """Azure (HNS) / Azure (non-HNS) is one backend, not disorder."""
        assert _mod.backends_in("Azure (HNS) Azure (non-HNS)") == ["Azure"]


class TestOrdering:
    def test_canonical_order_passes(self) -> None:
        canonical = [
            "Local", "Memory", "S3", "S3-PyArrow", "Azure",
            "Graph", "SFTP", "HTTP", "SQLBlob", "SQLQuery",
        ]  # fmt: skip
        assert _mod.is_ordered(canonical)

    def test_subset_in_order_passes(self) -> None:
        """An enumeration may abridge; it may not reorder."""
        assert _mod.is_ordered(["Local", "S3", "Azure", "SQLQuery"])

    def test_appended_backend_fails(self) -> None:
        """The exact drift the convention exists to stop: appended, not inserted."""
        assert not _mod.is_ordered(["Local", "S3", "SFTP", "Azure", "Graph", "Memory"])


class TestRegressions:
    """Each case was a live defect; each must fail the gate."""

    def _violations(self, tmp_path: Path, name: str, body: str) -> list:
        (tmp_path / name).write_text(body, encoding="utf-8")
        return _mod.scan_file(tmp_path / name)

    def test_inline_list_with_memory_appended(self, tmp_path: Path) -> None:
        """docs-src/index.md: the Mermaid backend node, Memory stranded at the end.

        Found by this gate, not by review and not by the grep.
        """
        found = self._violations(
            tmp_path,
            "index.md",
            'B_list["Local - S3 - SFTP - Azure - Graph - Http - Memory - SQL"]\n',
        )
        assert len(found) == 1
        assert "Memory" in found[0].found

    def test_abbreviated_sql_is_still_seen(self, tmp_path: Path) -> None:
        """The sentinel leak: an enumeration writing `SQL` was invisible to the grep."""
        found = self._violations(
            tmp_path,
            "context7.json",
            '"pick among Local, S3, S3PyArrow, SFTP, Azure, Graph, SQL, ReadOnlyHTTP"\n',
        )
        assert len(found) == 1

    def test_row_wise_table_out_of_order(self, tmp_path: Path) -> None:
        """concurrency.md § Summary table: Memory sat between SFTP and SQLBlob."""
        found = self._violations(
            tmp_path,
            "concurrency.md",
            "| Backend | Atomic? |\n"
            "|---|---|\n"
            "| [Local](l.md) | Yes |\n"
            "| [S3](s.md) | No |\n"
            "| [Azure](a.md) | No |\n"
            "| [Graph](g.md) | No |\n"
            "| [SFTP](f.md) | Yes |\n"
            "| [Memory](m.md) | Yes |\n"
            "| [SQLBlob](q.md) | Yes |\n",
        )
        assert len(found) == 1
        assert found[0].found[-2:] == ("Memory", "SQLBlob")

    def test_column_wise_table_header_out_of_order(self, tmp_path: Path) -> None:
        """capabilities-matrix.md: HTTP sat third, inside the local group."""
        found = self._violations(
            tmp_path,
            "capabilities-matrix.md",
            "| Capability | Local | Memory | HTTP | S3 | S3-PyArrow | SFTP | Azure | Graph |\n"
            "|---|---|---|---|---|---|---|---|---|\n"
            "| READ | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |\n",
        )
        assert len(found) == 1


class TestFalsePositives:
    """Shapes that look like disorder but are not. Each was a real misfire."""

    def _violations(self, tmp_path: Path, name: str, body: str) -> list:
        (tmp_path / name).write_text(body, encoding="utf-8")
        return _mod.scan_file(tmp_path / name)

    def test_comparison_row_cells_are_separate_lists(self, tmp_path: Path) -> None:
        """README 'How it compares': each cell is a *different product's* backends."""
        found = self._violations(
            tmp_path,
            "README.md",
            "| Backends | S3, GCS, Az, SFTP | S3, GCS, Azure | Local, Memory, S3, Azure, OneDrive, SFTP, HTTP, SQL |\n",
        )
        assert found == []

    def test_trailing_remention_after_a_list(self, tmp_path: Path) -> None:
        """`...SQLQuery by trade-off; Graph (OneDrive) is async-only.` is not disorder."""
        found = self._violations(
            tmp_path,
            "context7.json",
            '"pick among Local, Memory, S3, S3PyArrow, Azure, Graph, SFTP, '
            'ReadOnlyHTTP, SQLBlob, SQLQuery by trade-off; Graph is async-only."\n',
        )
        assert found == []

    def test_two_sentences_two_lists(self, tmp_path: Path) -> None:
        """`Built-in: <sync list>. Native async: <async list>.` — both ordered."""
        found = self._violations(
            tmp_path,
            "context7.json",
            '"Built-in backends: LocalBackend, MemoryBackend, S3Backend, '
            "S3PyArrowBackend, AzureBackend, SFTPBackend, ReadOnlyHttpBackend, "
            "SQLBlobBackend, SQLQueryBackend. Native async: AsyncAzureBackend, "
            'AsyncMemoryBackend, GraphBackend."\n',
        )
        assert found == []

    def test_prose_mentioning_a_few_backends(self, tmp_path: Path) -> None:
        """Below the threshold, co-mention is prose."""
        found = self._violations(
            tmp_path,
            "guide.md",
            "Develop against Memory, deploy to S3 or Azure.\n",
        )
        assert found == []


class TestRepository:
    def test_repo_is_clean(self) -> None:
        """The invariant CONTRIBUTING asserts actually holds."""
        violations = _mod.collect_violations(_REPO_ROOT)
        assert violations == [], "\n".join(f"{v.path}:{v.line}: {v.reason()}" for v in violations)

    def test_gate_scans_beyond_docs_src(self) -> None:
        """The pathspec leak: packaging/ and repo-root metadata must be in scope."""
        scanned = {p.relative_to(_REPO_ROOT).as_posix() for p in _mod.iter_scanned_files(_REPO_ROOT)}
        assert "context7.json" in scanned
        assert "packaging/conda-forge/recipe.yaml" in scanned
        assert "docs-src/context7.json" in scanned
