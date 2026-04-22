# SFTPUtils

!!! warning "Backend-specific module"
    `SFTPUtils`, `load_private_key`, and `HostKeyPolicy` are exclusive to the
    SFTP backend. Using them ties your code to `SFTPBackend`.

::: remote_store.backends.SFTPUtils
    options:
      members: false

## Methods

### load_private_key

::: remote_store.backends._sftp.load_private_key
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

- [SFTP Backend Guide](../backends/sftp.md) — connection setup, host key verification, and Key Vault integration
- [SFTP Backend example](../examples/sftp-backend.md) — end-to-end SFTP usage
