# Examples

Runnable example scripts demonstrating every feature of `remote-store`. Each example is self-contained and uses a temporary directory so you can run them directly.

## Core Examples

These run locally with no external services or credentials.

| Example | Description |
|---------|-------------|
| [Quickstart](quickstart.md) | Minimal config, write, and read |
| [File Operations](file-operations.md) | Full Store API: read, write, delete, move, copy, list, metadata |
| [Streaming I/O](streaming-io.md) | Streaming writes and reads with `BytesIO` |
| [Atomic Writes](atomic-writes.md) | Atomic writes and overwrite semantics |
| [Configuration](configuration.md) | Config-as-code, `from_dict()`, multiple stores, S3/SFTP backend configs |
| [Error Handling](error-handling.md) | Catching `NotFound`, `AlreadyExists`, and more |
| [Memory Backend](memory-backend.md) | In-process memory backend for testing and caching |
| [Store.child()](store-child.md) | Runtime sub-scoping, chaining, close semantics |

## Backend Examples

These require a running service (AWS, MinIO, an SFTP server, Azure, Azurite, etc.) and credentials supplied via environment variables. Each script prints a help message when the required variables are missing.

| Example | Description |
|---------|-------------|
| [S3 Backend](s3-backend.md) | S3 / MinIO: config, two stores, virtual folders |
| [S3-PyArrow Backend](s3-pyarrow-backend.md) | High-throughput S3 via PyArrow C++ + escape hatch |
| [SFTP Backend](sftp-backend.md) | SSH/SFTP: config, host key policies, `unwrap()` |
| [Azure Backend](azure-backend.md) | Azure Blob / ADLS Gen2: config, auth methods, `unwrap()` |
| [HTTP Backend](http-backend.md) | Read-only HTTP/HTTPS: capabilities, transport selection |

## Showcases

Full project examples demonstrating multiple extensions working together.

| Example | Description |
|---------|-------------|
| [Medallion + Dagster Showcase](medallion-dagster.md) | End-to-end Bronze/Silver/Gold pipeline with Dagster, 6 extensions, live MeteoSwiss data |

Interactive Jupyter notebooks are also available in the
[`examples/notebooks/`](https://github.com/haalfi/remote-store/tree/master/examples/notebooks)
directory of the repository.
