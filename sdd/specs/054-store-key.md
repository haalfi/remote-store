# 054: Store Key Specification

## Overview

A store maps every string a caller passes as a key onto one Key of
[spec 051](051-store-tree.md)'s tree, or refuses it, by one total function;
a backend may refuse a Key beyond that only under a profile it declares, and
never one in the portable floor. This spec states that function, its
precedence, the store's root spellings, the floor and the profiles. Its clauses
are function clauses
([`SPEC-DESIGN.md` Rule 2](../SPEC-DESIGN.md#kind-of-truth)): input to verdict.

Scope: the key arguments of `Store` and `AsyncStore` operations. Out of scope:
the tree a Key names and how names compare, which are spec 051's (§ Name
equality governs a backend that compares names more coarsely); the
`RemotePath` value object, spec 004's; `root_path`, STORE-001's; `child`'s
subpath, spec 015's; `glob` patterns, GLOB-007's; the keys a `Backend` takes when called directly,
including its root spellings, BE-029's, and on the kernel BE-030's; and where
an operation ranks a refusal among its other errors, which is that
operation's own clause (spec 001, spec 003).

## Terms

- **Input**: a `str` passed as a key argument to a `Store` or `AsyncStore`
  operation. Its characters are code points, so it may hold a **surrogate**,
  a code point in U+D800 to U+DFFF; every other code point is a **scalar
  value**.
- **Examples** quote inputs literally, except that `\0` stands for U+0000 and
  `\ud800` or `\udc00` for that surrogate; every other `\` is a backslash.
- **Separator**: `/` or `\`. A **segment** of an input is a maximal run of
  code points holding no separator; an input with *n* separators has *n* + 1
  segments, some possibly empty.
- **Key**, **name**, ε: spec 051's (TREE-007, TREE-009); ε is the Key of the
  root.
- **K(s)**: the store key of input *s*, a Key or **refused**.
- **Refused**: the operation given the input raises `InvalidPath`
  ([ERR-005](005-error-model.md#err-005-invalidpath)) carrying the input, and
  the store is unchanged.
- **Folder-shaped** operation: `exists`, `is_file`, `is_folder`,
  `iter_children`, `list_files`, `list_folders`, `get_folder_info`,
  `native_path` and `resolve`. **File-shaped**: `read`, `read_bytes`,
  `read_text`, `read_seekable`, `write`, `write_text`, `write_atomic`,
  `open_atomic`, `delete`, `get_file_info`, `head`, and both keys of `move`
  and `copy`. Each list holds the `AsyncStore` method of the same name where
  one exists ([STORE-002](001-store-api.md#store-002-path-validation) names
  the call-level rule).
- **Bytes**: a string's length in bytes is that of its UTF-8 encoding.
- **Portable name**: a name of at most 255 bytes whose code points are ASCII
  letters, digits, `.`, `_` and `-`, whose first is a letter or digit, whose
  last is not `.`, and which is not a **reserved name**: `CON`, `PRN`, `AUX`,
  `NUL`, `COM0` to `COM9` or `LPT0` to `LPT9`, compared ASCII
  case-insensitively, alone or followed by `.` and more.
- **Profile**: a named licence to refuse a Key
  ([`SPEC-DESIGN.md` Rule 5](../SPEC-DESIGN.md#profiles-and-assumptions)). A
  backend **declares** a profile, and a limit where the profile takes one, in
  its own spec under `sdd/specs/`.

---

## KEY-001: Totality

**Invariant:** K is total: every input maps to exactly one Key or to refused.

## PATH-002: Backslash Is a Separator

**Invariant:** `\` separates segments as `/` does, for every section below:
K(s) is K of *s* with every `\` replaced by `/`.

## PATH-003: Double-Dot Refusal

**Invariant:** An input with a segment equal to `..` is refused; a segment
merely containing `..`, such as `a..b`, is a name.

## PATH-007: Null Byte Refusal

**Invariant:** An input holding U+0000 is refused.

## KEY-002: Surrogate Refusal

**Invariant:** An input holding a surrogate is refused.

## KEY-003: Refusal Precedence

**Invariant:** An input that PATH-003, PATH-007 or KEY-002 refuses is refused
whatever its other segments are, so a refusal outranks both a Key and the
root: `./..` and `/\0` are refused, not ε.

## PATH-004: Leading and Trailing Separators

**Invariant:** The empty segments before the first separator and after the
last contribute nothing: K(`/a/b/`) = `a/b`.

## PATH-005: Repeated Separators

**Invariant:** The empty segment between two adjacent separators contributes
nothing: K(`a//b`) = K(`a\/b`) = `a/b`.

## PATH-006: Dot Segments

**Invariant:** A segment equal to `.` contributes nothing: K(`a/./b`) = `a/b`.

## KEY-004: Canonical Key

**Invariant:** An input no section refuses maps to its contributing segments,
in input order, joined by `/`, and to ε when none contributes.

| Input class (examples) | K(s) |
| --- | --- |
| canonical (`a`, `a/b`) | the input |
| non-canonical (`/a`, `a/`, `a//b`, `a/./b`, `a\b`) | the canonical Key (`a`, `a`, `a/b`, `a/b`, `a/b`) |
| only empty and `.` segments (`""`, `.`, `./`, `/`, `\`, `/./`) | ε |
| a `..` segment (`..`, `a/../b`, `a\..\b`, `./..`) | refused |
| U+0000 anywhere (`a\0b`, `/\0`) | refused |
| a surrogate anywhere (`\ud800`, `a/\udc00`) | refused |

## KEY-005: The Root at the Store

**Invariant:** An input *s* with K(s) = ε addresses the store root in a
folder-shaped operation, and is refused by a file-shaped operation and by
`delete_folder`.

## KEY-006: Addressable Keys

**Invariant:** Every Key K returns has names of scalar values with no `/`,
`\` or U+0000, none equal to `.` or `..`, and K maps that Key to itself.

## KEY-007: Portable Floor

**Invariant:** A Key of at most 255 bytes whose names are all portable names
is refused by no backend.

## KEY-008: Backend Refusal

**Invariant:** A backend that does not store a Key in K's range answers as
refused, and only where a profile its spec declares licenses it; a backend
whose spec declares no profile stores every such Key.

| Profile | A Key it may refuse | Bound |
| --- | --- | --- |
| `name-bytes` | one with a name longer than the backend's declared limit | the limit is at least 255 bytes |
| `key-bytes` | one whose backend key (STORE-003) is longer than the backend's declared limit | KEY-A-01 |
| `name-chars` | one with a name holding a code point other than an ASCII letter, digit, `.`, `_` or `-`, starting with one other than a letter or digit, or ending in `.` | — |
| `reserved-names` | one with a reserved name | — |

---

## Assumptions

| ID | Assumption |
| --- | --- |
| KEY-A-01 | A backend's native root and the store's `root_path` leave room on the platform for a further 255 bytes of key: within each `key-bytes` limit, and on Windows within the path length limit in force. |

## Notes

Not normative.

- PATH-002 to PATH-007, KEY-002 and KEY-004 define K; KEY-001, KEY-003 and
  KEY-006 follow from that definition and are sections because callers rely on
  them directly. KEY-003: the refusals inspect every segment and code point,
  and dropping a segment (PATH-004 to PATH-006) refuses nothing. KEY-006: a
  contributing segment is non-empty, holds no separator, is not `.` (PATH-006)
  and not `..` (PATH-003), and holds no U+0000 (PATH-007) or surrogate
  (KEY-002); joining such names is a canonical Key, which every section
  leaves unchanged.
- By KEY-006 a stored Key with a name holding `\`, U+0000 or a surrogate, or
  equal to `.` or `..`, is a Key of the tree that no input reaches; spec 053's
  BE-032 A.2 states how listings treat one. `a\b` as an input addresses `a/b`
  (PATH-002).
- Two levels state root spellings. At the store, every input KEY-004 maps to ε
  is the root (KEY-005), `\` included; a store hands its backend only the
  canonical ε, prefixed by `root_path` (STORE-003). BE-029's set, which
  excludes `\`, binds a `Backend` called directly.
- Every portable name is canonical, so a Key in the floor is its own K.
  KEY-007 holds per Key; whether two floor Keys differing only in case are two
  entities on a backend is spec 051 § Name equality.
- A profile is declared in the backend's spec rather than by the capability
  or driver flag [`SPEC-DESIGN.md` Rule 5](../SPEC-DESIGN.md#profiles-and-assumptions)
  names, by the maintainer's decision: the licence and its limit sit beside
  the backend's other clauses, and a conformance cell takes them as a
  per-backend parameter. A runtime declaration would replace it, not add to
  it.
- The reserved names are the device names of Microsoft's "Naming Files,
  Paths, and Namespaces"; the `name-chars` and `reserved-names` profiles cover
  what that page forbids beyond the floor.

## Tested against

The tests carrying a mark of this spec's sections, run with
`python scripts/run_tests.py tests/test_path.py tests/test_store.py tests/test_store_keys.py`.
No formal model governs these sections; `WellFormedPath` in
`sdd/formal/BackendContract.dfy` states the range of PATH-002 to PATH-007 with
no bridge.
