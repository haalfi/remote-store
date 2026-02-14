"""Configuration — config-as-code, from_dict(), and multiple stores.

Demonstrates different ways to create and use RegistryConfig.
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

            uploads.write("images/photo.jpg", b"\xff\xd8\xff\xe0fake-jpeg-data")
            reports.write("quarterly/q4.csv", b"revenue,profit\n100,20\n")

            print("Uploads:", [f.name for f in uploads.list_files("images")])
            print("Reports:", [f.name for f in reports.list_files("quarterly")])

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
