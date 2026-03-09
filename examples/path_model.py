"""Path model -- RemotePath normalization, properties, and validation.

Demonstrates:
- Path normalization rules (backslash, dots, slashes, trailing slashes)
- RemotePath properties: name, parent, parts, suffix
- The / operator for joining paths
- RemotePath.ROOT sentinel for root folder identity
- InvalidPath exceptions (double-dot, null byte, empty path)
- RemotePath immutability
- FileInfo.path is a RemotePath (working with listing results)
"""

from __future__ import annotations

from remote_store import InvalidPath, RemotePath, Store
from remote_store.backends import MemoryBackend


def demo(store):
    """RemotePath construction, normalization, and properties. Returns results dict."""
    results = {}

    # --- Normalization ---
    print("=== Normalization Rules ===\n")

    # Backslash to forward slash
    p1 = RemotePath("data\\reports\\q1.csv")
    results["backslash"] = str(p1)
    print(f"Backslash: 'data\\\\reports\\\\q1.csv' -> '{p1}'")

    # Trailing slash stripped
    p2 = RemotePath("data/reports/")
    results["trailing_slash"] = str(p2)
    print(f"Trailing slash: 'data/reports/' -> '{p2}'")

    # Consecutive slashes collapsed
    p3 = RemotePath("data///reports//q1.csv")
    results["double_slash"] = str(p3)
    print(f"Double slash: 'data///reports//q1.csv' -> '{p3}'")

    # Dot segments removed
    p4 = RemotePath("./data/./reports/./q1.csv")
    results["dot_segments"] = str(p4)
    print(f"Dot segments: './data/./reports/./q1.csv' -> '{p4}'")

    # All normalize to the same path
    all_equal = p1 == p2 / "q1.csv" == p3 == p4
    results["all_equal"] = all_equal
    print(f"All equivalent: {all_equal}")

    # --- Properties ---
    print("\n=== Properties ===\n")

    path = RemotePath("data/reports/quarterly/q1-2026.csv")

    results["name"] = path.name
    results["suffix"] = path.suffix
    results["parts"] = path.parts
    results["parent"] = str(path.parent)

    print(f"Path: '{path}'")
    print(f"  name: '{path.name}'")
    print(f"  suffix: '{path.suffix}'")
    print(f"  parts: {path.parts}")
    print(f"  parent: '{path.parent}'")

    # Parent chain
    current = path
    chain = [str(current)]
    while current.parent is not None:
        current = current.parent
        chain.append(str(current))
    results["parent_chain"] = chain
    print(f"  parent chain: {chain}")

    # No suffix
    no_ext = RemotePath("Makefile")
    results["no_suffix"] = no_ext.suffix
    print(f"\n  '{no_ext}' suffix: '{no_ext.suffix}' (empty)")

    # Single-component path has no parent
    single = RemotePath("file.txt")
    results["single_parent"] = single.parent
    print(f"  '{single}' parent: {single.parent}")

    # --- / operator ---
    print("\n=== / Operator ===\n")

    base = RemotePath("data")
    joined = base / "reports" / "q1.csv"
    results["joined"] = str(joined)
    print(f"RemotePath('data') / 'reports' / 'q1.csv' -> '{joined}'")

    # --- ROOT sentinel ---
    print("\n=== ROOT Sentinel ===\n")

    root = RemotePath.ROOT
    results["root_str"] = str(root)
    results["root_repr"] = repr(root)
    print(f"ROOT: str='{root}', repr={repr(root)}")

    # ROOT is used by get_folder_info for the store root
    store.write("a.txt", b"data")
    info = store.get_folder_info("")
    results["root_folder_path"] = str(info.path)
    is_root = info.path == RemotePath.ROOT
    results["is_root"] = is_root
    print(f"get_folder_info('').path == ROOT: {is_root}")

    # --- InvalidPath exceptions ---
    print("\n=== InvalidPath Exceptions ===\n")

    invalid_cases = {
        "double_dot": "../escape",
        "null_byte": "file\x00name.txt",
        "empty": "",
        "just_dots": "././.",
    }

    for label, raw in invalid_cases.items():
        try:
            RemotePath(raw)
            results[label] = None
        except InvalidPath as exc:
            results[label] = exc
            display = repr(raw) if "\x00" in raw else f"'{raw}'"
            print(f"  {display} -> InvalidPath: {exc.args[0]}")

    # --- Immutability ---
    print("\n=== Immutability ===\n")

    immutable_path = RemotePath("important/file.txt")
    try:
        immutable_path._path = "hacked"
    except AttributeError as exc:
        results["immutable"] = True
        print(f"Cannot modify: {exc}")

    # --- FileInfo.path is a RemotePath ---
    print("\n=== FileInfo.path ===\n")

    store.write("docs/readme.md", b"# Readme")
    store.write("docs/guide.md", b"# Guide")
    files = store.list_files("docs")
    for f in sorted(files, key=lambda fi: str(fi.path)):
        print(f"  {repr(f.path)}  name='{f.path.name}'  suffix='{f.path.suffix}'")
    results["fileinfo_is_remotepath"] = all(isinstance(f.path, RemotePath) for f in files)
    print(f"All paths are RemotePath: {results['fileinfo_is_remotepath']}")

    return results


if __name__ == "__main__":
    store = Store(backend=MemoryBackend())
    demo(store)
    print("\nDone!")
