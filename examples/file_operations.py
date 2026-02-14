"""File operations — read, write, delete, move, copy, list, and metadata.

Demonstrates the full range of Store methods using the local backend.
"""

from __future__ import annotations

import tempfile

from remote_store import BackendConfig, Registry, RegistryConfig, StoreProfile

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
            print("Created 3 files.\n")

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

            # --- Copy ---
            store.copy("docs/readme.txt", "docs/readme_backup.txt")
            print(f"\nCopied readme.txt -> readme_backup.txt (exists: {store.exists('docs/readme_backup.txt')})")

            # --- Move ---
            store.move("docs/changelog.txt", "archive/changelog.txt")
            print(f"Moved changelog.txt -> archive/ (original exists: {store.exists('docs/changelog.txt')})")

            # --- Delete ---
            store.delete("docs/readme_backup.txt")
            print(f"Deleted readme_backup.txt (exists: {store.exists('docs/readme_backup.txt')})")

            # --- Recursive listing from store root ---
            print("\nAll files (recursive):")
            for f in store.list_files("", recursive=True):
                print(f"  {f.path} ({f.size} bytes)")

    print("\nDone!")
