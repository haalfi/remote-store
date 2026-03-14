# Research: Google-Style Docstring Migration & Zensical Evaluation

**Item IDs:** ID-064 (docs enhancements)
**Related:** ID-067 (griffe-typingdoc — PEP 727 comparison in §5)
**Date:** 2026-03-13
**Context:** Evaluate migrating from Sphinx-style to Google-style docstrings
for native markdown support in mkdocstrings, and assess Zensical as a
potential mkdocs replacement.

---

## 1. Problem Statement

The current codebase uses Sphinx-style docstrings (`:param:`, `:returns:`,
`:raises:`). While mkdocstrings parses these correctly for parameter/return/raise
sections, Sphinx style has structural limitations:

- **No markdown inside docstrings.** Sphinx-style only parses the recognized
  `:param:`/`:returns:`/`:raises:` directives. Everything else (`:class:`,
  `:meth:`, `.. note::`, `.. code-block::`) passes through as literal text.
- **No native admonitions.** Cannot write `Note:` or `Warning:` sections that
  render as styled callouts in the docs.
- **Less readable in source.** `:param name: description` is denser than
  indented `Args:` / `Returns:` sections.
- **Second-class support in mkdocstrings.** The mkdocstrings maintainer has
  stated Sphinx/reST style is less well-supported than Google/NumPy. Google
  style has more configuration options and is the recommended style.

**Goal:** Native markdown in docstrings, no rendering workarounds, modern
API docs that look like FastAPI/Pydantic.

---

## 2. Google-Style Docstrings with mkdocstrings

### 2.1 Markdown Features That Work

| Feature | Support | Notes |
|---------|---------|-------|
| Fenced code blocks | Full | Requires `pymdownx.superfences` (already configured) |
| Admonitions | Native | Unrecognized section headers (`Note:`, `Warning:`, `Tip:`) auto-transform to admonitions |
| Cross-references | Full | `[display][package.module.Class]` or `[package.module.Class][]` syntax |
| Tables | Full | Standard markdown tables work inside docstrings |
| Inline code | Full | Backtick syntax works as expected |
| Examples (doctest) | Full | `>>>` / `...` lines auto-parse as `pycon` code blocks |

**Already configured** in `mkdocs.yml`:
- `admonition` extension
- `pymdownx.superfences`
- `pymdownx.highlight`
- `pymdownx.snippets`

No new markdown extensions needed.

### 2.2 Configuration Change

Current (`mkdocs.yml` lines 46-63):

```yaml
plugins:
  - mkdocstrings:
      handlers:
        python:
          options:
            docstring_style: sphinx
            docstring_section_style: list
```

After migration:

```yaml
plugins:
  - mkdocstrings:
      handlers:
        python:
          options:
            docstring_style: google
            docstring_section_style: list
            docstring_options:
              returns_multiple_items: true
              returns_named_value: true
              warn_unknown_params: true
```

Key additions:
- `docstring_style: google` (replaces `sphinx`)
- `docstring_options` — Google style exposes more configuration knobs than
  Sphinx; `warn_unknown_params: true` catches param/signature mismatches
  at docs build time.

### 2.3 Syntax Comparison

**Before (Sphinx):**

```python
def write(self, path: str, data: bytes, *, overwrite: bool = False) -> None:
    """Write binary data to a file.

    :param path: Backend-relative key.
    :param data: Content to write.
    :param overwrite: If ``True``, overwrite existing files.
    :returns: None
    :raises AlreadyExists: If *path* exists and *overwrite* is ``False``.
    :raises CapabilityNotSupported: If backend lacks ``WRITE``.
    """
```

**After (Google):**

```python
def write(self, path: str, data: bytes, *, overwrite: bool = False) -> None:
    """Write binary data to a file.

    Args:
        path: Backend-relative key.
        data: Content to write.
        overwrite: If `True`, overwrite existing files.

    Returns:
        None

    Raises:
        AlreadyExists: If *path* exists and *overwrite* is `False`.
        CapabilityNotSupported: If backend lacks `WRITE`.
    """
```

