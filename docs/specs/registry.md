# Registry Specification

## Overview

The Registry loads configuration, validates it, lazily instantiates backends, and provides access to named stores.

## REG-001: Construction and Validation

**Invariant:** Constructed with optional `RegistryConfig`. Validates immediately on construction.
**Raises:** `ValueError` if config is invalid.

## REG-002: get_store()

**Invariant:** `get_store(name)` returns a `Store` instance for the named profile.

## REG-003: Unknown Store

**Invariant:** `get_store(unknown)` raises a descriptive `KeyError`.

## REG-004: Lazy Backend Instantiation

**Invariant:** Backends are not instantiated until the first store referencing them is accessed.

## REG-005: Backend Sharing

**Invariant:** The same backend instance is shared across stores that reference the same backend config.

## REG-006: close()

**Invariant:** `close()` calls `close()` on all instantiated backends.

## REG-007: Context Manager

**Invariant:** Registry works as a context manager. `__exit__` calls `close()`.

## REG-008: Backend Factory Registry

**Invariant:** Maps type strings (e.g. `"local"`) to backend classes. `register_backend(type, cls)` adds entries.
