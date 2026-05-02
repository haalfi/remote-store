"""Configuration — Config-as-code, `from_dict()`, multiple stores, S3/SFTP backend configs.

Demonstrates different ways to create and use RegistryConfig, including
credential hygiene with Secret, from_dict() auto-wrapping, and
configuration examples across multiple backends.

---
see_also:
  - label: Choosing a Backend
    url: ../../guides/choosing-a-backend.md
    note: backend selection guide
"""

from __future__ import annotations

import tempfile

from remote_store import BackendConfig, Registry, RegistryConfig, Secret, StoreProfile


def demo():
    """Config creation, Secret hygiene, from_dict(), validation. Returns results dict."""
    results = {}

    # --- from_dict() — e.g. loaded from TOML or JSON ---
    with tempfile.TemporaryDirectory() as tmp:
        raw = {
            "backends": {
                "local": {"type": "local", "options": {"root": tmp}},
            },
            "stores": {
                "data": {"backend": "local", "root_path": "data"},
                "logs": {"backend": "local", "root_path": "logs"},
            },
        }

        config = RegistryConfig.from_dict(raw)
        results["from_dict_config"] = config

        with Registry(config) as registry:
            data = registry.get_store("data")
            logs = registry.get_store("logs")

            data.write("input.csv", b"a,b\n1,2\n")
            logs.write("app.log", b"[INFO] started\n")

            results["from_dict_data"] = data.read_bytes("input.csv")
            results["from_dict_logs"] = logs.read_bytes("app.log")
            print(f"from_dict() data: {results['from_dict_data'].decode().strip()}")
            print(f"from_dict() logs: {results['from_dict_logs'].decode().strip()}")

    # --- Credential hygiene: Secret wrapping ---
    manual_secret = Secret("my-secret-key")
    results["secret_repr"] = repr(manual_secret)
    results["secret_str"] = str(manual_secret)
    results["secret_reveal"] = manual_secret.reveal()
    assert repr(manual_secret) == "Secret('***')"
    assert str(manual_secret) == "***"
    print("\nSecret masking: repr -> Secret('***'), str -> ***")
    print(f"Secret reveal: {manual_secret.reveal()}")

    # from_dict() auto-wraps known sensitive keys:
    raw_with_creds = {
        "backends": {
            "s3": {
                "type": "s3",
                "options": {
                    "bucket": "my-bucket",
                    "key": "your-access-key-id",
                    "secret": "your-secret-access-key",
                },
            },
        },
        "stores": {"data": {"backend": "s3", "root_path": "data"}},
    }
    config_with_secrets = RegistryConfig.from_dict(raw_with_creds)
    s3_opts = config_with_secrets.backends["s3"].options
    results["auto_key_repr"] = repr(s3_opts["key"])
    results["auto_secret_repr"] = repr(s3_opts["secret"])
    results["bucket_value"] = s3_opts["bucket"]
    assert repr(s3_opts["key"]) == "Secret('***')"
    assert repr(s3_opts["secret"]) == "Secret('***')"
    print("\nAuto-wrapped credentials masked: key and secret -> Secret('***')")
    print(f"Bucket (not secret): {s3_opts['bucket']!r}")

    # --- Backend configs (config-only, no live credentials) ---
    s3_config = RegistryConfig(
        backends={
            "s3": BackendConfig(
                type="s3",
                options={
                    "bucket": "my-bucket",
                    "key": "your-access-key-id",
                    "secret": "your-secret-access-key",
                    "region_name": "eu-central-1",
                },
            ),
        },
        stores={
            "data": StoreProfile(backend="s3", root_path="data"),
            "backups": StoreProfile(backend="s3", root_path="backups"),
        },
    )
    print(f"\nS3 config: {len(s3_config.stores)} stores on {len(s3_config.backends)} backend(s)")

    s3pa_config = RegistryConfig(
        backends={
            "s3pa": BackendConfig(
                type="s3-pyarrow",
                options={"bucket": "big-data-bucket", "region_name": "us-east-1"},
            ),
        },
        stores={"lake": StoreProfile(backend="s3pa", root_path="lake/v1")},
    )
    print(f"S3-PyArrow config: {len(s3pa_config.stores)} store(s)")

    sftp_config = RegistryConfig(
        backends={
            "sftp": BackendConfig(
                type="sftp",
                options={
                    "host": "files.example.com",
                    "username": "deploy",
                    "password": "secret",
                    "base_path": "/srv/data",
                },
            ),
        },
        stores={"uploads": StoreProfile(backend="sftp", root_path="uploads")},
    )
    print(f"SFTP config: {len(sftp_config.stores)} store(s)")

    azure_config = RegistryConfig(
        backends={
            "azure": BackendConfig(
                type="azure",
                options={
                    "container": "my-container",
                    "account_name": "myaccount",
                    "account_key": "base64-account-key-here",
                },
            ),
        },
        stores={"documents": StoreProfile(backend="azure", root_path="documents")},
    )
    print(f"Azure config: {len(azure_config.stores)} store(s)")

    http_config = RegistryConfig(
        backends={
            "http": BackendConfig(
                type="http",
                options={
                    "base_url": "https://data.example.com/files/",
                    "timeout": 15.0,
                },
            ),
        },
        stores={"public": StoreProfile(backend="http", root_path="datasets")},
    )
    print(f"HTTP config: {len(http_config.stores)} store(s)")

    memory_config = RegistryConfig(
        backends={"mem": BackendConfig(type="memory")},
        stores={"scratch": StoreProfile(backend="mem", root_path="scratch")},
    )
    print(f"Memory config: {len(memory_config.stores)} store(s)")

    results["config_counts"] = {
        "s3_stores": len(s3_config.stores),
        "sftp_stores": len(sftp_config.stores),
        "azure_stores": len(azure_config.stores),
        "memory_stores": len(memory_config.stores),
    }

    # --- Config validation: referencing unknown backend raises ValueError ---
    try:
        bad = RegistryConfig(
            backends={},
            stores={"orphan": StoreProfile(backend="nonexistent")},
        )
        bad.validate()
    except ValueError as exc:
        results["validation_error"] = exc
        print(f"\nValidation error: {exc}")

    return results


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        # --- Option 1: Config-as-code with Python objects ---
        config = RegistryConfig(
            backends={
                "local": BackendConfig(type="local", options={"root": tmp}),
            },
            stores={
                "uploads": StoreProfile(backend="local", root_path="uploads"),
                "reports": StoreProfile(backend="local", root_path="reports"),
                "archive": StoreProfile(backend="local", root_path="archive"),
            },
        )

        with Registry(config) as registry:
            uploads = registry.get_store("uploads")
            reports = registry.get_store("reports")

            uploads.write("photo.jpg", b"\xff\xd8\xff\xe0fake-jpeg-data")
            reports.write("q4.csv", b"revenue,profit\n100,20\n")

            print("Uploads:", [f.name for f in uploads.list_files("")])
            print("Reports:", [f.name for f in reports.list_files("")])

    # --- Options 2+ (from_dict, Secrets, backend configs, validation) ---
    print()
    demo()
    print("\nDone!")
