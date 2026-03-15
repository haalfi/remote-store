# Migration Guide

Breaking changes and upgrade paths between `remote-store` versions.

`remote-store` has been published on PyPI since v0.11.0 (first Beta release).
The core Store API is stable, but extensions may evolve. This page documents
changes that require action when upgrading.

## v0.17.0 to next

**Extension imports moved (ADR-0013):**

Optional-dependency extensions are no longer re-exported from
`remote_store.__init__`. Import them directly from their extension module:

- Old: `from remote_store import pyarrow_fs, StoreFileSystemHandler`
- New: `from remote_store.ext.arrow import pyarrow_fs, StoreFileSystemHandler`

- Old: `from remote_store import otel_hooks, otel_observe`
- New: `from remote_store.ext.otel import otel_hooks, otel_observe`

- Old: `from remote_store import pydantic_to_registry_config`
- New: `from remote_store.ext.pydantic import pydantic_to_registry_config`

Pure-Python extensions (`ext.batch`, `ext.transfer`, `ext.glob`, `ext.observe`,
`ext.cache`, `ext.partition`) are unchanged -- they were already unconditionally
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
3. Run your test suite after upgrading -- the library has 95%+ coverage and
   you should too.

## See also

- [CHANGELOG](https://github.com/haalfi/remote-store/blob/master/CHANGELOG.md)
- [Contributing](contributing.md) -- stability tiers and versioning policy
