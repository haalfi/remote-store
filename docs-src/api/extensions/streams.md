# ext.streams

Composable `BinaryIO` wrappers for progress tracking and checksum computation.
These operate at the stream level — wrap the stream returned by `store.read()`
or passed to `store.write()`, no proxy wrapping needed.

See the [streams spec](https://github.com/haalfi/remote-store/blob/master/sdd/specs/033-ext-streams.md) for invariants.

::: remote_store.ext.streams

## See also

- [Streaming IO example](../../examples/streaming-io.md) — composable stream wrappers in action
