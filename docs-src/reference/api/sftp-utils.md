# SFTPUtils

!!! warning "Backend-specific module"
    The helpers and enums in this module are exclusive to the SFTP backend.
    Using them ties your code to `SFTPBackend`.

::: remote_store.backends.SFTPUtils
    options:
      members: false

## Methods

### load_private_key

::: remote_store.backends._sftp.load_private_key
    options:
      heading_level: 4
      show_root_heading: false

### enable_ssh_rsa_compat

::: remote_store.backends._sftp.enable_ssh_rsa_compat
    options:
      heading_level: 4
      show_root_heading: false

### scan_host_keys

::: remote_store.backends._sftp.scan_host_keys
    options:
      heading_level: 4
      show_root_heading: false

## Enums

### HostKeyPolicy

::: remote_store.backends._sftp.HostKeyPolicy
    options:
      heading_level: 4
      show_root_heading: false

## See also

- [SFTP Backend Guide](../../guides/backends/sftp.md) — connection setup, host key verification, and Key Vault integration
- [SFTP Backend example](../../../examples/backends/sftp_backend.py) — end-to-end SFTP usage
