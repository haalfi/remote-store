# 054: Store Key Specification

## Overview

A store answers a key parameter in two layers. The key function K maps the
parameter onto one Key of [spec 051](051-store-tree.md)'s tree or refuses it,
the same on every backend; the backend then admits that Key, or refuses it only
under a profile its spec declares and never when it is in the portable floor.
An operation acts on K(s) when both layers accept it, and refuses *s* otherwise.

Part 1 states K, a rule on the parameter; Part 2 states which Keys a backend
admits, and that an admitted Key reaches its own entity, rules on K's result. Both are function clauses
([`SPEC-DESIGN.md` Rule 2](../SPEC-DESIGN.md#kind-of-truth)): input to
verdict.

Scope: the key arguments of `Store` and `AsyncStore` operations. Out of scope:
the tree a Key names and how two Keys compare, which are spec 051's (§ Name
equality governs a backend that compares names more coarsely); the
`RemotePath` value object, spec 004's; `root_path`, STORE-001's; `child`'s
subpath, spec 015's; `glob` patterns, GLOB-007's; the keys a `Backend` takes
when called directly, including its root spellings, BE-029's, and on the
kernel BE-030's; and where an operation ranks a refusal among its other
errors, which is that operation's own clause (spec 001, spec 003).

## Terms

### On the parameter (Part 1)

| Term | Meaning |
| --- | --- |
| Input | A `str` passed as a key argument to a `Store` or `AsyncStore` operation. Its characters are code points. |
| Surrogate | A code point in U+D800 to U+DFFF; a Python `str` can hold one. |
| Scalar value | Any code point that is not a surrogate. |
| Examples | Quote inputs literally, except that `\0` stands for U+0000 and `\ud800` or `\udc00` for that surrogate; every other `\` is a backslash. |
| Separator | `/` or `\`. |
| Segment | A maximal run of code points holding no separator; an input with *n* separators has *n* + 1 segments, some possibly empty. |
| K(s) | The store key of input *s*: a Key, or refused. |
| Refused | The operation given the input raises `InvalidPath` ([ERR-005](005-error-model.md#err-005-invalidpath)) carrying the input, and the store is unchanged. |
| Folder-shaped | `exists`, `is_file`, `is_folder`, `iter_children`, `list_files`, `list_folders`, `get_folder_info`, `native_path`, `resolve`, and `delete_folder` except at the root (KEY-005). |
| File-shaped | `read`, `read_bytes`, `read_text`, `read_seekable`, `write`, `write_text`, `write_atomic`, `open_atomic`, `delete`, `get_file_info`, `head`, and both keys of `move` and `copy`. |

Both operation lists hold the `AsyncStore` method of the same name where one
exists; [STORE-002](001-store-api.md#store-002-path-validation) names the
call-level rule.

### On the Key (Part 2)

| Term | Meaning |
| --- | --- |
| Key, name, ε | Spec 051's (TREE-007, TREE-009); ε is the Key of the root. |
| Admits | A backend admits a Key when an operation on an input *s* with that K(s) is not refused for the Key's sake. |
| Bytes | A string's length in bytes is that of its UTF-8 encoding. |
| Portable name | A name of at most 255 bytes whose code points are ASCII letters, digits, `.`, `_` and `-`, whose first is a letter or digit, whose last is not `.`, and which is not a reserved name. |
| Reserved name | `CON`, `PRN`, `AUX`, `NUL`, `COM0` to `COM9` or `LPT0` to `LPT9`, compared ASCII case-insensitively, alone or followed by `.` and more. |
| Profile | A named licence to refuse a Key ([`SPEC-DESIGN.md` Rule 5](../SPEC-DESIGN.md#profiles-and-assumptions)). A backend declares a profile, and a limit where the profile takes one, in its own spec under `sdd/specs/`. |

---

## Part 1: The key function

### KEY-001: Totality

**Invariant:** K is total: every input maps to exactly one Key or to refused.

### PATH-002: Backslash Is a Separator

**Invariant:** `\` separates segments as `/` does, for every section below:
K(s) is K of *s* with every `\` replaced by `/`.

### PATH-003: Double-Dot Refusal

**Invariant:** An input with a segment equal to `..` is refused; a segment
merely containing `..`, such as `a..b`, is a name.

### PATH-007: Null Byte Refusal

**Invariant:** An input holding U+0000 is refused.

### KEY-002: Surrogate Refusal

**Invariant:** An input holding a surrogate is refused.

### KEY-003: Refusal Precedence

**Invariant:** An input that PATH-003, PATH-007 or KEY-002 refuses is refused
whatever its other segments are, so a refusal outranks both a Key and the
root: `./..` and `/\0` are refused, not ε.

### PATH-004: Leading and Trailing Separators

**Invariant:** The empty segments before the first separator and after the
last contribute nothing: K(`/a/b/`) = `a/b`.

### PATH-005: Repeated Separators

**Invariant:** The empty segment between two adjacent separators contributes
nothing: K(`a//b`) = K(`a\/b`) = `a/b`.

### PATH-006: Dot Segments

**Invariant:** A segment equal to `.` contributes nothing: K(`a/./b`) = `a/b`.

### KEY-004: Canonical Key

**Invariant:** An input no section refuses maps to its contributing segments,
in input order, joined by `/`, and to ε when none contributes.

| Input class (examples) | K(s) |
| --- | --- |
| canonical (`a`, `a/b`) | the input |
| a segment of whitespace only (`a/ /b`) | the input: whitespace is a name, neither dropped nor refused |
| non-canonical (`/a`, `a/`, `a//b`, `a/./b`, `a\b`) | the canonical Key (`a`, `a`, `a/b`, `a/b`, `a/b`) |
| only empty and `.` segments (`""`, `.`, `./`, `/`, `\`, `/./`) | ε |
| a `..` segment (`..`, `a/../b`, `a\..\b`, `./..`) | refused |
| U+0000 anywhere (`a\0b`, `/\0`) | refused |
| a surrogate anywhere (`\ud800`, `a/\udc00`) | refused |

### KEY-005: The Root at the Store

**Invariant:** An input *s* with K(s) = ε addresses the store root in a
folder-shaped operation, and is refused by a file-shaped operation and by
`delete_folder`.

### KEY-006: Addressable Keys

**Invariant:** Every Key K returns has names of scalar values with no `/`,
`\` or U+0000, none equal to `.` or `..`, and K maps that Key to itself.

---

## Part 2: Keys a backend admits

### KEY-007: Portable Floor

**Invariant:** Every backend admits a Key of at most 255 bytes whose names are
all portable names.

### KEY-008: Backend Refusal

**Invariant:** A backend admits every Key in K's range except where a profile
its spec declares licenses a refusal, and a Key it does not admit is answered
as refused; a backend whose spec declares no profile admits every such Key.

| Profile | A Key it may refuse | Bound |
| --- | --- | --- |
| `name-bytes` | one with a name longer than the backend's declared limit | the limit is at least 255 bytes |
| `key-bytes` | one whose backend key (STORE-003) is longer than the backend's declared limit | KEY-A-01 |
| `name-chars` | one with a name holding a code point other than an ASCII letter, digit, `.`, `_` or `-`, starting with one other than a letter or digit, or ending in `.` | — |
| `reserved-names` | one with a reserved name | — |

### KEY-009: Faithful Admission

**Invariant:** An operation on a Key a backend admits acts on that Key's own
entity, never on another Key's, wherever the Key alone decides it; a backend
whose namespace would address a Key as another Key does not admit it.

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
- K applies no Unicode normalisation and no case folding: by KEY-004 each name
  of K(s) is a segment of *s*, code point for code point. That is K's own
  rule, not spec 051's. Spec 051's exact name equality binds Keys, K's
  results; a normalising K would still return exactly compared Keys, as it
  already maps `a//b` and `a/b` onto one. The reason is addressability: a K
  that normalised would leave every Key stored in another normal form or case
  outside its range, unreachable as `a\b` is (next note).
- By KEY-006 a stored Key with a name holding `\`, U+0000 or a surrogate, or
  equal to `.` or `..`, is a Key of the tree that no input reaches; spec 053's
  BE-032 A.2 states how listings treat one. `a\b` as an input addresses `a/b`
  (PATH-002).
- A `..` segment is refused, never resolved against its parent: `a/../b` is
  not `b`, so no input reaches a Key outside the one it spells.
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
- KEY-009 binds where the key alone decides the address, such as a
  namespace that removes a trailing space or `.` from a Key's last name:
  there `a ` and `a` reach one entity, and `a/     ` reaches its parent `a`,
  whatever the store holds. Microsoft's "Naming Files, Paths, and Namespaces" states that
  Windows path handling removes them; such a backend takes `name-chars`.
  Aliasing that depends on what the store holds, such as two names differing
  only in case on a case-insensitive file system, is spec 051 § Name
  equality's. A POSIX file system keeps every name but `/` and U+0000 as
  written, a five-space name included.
- The reserved names are the device names of Microsoft's "Naming Files,
  Paths, and Namespaces"; the `name-chars` and `reserved-names` profiles cover
  what that page forbids beyond the floor.

## Tested against

The tests carrying a mark of this spec's sections, run with
`python scripts/run_tests.py tests/test_path.py tests/test_store.py tests/test_store_keys.py`.
No formal model governs these sections; `WellFormedPath` in
`sdd/formal/BackendContract.dfy` states the range of PATH-002 to PATH-007 with
no bridge.
