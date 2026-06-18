# Azure HNS Account Setup

Provision a real Azure Data Lake Storage Gen2 (ADLS Gen2 / Hierarchical
Namespace) account using the `az` CLI. This guide is for contributors who
need to run the live HNS test suite and for users who want to validate
their own ADLS Gen2 provisioning against `remote-store` before production.

If you only need flat blob storage, the [Azure backend guide](azure.md)
covers Azurite for local emulation. Azurite does not emulate Hierarchical
Namespace, so HNS-specific paths (atomic rename, real directories) require
a real account. That is what this guide sets up.

The shell snippets below are not executed in CI because they require
authenticated Azure access. Treat them as a recipe to copy line by line,
not as exact reproducible output.

## Prerequisites

- An Azure subscription. The free trial credit, the always-free tier, and
  any paid subscription all work. No specific SKU is required.
- The [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
  (`az`) version 2.x.

## Sign in

```bash
az login
```

If your tenant requires multi-factor authentication on a per-resource
basis, the default device flow may report
`AADSTS50076 ... must use multi-factor authentication`. Sign in directly
to that tenant instead:

```bash
az login --tenant <TENANT_ID>
```

Verify you have an enabled subscription:

```bash
az account show --query "{name:name, state:state}" -o table
```

The `state` column should read `Enabled`.

## Register the storage resource provider

A new subscription often has `Microsoft.Storage` unregistered. Registration
is idempotent and takes about a minute.

```bash
az provider register --namespace Microsoft.Storage
az provider show --namespace Microsoft.Storage --query "{state:registrationState}" -o table
```

Re-run the second command until the state is `Registered`.

## Pick a region

Choose a region close to your egress location. `westeurope`, `switzerlandnorth`,
and `germanywestcentral` are common picks for European users. List the
display names with:

```bash
az account list-locations --query "[].{name:name, displayName:displayName}" -o table
```

Storage accounts incur cross-region egress fees, so keeping the region
close to whoever runs the tests reduces both latency and cost.

## Pick an account name

Storage account names are globally unique, lowercase, alphanumeric, and
between 3 and 24 characters. Check availability before creating:

```bash
az storage account check-name --name <ACCOUNT_NAME> -o table
```

If `NameAvailable` is `False`, append a digit suffix and retry.

## Create the resource group, account, and filesystem

The three commands below provision the resource group, the HNS-enabled
storage account, and one ADLS Gen2 filesystem ("container" in flat-blob
terminology). Run them in sequence; each completes in a few seconds, except
for the account creation which takes about half a minute.

```bash
az group create \
  --name <RESOURCE_GROUP> \
  --location <REGION>

az storage account create \
  --name <ACCOUNT_NAME> \
  --resource-group <RESOURCE_GROUP> \
  --location <REGION> \
  --sku Standard_LRS \
  --kind StorageV2 \
  --enable-hierarchical-namespace true \
  --access-tier Hot \
  --allow-blob-public-access false \
  --min-tls-version TLS1_2

az storage fs create \
  --name <FILESYSTEM_NAME> \
  --account-name <ACCOUNT_NAME> \
  --auth-mode key
```

Why these flags:

- `--enable-hierarchical-namespace true` enables ADLS Gen2 semantics. This
  cannot be toggled after the account is created.
- `--sku Standard_LRS` is the cheapest redundancy tier and is sufficient
  for testing.
- `--access-tier Hot` minimises read costs, which matters for tests that
  read blob properties repeatedly.
- `--allow-blob-public-access false` and `--min-tls-version TLS1_2` align
  with current Azure security baselines.

If you copy the multi-line `az storage account create` form into a shell
that wraps long lines on display, the line break can be interpreted as a
command separator. If `isHnsEnabled` comes back as `null`, delete the
account and re-run as a single line.

Confirm HNS is enabled:

```bash
az storage account show \
  --name <ACCOUNT_NAME> \
  --resource-group <RESOURCE_GROUP> \
  --query "{name:name, hns:isHnsEnabled, tls:minimumTlsVersion}" \
  -o table
```

The `hns` column should read `True`.

!!! important "Declare `hns` when constructing the backend"
    The Azure backend does not auto-detect Hierarchical Namespace. Because this
    account has HNS enabled, construct the backend with `hns=True` (config
    `"hns": true`). For a flat Blob Storage account you would pass `hns=False`.
    If you ever need to discover an account's status programmatically, call
    `AzureUtils.detect_hns(...)` (or `await AzureUtils.adetect_hns(...)`) once
    and pass the result.

## Set CLI defaults

Setting the resource group and account once removes the need to repeat them
on every command:

```bash
az config set defaults.group=<RESOURCE_GROUP>
az config set storage.account=<ACCOUNT_NAME>
az config set storage.auth_mode=key
```

These settings are stored in `~/.azure/config` on your local machine.

## Wire credentials into the environment

`remote-store` test suites and benchmarks read the connection string from
the `AZURE_STORAGE_CONNECTION_STRING` environment variable. Pull the string
and place it in your project `.env`:

```bash
az storage account show-connection-string \
  --name <ACCOUNT_NAME> \
  --resource-group <RESOURCE_GROUP> \
  --query connectionString \
  -o tsv
```

Add the resulting line to `.env`:

```bash
AZURE_STORAGE_CONNECTION_STRING=<paste here>
```

To opt into live HNS coverage, also set:

```bash
RS_TEST_LIVE_HNS=1
RS_TEST_LIVE_HNS_CONTAINER=<FILESYSTEM_NAME>
```

`tests/backends/azure/test_live_hns.py` carries the `live` pytest marker
and exercises sync HNS semantics that the conformance suite against
`azure_live` cannot express: directory-blob `hdi_isfolder` probes,
WriteResult etag normalisation cross-check, the `write_atomic`
streaming-payload guard, the `get_folder_info("")` HNS root carve-out,
and the `exists` DataLake probe-fallback on real HNS directories.
`live`-marked tests are
excluded by default `addopts` and have to be opted into explicitly:

```bash
hatch run pytest -m live tests/backends/azure/test_live_hns.py
```

`tests/conftest.py` loads `.env` via `python-dotenv` when a `live` mark
expression is in play, so dropping all three variables above into `.env`
once is enough — a plain `hatch run pytest -m live …` picks them up.
`override=False` keeps any value already set in the shell or by CI
authoritative, and a regular `hatch run test` (with the default
`-m 'not live'`) never loads `.env`.

If `RS_TEST_LIVE_HNS=1` is set but `AZURE_STORAGE_CONNECTION_STRING` is
missing, empty, or points at the Azurite local emulator, the suite fails
loud with a `pytest.fail` message rather than silently skipping. Azurite
does not emulate Hierarchical Namespace, so an Azurite-backed run cannot
validate HNS-specific behaviour.

Async HNS coverage lives in `tests/backends/azure/aio/test_live_hns.py`,
which uses the same three-layer gate and a dedicated real-account fixture —
it is explicitly **not** co-located with the Azurite-backed async live
tests in `tests/backends/azure/aio/test_live.py` to avoid the Azurite
reachability guard blocking real-ADLS-Gen2 CI.

`.env` is gitignored. Do not commit the connection string.

## Smoke test

A round-trip via `az storage blob` confirms the account is usable:

```bash
az storage blob upload \
  --container-name <FILESYSTEM_NAME> \
  --name smoke/hello.txt \
  --file pyproject.toml \
  --overwrite

az storage blob list \
  --container-name <FILESYSTEM_NAME> \
  --prefix smoke/ \
  -o table

az storage blob delete \
  --container-name <FILESYSTEM_NAME> \
  --name smoke/hello.txt
```

If the upload returns an `etag` and the list shows the blob, the account
is ready for `remote-store` tests.

## Cost and cleanup

Standard_LRS HNS storage is the cheapest redundancy tier. Idle storage
and ad-hoc test traffic at this scale are negligible against a free trial
credit; consult the [Azure Storage pricing page](https://azure.microsoft.com/en-us/pricing/details/storage/blobs/)
for current rates.

When you are done, delete the resource group to remove the account and
all containers in one step:

```bash
az group delete \
  --name <RESOURCE_GROUP> \
  --yes \
  --no-wait
```

`--no-wait` returns immediately; the deletion completes asynchronously in
about a minute.

## Rotating the account key

If the connection string is exposed (committed accidentally, pasted into a
shared transcript, or copied to a less-trusted machine), rotate the key
and re-pull the connection string:

```bash
az storage account keys renew \
  --account-name <ACCOUNT_NAME> \
  --resource-group <RESOURCE_GROUP> \
  --key key1

az storage account show-connection-string \
  --name <ACCOUNT_NAME> \
  --resource-group <RESOURCE_GROUP> \
  --query connectionString \
  -o tsv
```

Update `.env` with the new connection string. Any session that already
holds the old key continues to work until you rotate `key2` as well.

## Troubleshooting

**`SubscriptionNotFound` after sign-in.** Your default tenant has no
subscriptions. Sign in with `az login --tenant <TENANT_ID>` against the
tenant that owns the subscription.

**`StorageAccountAlreadyTaken`.** The chosen account name is in use by
someone else. Pick a more specific name and retry the
`az storage account check-name` step.

**`AuthorizationFailed` on `az storage fs create`.** RBAC for data-plane
operations propagates a few minutes after account creation. Use
`--auth-mode key` (this guide's default) to bypass RBAC and authenticate
with the account key.

**`isHnsEnabled` returns `null` or `false`.** The
`--enable-hierarchical-namespace` flag did not reach the create call,
usually because the multi-line command was split on a wrap. Delete the
account and re-run on a single line.

## See also

- [Azure backend guide](azure.md) — using the account from `remote-store`
- [`AzureBackend` API reference](../../reference/api/backends/azure.md) — backend constructor options and method index
- [`AsyncStore` API reference](../../reference/api/aio/store.md) — async surface that the live HNS test suite exercises
- [Azure Storage Account documentation](https://learn.microsoft.com/en-us/azure/storage/common/storage-account-overview)
- [Hierarchical namespace overview](https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-namespace)
