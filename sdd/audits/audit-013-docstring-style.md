# Audit 013 — Docstring Style Compliance

**Date:** 2026-05-05
**Scope:** All Python docstrings in `src/`, `tests/`, and `scripts/` at
`master` `f5c8c37`.
**Method:** Agent-assisted full read of every `.py` file; each docstring
cross-checked against the three rules extracted below.

---

## Checked rules (verbatim extracts from doc system)

### DESIGN.md § 2 — Module & Package Descriptions

> Every module starts with a 1-2 sentence docstring explaining *why it exists*.

### DESIGN.md § 4 — Docstrings

> Google style (`Args:`, `Returns:`, `Raises:`). Short and purpose-focused:
>
> ```python
> def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
>     """Write content to a file.
>
>     Args:
>         path: Relative path within the store.
>         content: Bytes or binary stream to write.
>         overwrite: If ``True``, replace existing file.
>
>     Raises:
>         AlreadyExists: If file exists and ``overwrite`` is ``False``.
>
>     ```python
>     store.write("data/report.csv", b"hello", overwrite=True)
>     ```
>     """
> ```

No RST cross-reference roles are defined or valid in Google-style docstrings.
Roles such as `:class:`, `:mod:`, `:meth:`, `:func:`, `:data:`, `:exc:` and
the `~`-prefix shorthand render as literal punctuation-laden text in every
renderer that does not process RST (plain GitHub, mkdocstrings in Google mode,
IDEs).

### DOCUMENTATION.md § 3 — Docstring completeness

| Symbol | `Args` | `Returns` | `Raises` | Example |
|---|---|---|---|---|
| Public method | Yes | Yes | Yes | Yes (short) |
| Property | — | Yes (in summary) | If applicable | Optional |
| Class | Yes (`__init__` params) | — | — | Yes |
| Function | Yes | Yes | Yes | Yes |
| Enum | — | — | — | — |
| Error class | — | — | — | — |

> No TODOs or placeholders in published docstrings.

### DOCUMENTATION.md — Docstring style notes

> Supplementary context that does not fit Args/Returns/Raises goes in a
> `Notes:` block, not scattered inline or appended to the summary line.
>
> Use `Example:` (not `Usage:`) for code snippets in docstrings. In
> class/function docstrings, mkdocstrings renders `Example:` as a collapsible
> box. For module-level docstrings, use MkDocs admonition syntax:
> `!!! example` with indented code blocks (Google sections don't parse in
> module docstrings).

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| High     | 7     | RST-style roles in published `src/` docstrings (render as literal garbage on the docs site) |
| Medium   | 4     | RST-style roles in `tests/` or `scripts/` docstrings (not published, but violate project convention) |
| Low      | 1     | Module docstring far exceeds the 1-2 sentence guideline — should move prose to a comment block |

Total fixable items: **12 locations across 8 files.**

---

## High — RST roles in published src/ docstrings

mkdocstrings runs in Google mode. RST roles pass through un-interpreted and
render as literal text (e.g. `` :class:`Backend` `` rather than a link or
even clean code formatting). Each instance below is a confirmed rendering
defect in the published API docs.

### H-1. `src/remote_store/_async_to_sync_adapter.py` — module docstring

Lines 3, 6. Two `:class:` roles in the module-level docstring.

```
# line 3
Implements the sync :class:`Backend` ABC by delegating to an
# line 6
:class:`AsyncBackend` running on a private event loop
```

**Fix:** replace with plain double-backtick names: `` ``Backend`` ``,
`` ``AsyncBackend`` ``.

### H-2. `src/remote_store/_async_to_sync_adapter.py` — `unwrap` method

Lines 209, 215 (two roles), 228. Three roles across the `Raises:` section and
body prose.

```
# line 209
raises :class:`~remote_store._errors.CapabilityNotSupported`
# line 215
:class:`_SyncSafeHandleProvider` and return it from
:meth:`~_SyncSafeHandleProvider.sync_safe_unwrap`
# line 228
CapabilityNotSupported: If the wrapped backend does not implement
    :class:`_SyncSafeHandleProvider`.
```

**Fix:** `` ``CapabilityNotSupported`` ``, `` ``_SyncSafeHandleProvider`` ``,
`` ``_SyncSafeHandleProvider.sync_safe_unwrap()`` ``.

### H-3. `src/remote_store/_async_to_sync_adapter.py` — `check_health` method

Line 289. One `:class:` with `~` prefix.

