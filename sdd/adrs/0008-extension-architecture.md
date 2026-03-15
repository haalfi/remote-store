# ADR-0008: Extension Namespace Contract (`ext.*`)

## Status

Accepted

## Context

The project has three extensions (`ext.arrow`, `ext.batch`, `ext.transfer`)
that emerged organically but follow consistent patterns:

- Each lives in `src/remote_store/ext/<name>.py`.
- Each uses only the public `Store` / `Backend` API (never `_backend`).
- Each defines `__all__`.
- None owns or closes a Store.
- `CapabilityNotSupported` always propagates to the caller.
- Pure-Python extensions (`batch`, `transfer`) are exported unconditionally
  from `remote_store.__init__`.  Optional-dependency extensions (`arrow`)
  use a conditional `try/except` import with a helpful `ModuleNotFoundError`.

Future extensions (`ext.notify`, `ext.cache`, streaming atomic writes) and
potential third-party extensions need these rules written down.  Without a
documented contract, contributors would have to reverse-engineer the
conventions from existing code.

### Scope

This ADR covers the **namespace convention and module contract** for
stateless utility extensions — functions that accept a Store and operate
on it.  It does not define an extension framework with interfaces,
hooks, lifecycle management, or plugin discovery.  Those patterns will
be designed when needed (see "Future patterns" below).

## Decision

### Extension location

Extensions live in `src/remote_store/ext/<name>.py` (single module) or
`src/remote_store/ext/<name>/` (sub-package for complex extensions).
The `ext/__init__.py` re-exports nothing; each extension is imported
directly by the user or by `remote_store.__init__`.

### Public API only

Extensions MUST use only the public `Store` and `Backend` API.  Direct
access to private attributes (e.g., `store._backend`) is forbidden.
`Store.unwrap(type_hint)` is the approved escape hatch for native
backend access.

### Module exports

Every extension module defines `__all__` listing its public symbols.

### Lifecycle rules

Extensions do not own `Store` lifecycle.  They must never call
`store.close()` or use the Store as a context manager.  The caller owns
the Store and is responsible for its lifecycle.

### Error propagation

`CapabilityNotSupported` raised by Store methods MUST propagate to the
extension's caller.  Extensions must not catch and suppress it.

### Export rules

> Superseded by ADR-0013 -- optional-dependency extensions are no longer
> re-exported from `remote_store.__init__`. Import them directly from
> `remote_store.ext.<name>`.

Two patterns, determined by dependency requirements:

1. **Pure Python (no extra dependencies).**
   Exported unconditionally from `remote_store.__init__`.  Users get
   the symbols with `import remote_store` or
   `from remote_store import <name>`.

2. **Optional dependency (requires an extra).**
   The extension module guards its dependency import at the top level
   with a `try/except ModuleNotFoundError` that raises a helpful error:

   ```python
   # In ext/<name>.py:
   try:
       import pyarrow as pa
   except ModuleNotFoundError as _exc:
       raise ModuleNotFoundError(
           "PyArrow is required for the arrow extension. "
           "Install it with: pip install 'remote-store[arrow]'"
       ) from _exc
   ```

   `remote_store.__init__` conditionally re-exports these symbols with
   a silent `try/except ImportError` guard so that `from remote_store
   import pyarrow_fs` works when the dependency is installed, but core
   package import never fails:

   ```python
   # In remote_store/__init__.py:
   try:
       from remote_store.ext.arrow import StoreFileSystemHandler, pyarrow_fs
       __all__ += ["StoreFileSystemHandler", "pyarrow_fs"]
   except ImportError:
       pass
   ```

### Dependency rules

- Core `remote-store` stays zero-dependency.
- Optional dependencies are declared as extras in
  `pyproject.toml [project.optional-dependencies]`.
- Extension code must not import optional dependencies at the top level
  in `TYPE_CHECKING` blocks without a guard, since mypy may still
  evaluate those imports.

### Development lifecycle

New extensions follow the SDD pipeline:

1. RFC in `sdd/rfcs/` (proposal and design discussion).
2. Spec in `sdd/specs/` (contract and invariants).
3. Tests in `tests/test_<name>.py` with `@pytest.mark.spec("ID")`.
4. Implementation in `src/remote_store/ext/<name>.py`.
5. Guide in `guides/` and docs wiring in `docs-src/`.
6. CHANGELOG and BACKLOG updated in the same commit.

Tests live at `tests/test_<name>.py` (flat, not `tests/ext/`).

### Third-party extensions

External packages should use the naming convention
`remote-store-<name>` (PyPI package name).  They should:

- Use only the public Store/Backend API.
- Use `register_backend()` for backend registration (if applicable).
- Use `Store.unwrap()` for native handle access.
- For backend extensions: reuse the conformance test suite by importing
  and parameterizing it.

Entry-point based plugin discovery is deferred until third-party
extensions emerge and the discovery mechanism can be designed with
real use cases.

### Future patterns (not yet designed)

The current convention covers **stateless utility extensions** —
standalone functions that accept a Store and return results.  Planned
extensions will require additional patterns:

- **`ext.notify`** (ID-024) needs a hook/interceptor mechanism to wrap
  Store operations.  Likely a decorator or proxy Store pattern:
  `store = instrument(store, on_read=..., on_error=...)`.
- **`ext.cache`** (ID-025) needs a wrapping/proxy pattern that sits
  between the caller and the Store, intercepting reads and caching
  results.
- **Streaming atomic writes** (ID-026) needs a context manager protocol
  integrated with the Store.

These patterns will be designed as separate ADRs when the extensions
are implemented.  This ADR's rules (public API only, `__all__`,
dependency management, test location) apply to all extension types;
the additional patterns will layer on top.

## Consequences

- **Documented contract.** Contributors and third-party authors have a
  single reference for extension rules.
- **Consistent patterns.** New extensions follow the same structure,
  reducing review friction.
- **Zero breaking changes.** This ADR codifies existing practice; no
  existing code needs to change.
- **CONTRIBUTING.md checklist.** An "Adding an Extension" checklist
  ensures nothing is missed.
- **Deferred complexity.** Entry-point discovery, namespace packages,
  and extension registries are explicitly deferred until real need
  emerges.
