# Capabilities

::: remote_store.Capability

!!! info "Quality flags vs. method gates"
    Two kinds of capabilities exist. **Method gates** (`GLOB`, `ATOMIC_WRITE`,
    `METADATA`, `MOVE`, `COPY`, `DELETE`, `LIST`, `READ`, `WRITE_RESULT_NATIVE`,
    `USER_METADATA`) guard specific Store or Backend methods — calling a gated
    method on a backend that does not declare the capability raises
    `CapabilityNotSupported`. **Quality flags** (`SEEKABLE_READ`,
    `CONSISTENT_LISTING`, and similar) are informational only — they describe
    behaviour the backend provides but do not guard any method call. Check
    the class docstring for the full categorisation.

::: remote_store.CapabilitySet

## See also

- [Capabilities Matrix](../capabilities-matrix.md) — per-backend capability comparison
- [Capabilities & Errors example](../examples/capabilities-and-errors.md) — checking capabilities at runtime
