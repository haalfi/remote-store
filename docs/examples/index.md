# Examples

Runnable example scripts demonstrating every feature of `remote-store`. Each example is self-contained and uses a temporary directory so you can run them directly.

| Example | Description |
|---------|-------------|
| [Quickstart](quickstart.md) | Minimal config, write, and read |
| [File Operations](file-operations.md) | Full Store API: read, write, delete, move, copy, list, metadata, type checks, capabilities, to_key |
| [Streaming I/O](streaming-io.md) | Streaming writes and reads with `BytesIO` |
| [Atomic Writes](atomic-writes.md) | Atomic writes and overwrite semantics |
| [Configuration](configuration.md) | Config-as-code, `from_dict()`, multiple stores, S3/SFTP backend configs |
| [Error Handling](error-handling.md) | Catching `NotFound`, `AlreadyExists`, and more |

Interactive Jupyter notebooks are also available in the
[`examples/notebooks/`](https://github.com/haalfi/remote-store/tree/master/examples/notebooks)
directory of the repository.
