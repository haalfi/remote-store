# ext.streams — Stream-Level Wrappers

## Overview

`remote_store.ext.streams` provides composable `BinaryIO` wrappers for
progress tracking and checksum computation. These operate at the stream
level, not the Store level — no proxy wrapping is needed.

Stream wrappers compose naturally:

```python
stream = ChecksumReader(ProgressReader(store.read("file.bin"), on_progress), "sha256")
```

## STR-001: ProgressReader

**Invariant:** `ProgressReader` wraps a readable `BinaryIO` and calls
`callback(bytes_read)` after each `read()` that returns non-empty data.

**Postconditions:**
- `read(size)` delegates to the inner stream and fires `callback(len(data))`
  when `data` is non-empty.
- `read()` with empty result does not fire the callback.
- All other attributes are delegated to the inner stream via `__getattr__`.
- Supports the context manager protocol (`__enter__`/`__exit__`),
  delegating `close()` to the inner stream.

## STR-002: ProgressWriter

**Invariant:** `ProgressWriter` wraps a writable `BinaryIO` and calls
`callback(bytes_written)` after each `write()`.

**Postconditions:**
- `write(data)` delegates to the inner stream, fires `callback(len(data))`
  when `data` is non-empty, and returns the inner result.
- All other attributes are delegated to the inner stream via `__getattr__`.
- Supports the context manager protocol.

## STR-003: ChecksumReader

**Invariant:** `ChecksumReader` wraps a readable `BinaryIO` and
computes a rolling hash of all bytes read.

**Postconditions:**
- `read(size)` delegates to the inner stream and feeds the returned
  bytes into a `hashlib` hash object.
- `hexdigest()` returns the lowercase hex digest of all bytes read so far.
- `algorithm` property returns the algorithm name (lowercase).
- Default algorithm is `"sha256"`.
- All other attributes are delegated to the inner stream.
- Supports the context manager protocol.

## STR-004: ChecksumWriter

**Invariant:** `ChecksumWriter` wraps a writable `BinaryIO` and
computes a rolling hash of all bytes written.

**Postconditions:**
- `write(data)` delegates to the inner stream and feeds the data
  into a `hashlib` hash object.
- `hexdigest()` returns the lowercase hex digest of all bytes written so far.
- `algorithm` property returns the algorithm name (lowercase).
- Default algorithm is `"sha256"`.
- All other attributes are delegated to the inner stream.
- Supports the context manager protocol.

## STR-005: read_with_progress Convenience

**Invariant:** `read_with_progress(store, path, callback)` returns a
`ProgressReader` wrapping `store.read(path)`.

**Postconditions:** The caller is responsible for closing the returned stream.

## STR-006: Composition

**Invariant:** Stream wrappers compose in any order. Each wrapper
delegates unknown attributes to its inner stream.

**Example:**
```python
stream = ChecksumReader(
    ProgressReader(store.read("file.bin"), callback=update_bar),
    algorithm="sha256",
)
data = stream.read()
assert stream.hexdigest() == expected
```

## STR-007: Module Exports

**Invariant:** `ext.streams.__all__` contains:
`ProgressReader`, `ProgressWriter`, `ChecksumReader`, `ChecksumWriter`,
`read_with_progress`.
