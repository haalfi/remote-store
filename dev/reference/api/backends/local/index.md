# LocalBackend

API reference for `LocalBackend` — stores files on the local filesystem. Built-in, no extra dependencies required.

## LocalBackend

```
LocalBackend(root: str)
```

Local filesystem backend using only the Python standard library.

`move()` uses `shutil.move`, which calls `os.rename` for same-filesystem moves (atomic) but falls back to copy-then-delete for cross-filesystem moves (not atomic). `ATOMIC_MOVE` is declared because within-root moves are always same-filesystem.

Parameters:

- **`root`** (`str`) – Absolute path to the root directory on the local filesystem.

### resolve

```
resolve(path: str) -> ResolutionPlan
```

Return a `ResolutionPlan` with local filesystem details.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `ResolutionPlan` – Plan with kind="local" and details containing
- `ResolutionPlan` – root and absolute_path.

## See also

- [Local Backend Guide](https://docs.remotestore.dev/stable/guides/backends/local/index.md) — usage patterns, configuration, and examples
- [File Operations example](https://docs.remotestore.dev/stable/tutorial/examples/file-operations/index.md) — full Store API demo using LocalBackend
