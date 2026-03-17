# ext.integrity

Pure functions for computing and verifying file checksums over Store's public
API. These compose `store.read()` with `ChecksumReader` internally — no manual
stream lifecycle management needed.

See the [integrity spec](https://github.com/haalfi/remote-store/blob/master/sdd/specs/034-ext-integrity.md) for invariants.

::: remote_store.ext.integrity
