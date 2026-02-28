# RFC-0003: S3-PyArrow Read Path Optimization

## Status

Accepted

## Summary

Remove the `io.BufferedReader` wrapper from `S3PyArrowBackend.read()` and add a
direct `read()` method to `_PyArrowBinaryIO`, eliminating two unnecessary memory
copies per chunk on the streaming read path. This brings streaming `read()`
performance in line with the legacy S3Store that uses PyArrow C++ directly.

Note: `read_bytes()` is unaffected -- it already uses `open_input_stream` +
`bytes(stream.read())` directly, bypassing `BufferedReader` entirely.

## Motivation

Benchmark data (`legacy/benchmark_s3.py`, 15 iterations, 3 warmup, MinIO on
localhost) shows overhead on the streaming `read()` path:

| Benchmark        | Legacy (ms) | Remote (ms) | Ratio | Peak Mem        |
|------------------|-------------|-------------|-------|-----------------|
| `streaming_read` | 23.9        | 22.8        | 1.05x | 129 KB / 201 KB |
| `read_large`     | 8.9         | 10.9        | 0.82x | 978 KB / 1954 KB|

`streaming_read` exercises `Store.read()` with 64 KB chunked reads -- the code
path this RFC targets. The 1.05x ratio looks close to parity, but the 56% higher
peak memory (201 KB vs 129 KB) reveals the double-copy overhead. The
`read_large` row uses `read_bytes()` which bypasses `BufferedReader` entirely, so
its 0.82x ratio reflects a different bottleneck (not addressed here).

### Current chain (2 extra copies per chunk)

```
BufferedReader.read(n)
  -> readinto(8 KB internal buffer)
    -> _ErrorMappingStream.readinto(b)
      -> _PyArrowBinaryIO.readinto(b)
        -> data = self._pa.read(len(b))   # copy 1: C++ -> Python bytes
        -> b[:n] = data                   # copy 2: bytes -> BufferedReader buffer
```

`BufferedReader` calls `readinto()` in 8 KB chunks regardless of the requested
read size. Each chunk goes through two Python-level copies before reaching the
caller.

### Target chain (1 copy)

```
_ErrorMappingStream.read(n)
  -> _PyArrowBinaryIO.read(n)
    -> self._pa.read(n)                   # returns bytes directly from C++
```

By adding `read()` to `_PyArrowBinaryIO` and removing the `BufferedReader`
wrapper, reads go straight from PyArrow C++ to the caller. PyArrow's
`NativeFile.read()` already returns `bytes`, so no additional copy is needed.

## Proposal

### 1. Add `read()` to `_PyArrowBinaryIO`

```python
# src/remote_store/backends/_s3_pyarrow.py, class _PyArrowBinaryIO

def read(self, size: int = -1) -> bytes:
    # NativeFile.read() returns bytes; no wrapper needed.
    if size is None or size < 0:
        return self._pa.read()
    return self._pa.read(size)
```

Keep `readinto()` for compatibility -- anyone wrapping our stream in their own
`BufferedReader` still works.

### 2. Remove `BufferedReader` from `S3PyArrowBackend.read()`

Before:

```python
def read(self, path: str) -> BinaryIO:
    with self._pyarrow_errors(path):
        pa_file = self._pa_fs.open_input_file(self._pa_path(path))
        raw = _PyArrowBinaryIO(pa_file)
        return io.BufferedReader(
            cast("io.RawIOBase", _ErrorMappingStream(raw, self._classify_error, path))
        )
```

After:

```python
def read(self, path: str) -> BinaryIO:
    with self._pyarrow_errors(path):
        pa_file = self._pa_fs.open_input_file(self._pa_path(path))
        raw = _PyArrowBinaryIO(pa_file)
        return cast("BinaryIO", _ErrorMappingStream(raw, self._classify_error, path))
```

### What's preserved

- Error mapping via `_ErrorMappingStream` (OSError -> RemoteStoreError)
- Seekability (PyArrow RandomAccessFile)
- Context manager / `close()` lifecycle
- `readinto()` still works for callers that need it
- `_ErrorMappingStream.read()` already exists and delegates to inner `.read()`

### 3. Add chunked `readline()` to `_PyArrowBinaryIO`

Without `BufferedReader`, `readline()` falls back to `RawIOBase` default, which
calls `readinto(1)` in a tight loop -- one call per byte until `\n`. This is
pathologically slow for lines of any length.

