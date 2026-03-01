"""Glob pattern matching -- three-tier file filtering.

Demonstrates:
- Tier 1: list_files(pattern=...) -- fnmatch name filtering
- Tier 3: glob_files() -- portable full glob with ** recursive patterns
- Tier 2: Store.glob() -- native backend glob (capability-gated)
- Pattern syntax: *, **, ?, [abc], [!abc]
- Works with Store.child() scoping
"""

from __future__ import annotations

from remote_store import (
    BackendConfig,
    Capability,
    Registry,
    RegistryConfig,
    StoreProfile,
    glob_files,
)

if __name__ == "__main__":
    # Use MemoryBackend -- no filesystem or credentials needed.
    config = RegistryConfig(
        backends={"mem": BackendConfig(type="memory", options={})},
        stores={"data": StoreProfile(backend="mem", root_path="data")},
    )

    with Registry(config) as registry:
        store = registry.get_store("data")

        # --- Set up test files ---
        store.write("report.csv", b"quarterly report")
        store.write("report.txt", b"text version")
        store.write("logs/app.log", b"app log")
        store.write("logs/error.log", b"error log")
        store.write("logs/archive/old.log", b"archived log")
        store.write("docs/readme.md", b"readme")
        store.write("docs/guide.md", b"guide")
        store.write("docs/images/logo.png", b"logo")
        print("Created 8 test files across 4 directories\n")

        # --- Tier 1: list_files(pattern=...) ---
        print("=== Tier 1: list_files(pattern=...) ===\n")

        # Simple extension filter
        csvs = sorted(str(f.path) for f in store.list_files("", pattern="*.csv"))
        print(f"*.csv at root: {csvs}")

        # Multiple matches with name pattern
        reports = sorted(str(f.path) for f in store.list_files("", pattern="report.*"))
        print(f"report.* at root: {reports}")

        # Filter within a subdirectory
        md_files = sorted(str(f.path) for f in store.list_files("docs", pattern="*.md"))
        print(f"*.md in docs/: {md_files}")

        # Recursive + pattern: all .log files at any depth
        all_logs = sorted(str(f.path) for f in store.list_files("", recursive=True, pattern="*.log"))
        print(f"*.log recursive: {all_logs}")

        # --- Tier 3: glob_files() ---
        print("\n=== Tier 3: glob_files() ===\n")

        # Recursive glob with **
        deep_logs = sorted(str(f.path) for f in glob_files(store, "**/*.log"))
        print(f"**/*.log: {deep_logs}")

        # Subdirectory pattern
        doc_mds = sorted(str(f.path) for f in glob_files(store, "docs/*.md"))
        print(f"docs/*.md: {doc_mds}")

        # Match everything
        everything = sorted(str(f.path) for f in glob_files(store, "**/*"))
        print(f"**/* (all files): {everything}")

        # Scoped glob within a subdirectory
        logs_only = sorted(str(f.path) for f in glob_files(store, "logs/**/*.log"))
        print(f"logs/**/*.log: {logs_only}")

        # --- Tier 2: Store.glob() (capability-gated) ---
        print("\n=== Tier 2: Store.glob() ===\n")

        if store.supports(Capability.GLOB):
            native = sorted(str(f.path) for f in store.glob("**/*.csv"))
            print(f"Native glob **/*.csv: {native}")
        else:
            print(
                f"Backend '{store._backend.name}' does not support native glob."
                " Use list_files(pattern=...) or glob_files() instead."
            )

        # --- Works with Store.child() ---
        print("\n=== Store.child() scoping ===\n")

        logs_child = store.child("logs")

        # Tier 1 through child
        child_logs = sorted(str(f.path) for f in logs_child.list_files("", pattern="*.log"))
        print(f"child('logs').list_files(pattern='*.log'): {child_logs}")

        # Tier 3 through child
        child_deep = sorted(str(f.path) for f in glob_files(logs_child, "**/*.log"))
        print(f"glob_files(child('logs'), '**/*.log'): {child_deep}")

    print("\nDone!")
