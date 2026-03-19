# Code Deduplication Analysis

**Date:** 2026-03-19
**Status:** Proposal --- for discussion

---

## Motivation

With v0.18.0 shipped (ProxyStore, ext.streams, ext.integrity), the
codebase has matured enough that structural duplication is now the
dominant maintenance risk.  Six backends (1,092 lines across the two S3 backends) and
14 extensions share patterns that were copy-pasted and drifted
independently.  This proposal catalogues the duplication, groups it by
extraction strategy, and proposes a phased plan.

---

## 1. S3 backend twins (highest value)

`_s3.py` (502 lines) and `_s3_pyarrow.py` (590 lines) share an s3fs
code path for **all listing, metadata, and error handling** --- the
PyArrow backend only diverges for read/write I/O and copy (which route
through `pyarrow.fs`).

### 1a. Identical methods --- copy-paste verbatim

| Method | `_s3.py` lines | `_s3_pyarrow.py` lines | Diff |
|---|---|---|---|
| `list_files()` | 192--214 | 263--285 | `self._fs` vs `self._s3fs` |
| `list_folders()` | 216--232 | 287--303 | same |
| `iter_children()` | 234--253 | 305--324 | same |
| `glob()` | 255--263 | 326--334 | same |
| `get_folder_info()` stats loop | 286--306 | 352--372 | pragma comments |
| `_classify_error()` | 414--423 | 561--570 | pragma; identical logic |

**~155 duplicated lines** in truly identical methods.

### 1b. Near-identical methods

| Method | Difference |
|---|---|
| `_info_to_fileinfo()` | **Functional divergence:** S3Backend extracts ETag (21 lines); S3PyArrowBackend omits it entirely (17 lines).  The mixin cannot own this method without parameterizing ETag extraction --- see design note below. |
| `_errors()` / `_s3fs_errors()` | Identical body.  PyArrow adds a second `_pyarrow_errors()` for the OSError branch. |
| `move()` / `copy()` | Identical existence checks; PyArrow splits error context around `_pa_fs.copy_file()`. |
| `_s3_path()` | Verbatim identical. |
| `delete_folder()` | Same non-empty check via `self._s3fs.ls()`. |

### Proposed extraction: `_s3_base.py`

A private base class **`_S3Base`** (not a mixin --- it carries state
via the abstract property) that owns:

- `_s3_path()`, `to_key()`, `native_path()`
- `list_files()`, `list_folders()`, `iter_children()`, `glob()`
- `get_folder_info()` stats-accumulation loop
- `_classify_error()`
- `_s3fs_errors()` context manager

**Property contract:** The base defines an abstract property that both
backends must implement:

```python
from abc import abstractmethod

class _S3Base(Backend):
    @property
    @abstractmethod
    def _s3fs(self) -> s3fs.S3FileSystem:
        """Return the s3fs filesystem instance."""
        ...
```

`S3Backend` adds a one-line property alias (`_s3fs = property(lambda
self: self._fs)`).  `S3PyArrowBackend` already uses `_s3fs`
internally --- no change needed.

**`_info_to_fileinfo()` design:** The base class provides the common
path/size/datetime logic.  ETag extraction is handled by an overridable
hook:

```python
# In _S3Base
def _info_to_fileinfo(self, info: dict[str, Any], path: str) -> FileInfo:
    name = _name_from_path(path)
    size = info.get("size", info.get("Size", 0)) or 0
    modified = _normalize_modified(info.get("LastModified", info.get("last_modified")))
    etag = self._extract_etag(info)  # overridable
    return FileInfo(path=RemotePath(path), name=name, size=int(size),
                    modified_at=modified, etag=etag)

def _extract_etag(self, info: dict[str, Any]) -> str | None:
    """Override to suppress or customize ETag extraction.

    The base class defaults to extracting ETag because that's the
    common case (S3Backend + any future s3fs-based backend).
    S3PyArrowBackend overrides to return None because PyArrow's
    read path doesn't use s3fs metadata.
    """
    raw = info.get("ETag") or info.get("etag")
    return _clean_etag(raw)

# S3PyArrowBackend overrides:
def _extract_etag(self, info: dict[str, Any]) -> str | None:
    return None
```

Both backends inherit the base class and provide only their divergent
pieces:

