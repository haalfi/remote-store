# BUG-310 — Reading a closed Azure `read_seekable()` stream raises `RemoteStoreError` instead of `ValueError`
<!-- doc: repo-only -->

## Evidence

Found by a Pyright pass over `src/remote_store` (`reportOptionalMemberAccess` at
`backends/_azure.py:152`: `self._bc` is set to `None` by `close()` and then
dereferenced by `readinto()`), then measured on master `05b0fddb4`.

**Through the public path.** `AzureBackend.read_seekable()` returns
`_ErrorMappingStream(_AzureRangeReader(...), self._classify, path)`. Closing that
stream and reading it again, with a stub blob client and the backend's own
classifier, against an `io.BytesIO` wrapped the same way:

```
azure:   remote_store._errors.RemoteStoreError: 'NoneType' object has no attribute 'download_blob' | path='f.bin' | backend='azure'
bytesio: builtins.ValueError: I/O operation on closed file.
```

The `AttributeError` is raised inside `readinto()`'s `except Exception`, re-raised
as `OSError`, and mapped by `_ErrorMappingStream` into a `RemoteStoreError`, so
a caller's use-after-close bug reads as a backend failure.

**Per public composition.** `read(4)`, `seek(0)` and `tell()` after `close()`,
each stream built exactly as the cited backend line builds it, with stub SDK
clients (`unittest.mock`) and `AzureBackend._classify` as the mapper. Measured
on `b2979470a` (PR #1092's review round, which caught that an earlier table here
probed the raw adapters and so missed `read()`'s `BufferedReader`):

| Stream (source line) | read after close | seek / tell after close |
| --- | --- | --- |
| Azure `read_seekable()`: `_ErrorMappingStream(_AzureRangeReader)` (`_azure.py:739`) | `RemoteStoreError` | returns `0` / `0` |
| Azure `read()`: `BufferedReader(_ErrorMappingStream(_AzureBinaryIO))` (`_azure.py:706`) | `ValueError` | `ValueError` / `RemoteStoreError` |
| boto3 PoC `read()`: `_ErrorMappingStream(_S3RangeReader)` (`_s3_boto3.py:401`; excluded from the wheel) | `RemoteStoreError` | returns `0` / `0` |
| Reference: `_ErrorMappingStream(io.BytesIO)` | `ValueError` | `ValueError` / `ValueError` |

The `tell` on Azure `read()` is not a closed-stream defect: it raises the same
`RemoteStoreError: seek` while the stream is open, because the non-seekable
inner raises `io.UnsupportedOperation`, an `OSError` subclass that
`_ErrorMappingStream` maps. It is out of this item's diagnosis and filed as
BUG-312 (§ 2).

`_ErrorMappingStream` has no closed guard of its own: `read`, `readinto`,
`readline`, `seek` and `tell` delegate to the inner stream without checking
`self.closed` (`_stream.py`), so each unbuffered public stream answers
read-after-close however its inner adapter does. The other construction sites
were not measured: `rg -n '_ErrorMappingStream\(' src` prints nine lines; less
the class statement and a docstring mention in `_sftp.py`, seven construction
sites remain (S3 s3fs, S3-PyArrow, the boto3 PoC, SFTP, HTTP, and Azure twice).

No spec clause states read-after-close behaviour for a `Backend.read()` or
`read_seekable()` stream: `rg -n "closed file" sdd/specs` finds one hit,
`029-async-store-backend-api.md:482`, which covers only the async-to-sync
adapter's stream, whose tests assert `ValueError`. No conformance cell closes a
stream and then reads it (`rg -n "closed file|after_close" tests/backends/conformance`
finds none).

## Prescription (advisory)

Scope chosen in the session that filed this:

- State the clause in `006-streaming-io.md`: `read`, `readinto` and `readline`
  on a closed stream from `read()` or `read_seekable()` raise `ValueError`, and
  so do `seek` and `tell` on a closed seekable one, never a `RemoteStoreError`
  and never empty data.
- Add a conformance cell over every sync fixture, for both `read()` and
  `read_seekable()`, against real backends rather than stubs. Azure
  `read_seekable()` is known to fail it; the `read()` half on Azure is a
  regression guard, measured passing above.
- Settle the HTTP stream with real response objects in `tests/backends/http/`:
  the conformance `http` fixture is read-only and reaches no `WRITE`-gated cell
  (ID-244, § 2), and it uses the urllib transport only.
- Fix the boto3 PoC's `_S3RangeReader` alongside: identical code, so whoever
  revives the PoC inherits the fix.

Where the guard goes is open. Per adapter (`_AzureRangeReader`, `_S3RangeReader`)
matches `_ChunkPullReader.read`. A `self.closed` check in `_ErrorMappingStream`
itself would cover every unbuffered public stream at all seven construction
sites, including the unmeasured HTTP one. Either way, check that the
`ValueError` is not mapped: the wrapper catches `OSError` and `EOFError`, and
`io.UnsupportedOperation` subclasses both `OSError` and `ValueError`.
