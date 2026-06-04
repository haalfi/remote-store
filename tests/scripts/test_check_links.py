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


# ---------------------------------------------------------------------------
# ID-180: fragment resolution (#anchor) + anchor sanity (M1, M2, M3)
# ---------------------------------------------------------------------------


def test_slugify_heading_matches_github_style(check_links_mod):
    f = check_links_mod._slugify_heading
    assert f("Documentation framework") == "documentation-framework"
    assert f("4. Cross-linking requirements") == "4-cross-linking-requirements"
    assert f("`Capability` ClassVar") == "capability-classvar"
    assert f("GitHub PR I/O split") == "github-pr-io-split"


def test_extract_anchors_collects_a_id_and_heading_slugs(check_links_mod):
    text = '<a id="custom"></a>\n## Real Heading\n\n## Another\n'
    idx = check_links_mod._extract_anchors(text)
    assert "custom" in idx.ids
    assert "real-heading" in idx.ids
    assert "another" in idx.ids
    assert idx.duplicate_ids == ()
    assert idx.orphan_ids == ()


def test_extract_anchors_skips_fenced_code(check_links_mod):
    text = '```\n<a id="fake"></a>\n## fake heading\n```\n## real\n'
    idx = check_links_mod._extract_anchors(text)
    assert "fake" not in idx.ids
    assert "real" in idx.ids


def test_extract_anchors_flags_duplicate(check_links_mod):
    text = '<a id="x"></a>\n## First\n\n<a id="x"></a>\n## Second\n'
    idx = check_links_mod._extract_anchors(text)
    assert "x" in idx.duplicate_ids


def test_extract_anchors_flags_duplicate_heading_slug(check_links_mod):
    # Two headings that slug to the same value render as two `#rules`
    # candidates on GitHub but only the first resolves, so any consumer
    # `#rules` ref is silently ambiguous. The collision lands in
    # duplicate_heading_slugs (lazy — surfaced only when a live consumer
    # references it).
    text = "## Rules\n\nsome prose\n\n## Rules\n"
    idx = check_links_mod._extract_anchors(text)
    assert "rules" in idx.duplicate_heading_slugs
    assert idx.duplicate_ids == ()


def test_extract_anchors_anchor_plus_matching_heading_not_duplicate(check_links_mod):
    # The deliberate redundancy pattern: <a id="X"> immediately before
    # ## X (slug also "x"). Both target the same line; the id is not
    # ambiguous. Authors use this to freeze the section identity.
    text = '<a id="rules"></a>\n## Rules\n'
    idx = check_links_mod._extract_anchors(text)
    assert idx.duplicate_ids == ()
    assert idx.duplicate_heading_slugs == ()
    assert "rules" in idx.ids


def test_fragment_gate_resolves_in_page_fragment(check_links_mod, tmp_path):
    # `[text](#frag)` in-page refs must resolve against the source file's
    # own anchors. Closes the in-page leg of ID-180; the explicit anchor
    # planted above the heading is what the link targets.
    (tmp_path / "README.md").write_text(
        '[jump](#adding-a-new-backend)\n\n<a id="adding-a-new-backend"></a>\n## Adding a New Backend\n'
    )
    broken = check_links_mod.check_repo_link_fragments(tmp_path)
    assert broken == []


def test_fragment_gate_flags_broken_in_page_fragment(check_links_mod, tmp_path):
    # In-page ref that points at no anchor or matching heading in the same
    # file must be flagged. This is the rot the in-page leg of ID-180 closes:
    # if the heading is renamed and the anchor removed, the link breaks
    # silently today; the gate must catch it.
    (tmp_path / "README.md").write_text("[jump](#section-that-vanished)\n\n## Some Other Section\n")
    broken = check_links_mod.check_repo_link_fragments(tmp_path)
    assert any("no anchor #section-that-vanished" in b.resolved for b in broken), [b.resolved for b in broken]


def test_fragment_gate_lazy_strict_heading_slug_silent_without_consumer(check_links_mod, tmp_path):
    # Two `## Rules` produce a heading-slug collision, but nothing links to
    # `target.md#rules` — pages with intentional structural duplication
    # (sync + async on one page, two-presentation ripple tables) live here.
    # Lazy-strict: stay silent until a live consumer references the slug.
    (tmp_path / "target.md").write_text("## Rules\n\nfirst\n\n## Rules\n")
    (tmp_path / "README.md").write_text("# README - no inbound section ref.\n")
    broken = check_links_mod.check_repo_link_fragments(tmp_path)
    assert broken == []


def test_fragment_gate_lazy_strict_heading_slug_fires_with_consumer(check_links_mod, tmp_path):
    # Same colliding headings, now an inbound `target.md#rules` ref exists.
    # The link silently resolves to one of the two on GitHub; the gate must
    # call it out so the author disambiguates.
    (tmp_path / "target.md").write_text("## Rules\n\nfirst\n\n## Rules\n")
    (tmp_path / "README.md").write_text("[link](target.md#rules)\n")
    broken = check_links_mod.check_repo_link_fragments(tmp_path)
    assert any("duplicate heading slug #rules" in b.resolved for b in broken), [b.resolved for b in broken]


def test_extract_anchors_flags_orphan(check_links_mod):
    text = '<a id="dangling"></a>\n\nSome paragraph not a heading.\n'
    idx = check_links_mod._extract_anchors(text)
    assert idx.orphan_ids == ((1, "dangling"),)


