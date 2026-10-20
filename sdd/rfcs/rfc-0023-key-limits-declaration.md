# RFC-0023: Key limits as a driver declaration

## Status

Draft, 2026-10-20. Tracked as **BK-469**, which carries its acceptance and
its implementation; it amends spec 054 (BK-468) on acceptance.

## Summary

A backend says which Keys it cannot store through a `key_limits` declaration
on its driver, which the contract kernel checks before any I/O and refuses with
`InvalidPath`. A declared limit is an exact rule, not a licence: a backend
refuses exactly the Keys its declaration names and stores every other Key in
the key function's range. Spec 054's KEY-008 then points at the declaration,
and `SPEC-DESIGN.md` Rule 5 is amended to say what a declaration is rather than
which mechanism carries it.

## Motivation

A Key one backend stores fails on another, and each backend fails its own way.
Measured at `7491289` with `sdd/research/bk-468-key-probe/probe_write.py`:
Memory stores a 300-character name; Local on Linux raises a raw `OSError`
[Errno 36]. Read from `src/remote_store/backends/_local.py`, not measured:
Local creates a write's parent folders before it opens the file, so a nested
key fails after leaving them behind. BUG-334 records Windows Local's raw
`OSError` [Errno 22]. Measured on CI's windows-latest runner at `74271f9c4`
(`tests/test_store_keys.py`, KEY-009): Local stores `a `, `a.`, `d/x. ` and
`a./b` under their stripped names, and a write of `a/     ` lands on the folder
`a` and raises `PermissionDenied`.

Spec 054 first stated the licence to refuse as a profile declared in each
backend's spec. Three review rounds on PR #1171 found the cost: nothing at
runtime reads prose, so conformance copies each limit by hand, the store cannot
refuse ahead of I/O, and Rule 5's "a capability or a driver flag" disagreed
with it. A declaration the kernel reads removes the per-backend divergence for
every Key that its spelling alone rules out, from one implementation.

## Decisions

### D1. The declaration

A driver may carry `key_limits: KeyLimits`, read with a default that limits
nothing, as `stream_catch` and `size_probe` are read today. `KeyLimits` is a
frozen value:

| Field | The kernel refuses a Key | Bound |
| --- | --- | --- |
| `unit: "utf8" \| "utf16"` | — (the unit `name_max` and `key_max` count in) | — |
| `name_max: int \| None` | with a name longer than this many units | at least 255 |
| `key_max: int \| None` | longer than this many units, as the driver receives it (`root_path` included) | KEY-A-01 |
| `forbidden: frozenset[str]` | with a name holding one of these code points | none of the portable name's code points |
| `trailing: frozenset[str]` | with a name ending in one of these code points | none of the code points a portable name may end with (`A-Z`, `a-z`, `0-9`, `_`, `-`) |
| `reserved_names: bool` | with a reserved name (spec 054 Terms) | — |

`unit` exists because a name limit is counted where the namespace counts it:
NTFS allows 255 UTF-16 units, which no byte count matches (`"日"*200` is 600
bytes and stored; `"𝄞"*130` is 520 bytes and refused). A portable name is
ASCII, so 255 units is 255 bytes in either unit and the floor holds.

