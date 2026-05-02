"""Tests for scripts/docs/check_links.py (BK-167b link validation).

Spec: sdd/specs/047-docs-framework-tooling.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.os_sensitive

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def check_links_mod():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import docs.check_links as _mod

    return _mod


# ---------------------------------------------------------------------------
# _extract_links
# ---------------------------------------------------------------------------


def test_extract_links_skips_external_urls(check_links_mod):
    text = "[a](https://example.com)\n[b](http://foo.org)\n[c](mailto:x@y.com)\n"
    assert check_links_mod._extract_links(text) == []


def test_extract_links_skips_anchor_only(check_links_mod):
    assert check_links_mod._extract_links("[jump](#section)\n") == []


def test_extract_links_returns_internal_links(check_links_mod):
    text = "See [foo](../foo.md) and [bar](sub/bar.md).\n"
    assert check_links_mod._extract_links(text) == [(1, "../foo.md"), (1, "sub/bar.md")]


def test_extract_links_strips_title_attribute(check_links_mod):
    assert check_links_mod._extract_links('[link](target.md "Title")\n') == [(1, "target.md")]


def test_extract_links_preserves_line_numbers(check_links_mod):
    text = "Line one.\n\n[link](page.md)\n"
    assert check_links_mod._extract_links(text) == [(3, "page.md")]


# ---------------------------------------------------------------------------
# check_repo_links
# ---------------------------------------------------------------------------
# NOTE: tmp_path is never a git repo, so all tests here exercise the rglob
# fallback in _git_repo_markdown, not the git ls-files production path.


def test_check_repo_links_no_broken(check_links_mod, tmp_path):
    (tmp_path / "other.md").write_text("# Other\n")
    (tmp_path / "README.md").write_text("<!-- doc: dual dest=index.md -->\n[other](other.md)\n")
    assert check_links_mod.check_repo_links(tmp_path) == []


def test_check_repo_links_detects_broken(check_links_mod, tmp_path):
    (tmp_path / "README.md").write_text("[missing](nonexistent.md)\n")
    broken = check_links_mod.check_repo_links(tmp_path)
    assert len(broken) == 1
    assert broken[0].raw == "nonexistent.md"
    assert broken[0].line == 1
    assert broken[0].mode == "repo"


def test_check_repo_links_skips_external(check_links_mod, tmp_path):
    (tmp_path / "README.md").write_text("[ext](https://example.com)\n")
    assert check_links_mod.check_repo_links(tmp_path) == []


def test_check_repo_links_strips_fragment(check_links_mod, tmp_path):
    (tmp_path / "page.md").write_text("# Page\n")
    (tmp_path / "README.md").write_text("[link](page.md#section)\n")
    assert check_links_mod.check_repo_links(tmp_path) == []


# ---------------------------------------------------------------------------
# check_site_links
# ---------------------------------------------------------------------------


def test_check_site_links_no_broken(check_links_mod, tmp_path):
    adrs_dir = tmp_path / "sdd" / "adrs"
    adrs_dir.mkdir(parents=True)
    (tmp_path / "docs-src").mkdir()
    (adrs_dir / "0001-first.md").write_text("# ADR-0001: First\n\nSee [second](0002-second.md).\n")
    (adrs_dir / "0002-second.md").write_text("# ADR-0002: Second\n\nContent.\n")
    assert check_links_mod.check_site_links(tmp_path) == []


def test_check_site_links_detects_outside_repo_link(check_links_mod, tmp_path):
    # Target resolves outside repo_root: _lookup returns None, link is left
    # unchanged, and the raw repo-relative href is not a known docs dest.
    adrs_dir = tmp_path / "sdd" / "adrs"
    adrs_dir.mkdir(parents=True)
    (tmp_path / "docs-src").mkdir()
    # ../../../ from sdd/adrs/ escapes tmp_path entirely
    (adrs_dir / "0001-first.md").write_text("# ADR-0001: First\n\nSee [outside](../../../outside.md).\n")
    broken = check_links_mod.check_site_links(tmp_path)
    assert len(broken) == 1
    assert broken[0].mode == "site"
    assert "../../../outside.md" in broken[0].raw
