"""Tests for scripts/docs/check_links.py — unified single-mode link gate.

After BK-171 the gate enforces one rule: every relative ``](path)`` link in
every git-tracked ``.md`` file (including docs-only files under
``docs-src/``) must resolve to an on-disk repo path. The mkdocs hook
rewrites docs-site URLs at build time, so authors write on-disk paths
everywhere.

Spec: sdd/specs/047-docs-framework-tooling.md (DOCFRAME-008).
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


def test_extract_links_skips_fenced_code_block(check_links_mod):
    text = "Before.\n```\n[inside](fenced.md)\n```\n[after](real.md)\n"
    assert check_links_mod._extract_links(text) == [(5, "real.md")]


def test_extract_links_skips_inline_code_span(check_links_mod):
    text = "Use `[example](inline.md)` syntax.\nSee [real](target.md).\n"
    assert check_links_mod._extract_links(text) == [(2, "target.md")]


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


def test_check_repo_links_skips_external(check_links_mod, tmp_path):
    (tmp_path / "README.md").write_text("[ext](https://example.com)\n")
    assert check_links_mod.check_repo_links(tmp_path) == []


def test_check_repo_links_strips_fragment(check_links_mod, tmp_path):
    (tmp_path / "page.md").write_text("# Page\n")
    (tmp_path / "README.md").write_text("[link](page.md#section)\n")
    assert check_links_mod.check_repo_links(tmp_path) == []


# ---------------------------------------------------------------------------
# Docs-only files are checked too (BK-171).
# ---------------------------------------------------------------------------


def test_check_repo_links_includes_docs_only_files(check_links_mod, tmp_path):
    """A broken on-disk link inside ``docs-src/`` is flagged like any other.

    BK-171: previous behaviour skipped docs-src entirely under the docs-only
    carve-out. The unified gate now checks them.
    """
    docs_src = tmp_path / "docs-src"
    docs_src.mkdir()
    (docs_src / "page.md").write_text("[broken](../missing.md)\n")
    broken = check_links_mod.check_repo_links(tmp_path)
    assert len(broken) == 1
    assert broken[0].raw == "../missing.md"


def test_check_repo_links_resolves_cross_tree_on_disk_target(check_links_mod, tmp_path):
    """A docs-src file linking to an on-disk source outside docs-src passes.

    BK-171: authors write on-disk paths (``../../sdd/adrs/foo.md``); the gate
    verifies the target exists; the mkdocs hook rewrites to the docs-site URL
    at build time.
    """
    docs_src = tmp_path / "docs-src" / "explanation"
    docs_src.mkdir(parents=True)
    sdd_dir = tmp_path / "sdd" / "adrs"
    sdd_dir.mkdir(parents=True)
    (sdd_dir / "0001-foo.md").write_text("# ADR-0001\n")
    (docs_src / "architecture.md").write_text("[ADR-0001](../../sdd/adrs/0001-foo.md)\n")
    assert check_links_mod.check_repo_links(tmp_path) == []


@pytest.mark.spec("DOCFRAME-008")
def test_check_repo_links_against_live_repo(check_links_mod):
    """No broken on-disk links in the live repository (positive control).

    Exercises the git ls-files code path (unlike tmp_path tests which use rglob).
    Skipped when ROOT is not a git checkout.
    """
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=ROOT,
        capture_output=True,
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout")
    broken = check_links_mod.check_repo_links(ROOT)
    assert broken == [], "\n".join(f"{b.source.relative_to(ROOT)}:{b.line}: {b.raw}" for b in broken)


# ---------------------------------------------------------------------------
# _resolve_docs_site_path — docs-site URL → page path (DOCFRAME-009)
# ---------------------------------------------------------------------------


def test_resolve_docs_site_path_skips_non_url(check_links_mod):
    assert check_links_mod._resolve_docs_site_path("../reference/api/store.md") is None


def test_resolve_docs_site_path_skips_other_host(check_links_mod):
    assert check_links_mod._resolve_docs_site_path("https://example.com/stable/x/") is None


def test_resolve_docs_site_path_skips_bare_site_root(check_links_mod):
    # Bare root redirects to the default version; nothing to validate.
    assert check_links_mod._resolve_docs_site_path("https://docs.remotestore.dev/") is None


def test_resolve_docs_site_path_returns_page_for_stable_alias(check_links_mod):
    url = "https://docs.remotestore.dev/stable/reference/api/store/"
    assert check_links_mod._resolve_docs_site_path(url) == "reference/api/store"


def test_resolve_docs_site_path_accepts_latest_alias(check_links_mod):
    url = "https://docs.remotestore.dev/latest/guides/extensions/"
    assert check_links_mod._resolve_docs_site_path(url) == "guides/extensions"


def test_resolve_docs_site_path_stable_root_is_empty_string(check_links_mod):
    assert check_links_mod._resolve_docs_site_path("https://docs.remotestore.dev/stable/") == ""


def test_resolve_docs_site_path_skips_numbered_version(check_links_mod):
    # A pinned snapshot cannot be validated against the current docs-src/ tree.
    url = "https://docs.remotestore.dev/0.25/reference/api/store/"
    assert check_links_mod._resolve_docs_site_path(url) is None


def test_resolve_docs_site_path_drops_fragment(check_links_mod):
    url = "https://docs.remotestore.dev/stable/reference/api/store/#remote_store.Store.read"
    assert check_links_mod._resolve_docs_site_path(url) == "reference/api/store"


# ---------------------------------------------------------------------------
# _normalize_docs_dest — source path → directory-URL page path (DOCFRAME-009)
# ---------------------------------------------------------------------------


def test_normalize_docs_dest_site_root(check_links_mod):
    assert check_links_mod._normalize_docs_dest("index.md") == ""


def test_normalize_docs_dest_section_index(check_links_mod):
    assert check_links_mod._normalize_docs_dest("reference/api/index.md") == "reference/api"


def test_normalize_docs_dest_page(check_links_mod):
    assert check_links_mod._normalize_docs_dest("reference/api/store.md") == "reference/api/store"


def test_normalize_docs_dest_asset_kept_verbatim(check_links_mod):
    asset = "img/benchmarks/overhead.svg"
    assert check_links_mod._normalize_docs_dest(asset) == asset


# ---------------------------------------------------------------------------
# _find_broken_docs_site_links — flag links to non-existent pages (DOCFRAME-009)
# ---------------------------------------------------------------------------

# The stale segment that shipped to production: /stable/api/store/ should have
# been /stable/reference/api/store/.
_VALID = {"", "reference", "reference/api", "reference/api/store", "guides/extensions"}


@pytest.mark.spec("DOCFRAME-009")
def test_find_broken_docs_site_links_detects_stale_segment(check_links_mod, tmp_path):
    text = "See the [API reference](https://docs.remotestore.dev/stable/api/store/).\n"
    broken = check_links_mod._find_broken_docs_site_links(text, tmp_path / "README.md", _VALID)
    assert len(broken) == 1
    assert broken[0].raw == "https://docs.remotestore.dev/stable/api/store/"
    assert broken[0].line == 1


def test_find_broken_docs_site_links_accepts_real_page(check_links_mod, tmp_path):
    text = "See the [API reference](https://docs.remotestore.dev/stable/reference/api/store/).\n"
    assert check_links_mod._find_broken_docs_site_links(text, tmp_path / "README.md", _VALID) == []


def test_find_broken_docs_site_links_accepts_section_index(check_links_mod, tmp_path):
    # A section directory is a valid URL even with no page of its own name.
    text = "[API](https://docs.remotestore.dev/stable/reference/api/)\n"
    assert check_links_mod._find_broken_docs_site_links(text, tmp_path / "x.md", _VALID) == []


def test_find_broken_docs_site_links_ignores_other_hosts(check_links_mod, tmp_path):
    text = "[gh](https://github.com/haalfi/remote-store/blob/master/README.md)\n"
    assert check_links_mod._find_broken_docs_site_links(text, tmp_path / "x.md", _VALID) == []


def test_find_broken_docs_site_links_skips_fenced_code(check_links_mod, tmp_path):
    text = "```\n[x](https://docs.remotestore.dev/stable/api/store/)\n```\n"
    assert check_links_mod._find_broken_docs_site_links(text, tmp_path / "x.md", _VALID) == []


@pytest.mark.spec("DOCFRAME-009")
def test_docs_site_links_against_live_repo(check_links_mod):
    """Docs-site links resolve, and the page set covers known pages.

    Positive control on the live repo; skipped outside a git checkout.
    """
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=ROOT,
        capture_output=True,
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout")
    pages = check_links_mod._docs_site_pages(ROOT)
    # A static page, a static section index, a purely-generated section
    # index (no docs-src/ file), and the site root.
    assert {"", "reference/api/store", "guides/extensions", "explanation/design"} <= pages
    broken = check_links_mod.check_docs_site_links(ROOT)
    assert broken == [], "\n".join(f"{b.source.relative_to(ROOT)}:{b.line}: {b.raw}" for b in broken)
