"""Retry Policy — Configure retry attempts, backoff, and jitter per-backend.

Demonstrates RetryPolicy construction, defaults, disabled retries,
and config-driven retry via TOML-style dicts.

---
see_also:
  - label: Retry
    url: ../how-to/retry.md
    note: retry configuration guide
"""

from __future__ import annotations

from remote_store import BackendConfig, RegistryConfig, RetryPolicy


def demo() -> None:
    """Show RetryPolicy usage patterns."""
    # -- Default policy --
    print("--- Default RetryPolicy ---")
    default = RetryPolicy()
    print(f"  max_attempts={default.max_attempts}")
    print(f"  backoff_base={default.backoff_base}")
    print(f"  backoff_max={default.backoff_max}")
    print(f"  jitter={default.jitter}")
    print(f"  timeout={default.timeout}")

    # -- Custom policy --
    print("\n--- Custom RetryPolicy ---")
    custom = RetryPolicy(
        max_attempts=5,
        backoff_base=2.0,
        backoff_max=30.0,
        jitter=0.5,
        timeout=120.0,
    )
    print(f"  {custom}")

    # -- Disabled retries --
    print("\n--- Disabled retries ---")
    no_retry = RetryPolicy.disabled()
    print(f"  max_attempts={no_retry.max_attempts} (single attempt, no retry)")

    # -- Config-driven retry --
    print("\n--- Config-driven retry (from dict) ---")
    config_data = {
        "backends": {
            "remote": {
                "type": "sftp",
                "options": {"host": "sftp.example.com"},
                "retry": {"max_attempts": 5, "backoff_base": 2.0},
            },
            "local": {
                "type": "local",
                "options": {"root": "/tmp/demo"},
            },
        },
        "stores": {
            "files": {"backend": "remote"},
        },
    }
    registry_config = RegistryConfig.from_dict(config_data)
    remote_cfg: BackendConfig = registry_config.backends["remote"]
    local_cfg: BackendConfig = registry_config.backends["local"]
    print(f"  remote retry: {remote_cfg.retry}")
    print(f"  local retry: {local_cfg.retry} (None = backend default)")

    # -- Validation --
    print("\n--- Validation ---")
    try:
        RetryPolicy(max_attempts=0)
    except ValueError as e:
        print(f"  max_attempts=0 rejected: {e}")

    try:
        RetryPolicy(timeout=-1)
    except ValueError as e:
        print(f"  timeout=-1 rejected: {e}")

    print("\nDone.")


if __name__ == "__main__":
    demo()
