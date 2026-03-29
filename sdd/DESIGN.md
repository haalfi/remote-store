# Code Style & Conventions

## Intent & Scope

Coding conventions for all `src/`, `tests/`, and `examples/` code. All code must pass `ruff check`, `ruff format`, and `mypy --strict`.

## Rules

### 1. Formatting & Linting

- **Formatter/linter:** ruff (line-length 120)
- **Type checking:** mypy strict mode
- **`from __future__ import annotations`** in every module

### 2. Module & Package Descriptions

Every module starts with a 1-2 sentence docstring explaining *why it exists*:

```python
"""Normalized error hierarchy for remote_store."""
```

Package `__init__.py` files follow the same rule:

```python
"""Backend implementations for remote_store."""
```

### 3. Type Annotations

Public method signatures use PEP 604 union syntax (Python >=3.10):

```python
def __init__(self, config: RegistryConfig | None = None) -> None: ...
def write(self, path: str, content: BinaryIO | bytes, *, overwrite: bool = False) -> None: ...
```

- Required args are positional; behavior flags are keyword-only (`*`).
- `X | None` replaces `Optional[X]`, `X | Y` replaces `Union[X, Y]` (PEP 604).
- `typing` imports only for generics not yet built-in (`Callable`, `Iterator`, etc.).

### 4. Docstrings

Google style (`Args:`, `Returns:`, `Raises:`). Short and purpose-focused:

```python
def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
    """Write content to a file.

    Args:
        path: Relative path within the store.
        content: Bytes or binary stream to write.
        overwrite: If ``True``, replace existing file.

    Raises:
        AlreadyExists: If file exists and ``overwrite`` is ``False``.

    ```python
    store.write("data/report.csv", b"hello", overwrite=True)
    ```
    """
```

### 5. Code Organisation Comments

Two styles for structuring large files, each with a distinct purpose.

|               | Regions                              | Headlines                        |
|---------------|--------------------------------------|----------------------------------|
| Purpose       | Group related items by concern       | Introduce a new section          |
| Markers       | Paired (`# region:` ... `# endregion`) | Single (box divider)           |
| IDE behaviour | Foldable                             | None (purely visual)             |
| Scope         | Anywhere (class or module level)     | Module level                     |

**Regions** (`# region:` / `# endregion`) -- group related items by concern.
Paired markers that IDEs can fold. Use for items that are not individually
collapsible as a group (e.g. several methods that together form "read
operations"). **Never** wrap a single class or function -- those are already
collapsible on their own.

```python
# region: BE-006 through BE-007: read operations
def read(self, path: str) -> BinaryIO:
    ...

def read_bytes(self, path: str) -> bytes:
    ...
# endregion
```

**Headlines** (box dividers) -- introduce a new section at module level.
Single marker (not paired) before a top-level definition or group of
definitions. Purely visual; no IDE folding behaviour.

```python
# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def pyarrow_fs(store: Store, ...) -> pafs.PyFileSystem:
    ...
```

Use headlines in modules with multiple top-level classes or logical sections
(extensions, tests, benchmarks, scripts). Do not use inside classes -- use
regions there instead.

### 6. Method Ordering

Within a class, methods are ordered by logical grouping:

1. Class variables / constants
2. `__init__`
3. Properties
4. Public methods (grouped by domain: read, write, delete, list, etc.)
5. Dunder methods (`__eq__`, `__hash__`, `__repr__`)
6. Private helpers

### 7. Comments

Minimal, long-term value only. Do not comment *what* the code does -- comment *why* when the reason is non-obvious. No TODO comments without a linked issue.

### 8. Constants

- Public: `UPPER_SNAKE_CASE`
- Private: `_UPPER_SNAKE_CASE`

### 9. `__all__`

Declared only in public-facing `__init__.py` modules. Internal modules (`_errors.py`, etc.) do not need `__all__` -- the underscore prefix signals "internal".

### 10. Error Messages

f-strings with context for human-readable tracebacks. Structured attributes for programmatic access:

```python
raise NotFound(f"File not found: {path}", path=path, backend=self.name)
```

### 11. Test Style

Tests are grouped into classes by spec aspect. The class docstring references the spec IDs covered:

```python
class TestRemotePathNormalization:
    """PATH-002 through PATH-006: normalization rules."""

    @pytest.mark.spec("PATH-002")
    def test_backslash_to_forward_slash(self) -> None:
        assert str(RemotePath("a\\b\\c")) == "a/b/c"

    @pytest.mark.spec("PATH-005")
    def test_collapse_consecutive_slashes(self) -> None:
        assert str(RemotePath("a///b")) == "a/b"
```

Each test method carries a `@pytest.mark.spec("ID")` marker for traceability.

For test **quality** rules (assertions, mocking, coverage), see `sdd/TESTING.md`.
