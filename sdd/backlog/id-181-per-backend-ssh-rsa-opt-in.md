# ID-181 — Per-backend `ssh-rsa` opt-in via `paramiko.Transport` subclass
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 4](../BACKLOG.md#no-workarounds) by the ADR-0040 § 4
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`SFTPUtils.enable_ssh_rsa_compat()` mutates paramiko's class attributes
so every `Transport` instance in the process accepts SHA-1 host keys
thereafter. For single-server use cases this is fine and documented as
a security tradeoff. For processes that talk to a mix of modern and
legacy SFTP backends (e.g. a Dagster job, a multi-tenant pipeline),
the shim leaks SHA-1 acceptance into every other transport, so one legacy
server weakens every other connection in the process.
Sketch: `BackendConfig(type="sftp", options={..., "allow_legacy_ssh_rsa": True})`
constructs a `Transport` subclass whose instance-level `_preferred_keys`
/ `_preferred_pubkeys` include `ssh-rsa`, leaving `paramiko.Transport`
class attrs untouched. `Transport._key_info` and `RSAKey.HASHES` are
read at class scope so they still need a module-level patch — but
those are algorithm-name → impl lookup tables, not security policy.

## Re-measured, 2026-09-27

The diagnosis holds and gains a bound. `enable_ssh_rsa_compat`'s docstring
(`rg -n -A46 'def enable_ssh_rsa_compat' src/remote_store/backends/_sftp.py`)
names four class attributes it patches: `Transport._preferred_keys`,
`Transport._key_info`, `RSAKey.HASHES` and `Transport._preferred_pubkeys`, and
warns under "Process-global side effect" that every transport in the process
then accepts SHA-1 host keys. It also says the helper is a no-op on paramiko
< 5.0, where all four sites carry `ssh-rsa` by default, so the leak this item
scopes arises only on paramiko ≥ 5.0. `pyproject.toml` pins `paramiko>=3.1`
with no upper bound (`rg -n 'paramiko' pyproject.toml`), so both occur.
`rg -n allow_legacy_ssh_rsa src docs-src sdd/specs` finds nothing: the sketched
option is unbuilt. Found by the ADR-0040 § 4 conversion.