```
:class:`~remote_store.aio.AsyncBackend`, and any connectivity error
```

**Fix:** `` ``AsyncBackend`` ``.

### H-4. `src/remote_store/_async_to_sync_adapter.py` — `read` method

Line 329. One `:class:` role.

```
A forward-only :class:`io.RawIOBase` stream over the file
```

**Fix:** `` ``io.RawIOBase`` ``.

### H-5. `src/remote_store/_config.py` — `resolve_env` function

Line 405. One `:data:` role.

```
environ: Variable source. Defaults to :data:`os.environ`.
```

**Fix:** `` ``os.environ`` ``.

### H-6. `src/remote_store/_info.py` — `InfoResult` TypedDict

Line 35. One `:func:` role.

```
"""Structured result of :func:`info`."""
```

**Fix:** `` """Structured result returned by ``info()``.""" ``

### H-7. `src/remote_store/aio/_async_store.py` — `_read_chunks` method

Line 81. One `:meth:` role.

```
"""Inner generator for :meth:`read` — yields chunks from backend."""
```

**Fix:** `` """Inner generator for ``read()`` — yields chunks from backend.""" ``

### H-8. `src/remote_store/aio/_sync_adapter.py` — `SyncBackendAdapter` class

Lines 47, 50. Two roles in the class docstring.

```
# line 47
"""Wraps a synchronous :class:`Backend` as an :class:`AsyncBackend`.
# line 50
:func:`asyncio.to_thread`, keeping the event loop responsive.
```

**Fix:** `` ``Backend`` ``, `` ``AsyncBackend`` ``, `` ``asyncio.to_thread()`` ``.

---

## Medium — RST roles in tests/ and scripts/ docstrings

These files are not published to the docs site via mkdocstrings, so there is
no rendering defect. The violation is pure style inconsistency: RST roles have
no meaning in a Google-style project.

### M-1. `tests/backends/test_azure_live_hns.py` — module docstring

Lines 6, 7, 11, 13, 17, 39. Six RST roles: four `:class:` with `~` prefix,
two `:mod:`. This is the file added today; RST was introduced despite the
doc-system rules being in scope.

```
# line 6
``TestAzureWriteOnHnsDirectory`` in :mod:`tests.backends.test_azure` fabricates
# line 7
mocked :class:`~azure.storage.blob.BlobProperties` and
# line 11
:class:`~remote_store._errors.InvalidPath` when the target is an HNS
# line 13
:class:`~azure.storage.filedatalake.DataLakeServiceClient`.
# line 17
:mod:`tests.aio.test_async_azure` only verifies that
# line 39
:class:`tests.aio.test_async_azure_live.TestAsyncAzureLiveHNS`
```

**Fix per occurrence:**

| Line | RST role | Replace with |
|------|----------|-------------|
| 6 | `:mod:`tests.backends.test_azure`` | `` ``test_azure`` `` |
| 7 | `:class:`~azure.storage.blob.BlobProperties`` | `` ``BlobProperties`` `` |
| 11 | `:class:`~remote_store._errors.InvalidPath`` | `` ``InvalidPath`` `` |
| 13 | `:class:`~azure.storage.filedatalake.DataLakeServiceClient`` | `` ``DataLakeServiceClient`` `` |
| 17 | `:mod:`tests.aio.test_async_azure`` | `` ``test_async_azure`` `` |
| 39 | `:class:`tests.aio.test_async_azure_live.TestAsyncAzureLiveHNS`` | `` ``TestAsyncAzureLiveHNS`` `` |

### M-2. `tests/backends/test_azure_live_hns.py` — `live_hns_backend` fixture

Line 147. One `:meth:` with `~` prefix in the `Yields:` prose.

```
:meth:`~azure.storage.filedatalake.FileSystemClient.create_directory`.
```

**Fix:** `` ``FileSystemClient.create_directory()`` ``.

### M-3. `tests/backends/test_azure_live_hns.py` — `TestAzureLiveHnsMetadataSurvivesRename` class

Line 247. One `:mod:` role in the class docstring.

```
Companion to ``test_write_atomic_hns_metadata_preserved`` in
:mod:`tests.aio.test_async_azure`, which mocks ``upload_data``
```

**Fix:** `` ``test_async_azure`` ``.

### M-4. `scripts/gen_pages.py` — module docstring

Lines 8, 15. One `:func:` with `~` prefix, one `:mod:`.

