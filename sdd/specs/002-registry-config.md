# Registry & Configuration Specification

## Overview

The Registry loads configuration, validates it, lazily instantiates backends, and provides access to named stores. Configuration objects are immutable data containers that describe — but do not instantiate — backends and stores.

---

## Configuration

### CFG-001: BackendConfig

**Invariant:** `BackendConfig(type, options)` is a frozen dataclass.
**Postconditions:** `type` is a string identifying the backend type. `options` is a `dict[str, object]`.

### CFG-002: StoreProfile

**Invariant:** `StoreProfile(backend, root_path, options)` is a frozen dataclass.
**Postconditions:** `backend` is a string referencing a backend name. `root_path` is the path prefix. `options` defaults to `{}`.

### CFG-003: RegistryConfig

**Invariant:** `RegistryConfig(backends, stores)` is the top-level config container.
**Postconditions:** `backends` maps names to `BackendConfig`. `stores` maps names to `StoreProfile`.

### CFG-004: Validation

**Invariant:** `validate()` checks that every store references an existing backend.
**Raises:** `ValueError` if any store references a non-existent backend.

### CFG-005: from_dict()

**Invariant:** `from_dict(data)` constructs a `RegistryConfig` from a dict.
**Example:**
```python
config = RegistryConfig.from_dict({
    "backends": {"local": {"type": "local", "options": {"root": "/tmp"}}},
    "stores": {"main": {"backend": "local", "root_path": "data"}},
})
```

### CFG-006: Immutability

**Invariant:** Config objects are immutable (frozen dataclasses).

### CFG-007: Config Priority

**Invariant:** Config-as-code has absolute priority. No env var merging.
**Rationale:** See [ADR-0002](../adrs/0002-config-resolution-no-merge.md).

---

## Registry

### REG-001: Construction and Validation

**Invariant:** Constructed with optional `RegistryConfig`. Validates immediately on construction.
**Raises:** `ValueError` if config is invalid.

### REG-002: get_store()

**Invariant:** `get_store(name)` returns a `Store` instance for the named profile.

### REG-003: Unknown Store

**Invariant:** `get_store(unknown)` raises a descriptive `KeyError`.

### REG-004: Lazy Backend Instantiation

**Invariant:** Backends are not instantiated until the first store referencing them is accessed.

### REG-005: Backend Sharing

**Invariant:** The same backend instance is shared across stores that reference the same backend config.

### REG-006: close()

**Invariant:** `close()` calls `close()` on all instantiated backends.

### REG-007: Context Manager

**Invariant:** Registry works as a context manager. `__exit__` calls `close()`.

### REG-008: Backend Factory Registry

**Invariant:** Maps type strings (e.g. `"local"`) to backend classes. `register_backend(type, cls)` adds entries.
