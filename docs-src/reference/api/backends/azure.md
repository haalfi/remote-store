# AzureBackend

API reference for `AzureBackend` — stores files in Azure Blob Storage and
ADLS Gen2. Behavior adapts to the declared `hns` value (Hierarchical
Namespace); there is no runtime auto-detection.

::: remote_store.backends.AzureBackend
    options:
      show_bases: false

## See also

- [Azure Backend Guide](../../../guides/backends/azure.md) — usage patterns, configuration, and examples
- [AzureUtils](../azure-utils.md) — discover an account's HNS status with `detect_hns()`
- [Azure Backend example](../../../../examples/backends/azure_backend.py) — Azure backend in action
