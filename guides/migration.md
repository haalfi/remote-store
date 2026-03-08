# Migration Guide

Breaking changes and upgrade paths between `remote-store` versions.

`remote-store` has been published on PyPI since v0.11.0 (first Beta release).
The core Store API is stable, but extensions may evolve. This page documents
changes that require action when upgrading.

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

1. Pin to a specific minor version in production: `remote-store>=0.14,<0.15`.
2. Read the [CHANGELOG](https://github.com/haalfi/remote-store/blob/master/CHANGELOG.md)
   for each version you skip.
3. Run your test suite after upgrading -- the library has 95%+ coverage and
   you should too.

## See also

- [CHANGELOG](https://github.com/haalfi/remote-store/blob/master/CHANGELOG.md)
- [Contributing](contributing.md) -- stability tiers and versioning policy
