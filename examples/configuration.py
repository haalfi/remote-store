"""Configuration — config-as-code, from_dict(), multiple stores, and backend configs.

Demonstrates different ways to create and use RegistryConfig, including
configuration for S3, S3-PyArrow, and SFTP backends.
"""

from __future__ import annotations

import tempfile

from remote_store import BackendConfig, Registry, RegistryConfig, StoreProfile

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

    # --- Option 2: from_dict() — e.g. loaded from TOML or JSON ---
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

        with Registry(config) as registry:
            data = registry.get_store("data")
            logs = registry.get_store("logs")

            data.write("input.csv", b"a,b\n1,2\n")
            logs.write("app.log", b"[INFO] started\n")

            print(f"\nfrom_dict() data: {data.read_bytes('input.csv').decode().strip()}")
            print(f"from_dict() logs: {logs.read_bytes('app.log').decode().strip()}")

    # --- Backend configs for S3, S3-PyArrow, and SFTP ---
    # These are config-only examples. They show the structure but don't
    # connect to real services (no live credentials here).

    s3_config = RegistryConfig(
        backends={
            "s3": BackendConfig(
                type="s3",
                options={
                    "bucket": "my-bucket",
                    "key": "AKIAIOSFODNN7EXAMPLE",
                    "secret": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
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
                options={
                    "bucket": "big-data-bucket",
                    "region_name": "us-east-1",
                },
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

    # --- Config validation: referencing unknown backend raises ValueError ---
    try:
        bad = RegistryConfig(
            backends={},
            stores={"orphan": StoreProfile(backend="nonexistent")},
        )
        bad.validate()
    except ValueError as exc:
        print(f"\nValidation error: {exc}")

    print("\nDone!")