| `S3Backend` keeps | `S3PyArrowBackend` keeps |
|---|---|
| `_s3fs` property alias (one-liner) | `_s3fs` + `_pa_fs` properties |
| `read()`, `write()` via s3fs | `read()`, `write()` via PyArrow |
| `move()`, `copy()` single error ctx | `move()`, `copy()` split error ctx |
| --- | `_pyarrow_errors()` |
| `_head_to_fileinfo()`, digest helpers | `_extract_etag()` override (returns None) |

**Estimated savings:** ~130 net lines removed (gross ~150, plus ~20
lines for the base class itself), single maintenance point for listing
logic, error classification, and FileInfo construction.

**Backward compatibility:** The MRO of both backends changes (new base
class inserted).  `isinstance(backend, S3Backend)` still works.
`type(backend).__mro__` gains `_S3Base` --- low risk, but worth noting
for anyone doing MRO introspection.

**Test impact:** Both S3 test suites have independent fixture setups
(moto mocking).  The conformance suite covers all public operations,
so the mixin extraction is guarded by existing tests.  No test
restructuring is expected --- both test modules continue to
instantiate their concrete backend class.

**Spec impact:** No spec references internal backend method names
(`_classify_error`, `_info_to_fileinfo`, etc.).  Specs reference
public `Store` operations and capability names only.

---

## 2. Cross-backend error boilerplate

Every backend implements the same four-layer exception cascade:

```python
try:
    yield
except RemoteStoreError:
    raise
except FileNotFoundError:
    raise NotFound(..., path=path, backend=self.name) from None
except PermissionError:
    raise PermissionDenied(..., path=path, backend=self.name) from None
except Exception as exc:
    raise self._classify_error(exc, path) from None
```

And every `_classify_error()` does string-matching on the exception
message for `"404"`, `"403"`, `"connect"`, etc.

### 2a. Error factory helpers

Add to `_errors.py`:

```python
def not_found(path: str, backend: str) -> NotFound:
    return NotFound(f"Not found: {path}", path=path, backend=backend)

def permission_denied(path: str, backend: str) -> PermissionDenied:
    return PermissionDenied(f"Permission denied: {path}", path=path, backend=backend)
```

### 2b. `classify_by_message()` --- fallback, not primary path

The string-matching heuristic (`"404"`, `"403"`, etc.) is a code smell
being promoted to shared infrastructure.  Design it as a **fallback**
that backends can override with structured classification:

```python
def classify_by_message(exc: Exception, path: str, backend: str) -> RemoteStoreError:
    """Heuristic fallback classifier.  Backends with structured SDK
    errors (e.g. botocore ClientError.response['Error']['Code'])
    should classify those first and only call this for unrecognised
    exceptions."""
    msg = str(exc).lower()
    if "404" in msg or "not found" in msg:
        return not_found(path, backend)
    if "403" in msg or "access denied" in msg:
        return permission_denied(path, backend)
    if any(kw in msg for kw in ("endpoint", "connect", "timeout", "dns")):
        return BackendUnavailable(str(exc), path=path, backend=backend)
    return RemoteStoreError(str(exc), path=path, backend=backend)
```

Backends retain their own `_classify_error()` methods, which dispatch
on SDK-specific exception types first (e.g., `botocore ClientError`
error codes, Azure `HttpResponseError.status_code`, paramiko exception
classes) and fall through to `classify_by_message()` only for
unrecognised exceptions.  This makes the shared helper a safety net,
not the canonical classification strategy.

### 2c. Shared listing-error context manager

A generic `listing_errors()` context manager in the backend package
that handles the "missing folder returns empty iterator" convention:

```python
@contextmanager
def listing_errors(classifier, path: str, backend: str):
    try:
        yield
    except RemoteStoreError:
        raise
    except FileNotFoundError:
        return
    except PermissionError:
        raise permission_denied(path, backend) from None
    except Exception as exc:
        raise classifier(exc, path) from None
```

**Estimated savings:** ~70 net lines across 5 writable backends
(gross ~80, minus ~10 for the shared module), and a single place to
add new exception mappings.

---

## 3. FileInfo construction helpers

Five methods across four backends contain the same datetime/name/etag
normalization:

