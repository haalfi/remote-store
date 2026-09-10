# AzureUtils

Backend-specific module

The helpers in this module are exclusive to the Azure backend. Using them ties your code to `AzureBackend` / `AsyncAzureBackend`.

`AzureUtils` is a namespace of stateless, one-shot helpers for Azure Storage accounts that do not require constructing a full backend — mirroring [`SFTPUtils`](https://docs.remotestore.dev/stable/reference/api/sftp-utils/index.md) and [`GraphUtils`](https://docs.remotestore.dev/stable/reference/api/aio/backends/graph/#graphutils).

Its primary use is discovering whether an account has Hierarchical Namespace (ADLS Gen2) enabled, so you can pass the result to `AzureBackend(hns=...)`. Unlike a silent runtime probe, these helpers are **fail-loud**: a probe error is raised, never swallowed.

## AzureUtils

Stateless helpers for Azure Storage accounts.

A namespace of one-shot utilities that do not require constructing a full `AzureBackend` -- mirroring `SFTPUtils` and `GraphUtils`.

## Methods

### detect_hns

```
detect_hns(
    *,
    account_name: str | None = None,
    account_url: str | None = None,
    account_key: str | Secret | None = None,
    sas_token: str | Secret | None = None,
    connection_string: str | Secret | None = None,
    credential: Any | None = None,
    client_options: dict[str, Any] | None = None,
) -> bool
```

Probe whether a storage account has Hierarchical Namespace enabled.

Issues a single `GetAccountInfo` call against the account, intended for discovering the value to pass as `AzureBackend(hns=...)`. This is **fail-loud**: a probe error is mapped to a `remote_store` error and raised, never swallowed.

Parameters:

- **`account_name`** (`str | None`, default: `None` ) – Storage account name.
- **`account_url`** (`str | None`, default: `None` ) – Full account URL (blob endpoint).
- **`account_key`** (`str | Secret | None`, default: `None` ) – Storage account key.
- **`sas_token`** (`str | Secret | None`, default: `None` ) – Shared Access Signature token.
- **`connection_string`** (`str | Secret | None`, default: `None` ) – Azure Storage connection string. When set, takes precedence over account_url / account_name.
- **`credential`** (`Any | None`, default: `None` ) – Any credential object (e.g. DefaultAzureCredential()).
- **`client_options`** (`dict[str, Any] | None`, default: `None` ) – Additional options passed to the service client.

Returns:

- `bool` – True if Hierarchical Namespace (ADLS Gen2) is enabled, False
- `bool` – for a flat Blob Storage account.

Raises:

- `RemoteStoreError` – If the probe fails (authentication, network, etc.).

### adetect_hns

```
adetect_hns(
    *,
    account_name: str | None = None,
    account_url: str | None = None,
    account_key: str | Secret | None = None,
    sas_token: str | Secret | None = None,
    connection_string: str | Secret | None = None,
    credential: Any | None = None,
    client_options: dict[str, Any] | None = None,
) -> bool
```

Async sibling of `detect_hns` (uses the async Blob SDK).

Accepts the same parameters as `detect_hns`.

Returns:

- `bool` – True if Hierarchical Namespace (ADLS Gen2) is enabled,
- `bool` – False for a flat Blob Storage account.

Raises:

- `RemoteStoreError` – If the probe fails (authentication, network, etc.).

## See also

- [Azure Backend Guide](https://docs.remotestore.dev/stable/guides/backends/azure/index.md) — usage patterns, configuration, and the `hns` declaration
- [Azure Backend example](https://docs.remotestore.dev/stable/tutorial/examples/azure-backend/index.md) — Azure backend in action
