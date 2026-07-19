# ADR-0005: Bidirectional Path Resolution via `to_key`

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

The Store API has a round-trip problem. Users pass **store-relative keys**
(e.g. `"reports/q1.csv"`) into Store methods, and the Store joins them with
`root_path` before delegating to the backend. But the **return path** is broken:

- `list_files` and `get_file_info` delegate to the backend, which returns
  `FileInfo` with paths relative to the **backend root** — these include the
  store's `root_path` prefix. A `Store(root_path="data")` listing returns
  `FileInfo.path = "data/reports/q1.csv"`, not `"reports/q1.csv"`.
- If the user feeds that path back into `store.read(str(info.path))`, the Store
  prepends `root_path` again → `"data/data/reports/q1.csv"` → `NotFound`.

A second, related problem: users receive **absolute or backend-native paths**
from external sources (SFTP server logs, S3 event notifications, filesystem
watchers) and need to convert them to store-relative keys. No public helper
exists for this.

Both problems reduce to the same missing primitive: **convert a
backend-native/absolute path to a store-relative key**.

### Current ad-hoc handling

Each backend strips its own root differently:
- **Local:** `Path.relative_to(self._root)` inline in listing methods.
- **S3:** `_rel_path()` helper strips the bucket prefix.
- **SFTP:** String concatenation from input path + filename (no dedicated helper).

None of them strip the **store root** — that responsibility belongs to the Store
layer, which currently doesn't do it at all.

## Decision

- **A `to_key` primitive at two levels, `Backend.to_key` and `Store.to_key`,
  same-named by design (clear intent, composable).** Both the broken listing
  round-trip and external-path conversion reduce to one operation: stripping a
  layer's own root. `Backend.to_key` strips the backend's native root/prefix;
  `Store.to_key` composes that with stripping `root_path` to yield a
  store-relative key. *Reverse if* a use case needs a path transform that is not
  root-stripping; then `to_key` is the wrong primitive, not merely
  under-featured.
- **`Backend.to_key` is a concrete ABC method with an identity default.** Only
  backends with a custom root override it; every other backend inherits the
  identity, so the change is zero-behavioral for them: the
  backward-compatibility invariant. *Reverse if* the identity default ever
  yields a wrong key for an un-overridden backend, which would mean the default
  is unsafe and the method must become abstract.
- **`to_key` is pure, deterministic, and total (no I/O, no side effects).** That
  purity is what makes a concrete default safe to inherit and lets the inverse
  round-trip hold. *Reverse if* a backend's native→key mapping genuinely
  requires I/O, breaking totality.
- **The Store owns the round-trip guarantee.** The Store layer strips
  `root_path`; backends only know their own root. The path-returning listing
  methods (`list_files`, `get_file_info`, `get_folder_info`) strip `root_path`
  so returned paths feed back into Store methods without double-prefixing;
  `list_folders` returns immediate subfolder *names* and is unaffected (spec 010
  § NPR-015). *Reverse if* backends must become root-aware for another reason,
  making a single Store-level strip point insufficient.

Exact signatures, per-backend stripping examples, the composition sequence, and
the full methods-that-strip enumeration are spec-rate and live in spec 010
(NPR-003, NPR-006/007/008, NPR-010/011, NPR-014/015).

## Consequences

- **Round-trip works** — `FileInfo.path` from listing is directly usable as
  input to `read`, `write`, `delete`, etc.
- **External paths are supported** — users can convert absolute paths from logs,
  events, and other systems to store keys via a public API.
- **Backend path logic is centralized** — each backend defines its
  native→relative conversion in one place instead of scattering it.
- **RemotePath is untouched** — all PATH-* spec invariants remain in force.
- **Backward compatible** — identity default means zero behavioral change for
  backends that don't override.
