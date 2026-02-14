# Capabilities Specification

## Overview

Backends declare their supported operations via a `Capability` enum and a `CapabilitySet` collection. Operations are capability-gated: unsupported operations fail explicitly.

## CAP-001: Capability Enum Members

**Invariant:** `Capability` is an enum with members: `READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `GLOB`, `RECURSIVE_LIST`, `METADATA`.

## CAP-002: CapabilitySet Construction

**Invariant:** `CapabilitySet` is constructed from a `set[Capability]`.
**Example:**
```python
cs = CapabilitySet({Capability.READ, Capability.WRITE})
```

## CAP-003: supports() Method

**Invariant:** `supports(cap)` returns `True` if `cap` is in the set, `False` otherwise.

## CAP-004: require() Method

**Invariant:** `require(cap)` raises `CapabilityNotSupported` if `cap` is not in the set.
**Raises:** `CapabilityNotSupported` with `capability` attribute set to the capability name.

## CAP-005: Iteration and Membership

**Invariant:** `CapabilitySet` supports `in` operator and `__iter__`.
**Example:**
```python
assert Capability.READ in cs
for cap in cs:
    print(cap)
```

## CAP-006: Immutability

**Invariant:** `CapabilitySet` is immutable after construction. The internal set cannot be modified.
