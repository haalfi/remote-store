"""MkDocs gen-files helpers: scan sources, render pages, assemble nav.

Split across three modules:

  scan   -- Discovery of sdd/ specs/ADRs/RFCs and examples/ scripts into
            typed records (see :mod:`scripts.docs.scan`).
  render -- Filling ``_index.tmpl`` templates, wrapper-page emission, and
            the examples index (see :mod:`scripts.docs.render`).
  nav    -- Assembling ``SUMMARY.md`` from the per-section ``_nav.yml`` files
            plus the scanned records (see :mod:`scripts.docs.nav`).

The public entry point is :func:`build` in :mod:`scripts.gen_pages`, which
calls these in order; the hook is wired into MkDocs via ``mkdocs-gen-files``.
"""