**New capabilities unlocked (Google only):**

```python
def write(self, path: str, data: bytes, *, overwrite: bool = False) -> None:
    """Write binary data to a file.

    Args:
        path: Backend-relative key.
        data: Content to write.
        overwrite: If `True`, overwrite existing files.

    Returns:
        None

    Raises:
        AlreadyExists: If *path* exists and *overwrite* is `False`.
        CapabilityNotSupported: If backend lacks `WRITE`.

    Note:
        For text data, use [`write_text()`][remote_store.Store.write_text]
        instead — it handles encoding automatically.

    Example:
        ```python
        store.write("data/output.bin", b"hello world", overwrite=True)
        ```
    """
```

The `Note:` section renders as a styled admonition. The cross-reference
link resolves automatically. Neither is possible with Sphinx style.

### 2.4 Known Gotchas

1. **Strict parameter parsing.** Griffe's Google parser is stricter than
   Sphinx. Types in parentheses after parameter names (e.g., `path (str):`)
   are parsed but redundant when type hints exist in the signature. Omit
   them — mkdocstrings pulls types from annotations.

2. **Returns section syntax.** With `returns_named_value: true` (default),
   `thing: Description` is parsed as name + description, not type +
   description. To specify a return type inline, use `(int): Description`.
   In practice, return types come from annotations, so this rarely matters.

3. **Tuple return documentation.** Google style lacks clean syntax for
   individual tuple members. Workaround: describe in prose within the
   Returns section. NumPy style handles this better, but remote-store has
   no tuple-returning public methods.

4. **Cross-references require full paths.** `[Store][]` won't resolve;
   must be `[Store][remote_store.Store]`. Relative cross-references
   (`[.name]`) are a mkdocstrings-python Insiders feature.

5. **No nested admonitions.** Section-header admonitions (`Note:`,
   `Warning:`) cannot be nested. For complex callouts, use the prose
   section of the docstring with standard markdown admonition syntax.

---

## 3. Migration Plan

### 3.1 Scope

| Category | Count | Files |
|----------|-------|-------|
| Core modules | ~10 | `_store.py`, `_backend.py`, `_errors.py`, `_models.py`, `_capabilities.py`, `_path.py`, `_secret.py`, etc. |
| Backends | ~7 | `_local.py`, `_s3.py`, `_s3_pyarrow.py`, `_sftp.py`, `_azure.py`, `_memory.py`, backend init |
| Extensions | ~10 | `ext/arrow.py`, `ext/batch.py`, `ext/cache.py`, `ext/glob.py`, `ext/observe.py`, `ext/otel.py`, `ext/partition.py`, `ext/pydantic.py`, `ext/transfer.py`, `ext/yaml.py` |
| Config modules | ~4 | `_config.py`, backend configs |
| Total | ~31 | ~120+ docstring blocks |

### 3.2 Automated Tooling

Three conversion tools exist:

| Tool | Approach | Quality | Recommendation |
|------|----------|---------|----------------|
| **pyment** | Regex-based | Medium — known bugs, last updated 2024 | Skip |
| **docconvert** | Pattern matching | Good — supports `--in-place`, multi-threaded | Viable for first pass |
| **pymend** | AST-based (fork of pyment) | Best — uses `docstring_parser`, handles edge cases | Best option |

**Recommended approach:**
1. Run `pymend -w -s rest -t google src/` for AST-based mechanical conversion
2. Manual review pass: fix edge cases, add `Note:`/`Example:` sections where
   valuable, verify cross-references
3. Run `hatch run docs-build` to catch warnings from `warn_unknown_params`
4. Run `hatch run test` to verify no doctest breakage

### 3.3 Sequencing

1. **Config change** — switch `docstring_style: sphinx` to `google` in
   `mkdocs.yml`, add `docstring_options`
