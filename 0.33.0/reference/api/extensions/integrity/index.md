# ext.integrity

Pure functions for computing and verifying file checksums over Store's public API. These compose `store.read()` with `ChecksumReader` internally — no manual stream lifecycle management needed.

See the [integrity spec](https://docs.remotestore.dev/stable/explanation/design/specs/034-ext-integrity/index.md) for invariants.

## integrity

Checksum verification helpers over Store's public API.

Pure functions for computing and verifying file integrity. These compose `store.read()` with ChecksumReader internally — users don't need to manage stream lifecycle.

Example

```
from remote_store.ext.integrity import checksum, verify

algorithm, hex_digest = checksum(store, "data/file.bin")
print(algorithm, hex_digest)

ok = verify(store, "data/file.bin", expected="a3f2b8...", algorithm="sha256")
```

### checksum

```
checksum(
    store: Store, path: str, algorithm: str = "sha256"
) -> tuple[str, str]
```

Compute the checksum of a file in the store.

Reads the file in chunks (never fully materialized in memory) and returns a `(algorithm, hex_digest)` tuple.

Parameters:

- **`store`** (`Store`) – The Store to read from.
- **`path`** (`str`) – Store-relative file path.
- **`algorithm`** (`str`, default: `'sha256'` ) – Hash algorithm name (default "sha256").

Returns:

- `tuple[str, str]` – Tuple of (algorithm, hex_digest) with lowercase values.

Raises:

- `NotFound` – If the file does not exist.
- `ValueError` – If the algorithm is not supported by hashlib.

### content_digest

```
content_digest(
    store: Store, path: str, algorithm: str = "sha256"
) -> ContentDigest
```

Compute the content digest of a file in the store.

Like checksum, but returns a ContentDigest instead of a raw tuple.

Parameters:

- **`store`** (`Store`) – The Store to read from.
- **`path`** (`str`) – Store-relative file path.
- **`algorithm`** (`str`, default: `'sha256'` ) – Hash algorithm name (default "sha256").

Returns:

- `ContentDigest` – A ContentDigest with normalized algorithm and hex value.

Raises:

- `NotFound` – If the file does not exist.
- `ValueError` – If the algorithm is not supported by hashlib.

### verify

```
verify(
    store: Store,
    path: str,
    expected: str,
    algorithm: str = "sha256",
) -> bool
```

Verify a file's checksum against an expected hex value.

Parameters:

- **`store`** (`Store`) – The Store to read from.
- **`path`** (`str`) – Store-relative file path.
- **`expected`** (`str`) – Expected hex digest (case-insensitive).
- **`algorithm`** (`str`, default: `'sha256'` ) – Hash algorithm name (default "sha256").

Returns:

- `bool` – True if the computed digest matches expected.

Raises:

- `NotFound` – If the file does not exist.
- `ValueError` – If the algorithm is not supported by hashlib.

### verify_hex

```
verify_hex(
    store: Store,
    path: str,
    algorithm: str,
    expected_hex: str,
) -> bool
```

Verify a file's checksum given an algorithm and expected hex value.

Parameters:

- **`store`** (`Store`) – The Store to read from.
- **`path`** (`str`) – Store-relative file path.
- **`algorithm`** (`str`) – Hash algorithm name.
- **`expected_hex`** (`str`) – Expected hex digest (case-insensitive).

Returns:

- `bool` – True if the computed digest matches expected_hex.

Raises:

- `NotFound` – If the file does not exist.
- `ValueError` – If the algorithm is not supported by hashlib.

## See also

- [ext.streams](https://docs.remotestore.dev/stable/reference/api/extensions/streams/index.md) — composable BinaryIO wrappers used internally by integrity helpers
