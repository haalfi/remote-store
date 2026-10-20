# RFC-0023: Key limits as a driver declaration

## Status

Draft, 2026-10-20. Tracked as **BK-468**, whose spec 054 it amends on
acceptance; the implementation is BK-469's.

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
[Errno 36] after creating the parent folders. BUG-334 records Windows Local's
raw `OSError` [Errno 22]; Win32 path handling drops a last name's trailing
space or dot, so `a.` reaches `a` (spec 054 KEY-009's Note, documented, not
measured here).

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
| `name_bytes: int \| None` | with a name longer than this many bytes | at least 255 |
| `key_bytes: int \| None` | longer than this many bytes, as the driver receives it (`root_path` included) | KEY-A-01 |
| `forbidden: frozenset[str]` | with a name holding one of these code points | none of the portable name's code points |
| `trailing: frozenset[str]` | with a name ending in one of these code points | none of the portable name's code points |
| `reserved_names: bool` | with a reserved name (spec 054 Terms) | — |

Local's driver on Windows, for instance, declares `forbidden` as `<>:"|?*` and
U+0001 to U+001F (spec 054 has already folded `\`), `trailing` as space and `.`, and `reserved_names`; a name holding a
space elsewhere, such as `my file.txt`, stays stored. Each bound keeps spec
054's portable floor (KEY-007) inside every declaration.

### D2. A declared limit is an exact rule

A backend refuses exactly the Keys its declaration names, and stores every
other Key in spec 054's range. Spec 054's profiles become the declaration's
fields: KEY-008's table maps one row per field, and its licence ("may refuse")
becomes a rule ("refuses"), testable both ways. KEY-009 follows from it: a
backend whose namespace drops a trailing space or `.` declares them in
`trailing`.

### D3. The kernel enforces it

On the kernel, the check runs on the canonical key, after BE-030's root check
and before the driver; the root has no name and no limit applies to it.
Addressing (`native_path`, `resolve`) runs no check, so it stays total
(BE-025). A driver whose wire refuses a Key the declaration admits answers
through BE-021's error mapping as today: the declaration narrows that path, it
does not replace it.

### D4. A value is derived at construction

A driver computes its declaration from its environment when it is built, never
from a backend's name. Local reads its file system's name limit and, on
Windows, derives `key_bytes` from the path limit in force less its root's
length; S3, Azure and SQL declare their documented or schema limits. The
declaration is fixed for the driver's lifetime.

### D5. Backends not on the kernel

A backend not on the kernel carries no declaration, so spec 054 KEY-008 holds
it to storing every Key in K's range; where it does not (Local today), that is
BK-469's breakage until its migration step (RFC-0017 D3).

### D6. Rule 5 is amended

`SPEC-DESIGN.md` Rule 5's first sentence becomes:

> A behaviour that differs by backend is stated as a named profile, selected
> by a declaration the backend carries at runtime (a capability, or a field
> of the Backend or of its driver), never by a backend's name or by prose
> alone. Each outcome a profile allows is stated in the clause, and whether
> the profile licenses a variation or fixes it. A declaration whose value
> depends on the environment is derived by the backend at construction, and
> the clause states the bound it may not cross.

Its remaining sentences stand. ADR-0048's decision ("a variation is a named
profile with each outcome it allows") names no mechanism and is unchanged.

### D7. What changes on acceptance

- Spec 054: KEY-008 states the declaration and the exact rule, its table one
  row per field; the Terms' Profile and the Note recording the departure from
  Rule 5 go.
- Spec 053: a new section, BE-034 (Key Limits on the Kernel), states D1 to D4.
  BE-030 is not reworded.
- `SPEC-DESIGN.md` Rule 5, as D6.
- An ADR records D1, D2, D3 and D6.

## Alternatives

- **The declaration in each backend's spec** (spec 054 as first drafted).
  Rejected: nothing at runtime reads it, so the divergence it states is not
  removed and conformance copies it by hand.
- **The Store checks a Backend property.** Covers every backend now. Rejected
  by the maintainer: key rules belong to the kernel (BE-030), and a second
  check at the store would state one rule twice.
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
3. **Windows path limit.** How Local detects long-path support, and whether
   `key_bytes` counts UTF-16 units there rather than bytes.
4. **Callers.** Whether `Store` exposes the declaration, so a caller can check
   a key without a call.

## References

- Spec 054 (KEY-007 to KEY-009), spec 053 BE-030, spec 003 BE-021 and BE-025.
- `SPEC-DESIGN.md` Rule 5; ADR-0048; RFC-0017 D3; ADR-0042.
- Microsoft, "Naming Files, Paths, and Namespaces".
