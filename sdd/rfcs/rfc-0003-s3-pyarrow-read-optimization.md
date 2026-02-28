# RFC-0003: S3-PyArrow Read Path Optimization

## Status

Draft

## Summary

Remove the `io.BufferedReader` wrapper from `S3PyArrowBackend.read()` and add a
direct `read()` method to `_PyArrowBinaryIO`, eliminating two unnecessary memory
copies per chunk on the streaming read path. This brings `read()`/`read_bytes()`
performance in line with the legacy S3Store that uses PyArrow C++ directly.

## Motivation

Benchmark data (`legacy/benchmark_s3.py` against MinIO) shows remote-store's
S3-PyArrow `read_bytes()` is 15-25% slower than the legacy implementation,
despite both using PyArrow C++ underneath. The overhead comes from Python wrapper
layers in the streaming read path.

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
    -> bytes(self._pa.read(n))            # single copy: C++ -> Python bytes
```

By adding `read()` to `_PyArrowBinaryIO` and removing the `BufferedReader`
wrapper, reads go straight from PyArrow C++ to the caller with a single
unavoidable copy (C++ buffer -> Python bytes object).

## Proposal

### 1. Add `read()` to `_PyArrowBinaryIO`

```python
# src/remote_store/backends/_s3_pyarrow.py, class _PyArrowBinaryIO

def read(self, size: int = -1) -> bytes:
    if size is None or size < 0:
        return bytes(self._pa.read())
    return bytes(self._pa.read(size))
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

### What changes

- `readline()` falls back to `RawIOBase` default (byte-by-byte). Acceptable:
  S3 binary streams are not used line-by-line. Users needing lines should wrap
  in `io.TextIOWrapper`.
- No `BufferedReader` means callers get exactly the bytes they asked for in a
  single `read()` call, without 8 KB chunking overhead.

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
- **Performance:** Expected 15-25% improvement on `read_bytes()` and streaming
  reads for the S3-PyArrow backend, bringing it to parity with legacy.
- **Testing:** No new tests needed. Existing tests cover:
  - `tests/test_stream.py` -- `_ErrorMappingStream` read/readinto paths
  - `tests/backends/test_conformance.py` -- chunked reads, position tracking
  - `tests/backends/test_s3_pyarrow.py` -- S3-PyArrow specific tests
  - `tests/test_transfer.py` -- streaming transfers
- **Scope:** Only `S3PyArrowBackend`. Other backends (S3, SFTP, Azure, Local,
  Memory) are untouched.

## Open Questions

1. **Should other backends also drop `BufferedReader`?** The SFTP backend also
   wraps in `BufferedReader`. If the same pattern applies, it could benefit too.
   Out of scope for this RFC -- profile first.

## References

- Benchmark: `legacy/benchmark_s3.py` (CPU/memory instrumentation added)
- Source: `src/remote_store/backends/_s3_pyarrow.py` (lines 36-64, 289-293)
- Error mapping stream: `src/remote_store/_stream.py`
- Related spec: `sdd/specs/011-s3-pyarrow-backend.md`
- Related backlog: ID-020 (benchmark improvements)
