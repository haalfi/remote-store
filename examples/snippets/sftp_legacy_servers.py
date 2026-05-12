"""SFTP legacy-server snippets — sourced by the SFTP backend guide.

Demonstrates the SFTP legacy-server compatibility helpers
(`enable_ssh_rsa_compat`, `scan_host_keys`) against process state only
(no network). Each snippet exercises the helper end to end so CI catches
drift between docs and the API shape.

The `scan_host_keys` example in the guide is hand-written (Rule 6
exemption, documented inline there): it requires a live SFTP server to
be meaningful, and snippets run via `hatch run examples` without test
fixtures.
"""

from __future__ import annotations

from typing import Any

import paramiko


def demo() -> None:
    """Execute the legacy-server snippets."""
    _enable_ssh_rsa_compat()


def _enable_ssh_rsa_compat() -> None:
    # --8<-- [start:enable-ssh-rsa-compat]
    from remote_store.backends import SFTPUtils

    # Call once, before any SFTPBackend connect to a legacy server.
    SFTPUtils.enable_ssh_rsa_compat()
    # --8<-- [end:enable-ssh-rsa-compat]
    # Prove the call mutated the four removal sites so docs-vs-runtime drift
    # surfaces in CI. The four private attributes are unstyped in
    # types-paramiko; route through an Any-typed alias for mypy.
    from paramiko.rsakey import RSAKey

    transport_cls: Any = paramiko.Transport
    assert "ssh-rsa" in transport_cls._preferred_keys
    assert "ssh-rsa" in transport_cls._preferred_pubkeys
    assert "ssh-rsa" in transport_cls._key_info
    assert "ssh-rsa" in RSAKey.HASHES


if __name__ == "__main__":
    demo()
