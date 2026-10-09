# BUG-310 — Reading a closed Azure stream answers a `RemoteStoreError` or end-of-file instead of `ValueError`
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

**Per adapter.** `read(4)`, `readinto(bytearray(4))`, `seek(0)` and `tell()`
after `close()`, each adapter constructed directly (stub clients via
`unittest.mock`):

| Adapter | read / readinto after close | seek / tell after close |
| --- | --- | --- |
| `_AzureRangeReader` (`read_seekable`) | `OSError`, mapped to `RemoteStoreError` | returns `0` |
| `_AzureBinaryIO` (Azure `read()`) | returns `b""` / `0`, indistinguishable from EOF | `UnsupportedOperation` |
| `_S3RangeReader` (boto3 PoC, excluded from the wheel) | `OSError` on `None.get_object` | returns `0` |
| `_PyArrowBinaryIO` | `ValueError` | `ValueError` |
| `_HttpxStreamAdapter`, `_Urllib3StreamAdapter` | inconclusive: the stubs did not behave like a real `httpx.Response` / `urllib3.HTTPResponse` | `UnsupportedOperation` |
| `io.BytesIO` (reference) | `ValueError` | `ValueError` |

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
  `read_seekable()`, against real backends rather than stubs; fix every adapter
  that fails it. The two Azure adapters are known to.
- Settle the two HTTP adapters with real response objects in
  `tests/backends/http/`: the conformance `http` fixture is read-only and
  reaches no `WRITE`-gated cell (ID-244, § 2), and it uses the urllib transport only.
- Fix `_S3RangeReader` alongside: identical code, so whoever revives the PoC
  inherits the fix.

Guarding on `self.closed` at the top of `readinto`, `seek` and `tell` matches
`_ChunkPullReader.read`. Check that `_ErrorMappingStream` lets the `ValueError`
through: it catches `OSError` and `EOFError` only, but `io.UnsupportedOperation`
subclasses both `OSError` and `ValueError`.
