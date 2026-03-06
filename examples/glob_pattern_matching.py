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


def demo(store):
    """Three-tier glob filtering. Returns matched file lists."""
    results = {}

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

    csvs = sorted(str(f.path) for f in store.list_files("", pattern="*.csv"))
    results["tier1_csvs"] = csvs
    print(f"*.csv at root: {csvs}")

    reports = sorted(str(f.path) for f in store.list_files("", pattern="report.*"))
    results["tier1_reports"] = reports
    print(f"report.* at root: {reports}")

    md_files = sorted(str(f.path) for f in store.list_files("docs", pattern="*.md"))
    results["tier1_md"] = md_files
    print(f"*.md in docs/: {md_files}")

    all_logs = sorted(str(f.path) for f in store.list_files("", recursive=True, pattern="*.log"))
    results["tier1_logs_recursive"] = all_logs
    print(f"*.log recursive: {all_logs}")

    # --- Tier 3: glob_files() ---
    print("\n=== Tier 3: glob_files() ===\n")

    deep_logs = sorted(str(f.path) for f in glob_files(store, "**/*.log"))
    results["tier3_deep_logs"] = deep_logs
    print(f"**/*.log: {deep_logs}")

    doc_mds = sorted(str(f.path) for f in glob_files(store, "docs/*.md"))
    results["tier3_doc_mds"] = doc_mds
    print(f"docs/*.md: {doc_mds}")

    everything = sorted(str(f.path) for f in glob_files(store, "**/*"))
    results["tier3_everything"] = everything
    print(f"**/* (all files): {everything}")

    logs_only = sorted(str(f.path) for f in glob_files(store, "logs/**/*.log"))
    results["tier3_logs_scoped"] = logs_only
    print(f"logs/**/*.log: {logs_only}")

    # --- Tier 2: Store.glob() (capability-gated) ---
    print("\n=== Tier 2: Store.glob() ===\n")

    if store.supports(Capability.GLOB):
        native = sorted(str(f.path) for f in store.glob("**/*.csv"))
        results["tier2_native"] = native
        print(f"Native glob **/*.csv: {native}")
    else:
        print(
            f"Backend '{store._backend.name}' does not support native glob."
            " Use list_files(pattern=...) or glob_files() instead."
        )

    # --- Works with Store.child() ---
    print("\n=== Store.child() scoping ===\n")

    logs_child = store.child("logs")

    child_logs = sorted(str(f.path) for f in logs_child.list_files("", pattern="*.log"))
    results["child_tier1"] = child_logs
    print(f"child('logs').list_files(pattern='*.log'): {child_logs}")

    child_deep = sorted(str(f.path) for f in glob_files(logs_child, "**/*.log"))
    results["child_tier3"] = child_deep
    print(f"glob_files(child('logs'), '**/*.log'): {child_deep}")

    return results


if __name__ == "__main__":
    config = RegistryConfig(
        backends={"mem": BackendConfig(type="memory", options={})},
        stores={"data": StoreProfile(backend="mem", root_path="data")},
    )

    with Registry(config) as registry:
        store = registry.get_store("data")
        demo(store)

    print("\nDone!")