| Backend | Method | Lines |
|---|---|---|
| `_s3.py` | `_info_to_fileinfo()` | 425--445 |
| `_s3.py` | `_head_to_fileinfo()` | 455--480 |
| `_s3_pyarrow.py` | `_info_to_fileinfo()` | 572--588 |
| `_azure.py` | `_props_to_fileinfo()` | 764--791 |
| `_http.py` | response-to-FileInfo | 546--580 |

Common sub-patterns:

- **Name from path:** `path.rsplit("/", 1)[-1] if "/" in path else path` ---
  appears 6+ times.
- **Timezone normalization:** parse string, add UTC if naive, fallback to
  `now(UTC)` --- appears 5 times.
- **ETag cleaning:** `raw.strip('"').lower()` --- appears 3 times.

### Proposed extraction: `backends/_fileinfo.py`

```python
def _name_from_path(path: str) -> str:
    return path.rsplit("/", 1)[-1] if "/" in path else path

def _normalize_modified(value: str | datetime | None) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value is not None and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value or datetime.now(tz=timezone.utc)

def _clean_etag(raw: str | None) -> str | None:
    return raw.strip('"').lower() if isinstance(raw, str) else None
```

**Estimated savings:** ~40 net lines, plus elimination of the
copy-paste drift risk (e.g., `_s3_pyarrow` already dropped ETag
silently).

---

## 4. Stream wrapper boilerplate (`ext/streams.py`)

All four stream classes (`ProgressReader`, `ProgressWriter`,
`ChecksumReader`, `ChecksumWriter`) repeat identical:

- `close()` --- 3 lines x 4 = 12 lines
- `__enter__` / `__exit__` --- 9 lines x 4 = 36 lines
- `__getattr__` --- 2 lines x 4 = 8 lines

**56 lines of pure boilerplate.**

### Proposed extraction: `_StreamWrapper` base

```python
class _StreamWrapper:
    """Base for composable BinaryIO wrappers."""
    _inner: BinaryIO

    def close(self) -> None:
        self._inner.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
```

Each subclass provides only its data-path methods (`read`, `write`,
`readline`, `hexdigest`, etc.).

**Estimated savings:** ~35 net lines (gross ~40, minus ~5 for the base
class).  Also makes adding new wrappers trivial (e.g., a `TeeReader`
or `ThrottleWriter`).

---

## 5. Batch operation executor (`ext/batch.py`)

`batch_delete()` and `batch_copy()` each implement both sequential and
concurrent paths with identical:

- Error collection into `succeeded` / `failed` dicts
- `CapabilityNotSupported` re-raise
- `ThreadPoolExecutor` lifecycle
- Logging of results

~160 lines of near-identical scaffolding.

### Proposed extraction: generic `_run_batch()`

```python
def _run_batch(
    items: Iterable[T],
    fn: Callable[[T], None],
    *,
    max_workers: int | None,
    stop_on_error: bool,
    label: str,
) -> BatchResult:
    ...
```

Each batch function reduces to validation + one call to `_run_batch()`.

**Estimated savings:** ~65 net lines (gross ~80, minus ~15 for the
generic function).

---

## 6. Optional-dependency import guards

Five extensions repeat the same try/except pattern:

```python
try:
    import some_package
except ModuleNotFoundError as _exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "... is required ... Install with: pip install 'remote-store[...]'"
    ) from _exc
```

Three of the five sites import specific names (`from pydantic import
SecretStr`, `from dagster import IOManager`), not just the module
itself.

### Proposed extraction: `_require_extra()` as void guard

A void function that validates availability, then callers do their
normal imports:

```python
def _require_extra(package: str, extra: str) -> None:
    """Raise a helpful error if *package* is not installed.

    The import result is discarded --- callers do their own
    ``from X import Y`` afterwards.  This is safe because Python
    caches modules in ``sys.modules``, so the second import is a
    dict lookup with no runtime cost.
    """
    try:
        importlib.import_module(package)
    except ModuleNotFoundError as exc:  # pragma: no cover
        msg = f"{package} is required. Install with: pip install 'remote-store[{extra}]'"
        raise ModuleNotFoundError(msg) from exc
```

Usage:

```python
_require_extra("pydantic", "pydantic")
from pydantic import BaseModel, SecretStr  # normal import after guard
```

This avoids the awkward `mod = _require_extra(...); SecretStr =
mod.SecretStr` pattern.

**Location:** `ext/_helpers.py` (not `ext/__init__.py` --- that would
pollute the public namespace).

