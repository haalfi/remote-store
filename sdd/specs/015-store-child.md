# Store.child() Specification

## Overview

`Store.child(subpath)` returns a new Store scoped to a subfolder of the parent, sharing the parent's backend instance. This enables runtime sub-scoping for folder isolation in service DI, multi-tenant routing, and hierarchical data layouts — without creating new backend connections.

**Related:** [001-store-api.md](001-store-api.md) (STORE-008), ID-021.

---

## Requirements

### CHILD-001: Method Signature

**Invariant:** `Store` exposes a method `child(subpath: str) -> Store`. The `subpath` argument is a non-empty relative path.

### CHILD-002: Root Composition

**Invariant:** The child store's effective root is `{parent_root}/{subpath}` when the parent has a non-empty root, or just `{subpath}` when the parent root is empty.

### CHILD-003: Subpath Validation

**Invariant:** The `subpath` argument is validated via `RemotePath`. Empty strings, paths containing `..` segments, and paths containing null bytes are rejected with `InvalidPath`.

### CHILD-004: Backend Sharing

**Invariant:** The child store's backend is the same object as the parent's backend (identity, not equality). No new connections are created.

### CHILD-005: Chaining

**Invariant:** `store.child("a").child("b")` produces a Store equivalent to `store.child("a/b")` — same backend identity and same effective root.

### CHILD-006: Close Semantics

**Invariant:** `child.close()` does **not** close the shared backend. Only the store that owns the backend (the original parent) may close it.

### CHILD-007: Context Manager

**Invariant:** A child store supports the context manager protocol. Exiting the `with` block calls the child's `close()`, which — per CHILD-006 — does not close the backend.

### CHILD-008: Equality

**Invariant:** A child store compares equal to (and hashes the same as) a directly constructed `Store` with the same backend instance and the same effective root path.

### CHILD-009: Path Round-Trip

**Invariant:** Paths returned by listing methods on a child store are child-relative. They can be fed directly back into the child's other methods (read, write, delete, etc.) without modification.

### CHILD-010: Thread Safety

**Invariant:** `child()` and the returned Store are safe to use across threads. The child inherits the parent's thread-safety guarantees (STORE-007).

### CHILD-011: Repr

**Invariant:** `repr(child)` shows the combined effective root path. It is indistinguishable from the repr of a directly constructed Store with the same root.
