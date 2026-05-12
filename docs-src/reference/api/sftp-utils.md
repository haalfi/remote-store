# SFTPUtils

!!! warning "Backend-specific module"
    The helpers and enums in this module are exclusive to the SFTP backend.
    Using them ties your code to `SFTPBackend`.

::: remote_store.backends.SFTPUtils
    options:
      members: false

## Methods

::: remote_store.backends.SFTPUtils.load_private_key
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.backends.SFTPUtils.enable_ssh_rsa_compat
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.backends.SFTPUtils.scan_host_keys
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.backends.SFTPUtils.scan_host_algorithms
    options:
      show_root_heading: true
      heading_level: 3

## Enums

::: remote_store.backends._sftp.HostKeyPolicy
    options:
      show_root_heading: true
      heading_level: 3

## See also

- [SFTP Backend Guide](../../guides/backends/sftp.md) — connection setup, host key verification, and Key Vault integration
- [SFTP Backend example](../../../examples/backends/sftp_backend.py) — end-to-end SFTP usage