2. **Mechanical conversion** — run automated tool, commit
3. **Manual review** — fix edge cases, enhance with markdown features
4. **Docs build validation** — strict mode, check all pages render correctly
5. **Update style guide** — update `sdd/DESIGN.md` section 4 to reflect
   Google style conventions
6. **Update CLAUDE.md** — if docstring style is referenced in instructions

### 3.4 Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Automated tool misparses edge cases | Medium | Low | Manual review pass |
| Cross-references break | Low | Medium | `signature_crossrefs: true` already configured; `hatch run docs-build` catches broken links |
| Doctest examples break | Low | Low | `hatch run test` includes doctest collection |
| Large diff obscures review | High | Low | Single-purpose PR, mechanical changes clearly separated from enhancements |

---

## 4. Zensical Evaluation

### 4.1 What Is Zensical?

Zensical is the **official successor to Material for MkDocs**, built by the
same creator (Martin Donath / squidfunk). It is a Rust+Python static site
generator purpose-built for documentation, motivated by MkDocs being
unmaintained since August 2024.

### 4.2 Current State (March 2026)

| Aspect | Status |
|--------|--------|
| Version | 0.0.26 |
| Stability | No ETA for 1.0; "ready for prime time" per team, but 0.0.x signals API churn |
| Migration path | Reads `mkdocs.yml` natively; existing Markdown/CSS/JS carry over |
| mkdocstrings support | Preliminary — basic API reference works via `mkdocstrings-python` (Griffe) |
| **Cross-references** | **Broken** — GitHub issue #237. `[func][pkg.func]` does not resolve. Blocker. |
| Admonitions | Work in regular pages; behavior inside docstrings depends on mkdocstrings integration |
| Performance | 4-5x faster incremental rebuilds |
| Rust CommonMark parser | Planned, not shipped |

### 4.3 Assessment

**Zensical is not yet viable for remote-store.** The broken cross-reference
support in mkdocstrings (issue #237) is a dealbreaker for library API docs
where interlinked classes, methods, and error types are essential.

**Recommendation:** Revisit when:
- Issue #237 (cross-references) is resolved
- Version reaches 0.1.0+ with stable plugin API
- mkdocstrings integration moves beyond "preliminary"

The Google-style migration is independent of Zensical — Google style works
with both mkdocs-material (current) and Zensical (future). Migrating now
does not create migration debt.

---

## 5. Comparison: Google Style vs PEP 727 (`Annotated[T, Doc()]`)

For completeness, comparing against ID-067 (griffe-typingdoc):

| Criterion | Google Style | PEP 727 |
|-----------|-------------|---------|
| Maturity | Battle-tested, universal tooling | PEP not accepted, experimental |
| Tooling | All editors, linters, formatters support it | Requires `griffe-typingdoc` extension |
| Readability | Good — structured sections | Mixed — docs inline with type hints |
| Markdown support | Full via mkdocstrings | Full via griffe |
| Migration effort | ~100 docstring blocks, mechanical | Rewrites every function signature |
| Ecosystem | Standard across Python ecosystem | FastAPI-specific pattern |

**Verdict:** Google style is the right move now. PEP 727 remains a future
option (ID-067 stays in parking lot).

---

## 6. Recommendations

1. **Migrate to Google-style docstrings** — single dedicated PR, mechanical
   conversion + manual review. Immediate payoff: markdown in docstrings,
   native admonitions, better source readability.

2. **Do not migrate to Zensical yet** — cross-reference support is broken,
   0.0.x versioning signals instability. Monitor issue #237.

3. **Keep ID-067 (PEP 727) in parking lot** — not recommended until PEP is
   accepted and ecosystem tooling matures.

4. **Suggested backlog item:** New ID for Google-style migration (distinct from
   ID-064), prioritized in Feature work. Estimated scope: ~31 files, ~120+
   docstring blocks, 1 config change, 1 style guide update.
