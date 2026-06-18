# AzureUtils

!!! warning "Backend-specific module"
    The helpers in this module are exclusive to the Azure backend.
    Using them ties your code to `AzureBackend` / `AsyncAzureBackend`.

`AzureUtils` is a namespace of stateless, one-shot helpers for Azure Storage
accounts that do not require constructing a full backend — mirroring
[`SFTPUtils`](sftp-utils.md) and [`GraphUtils`](aio/backends/graph.md#graphutils).

Its primary use is discovering whether an account has Hierarchical Namespace
(ADLS Gen2) enabled, so you can pass the result to `AzureBackend(hns=...)`.
Unlike a silent runtime probe, these helpers are **fail-loud**: a probe error
is raised, never swallowed.

::: remote_store.backends.AzureUtils
    options:
      members: false

## Methods

::: remote_store.backends.AzureUtils.detect_hns
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.backends.AzureUtils.adetect_hns
    options:
      show_root_heading: true
      heading_level: 3

## See also

- [Azure Backend Guide](../../guides/backends/azure.md) — usage patterns, configuration, and the `hns` declaration
- [Azure Backend example](../../../examples/backends/azure_backend.py) — Azure backend in action
