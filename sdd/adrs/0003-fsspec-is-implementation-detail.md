# ADR-0003: fsspec Is an Implementation Detail

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

[fsspec](https://filesystem-spec.readthedocs.io/) provides a unified filesystem interface for Python. Many storage backends (S3, Azure, HDFS) have fsspec implementations. We could either:

1. Expose fsspec as part of our public API
2. Use fsspec internally but hide it behind our own ABC

## Decision

**fsspec is an implementation detail, never exposed in the public API.**

- **Backend adapters may use fsspec internally** (e.g. S3 via `s3fs`, Azure via
  `adlfs`), or boto3, paramiko, or raw stdlib. The implementor chooses; nothing
  in the public API reveals which.
- **The `Backend` ABC is our own contract, not fsspec's.** It does not extend or
  depend on fsspec. A separate ABC earns its maintenance cost because ours is
  deliberately stricter than fsspec's interface: capability-driven,
  error-normalized, streaming-first. That stricter contract is the reason to
  hide fsspec rather than re-export it.
- **Native handles stay reachable through a type-safe, explicit escape hatch**
  (`unwrap()`), so extensions that knowingly accept backend coupling keep full
  access without being forced onto the normalized surface. The `unwrap()` API
  contract lives in spec 003 § BE-022; this ADR owns only the decision to keep
  fsspec behind it.

*Reverse if* our ABC's stricter guarantees stop earning their cost: e.g. fsspec
gains equivalent capability negotiation and error normalization, so a separate
contract would duplicate the ecosystem rather than add over it.

## Consequences

- Public API is stable regardless of fsspec changes
- Users don't need to learn fsspec
- Backend implementors can use fsspec, boto3, paramiko, or raw stdlib — their choice
- Extensions that need native access use `unwrap()` — explicit coupling, not accidental
- The local backend uses only stdlib (no fsspec) — proves the abstraction works without it
- Trade-off: we maintain our own ABC instead of reusing fsspec's. Intentional; the stricter contract (see Decision) is worth the cost.
