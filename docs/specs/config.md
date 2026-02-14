# Configuration Specification

## Overview

Configuration objects describe backends and stores. They are immutable data containers — they describe, but do not instantiate.

## CFG-001: BackendConfig

**Invariant:** `BackendConfig(type, options)` is a frozen dataclass.
**Postconditions:** `type` is a string identifying the backend type. `options` is a `dict[str, object]`.

## CFG-002: StoreProfile

**Invariant:** `StoreProfile(backend, root_path, options)` is a frozen dataclass.
**Postconditions:** `backend` is a string referencing a backend name. `root_path` is the path prefix. `options` defaults to `{}`.

## CFG-003: RegistryConfig

**Invariant:** `RegistryConfig(backends, stores)` is the top-level config container.
**Postconditions:** `backends` maps names to `BackendConfig`. `stores` maps names to `StoreProfile`.

## CFG-004: Validation

**Invariant:** `validate()` checks that every store references an existing backend.
**Raises:** `ValueError` if any store references a non-existent backend.

## CFG-005: from_dict()

**Invariant:** `from_dict(data)` constructs a `RegistryConfig` from a dict.
**Example:**
```python
config = RegistryConfig.from_dict({
    "backends": {"local": {"type": "local", "options": {"root": "/tmp"}}},
    "stores": {"main": {"backend": "local", "root_path": "data"}},
})
```

## CFG-006: Immutability

**Invariant:** Config objects are immutable (frozen dataclasses).

## CFG-007: Config Priority

**Invariant:** Config-as-code has absolute priority. No env var merging.
