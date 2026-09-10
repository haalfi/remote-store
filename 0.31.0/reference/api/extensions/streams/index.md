# ext.streams

Composable `BinaryIO` wrappers for progress tracking and checksum computation. These operate at the stream level — wrap the stream returned by `store.read()` or passed to `store.write()`, no proxy wrapping needed.

See the [streams spec](https://docs.remotestore.dev/stable/explanation/design/specs/033-ext-streams/index.md) for invariants.

## streams

Stream-level wrappers for progress tracking and checksum computation.

Composable `BinaryIO` wrappers that operate at the stream level, not the Store level. No proxy wrapping is needed — just wrap the stream returned by `store.read()` or passed to `store.write()`.

Example

```
from remote_store.ext.streams import ProgressReader, ChecksumReader

stream = ChecksumReader(
    ProgressReader(store.read("file.bin"), callback=update_bar),
    algorithm="sha256",
)
data = stream.read()
assert stream.hexdigest() == expected_hex
```

### ProgressReader

```
ProgressReader(
    inner: BinaryIO, callback: Callable[[int], None]
)
```

Bases: `_StreamWrapper`

Readable `BinaryIO` wrapper that fires a callback per `read()`.

The callback receives the number of bytes read (not cumulative). Empty reads do not fire the callback.

Parameters:

- **`inner`** (`BinaryIO`) – Readable binary stream to wrap.
- **`callback`** (`Callable[[int], None]`) – Called with len(data) after each non-empty read().

### ProgressWriter

```
ProgressWriter(
    inner: BinaryIO, callback: Callable[[int], None]
)
```

Bases: `_StreamWrapper`

Writable `BinaryIO` wrapper that fires a callback per `write()`.

The callback receives the number of bytes written (not cumulative). Empty writes do not fire the callback.

Note

Assumes buffered I/O semantics — `write()` consumes all data or raises. Wrapping a `RawIOBase` (partial-write) stream would cause the reported byte count to diverge from the bytes actually written.

Parameters:

- **`inner`** (`BinaryIO`) – Writable binary stream to wrap.
- **`callback`** (`Callable[[int], None]`) – Called with len(data) after each non-empty write().

### ChecksumReader

```
ChecksumReader(inner: BinaryIO, algorithm: str = 'sha256')
```

Bases: `_StreamWrapper`

Readable `BinaryIO` wrapper that computes a rolling hash.

Parameters:

- **`inner`** (`BinaryIO`) – Readable binary stream to wrap.
- **`algorithm`** (`str`, default: `'sha256'` ) – Hash algorithm name (default "sha256"). Must be supported by hashlib.

#### algorithm

```
algorithm: str
```

Hash algorithm name (lowercase).

#### hexdigest

```
hexdigest() -> str
```

Return the lowercase hex digest of all bytes read so far.

### ChecksumWriter

```
ChecksumWriter(inner: BinaryIO, algorithm: str = 'sha256')
```

Bases: `_StreamWrapper`

Writable `BinaryIO` wrapper that computes a rolling hash.

Note

Assumes buffered I/O semantics — `write()` consumes all data or raises. Wrapping a `RawIOBase` (partial-write) stream would cause the hash to include bytes that were not actually written.

Parameters:

- **`inner`** (`BinaryIO`) – Writable binary stream to wrap.
- **`algorithm`** (`str`, default: `'sha256'` ) – Hash algorithm name (default "sha256"). Must be supported by hashlib.

#### algorithm

```
algorithm: str
```

Hash algorithm name (lowercase).

#### hexdigest

```
hexdigest() -> str
```

Return the lowercase hex digest of all bytes written so far.

### read_with_progress

```
read_with_progress(
    store: Store, path: str, callback: Callable[[int], None]
) -> ProgressReader
```

Read a file with progress tracking.

Convenience wrapper around `ProgressReader(store.read(path), callback)`. The caller is responsible for closing the returned stream.

Parameters:

- **`store`** (`Store`) – The Store to read from.
- **`path`** (`str`) – Store-relative file path.
- **`callback`** (`Callable[[int], None]`) – Called with byte count after each non-empty read().

Returns:

- `ProgressReader` – A ProgressReader wrapping the store's read stream.

## See also

- [Streaming IO example](https://docs.remotestore.dev/stable/tutorial/examples/streaming-io/index.md) — composable stream wrappers in action