Add a `readline()` that reads in blocks (e.g. 8 KB) and scans for `\n`:

```python
# src/remote_store/backends/_s3_pyarrow.py, class _PyArrowBinaryIO

_READLINE_CHUNK = 8192

def readline(self, size: int = -1) -> bytes:
    buf = bytearray()
    while size is None or size < 0 or len(buf) < size:
        remaining = size - len(buf) if size is not None and size >= 0 else self._READLINE_CHUNK
        chunk = self._pa.read(min(remaining, self._READLINE_CHUNK))
        if not chunk:
            break
        idx = chunk.find(b"\n")
        if idx >= 0:
            buf.extend(chunk[: idx + 1])
            # seek back past the unused portion
            self._pa.seek(-(len(chunk) - idx - 1), 1)
            break
        buf.extend(chunk)
    return bytes(buf)
```

Current callers don't use line-oriented reads on S3 binary streams, but removing
`BufferedReader` without this would leave a pathological performance trap for
anyone wrapping the stream in `io.TextIOWrapper`.

### What changes

- No `BufferedReader` means callers get exactly the bytes they asked for in a
  single `read()` call, without 8 KB chunking overhead.
- `readline()` uses a new chunked implementation instead of `BufferedReader`'s
  internal buffer.

## Alternatives Considered

1. **Increase `BufferedReader` buffer size.** Setting a larger buffer (e.g.
   64 KB) reduces per-call overhead but still has two copies per chunk.
   Rejected: doesn't eliminate the fundamental issue.

2. **Override `readinto()` to avoid the intermediate bytes object.** PyArrow's
   `read_buffer()` returns a `pyarrow.Buffer` which supports the buffer protocol,
   but `NativeFile.read()` already returns `bytes`. We'd need `read_buffer()` +
   memoryview copy, which is roughly equivalent. Rejected: more complexity for
   the same result.

3. **Use `open_input_stream` instead of `open_input_file`.** Loses seekability.
   Rejected: `read()` contract requires seekable streams (position tracking,
   `seek()`/`tell()`).

## Impact

- **Public API:** No changes to `__all__` or Store interface.
- **Backwards compatibility:** Non-breaking. The return type is still `BinaryIO`.
  Callers using `.read()`, `.seek()`, `.tell()`, `.close()` are unaffected.
  Callers relying on `isinstance(stream, io.BufferedReader)` would break, but
  that's not part of the contract (spec SIO-001 only requires `BinaryIO`).
- **Performance:** Improvement applies to streaming `read()` calls only (the
  `streaming_read` benchmark path). `read_bytes()` is unaffected -- it already
  bypasses `BufferedReader`. Expect reduced per-chunk overhead and lower peak
  memory for chunked streaming reads.
- **Testing:** Existing tests cover correctness:
  - `tests/test_stream.py` -- `_ErrorMappingStream` read/readinto paths
  - `tests/backends/test_conformance.py` -- chunked reads, position tracking
  - `tests/backends/test_s3_pyarrow.py` -- S3-PyArrow specific tests
  - `tests/test_transfer.py` -- streaming transfers

  Additionally, add a structural assertion that `S3PyArrowBackend.read()`
  returns a stream that is NOT wrapped in `BufferedReader`, to prevent
  regression.
- **Scope:** Only `S3PyArrowBackend`. Other backends (S3, SFTP, Azure, Local,
  Memory) are untouched.

## Open Questions

1. **Should other backends also drop `BufferedReader`?** The SFTP backend also
   wraps in `BufferedReader`, but the situation is different: SFTP's underlying
   stream is Paramiko's `SFTPFile`, which has its own `prefetch()` mechanism and
   internal buffering. `BufferedReader` may serve a useful purpose there by
   smoothing bursty network reads. Removing it could interact with Paramiko's
   chunking behavior differently than removing it from PyArrow's in-memory
   `NativeFile.read()`. Out of scope -- requires separate profiling and analysis.

## References

- Benchmark: `legacy/benchmark_s3.py` (CPU/memory instrumentation added)
- Source: `src/remote_store/backends/_s3_pyarrow.py` (lines 36-64, 289-293)
- Error mapping stream: `src/remote_store/_stream.py`
- Related spec: `sdd/specs/011-s3-pyarrow-backend.md`
- Related backlog: ID-020 (benchmark improvements)