Local's driver on Windows, for instance, declares `unit` as `"utf16"`,
`forbidden` as `<>:"|?*` and U+0001 to U+001F (spec 054 has already folded
`\`), `trailing` as space and `.`, and `reserved_names`; a name holding a space
elsewhere, such as `my file.txt`, stays stored. Each bound keeps spec
054's portable floor (KEY-007) inside every declaration.

### D2. A declared limit is an exact rule

A backend refuses exactly the Keys its declaration names, and stores every
other Key in spec 054's range. Spec 054's profiles become the declaration's
fields: KEY-008's table maps one row per field, and its licence ("may refuse")
becomes a rule ("refuses"), testable both ways. KEY-009 follows from it: a
backend whose namespace drops a trailing space or `.` declares them in
`trailing`. One part of `name-chars` has no field: refusing a name by its
first code point. No backend measured or documented here refuses `.a` or
`_a`, so it is dropped; the floor still excludes such names, for the tools
that treat them specially, not for any backend.

### D3. The kernel enforces it

On the kernel, the check runs on the canonical key, after BE-030's root check
and before the driver; the root has no name and no limit applies to it.
Addressing (`native_path`, `resolve`) runs no check, so it stays total
(BE-025), and spec 054 KEY-008 exempts it (D7). A `glob` pattern is not
checked: it is no key, and Windows' `forbidden` holds its wildcards `*` and
`?`; what it lists are stored keys. A driver whose wire refuses a Key its
declaration admits breaks KEY-008: the declaration is incomplete. BE-021's
error mapping still types that refusal, so the breach is a typed error and
not a raw one, but it is a breach, not a licence.

### D4. A value is derived at construction

A driver computes its declaration from its environment when it is built, never
from a backend's name. Local reads its file system's name limit and, on
Windows, derives `key_max` from the path limit in force less its root's
length; S3, Azure and SQL declare their documented or schema limits. The
declaration is fixed for the driver's lifetime.

### D5. Backends not on the kernel

A backend not on the kernel carries no declaration, so spec 054 KEY-008 holds
it to storing every Key in K's range; where it does not (Local today), that is
BK-469's breakage until its migration step (RFC-0017 D3). That divergence is
accepted for the migration's duration, while no release is planned (see
Alternatives).

### D6. Rule 5 is amended

`SPEC-DESIGN.md` Rule 5's first sentence becomes, one phrase changed:

> A behaviour that differs by backend is stated as a named profile, selected
> by a declaration the backend carries at runtime, with each outcome it allows
> stated in the clause, never implied by an example backend.

"Selected by a declaration the backend carries at runtime" replaces "declared
by a capability or a driver flag": it covers both and a Backend's own field,
and rules out a declaration in prose. Whether a profile licenses or fixes an
outcome is each clause's to state (spec 054 KEY-008, D2), and a value derived
from the environment is this design's (D4), so neither enters the rule. Its
remaining sentences stand. ADR-0048's decision ("a variation is a named
profile with each outcome it allows") names no mechanism and is unchanged.

### D7. What changes on acceptance

- Spec 054: KEY-008 states the declaration and the exact rule, its table one
  row per field, and exempts `native_path` and `resolve`. Every other mention
  of the profiles follows: the Overview's "a profile its spec declares", the
  Terms' Profile, KEY-A-01's `key-bytes`, and the Notes naming `name-chars`,
  `reserved-names` and the departure from Rule 5.
- Spec 053: a new section, BE-040 (Key Limits on the Kernel), states D1 to D4.
  BE-030 is not reworded.
- `SPEC-DESIGN.md` Rule 5, as D6.
- An ADR (ADR-0050 or the next free number) records D1, D2, D3 and D6.

## Alternatives

- **The declaration in each backend's spec** (spec 054 as first drafted).
  Rejected: nothing at runtime reads it, so the divergence it states is not
  removed and conformance copies it by hand.
- **The Store checks a Backend property.** Covers every backend now. Rejected
  by the maintainer (2026-10-20): during the migration onto the kernel the
  existing backends, the store and the spec are allowed to diverge, and the
  kernel and driver path is to be done properly rather than the old path
  patched. No release is planned while they diverge, so no user meets the gap.
  A store check would also state BE-030's rule a second time.
- **A capability per profile.** Readable through `Store.supports`, but a
  capability carries no number, so limits would need a second channel.
- **A licence.** A backend may refuse what it declares and still store it.
  Rejected: tests can check one direction only, and outcomes stay variable
  inside the licence.
- **Coarse switches** (`portable_names: bool`). Rejected while drafting: on
  Windows it would refuse every name with an inner space.

## Impact

- **Public API:** `KeyLimits` joins `remote_store.drivers`; the attribute is
  optional, so no driver breaks.
- **Backwards compatibility:** a Key a declaring backend failed on with a raw
  error now raises `InvalidPath` before I/O. A Key it silently aliased (Windows
  `a.`) now raises `InvalidPath`: breaking for a caller that relied on the
  alias, at that backend's migration step.
- **Performance:** one pass over the key per keyed call.
- **Testing:** kernel cells generated from a fake driver's declaration, both
  directions; per backend, conformance reads the driver's declaration for the
  must-store and must-refuse cells.

## Open Questions

1. **Listings.** An entry another tool stored that the declaration refuses
   (on Windows a foreign `a.` cannot exist; on a SQL table whose column was
   later narrowed it can): omitted and logged as BE-030 omits a non-canonical
   key, or listed but unreachable?
2. **Precedence against WR-010's metadata gate.** Proposed: the key check
   first, as a key refusal comes before what is written there.
3. **Windows path limit.** How Local detects long-path support for
   `key_max`.
4. **Callers.** Whether `Store` exposes the declaration, so a caller can check
   a key without a call.

## References

- Spec 054 (KEY-007 to KEY-009), spec 053 BE-030, spec 003 BE-021 and BE-025.
- `SPEC-DESIGN.md` Rule 5; ADR-0048; RFC-0017 D3; ADR-0042.
- Microsoft, "Naming Files, Paths, and Namespaces" and "File path formats on
  Windows systems".