def test_extract_anchors_inline_anchor_in_list_item(check_links_mod):
    # Rule list items use inline <a id> before the bold token.
    text = '## Rules\n\n6. <a id="workflows"></a>**Workflows**:\n'
    idx = check_links_mod._extract_anchors(text)
    # Inline anchor inside a list item is co-located with its semantic target
    # (the list item content); the orphan-suppression branch must skip it so
    # the live tree's `2. <a id="spec-test-traceability"></a>...` in
    # sdd/000-process.md does not fire M3.
    assert "workflows" in idx.ids
    assert idx.orphan_ids == ()


def test_is_denylisted_consumer(check_links_mod):
    f = check_links_mod._is_denylisted_consumer
    assert f("CHANGELOG.md")
    assert f("sdd/BACKLOG-DONE.md")
    assert f("sdd/audits/audit-014.md")
    assert f("sdd/research/foo.md")
    assert f("sdd/traces/bk-251.yml")
    assert not f("CLAUDE.md")
    assert not f("sdd/BACKLOG.md")
    assert not f("sdd/AUTHORING.md")


def test_fragment_gate_resolves_against_a_id(check_links_mod, tmp_path):
    (tmp_path / "target.md").write_text('<a id="here"></a>\n## Some Heading\n')
    (tmp_path / "README.md").write_text("[link](target.md#here)\n")
    broken = check_links_mod.check_repo_link_fragments(tmp_path)
    assert [b for b in broken if b.line > 0] == []


def test_fragment_gate_resolves_against_heading_slug(check_links_mod, tmp_path):
    (tmp_path / "target.md").write_text("## Coverage gate\n")
    (tmp_path / "README.md").write_text("[link](target.md#coverage-gate)\n")
    broken = check_links_mod.check_repo_link_fragments(tmp_path)
    assert [b for b in broken if b.line > 0] == []


def test_fragment_gate_flags_unresolved(check_links_mod, tmp_path):
    (tmp_path / "target.md").write_text("## Something Else\n")
    (tmp_path / "README.md").write_text("[link](target.md#nope)\n")
    broken = [b for b in check_links_mod.check_repo_link_fragments(tmp_path) if b.line > 0]
    assert len(broken) == 1
    assert "nope" in broken[0].resolved


def test_fragment_gate_denylist_skips(check_links_mod, tmp_path):
    (tmp_path / "target.md").write_text("## Something\n")
    chlog = tmp_path / "CHANGELOG.md"
    chlog.write_text("[stale](target.md#nope)\n")
    broken = [b for b in check_links_mod.check_repo_link_fragments(tmp_path) if b.line > 0]
    assert broken == []


def test_fragment_gate_skips_non_md_target(check_links_mod, tmp_path):
    (tmp_path / "img.svg").write_text("<svg></svg>")
    (tmp_path / "README.md").write_text("[img](img.svg#whatever)\n")
    broken = [b for b in check_links_mod.check_repo_link_fragments(tmp_path) if b.line > 0]
    assert broken == []


def test_fragment_gate_skips_missing_target(check_links_mod, tmp_path):
    # The on-disk gate flags missing files; the fragment gate stays silent
    # to avoid duplicate diagnostics.
    (tmp_path / "README.md").write_text("[gone](missing.md#frag)\n")
    broken = [b for b in check_links_mod.check_repo_link_fragments(tmp_path) if b.line > 0]
    assert broken == []


def test_fragment_gate_reports_duplicate_anchor(check_links_mod, tmp_path):
    (tmp_path / "target.md").write_text('<a id="x"></a>\n## A\n\n<a id="x"></a>\n## B\n')
    (tmp_path / "README.md").write_text("[link](target.md#x)\n")
    broken = check_links_mod.check_repo_link_fragments(tmp_path)
    assert any("duplicate" in b.resolved for b in broken)


def test_fragment_gate_reports_orphan_anchor(check_links_mod, tmp_path):
    (tmp_path / "target.md").write_text('<a id="orph"></a>\n\nNot a heading line.\n')
    (tmp_path / "README.md").write_text("[link](target.md#orph)\n")
    broken = check_links_mod.check_repo_link_fragments(tmp_path)
    assert any("orphan" in b.resolved for b in broken)


def test_fragment_gate_reports_duplicate_without_inbound_link(check_links_mod, tmp_path):
    # Regression: M2 / M3 must cover every Markdown file, not only files reached
    # as link targets. A duplicate anchor in a doc no consumer happens to point at
    # would silently slip past otherwise.
    (tmp_path / "target.md").write_text('<a id="x"></a>\n## A\n\n<a id="x"></a>\n## B\n')
    (tmp_path / "README.md").write_text("# README\n")
    broken = check_links_mod.check_repo_link_fragments(tmp_path)
    assert any("duplicate" in b.resolved for b in broken)


def test_fragment_gate_reports_orphan_without_inbound_link(check_links_mod, tmp_path):
    (tmp_path / "target.md").write_text('<a id="orph"></a>\n\nNot a heading line.\n')
    (tmp_path / "README.md").write_text("# README\n")
    broken = check_links_mod.check_repo_link_fragments(tmp_path)
    assert any("orphan" in b.resolved for b in broken)


@pytest.mark.spec("DOCFRAME-008")
def test_fragment_gate_against_live_repo(check_links_mod):
    """No broken anchor refs on the live tree (positive control for ID-180)."""
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=ROOT,
        capture_output=True,
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout")
    broken = check_links_mod.check_repo_link_fragments(ROOT)
    assert broken == [], "\n".join(f"{b.source.relative_to(ROOT)}:{b.line}: {b.raw} → {b.resolved}" for b in broken)


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
