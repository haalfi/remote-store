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

**Error behavior:**
- If the inner stream's `read()` raises, the callback is not called and
  the exception propagates unchanged.
- If the callback raises, the exception propagates to the caller. The
  bytes have already been read from the inner stream (they are not
  pushed back).

## STR-002: ProgressWriter

**Invariant:** `ProgressWriter` wraps a writable `BinaryIO` and calls
`callback(bytes_written)` after each `write()`.

**Assumption:** Buffered I/O semantics — `write()` consumes all data or
raises. Wrapping a `RawIOBase` (partial-write) stream would cause the
reported byte count to diverge from the bytes actually written.

**Postconditions:**
- `write(data)` delegates to the inner stream, fires `callback(len(data))`
  when `data` is non-empty, and returns the inner result.
- All other attributes are delegated to the inner stream via `__getattr__`.
- Supports the context manager protocol.

**Error behavior:**
- If the inner stream's `write()` raises, the callback is not called.
- If the callback raises, the exception propagates. The bytes have
  already been written to the inner stream.

## STR-003: ChecksumReader

**Invariant:** `ChecksumReader` wraps a readable `BinaryIO` and
computes a rolling hash of all bytes read through intercepted methods.

**Postconditions:**
- `read(size)` delegates to the inner stream and feeds the returned
  bytes into a `hashlib` hash object.
- `readline()` and `readlines()` delegate to the inner stream and feed
  the returned bytes into the hash object. All data-reading methods
  contribute to the digest — none bypass it.
- `hexdigest()` returns the lowercase hex digest of all bytes read so far.
- `algorithm` property returns the algorithm name (lowercase).
- Default algorithm is `"sha256"`.
- Non-data attributes (e.g. `seek`, `tell`, `name`) are delegated to
  the inner stream via `__getattr__`.
- Supports the context manager protocol.

**Error behavior:**
- If the inner stream raises during any read method, the hash state
  reflects only bytes successfully read before the error.
- Construction raises `ValueError` if the algorithm is not supported
  by `hashlib` (the `hashlib` error propagates unchanged).

## STR-004: ChecksumWriter

**Invariant:** `ChecksumWriter` wraps a writable `BinaryIO` and
computes a rolling hash of all bytes written.

**Assumption:** Buffered I/O semantics — `write()` consumes all data or
raises. Wrapping a `RawIOBase` (partial-write) stream would cause the
hash to include bytes that were not actually written.

**Postconditions:**
- `write(data)` delegates to the inner stream and feeds the data
  into a `hashlib` hash object.
- `hexdigest()` returns the lowercase hex digest of all bytes written so far.
- `algorithm` property returns the algorithm name (lowercase).
- Default algorithm is `"sha256"`.
- Non-data attributes are delegated to the inner stream via `__getattr__`.
- Supports the context manager protocol.

**Error behavior:**
- If the inner stream's `write()` raises, the data is not fed into
  the hash.
- Construction raises `ValueError` if the algorithm is not supported
  by `hashlib` (the `hashlib` error propagates unchanged).

## STR-005: read_with_progress Convenience

**Invariant:** `read_with_progress(store, path, callback)` returns a
`ProgressReader` wrapping `store.read(path)`.

**Postconditions:** The caller is responsible for closing the returned stream.

## STR-006: Composition

**Invariant:** Stream wrappers compose by nesting. The outer wrapper
intercepts its own methods and delegates all others to the inner wrapper
via `__getattr__`.

**Postconditions:**
- Inner wrapper methods are accessible through the outer wrapper when
  the outer does not define them. For example, `hexdigest()` on a
  `ChecksumReader` that wraps a `ProgressReader` is resolved on the
  `ChecksumReader` itself, while `close()` delegates inward.
- Each wrapper independently maintains its own state (callback
  reference, hash object). Nesting order affects which wrapper sees
  the data first but does not affect correctness.
- Wrappers compose in any order for orthogonal concerns (progress +
  checksum). For two wrappers of the same kind (e.g. two
  `ChecksumReader`s with different algorithms), each independently
  computes its digest.

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
