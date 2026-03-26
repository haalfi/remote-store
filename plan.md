# ID-107b: `Backend.list_files(max_depth=N)` Native Optimization

## Summary

Add optional `max_depth` kwarg to the `Backend.list_files()` ABC and implement
native depth limiting in Local, SFTP, and Memory backends. S3/Azure accept the
parameter but rely on the existing Store-level client-side filter.

**Depends on:** ID-107 (completed).
**Research:** `sdd/research/research-depth-limited-listing.md` §4.6.

---

## Steps

### 1. Update spec — add Phase 2 section to `sdd/specs/037-depth-limited-listing.md`

Add a new section **DEPTH-003: Backend-native `max_depth` optimization** covering:
- ABC signature change: `max_depth: int | None = None` added to `Backend.list_files()`
- Default behavior: backends that don't override ignore `max_depth` (backward-compat)
- Store still applies client-side depth filter as a safety net
- No new capability flag needed (results are identical, only performance differs)
- Backend strategy table (Local: `os.walk` depth counter, SFTP: depth tracking in recursion, Memory: DFS stack depth, S3/Azure: pass-through)

**File:** `sdd/specs/037-depth-limited-listing.md`

### 2. Update Backend ABC signature

Change the abstract method signature in `_backend.py:217`:

```python
@abc.abstractmethod
def list_files(
    self, path: str, *, recursive: bool = False, max_depth: int | None = None,
) -> Iterator[FileInfo]:
```

Update docstring to document `max_depth`.

**File:** `src/remote_store/_backend.py`

### 3. Update Store to pass `max_depth` through to backend

In `_store.py:335-396`, modify the `self._backend.list_files()` call to pass
`max_depth` through. Keep the existing client-side depth filter as a safety net.

```python
for info in self._backend.list_files(
    self._full_path(path),
    recursive=effective_recursive,
    max_depth=max_depth,
):
```

**File:** `src/remote_store/_store.py`

### 4. Implement native `max_depth` in Local backend (P0)

Replace `rglob("*")` with `os.walk()` + depth counter. When `max_depth` is set
and `recursive` is true, use `os.walk()` tracking depth from the base directory
and skip directories beyond the limit.

**File:** `src/remote_store/backends/_local.py` (lines ~213-226)

### 5. Implement native `max_depth` in SFTP backend (P0)

Add depth tracking to the recursive `list_files` calls. When `max_depth` is set,
stop recursing into subdirectories when depth would exceed the limit. This saves
network round-trips — the biggest performance win.

**File:** `src/remote_store/backends/_sftp.py` (lines ~422-439)

### 6. Implement native `max_depth` in Memory backend (P1)

Track depth in the DFS stack in `_collect_files()`. Add `max_depth` parameter;
when set, don't push child directories to the stack if current depth equals
`max_depth`. Update `list_files()` to pass `max_depth` through.

**Files:** `src/remote_store/backends/_memory.py` (lines ~212-220, ~473-503)

### 7. Update S3 backends — accept parameter, no native optimization

Update `list_files` signature in `_s3_base.py` to accept `max_depth` but ignore
it (Store-level filter handles depth). Same for the PyArrow S3 backend if it
exists.

**File:** `src/remote_store/backends/_s3_base.py` (lines ~64-86)

### 8. Update Azure backend — accept parameter, no native optimization

Update `list_files` signature in `_azure.py` to accept `max_depth` but ignore it.

**File:** `src/remote_store/backends/_azure.py` (lines ~470-494)

### 9. Add backend-level tests

Add tests in a new test file or extend `tests/test_depth_listing.py` to verify:
- Backend ABC accepts `max_depth` kwarg
- Local backend natively limits depth (verify fewer filesystem operations)
- SFTP backend stops recursing at depth limit
- Memory backend stops DFS at depth limit
- S3/Azure still work correctly (client-side filter via Store)
- End-to-end tests via Store still pass (existing tests serve as regression)

Use `@pytest.mark.spec("DEPTH-003")` for traceability.

**File:** `tests/test_depth_listing.py` (extend) or new `tests/test_depth_backend_native.py`

### 10. Update BACKLOG.md

Move ID-107b from Ideas to In Progress, then mark as done after implementation.
Move completed item to `sdd/BACKLOG-DONE.md`.

**Files:** `sdd/BACKLOG.md`, `sdd/BACKLOG-DONE.md`

### 11. Update CHANGELOG.md

Add entry under `[Unreleased]` noting the backend-native `max_depth` optimization.

**File:** `CHANGELOG.md`

### 12. Lint, typecheck, and test

```bash
hatch run lint
hatch run typecheck
hatch run test
```

---

## Key Design Decisions

1. **Backward compatibility:** `max_depth=None` default means existing code and
   third-party backends continue to work unchanged.
2. **Safety net:** Store always applies client-side depth filter regardless of
   backend support — correctness over performance.
3. **No capability flag:** Unlike glob, depth filtering produces identical results
   whether native or client-side. The optimization is purely performance.
4. **S3/Azure deferred:** Flat scan + client filter is often optimal for object
   stores. Level-by-level prefix listing needs tree shape heuristics (future work).

## Risk Assessment

- **Low risk:** All changes are additive (new optional kwarg with default `None`).
- **Testing:** Existing `test_depth_listing.py` tests serve as regression suite;
  new tests verify backend-level behavior.
- **Third-party backends:** Will continue to work — they inherit `max_depth=None`
  default and Store filters client-side.