```
# line 8
via :func:`~scripts.docs.render.render_dual_pages`.
# line 15
See :mod:`scripts.docs` for the helpers and
```

**Fix:** `` ``scripts.docs.render.render_dual_pages()`` ``,
`` ``scripts.docs`` ``.

### M-5. `scripts/mkdocs_hooks.py` — module docstring

Line 1. One `:class:` role.

```
"""MkDocs hook: apply :class:`LinkResolver` to docs-src files.
```

**Fix:** `` """MkDocs hook: apply ``LinkResolver`` to docs-src files. ``

---

## Low — Module docstring length

### L-1. `tests/backends/test_azure_live_hns.py` — 54-line module docstring

DESIGN.md § 2 prescribes 1-2 sentences for module docstrings. The module
docstring here runs 54 lines and contains design rationale, gating
architecture, cost-discipline policy, and companion-test cross-references.
This content is valid and useful, but it is not the "why it exists" sentence
— it is a spec-style preface.

Consequence: if mkdocstrings ever picks up test modules, this will render
verbatim. More practically, the guideline exists to keep module intent
scannable; 54 lines defeats that.

**Suggested relocation:** condense module docstring to 1-2 sentences; move the
rationale blocks into a section comment (``# ---`` headline) immediately below
the imports. Section comments are not consumed by any doc renderer but remain
fully readable in-editor.

---

## Out of scope / false positives

### AF-1. Double-backtick inline code (`` ``foo`` ``) — not a violation

Google-style docstrings use either single backticks (code spans in Markdown,
rendered by mkdocstrings) or double backticks (RST inline literals, also
rendered correctly by mkdocstrings in Google mode). Both are present throughout
the codebase. Double backticks are preferred for symbol names to match the
existing convention in the codebase. Not flagged.

### AF-2. `--` in method-summary lines — not a violation

Several one-liner docstrings use `` — `` (em dash) for "for" separators
(e.g. `` """Inner generator for ``read()`` — yields chunks from backend.""" ``).
This is within the CLAUDE.md em-dash convention (sparingly, not `--`). Not
flagged.

### AF-3. Test methods without docstrings — intentional

DESIGN.md § 11 requires class docstrings with spec IDs and `@pytest.mark.spec`
on methods. It does not mandate a prose docstring on every test method; a
clear method name is the primary documentation. Methods without a docstring
are not flagged unless the test name alone is insufficient.

---

## Complete todo list

Ordered by file, then line, for mechanical cleanup.

| # | File | Line(s) | Symbol | Violation | Severity |
|---|------|---------|--------|-----------|----------|
| 1 | `src/remote_store/_info.py` | 35 | `InfoResult` | `:func:\`info\`` | High |
| 2 | `src/remote_store/_async_to_sync_adapter.py` | 3, 6 | module docstring | `:class:` × 2 | High |
| 3 | `src/remote_store/_async_to_sync_adapter.py` | 209, 215 (×2), 228 | `unwrap` | `:class:`, `:meth:`, `:class:` | High |
| 4 | `src/remote_store/_async_to_sync_adapter.py` | 289 | `check_health` | `:class:` with `~` | High |
| 5 | `src/remote_store/_async_to_sync_adapter.py` | 329 | `read` | `:class:` | High |
| 6 | `src/remote_store/_config.py` | 405 | `resolve_env` | `:data:` | High |
| 7 | `src/remote_store/aio/_async_store.py` | 81 | `_read_chunks` | `:meth:` | High |
| 8 | `src/remote_store/aio/_sync_adapter.py` | 47, 50 | `SyncBackendAdapter` | `:class:` × 2, `:func:` | High |
| 9 | `tests/backends/test_azure_live_hns.py` | 6, 7, 11, 13, 17, 39 | module docstring | `:mod:` × 2, `:class:` × 4 | Medium |
| 10 | `tests/backends/test_azure_live_hns.py` | 147 | `live_hns_backend` fixture | `:meth:` with `~` | Medium |
| 11 | `tests/backends/test_azure_live_hns.py` | 247 | `TestAzureLiveHnsMetadataSurvivesRename` | `:mod:` | Medium |
| 12 | `scripts/gen_pages.py` | 8, 15 | module docstring | `:func:` with `~`, `:mod:` | Medium |
| 13 | `scripts/mkdocs_hooks.py` | 1 | module docstring | `:class:` | Medium |
| 14 | `tests/backends/test_azure_live_hns.py` | 1–54 | module docstring | 54-line docstring vs 1-2 sentence guideline | Low |
