# Seekable Read

Seekable read is built into the Store API via `Store.read_seekable()`.
See the [Store API reference](../store.md) for method documentation.

`ext.seekable` was removed before its first release — its functionality
is now part of the core API (ADR-0017).

## See also

- [Seekable read spec](https://github.com/haalfi/remote-store/blob/master/sdd/specs/036-seekable-read.md) — SEEK-001 through SEEK-012
- [ADR-0017](https://github.com/haalfi/remote-store/blob/master/sdd/adrs/0017-seekable-read-on-store-api.md) — Store-level read_seekable() design
- [ext.streams](streams.md) — composable BinaryIO wrappers for progress and checksums
