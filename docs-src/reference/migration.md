# Migration Guide

Breaking changes and upgrade paths between `remote-store` versions.

`remote-store` has been published on PyPI since v0.11.0 (first Beta release).
The core Store API is stable, but extensions may evolve. This page documents
changes that require action when upgrading.

## v0.20.0 to v0.21.0

**`ParquetSerializer.deserialize()` returns Arrow Table (BUG-135):**

`ParquetSerializer.deserialize()` now returns a `pyarrow.Table` instead of a
`pandas.DataFrame`. This removes the hidden hard dependency on pandas for
`remote-store[dagster,arrow]` users.

- Old: `result = serializer.deserialize(data)  # pandas DataFrame`
- New: `result = serializer.deserialize(data)  # pyarrow.Table`
- If you need pandas: `df = serializer.deserialize(data).to_pandas()`
- If you need polars: `df = pl.from_arrow(serializer.deserialize(data))`

Custom subclasses that override `deserialize()` (e.g. `PolarsParquetSerializer`
from the medallion example) continue to work but the override is now optional —
the base class already returns a framework-neutral Arrow Table.

## v0.19.0 to v0.20.0

**Deprecated aliases removed (BK-130):**

Three factory functions renamed in v0.18.0 have had their old names removed:

- `pydantic_to_registry_config()` → use `from_pydantic()`
- `remote_store_io_manager()` → use `dagster_io_manager()`
- `cached_store()` → use `cache()`

Pre-v1: removed without a deprecation cycle. Find-and-replace is sufficient.

## v0.18.0 to v0.19.0

**Factory function renames (BK-010):**

Three ext factory functions were renamed for naming consistency.
Old names emitted `DeprecationWarning` in v0.18.x and are removed after
v0.19.0 (see [above](#v0190-to-v0200)).

- `pydantic_to_registry_config()` → `from_pydantic()`
- `remote_store_io_manager()` → `dagster_io_manager()`
- `cached_store()` → `cache()`

## v0.17.0 to v0.18.0

**Extension imports moved (ADR-0013):**

Optional-dependency extensions are no longer re-exported from
`remote_store.__init__`. Import them directly from their extension module:

- Old: `from remote_store import pyarrow_fs, StoreFileSystemHandler`
- New: `from remote_store.ext.arrow import pyarrow_fs, StoreFileSystemHandler`

- Old: `from remote_store import otel_hooks, otel_observe`
- New: `from remote_store.ext.otel import otel_hooks, otel_observe`

- Old: `from remote_store import pydantic_to_registry_config`
- New: `from remote_store.ext.pydantic import from_pydantic`

- Old: `from remote_store import from_yaml`
- New: `from remote_store.ext.yaml import from_yaml`

Pure-Python extensions (`ext.batch`, `ext.transfer`, `ext.glob`, `ext.observe`,
`ext.cache`, `ext.partition`) are unchanged — they were already unconditionally
exported from `remote_store.__init__`.

## v0.15.0 to v0.16.0

**YAML config loader moved to extension:**

- `RegistryConfig.from_yaml()` has been removed from the core class and
  replaced by `from_yaml()` in `remote_store.ext.yaml`.
- Old: `config = RegistryConfig.from_yaml("config.yaml")`
- New: `from remote_store.ext.yaml import from_yaml` then `config = from_yaml("config.yaml")`
- Install the optional extra: `pip install "remote-store[yaml]"`

## v0.13.0 to v0.14.0

**Config loaders (new feature, no breaking changes):**

- `RegistryConfig.from_toml()` and `from_yaml()` are new. Existing
  `from_dict()` usage continues to work unchanged.
- `from_dict()` now warns on unknown keys (CFG-012). If you were passing
  extra keys silently, you will see warnings. Remove the unknown keys or
  suppress the warning.

## v0.12.0 to v0.13.0

**Credential hygiene:**

- Backend config values for keys named `key`, `secret`, `password`,
  `account_key`, `sas_token`, and `connection_string` are now automatically
  wrapped in `Secret` objects by `from_dict()`.
- If you were accessing these values directly as strings, use
  `secret.reveal()` to get the plain-text value.
- `repr()` and `str()` of config objects now mask credentials with `***`.

## v0.11.0 to v0.12.0

**Glob capability:**

- `Store.glob()` now requires `Capability.GLOB`. Backends that do not support
  it (Memory, SFTP) will raise `CapabilityNotSupported`.
- Use `ext.glob.glob_files()` as a portable fallback for all backends.

## General upgrade advice

1. Pin to a specific minor version in production: `remote-store>=0.16,<0.17`.
2. Read the [CHANGELOG](https://github.com/haalfi/remote-store/blob/master/CHANGELOG.md)
   for each version you skip.
3. Run your test suite after upgrading — the library has 95%+ coverage and
   you should too.

## See also

- [CHANGELOG](https://github.com/haalfi/remote-store/blob/master/CHANGELOG.md)
- [Contributing](https://github.com/haalfi/remote-store/blob/master/CONTRIBUTING.md) — stability tiers and versioning policy
