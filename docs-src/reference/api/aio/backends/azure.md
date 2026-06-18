# AsyncAzureBackend

Native async Azure Storage backend. Uses the async Blob SDK for non-HNS
accounts (plain Blob Storage, Azurite) and the async DataLake SDK for HNS
accounts (ADLS Gen2) to get atomic rename and real directory support.
Whether the account is HNS is declared via the required `hns` argument; use
`AzureUtils.adetect_hns()` to discover it once if unknown.

::: remote_store.aio.AsyncAzureBackend
    options:
      show_bases: false

## See also

- [AzureBackend](../../backends/azure.md) — synchronous counterpart
- [Azure Backend Guide](../../../../guides/backends/azure.md) — configuration and usage
- [Azure HNS setup](../../../../guides/backends/azure-hns-setup.md) — ADLS Gen2 provisioning