**Estimated savings:** ~20 net lines, plus consistent error messages.

---

## 7. Deprecated alias pattern

Three extensions (`pydantic.py`, `dagster.py`, `cache.py`) have
identical deprecation wrappers from BK-010.

### Proposed extraction: `_deprecated_alias()` decorator

```python
def _deprecated_alias(old_name: str, new_fn: Callable[P, T]) -> Callable[P, T]:
    @functools.wraps(new_fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        warnings.warn(
            f"{old_name}() is deprecated, use {new_fn.__name__}() instead",
            DeprecationWarning, stacklevel=2,
        )
        return new_fn(*args, **kwargs)
    wrapper.__name__ = old_name
    return wrapper
```

**Location:** `ext/_helpers.py` (alongside `_require_extra()`).

**Estimated savings:** ~25 net lines across 3 files.  Also makes
future renames zero-effort.

---

## 8. `Store` move/copy duplication

`Store.move()` (lines 394--423) and `Store.copy()` (lines 425--454)
share identical logic: capability check, path validation,
same-path short-circuit, delegation, logging.  Only the method name
and log string differ.

### Assessment: not worth extracting

The two methods are 30 lines each, adjacent, and readable.  A generic
`_path_operation()` helper would save ~15 lines but add indirection.
**Leave as-is** unless a third path-to-path operation appears.

---

## Prioritized implementation plan

| Phase | Scope | Net savings | Risk | Backlog ID |
|---|---|---|---|---|
| **1** | S3 base class + error factories + FileInfo helpers | ~240 lines | Medium --- MRO change, abstract property contract | BK-011 (done, PR #242) |
| **2** | `_StreamWrapper` base | ~35 lines | Low | new |
| **3** | `_run_batch()` generic executor | ~65 lines | Low --- tests already comprehensive | new |
| **4** | `ext/_helpers.py`: `_require_extra()` + `_deprecated_alias()` | ~45 lines | Low | new |

**Total estimated net reduction: ~385 lines** (~6.4% of the 6,031
lines in the analysed files).  Gross reduction ~455 lines, offset by
~70 lines for the new shared modules.

### Phasing rationale

- **Phase 1** bundles the tightly coupled pieces: the S3 base class
  needs the error factories (Phase 2 originally) and FileInfo helpers
  (Phase 3 originally).  One PR, one review cycle.  The diff will be
  large (~5 backend files, 2--3 new modules), so structure it as
  stacked commits for reviewability: (1) `_fileinfo.py` helpers,
  (2) error factories in `_errors.py`, (3) `_S3Base` extraction.
- **Phases 2--4** are independent leaves; batch into a single second
  PR.

### Test impact

- **Phase 1 (S3 base):** Both S3 test suites instantiate their
  concrete backend class over moto fixtures.  The conformance suite
  covers all public operations, so the extraction is guarded by
  existing tests.  No fixture restructuring expected.
- **Phases 2--4:** Pure internal refactors with full test coverage.
  No new test files needed.

### Backward compatibility

- **Phase 1:** Both S3 backends gain `_S3Base` in their MRO.
  `isinstance()` checks still pass.  No public API change.
- **Phases 2--4:** Internal only.  No public API surface affected.

### Spec impact

No specs reference internal backend method names (`_classify_error`,
`_info_to_fileinfo`, `_s3fs_errors`, etc.).  Specs reference public
`Store` operations and capability names only.  No spec updates needed.

### What this proposal does NOT cover

- **ProxyStore override boilerplate** in `observe.py` / `cache.py`:
  both override ~9 identical method signatures with different wrapping
  logic.  A mixin or code-gen approach could help, but the semantic
  difference (timing hooks vs cache lookup) makes a shared abstraction
  fragile.  Revisit after the async API work (ID-013) settles the
  method surface.
- **`Store` logging boilerplate** (29 structured log calls): a
  `_log_op()` helper could eliminate repetition, but the current
  approach is explicit and grep-friendly.  Not worth the indirection.

---

## Decision requested

1. Phase 1 bundles S3 base + error factories + FileInfo helpers into
   one PR.  Phases 2--4 as separate PRs, or batch them?
2. Naming: `_s3_base.py` for the base class module.  Agreed?
3. Confirmed: `_require_extra()` and `_deprecated_alias()` go in
   `ext/_helpers.py`.
