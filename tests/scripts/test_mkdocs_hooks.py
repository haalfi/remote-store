"""Tests for mkdocs_hooks.py — on_page_markdown dispatch branches.

Branch coverage:
  1. page.file.abs_src_path is None → pass-through (no resolver call).
  2. abs_src_path outside docs-src/ → pass-through (gen-files virtual page).
  3. abs_src_path inside docs-src/ → links rewritten via LinkResolver.

Spec: sdd/specs/047-docs-framework-tooling.md (DOCFRAME-008, Bridge invariant).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"
DOCS_SRC = ROOT / "docs-src"


@pytest.fixture(scope="module")
def hooks_mod():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import mkdocs_hooks as mod

    return mod


class _FakePage:
    """Minimal MkDocs Page stand-in for on_page_markdown tests."""

    class _FakeFile:
        def __init__(self, abs_src_path: str | None, src_uri: str = "guides/page.md") -> None:
            self.abs_src_path = abs_src_path
            self.src_uri = src_uri

    def __init__(self, abs_src_path: str | None, src_uri: str = "guides/page.md") -> None:
        self.file = self._FakeFile(abs_src_path, src_uri)


@pytest.mark.spec("DOCFRAME-008")
def test_on_page_markdown_passthrough_when_abs_src_none(hooks_mod):
    """Branch 1: abs_src_path is None → markdown returned unchanged, resolver not called."""
    page = _FakePage(None)
    md = "# Title\n[link](../missing.md)\n"
    result = hooks_mod.on_page_markdown(md, page, None, None)
    assert result is md


@pytest.mark.spec("DOCFRAME-008")
def test_on_page_markdown_passthrough_outside_docs_src(hooks_mod, tmp_path):
    """Branch 2: abs_src_path outside docs-src/ → pass-through (gen-files virtual page)."""
    outside_path = str(tmp_path / "gen_files_cache" / "sdd" / "specs" / "047.md")
    page = _FakePage(outside_path, src_uri="explanation/design/specs/047.md")
    md = "# Spec\n[link](other.md)\n"
    result = hooks_mod.on_page_markdown(md, page, None, None)
    assert result is md


@pytest.mark.spec("DOCFRAME-008")
def test_on_page_markdown_rewrites_docs_src_links(hooks_mod):
    """Branch 3: abs_src_path inside docs-src/ → LinkResolver.rewrite is called."""
    src_abs = str(DOCS_SRC / "guides" / "backends" / "s3.md")
    dest = "guides/backends/s3.md"
    page = _FakePage(src_abs, src_uri=dest)
    md = "[S3 spec](../../../sdd/specs/001.md)\n"
    expected = "[S3 spec](../explanation/design/specs/001.md)\n"

    mock_resolver = MagicMock(spec=["rewrite"])
    mock_resolver.rewrite.return_value = expected

    with patch.object(hooks_mod, "_get_resolver", return_value=mock_resolver):
        result = hooks_mod.on_page_markdown(md, page, None, None)

    mock_resolver.rewrite.assert_called_once_with(md, Path(src_abs).resolve(), dest)
    assert result == expected
