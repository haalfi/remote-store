"""File operations — the full Store API demonstrated.

Covers: read, write, delete, delete_folder, move, copy, list, metadata,
is_file, is_folder, supports, and to_key — using the local backend.
"""

from __future__ import annotations

import os
import tempfile

from remote_store import BackendConfig, Registry, RegistryConfig, StoreProfile
from remote_store._capabilities import Capability

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        config = RegistryConfig(
            backends={"local": BackendConfig(type="local", options={"root": tmp})},
            stores={"files": StoreProfile(backend="local", root_path="workspace")},
        )

        with Registry(config) as registry:
            store = registry.get_store("files")

            # --- Write ---
            store.write("docs/readme.txt", b"First file")
            store.write("docs/changelog.txt", b"v0.1.0 - initial release")
            store.write("data/report.csv", b"col1,col2\n1,2\n3,4")
            store.write("tmp/scratch.txt", b"temporary data")
            print("Created 4 files.\n")

            # --- List files in a folder ---
            print("Files in docs/:")
            for f in store.list_files("docs"):
                print(f"  {f.name} ({f.size} bytes)")

            # --- List folders at the store root ---
            print("\nFolders at store root:")
            for folder in store.list_folders(""):
                print(f"  {folder}/")

            # --- Read ---
            content = store.read_bytes("data/report.csv")
            print(f"\nreport.csv content:\n{content.decode()}")

            # --- Metadata ---
            info = store.get_file_info("docs/readme.txt")
            print(f"readme.txt - size: {info.size}, modified: {info.modified_at}")

            folder_info = store.get_folder_info("docs")
            print(f"docs/ - {folder_info.file_count} files, {folder_info.total_size} bytes total")

            # --- is_file / is_folder ---
            print(f"\nis_file('docs/readme.txt'):  {store.is_file('docs/readme.txt')}")
            print(f"is_folder('docs'):           {store.is_folder('docs')}")
            print(f"is_file('docs'):             {store.is_file('docs')}")
            print(f"is_folder('docs/readme.txt'):{store.is_folder('docs/readme.txt')}")

            # --- Copy ---
            store.copy("docs/readme.txt", "docs/readme_backup.txt")
            print(f"\nCopied readme.txt -> readme_backup.txt (exists: {store.exists('docs/readme_backup.txt')})")

            # --- Move ---
            store.move("docs/changelog.txt", "archive/changelog.txt")
            print(f"Moved changelog.txt -> archive/ (original exists: {store.exists('docs/changelog.txt')})")

            # --- Delete ---
            store.delete("docs/readme_backup.txt")
            print(f"Deleted readme_backup.txt (exists: {store.exists('docs/readme_backup.txt')})")

            # --- delete_folder ---
            store.delete_folder("tmp", recursive=True)
            print(f"Deleted tmp/ folder (exists: {store.exists('tmp')})")

            # --- supports ---
            print(f"\nBackend supports ATOMIC_WRITE: {store.supports(Capability.ATOMIC_WRITE)}")
            print(f"Backend supports READ:         {store.supports(Capability.READ)}")

            # --- to_key ---
            # Convert a filesystem-absolute path back to a store-relative key
            absolute_path = os.path.join(tmp, "workspace", "data", "report.csv")
            store_key = store.to_key(absolute_path)
            print(f"\nto_key('{absolute_path}')")
            print(f"  -> '{store_key}'")

            # --- Recursive listing from store root ---
            print("\nAll files (recursive):")
            for f in store.list_files("", recursive=True):
                print(f"  {f.path} ({f.size} bytes)")

    print("\nDone!")
