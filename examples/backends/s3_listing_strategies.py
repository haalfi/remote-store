"""S3 listing strategies and performance best practices.

Demonstrates:
- Shallow listing (direct children only) — O(n_children) cost
- Recursive listing (flat stream) — O(n_total_files) cost
- When to use each approach
- Why parallelization is wrong for large buckets
- Impact of bucket structure on listing performance

Prerequisites:
- pip install "remote-store[s3]"
- An S3-compatible service with sample data

Environment variables:
    RS_S3_BUCKET    S3 bucket name (required)
    RS_S3_KEY       AWS access key ID
    RS_S3_SECRET    AWS secret access key
    RS_S3_ENDPOINT  Custom endpoint URL (e.g. http://localhost:9000 for MinIO)
"""

from __future__ import annotations

import os
import sys
import time
from typing import TYPE_CHECKING, Iterator

from remote_store import (
    BackendConfig,
    FileInfo,
    FolderEntry,
    Registry,
    RegistryConfig,
    StoreProfile,
)

if TYPE_CHECKING:
    from remote_store import Store

BUCKET = os.environ.get("RS_S3_BUCKET", "")

if not BUCKET:
    print(
        "Set RS_S3_BUCKET to run this example.\n"
        "Optional: RS_S3_KEY, RS_S3_SECRET, RS_S3_ENDPOINT\n"
    )
    sys.exit(1)


def setup_registry() -> Registry:
    """Create a registry connected to S3."""
    options: dict[str, object] = {"bucket": BUCKET}
    if val := os.environ.get("RS_S3_KEY"):
        options["key"] = val
    if val := os.environ.get("RS_S3_SECRET"):
        options["secret"] = val
    if val := os.environ.get("RS_S3_ENDPOINT"):
        options["endpoint_url"] = val

    config = RegistryConfig(
        backends={"s3": BackendConfig(type="s3", options=options)},
        stores={"demo": StoreProfile(backend="s3", root_path="listing-demo")},
    )
    return Registry(config)


def setup_sample_data(store_profile: Store) -> None:
    """Create sample directory structure for demonstration."""
    print("📝 Setting up sample data...")

    # Create a nested structure:
    # listing-demo/
    #   ├── file_at_root.txt
    #   ├── level1/
    #   │   ├── file1.txt
    #   │   ├── file2.txt
    #   │   └── level2/
    #   │       ├── file3.txt
    #   │       └── level3/
    #   │           └── file4.txt
    #   └── another/
    #       └── orphan.txt

    files = [
        "file_at_root.txt",
        "level1/file1.txt",
        "level1/file2.txt",
        "level1/level2/file3.txt",
        "level1/level2/level3/file4.txt",
        "another/orphan.txt",
    ]

    for path in files:
        store_profile.write(path, f"Content of {path}".encode())

    print(f"  ✓ Created {len(files)} files\n")


def demo_shallow_listing(store_profile: Store) -> None:
    """Shallow listing: list only direct children."""
    print("1️⃣  SHALLOW LISTING (direct children only)")
    print("   Code: store.iter_children(path)")
    print("   Cost: 1–N API calls (1 per 1000 items, with pagination)\n")

    print("   Direct children of 'listing-demo/':")
    for entry in store_profile.iter_children(""):
        if isinstance(entry, FileInfo):
            print(f"     📄 {entry.name} ({entry.size} bytes)")
        else:  # FolderEntry
            print(f"     📁 {entry.name}/")

    print("\n   Direct children of 'listing-demo/level1/':")
    for entry in store_profile.iter_children("level1"):
        if isinstance(entry, FileInfo):
            print(f"     📄 {entry.name} ({entry.size} bytes)")
        else:
            print(f"     📁 {entry.name}/")

    print()


def demo_recursive_listing(store_profile: Store) -> None:
    """Recursive listing: flat stream of all files."""
    print("2️⃣  RECURSIVE LISTING (flat stream, all files)")
    print("   Code: store.list_files(path, recursive=True)")
    print("   Cost: 1–N API calls (1 per 1000 items, S3 handles pagination)\n")

    print("   All files under 'listing-demo/' (recursive):")
    count = 0
    total_size = 0
    for file_info in store_profile.list_files("", recursive=True):
        count += 1
        total_size += file_info.size
        print(f"     📄 {file_info.path} ({file_info.size} bytes)")

    print(f"\n   Total: {count} files, {total_size} bytes\n")


def demo_filtering_on_stream(store_profile: Store) -> None:
    """Filter files while streaming (memory-efficient)."""
    print("3️⃣  FILTERING ON STREAM (memory-efficient)")
    print("   Process files without loading entire listing into memory\n")

    print("   Files matching pattern (*.txt):")
    for file_info in store_profile.list_files("", recursive=True):
        if str(file_info.path).endswith(".txt"):
            print(f"     📄 {file_info.path}")

    print()


def demo_performance_comparison(store_profile: Store) -> None:
    """Compare shallow vs recursive listing performance."""
    print("4️⃣  PERFORMANCE CHARACTERISTICS")
    print("   (These would be more dramatic with 1000s of files)\n")

    # Shallow listing
    start = time.perf_counter()
    list(store_profile.iter_children("level1"))
    shallow_time = (time.perf_counter() - start) * 1000

    # Recursive listing
    start = time.perf_counter()
    list(store_profile.list_files("level1", recursive=True))
    recursive_time = (time.perf_counter() - start) * 1000

    print(f"   Shallow (direct children):  {shallow_time:.2f}ms")
    print(f"   Recursive (entire tree):    {recursive_time:.2f}ms")
    print(f"   Ratio: {recursive_time / shallow_time:.1f}x (flat cost amortized over N files)\n")


def demo_antipattern(store_profile: Store) -> None:
    """Show what NOT to do: manual folder traversal."""
    print("5️⃣  ANTI-PATTERN: Manual Folder Traversal (❌ DON'T DO THIS)")
    print("   Pseudocode:\n")

    def manual_traverse(path: str) -> Iterator[FileInfo]:
        """Inefficient folder-by-folder traversal."""
        # This makes one API call per folder level
        for entry in store_profile.iter_children(path):
            if isinstance(entry, FileInfo):
                yield entry
            else:  # FolderEntry
                yield from manual_traverse(str(entry.path))

    print("   def manual_traverse(path):")
    print("       for entry in list_children(path):       # 1 API call")
    print("           if is_file:")
    print("               yield entry")
    print("           else:")
    print("               yield from manual_traverse(subfolder)  # Recursive calls!")
    print("\n   ❌ This costs O(n_folders) × API overhead")
    print("   ✓ Instead use: list_files(path, recursive=True)\n")


def cleanup(store_profile: Store) -> None:
    """Delete all demo files."""
    print("🧹 Cleaning up...")
    for file_info in store_profile.list_files("", recursive=True):
        store_profile.delete(str(file_info.path))
    print("   ✓ Deleted all demo files\n")


if __name__ == "__main__":
    registry = setup_registry()

    with registry:
        store = registry.get_store("demo")

        try:
            setup_sample_data(store)
            demo_shallow_listing(store)
            demo_recursive_listing(store)
            demo_filtering_on_stream(store)
            demo_performance_comparison(store)
            demo_antipattern(store)

        finally:
            cleanup(store)

    print("✅ Done! See guides/backends/s3.md for detailed performance analysis.")
