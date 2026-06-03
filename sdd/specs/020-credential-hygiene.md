# Credential Hygiene Specification

## Overview

Adds a `Secret` wrapper type that makes credential leakage structurally
impossible at the config layer, plus SFTP enum coercion and a logging
redaction filter.

**Module:** `src/remote_store/_config.py`
**Dependencies:** None (pure Python, always available)
**Related:** [002-registry-config.md](002-registry-config.md) (CFG sections),
[009-sftp-backend.md](009-sftp-backend.md) (SFTP-001), AF-008 (backend repr
masking), ID-039.

---

## Secret Wrapper

### SEC-001: Secret Class

**Invariant:** `Secret(value)` wraps a string credential. `__repr__` returns
`"Secret('***')"`, `__str__` returns `"***"`, `.reveal()` returns the
plain-text value. `__eq__` and `__hash__` compare/hash the underlying value.
`__bool__` delegates to the underlying string. `Secret` does not implement
`__iter__`, `__getitem__`, or `__len__` to prevent accidental unpacking.
**Raises:** `TypeError` if *value* is not a `str`.

### SEC-002: Secret Immutability

**Invariant:** `Secret.__setattr__` and `__delattr__` raise `AttributeError`
after construction. The class uses `__slots__ = ("_value",)` and bypasses the
override in `__init__` via `object.__setattr__`. `__reduce__` is implemented
so that `pickle` and `copy.deepcopy` reconstruct via the public constructor
instead of hitting the `__setattr__` override.

---

## Config Integration

### SEC-003: from_dict() Secret Wrapping

**Invariant:** `RegistryConfig.from_dict()` wraps string values for keys in
`_SENSITIVE_KEYS` (`key`, `secret`, `password`, `account_key`, `sas_token`,
`connection_string`) inside `Secret()`. Non-string values (e.g., `None`,
credential objects) are left unchanged.
**Forward note:** Extended at ID-127 (Graph backend) implementation to
add `"client_secret"` and `"client_certificate"` so config-loaded
Graph backends inherit the same auto-wrap protection
([RFC-0010](../rfcs/rfc-0010-graph-backend.md) §Auth,
[ADR-0022](../adrs/0022-graph-auth-model.md) §Credential masking).

### SEC-004: Backend Secret Acceptance

**Invariant:** Backend `__init__` methods accept `str | Secret | None` for
credential parameters and call `_reveal()` to unwrap them. Backends store
revealed plain strings internally — they already have AF-008 `__repr__`
masking, and SDK clients need plain strings.

| Backend | Parameters |
|---------|-----------|
| S3 | `key`, `secret` |
| S3-PyArrow | `key`, `secret` |
| SFTP | `password` |
| Azure | `account_key`, `sas_token`, `connection_string` |

### SEC-005: SFTP Host Key Policy Enum Coercion

**Invariant:** `SFTPBackend.__init__` accepts `host_key_policy` as either a
`HostKeyPolicy` enum member or a string value (`"strict"`, `"tofu"`,
`"auto"`). String values are coerced to the enum via `HostKeyPolicy(value)`.
Invalid strings raise `ValueError`.

### SEC-006: Config Repr Safety

**Invariant:** `repr(BackendConfig)` never leaks secret values. This is
structurally guaranteed by `Secret.__repr__` returning `"Secret('***')"` for
any wrapped credential in the `options` dict.

---

## Logging

### SEC-007: SecretRedactionFilter

**Invariant:** `SecretRedactionFilter` is a `logging.Filter` subclass that
replaces `Secret` instances in `record.args` (tuple or dict) with `"***"`
before the log message is formatted. Always returns `True` (does not suppress
records).

---

## Regression

### SEC-008: No-Leak Regression Tests

**Invariant:** Test suite includes assertions that known test secrets (e.g.,
`"AKID_TEST"`, `"SK_TEST"`) never appear in the `repr()` of config objects
constructed via `from_dict()`.
