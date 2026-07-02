# Capabilities

::: remote_store.Capability

!!! info "Quality flags vs. method gates"
    Two kinds of capabilities exist. **Method gates** (e.g. `READ`, `WRITE`,
    `DELETE`) guard specific Store or Backend methods — calling a gated
    method on a backend that does not declare the capability raises
    `CapabilityNotSupported`. **Quality flags** (e.g. `SEEKABLE_READ`,
    `WRITE_RESULT_NATIVE`) are informational only — they describe behaviour
    the backend provides but do not guard any method call. For example, a
    backend that omits `SEEKABLE_READ` still supports `read_seekable()` — the
    flag reports only whether `read()` itself is seekable, not whether
    `read_seekable()` is native or spooled. Check the class docstring for the
    full categorisation.

::: remote_store.CapabilitySet

## See also

- [Capabilities Matrix](../capabilities-matrix.md) — per-backend capability comparison
- [Capabilities & Errors example](../../../examples/errors/capabilities_and_errors.py) — checking capabilities at runtime
