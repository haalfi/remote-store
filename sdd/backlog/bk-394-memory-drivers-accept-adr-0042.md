# BK-394 — No backend runs on RFC-0017's kernel, so ADR-0042 stays Proposed
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** Split from BK-389 on 2026-10-02 under
[§ Completing work](../BACKLOG.md#how-this-file-works) "partly done", in the
planning PR that settled step 1's open decisions. RFC-0017 D3 step 1 ships as
two PRs: BK-389 lands the kernel, private, under the Proposed
[ADR-0042](../adrs/0042-contract-kernel-over-thin-drivers.md); this item lands
the two Memory drivers on it and is **the PR that accepts ADR-0042 and
RFC-0017**, the first backend on the new design. **It merges only after the
v0.33.0 tag, and after BK-389.** The decisions both halves rest on are in
[BK-389's dossier](bk-389-kernel-step-1-memory.md) § Decisions; read them
first.

## Decisions (planning PR, 2026-10-02)

Taken by the maintainer through the interview, the recommended option each
time.

1. **Public identity is kept.** `MemoryBackend` becomes
   `class MemoryBackend(DriverBackend)` and `AsyncMemoryBackend` becomes
   `class AsyncMemoryBackend(AsyncDriverBackend)`: same names and import
   paths, zero-argument constructors that build their driver, `isinstance`
   against `Backend` and `AsyncBackend` unchanged, user subclasses keep
   working, `name` stays `"memory"` and `"async-memory"`, and MEM-004's
   `repr` is kept. `MemoryDriver` and `AsyncMemoryDriver` are new public
   names beside them. Private internals (`_root`, `_traverse`, `_split_path`)
   move to the driver and were never promised.
2. **This PR makes the kernel public.** It exports the names RFC-0017
   § Impact, Public API lists, with the spec amendments below and the API
   reference pages; BK-389 left them unexported.
3. **Spec 013 is amended here,** with a kernel/driver placement per clause,
   IDs and prose kept, the pattern item 4 below prescribes for BE-021. Spec
   013 was assigned to no step before this split (`rg -n '013|MEM-'` over
   RFC-0017 returned nothing). The placement:

   | Owner after this PR | Clauses |
   |---|---|
   | kernel | MEM-013 (`write_atomic` as `put`, from `put_is_atomic = True`), MEM-015 (aggregation, now BE-017's rule: an unknown time skipped, `None` when none is known), MEM-018 (`close` through `close_is_terminal = False`), MEM-020 (the choke point; the driver raises nothing native, so `classify` is never reached), MEM-DS-005's root rows (the kernel's root check decides `""`, `"."` and the other spellings first) |
   | driver | MEM-DS-001 to 004 and 006, MEM-010, MEM-011, MEM-012, MEM-016 (`SupportsAtomicMove`, one lock), MEM-016b (`SupportsCopy`), MEM-025, MEM-026, MEM-DS-005's remaining rows (`..`, null byte, absolute) |
   | forwarded or declared | MEM-001 (constructor), MEM-002 (`name`), MEM-003 (capabilities, declared by the driver), MEM-005 (registration), MEM-017 (`to_key`), MEM-019 (`unwrap`) |
   | unchanged | MEM-030 to 032 (testing), MEM-040 to 042 (performance) |

## What it owes

Items 2 (the Memory half), 4, 5, 6 and 7 of BK-389's original list, moved
verbatim; bracketed text is added at the split.

2. `MemoryBackend` and `AsyncMemoryBackend` as drivers, gated by the
   conformance suite with D3's enumerated cell changes[; the fake-driver
   kernel suite stayed with BK-389].
4. Spec amendments that become true here:
   - spec 003: a BE-021 placement table assigning each obligation to kernel or
     driver, IDs kept and prose kept, plus placement notes on BE-020 and
     BE-029. A class not yet migrated discharges both halves.
   - spec 005: ERR-001's `path` and `backend`, and ERR-009's floor, are set by
     the kernel for a migrated class.
   - spec 037: the `max_depth` algorithm decided once, on DEPTH-003.
   - spec 003 BE-017: the folder `modified_at` rule above, sentinel and
     `None` included, with a note that `GraphBackend` answers its folder
     item's own time until step 7 migrates it (BK-390).
   - spec 029: the async surface and `AsyncDriver`.
   - specs 007 and 022, kernel half: `write_atomic` and temp-and-promote as
     kernel behaviour over `put_is_atomic`, `open_write` and `rename`.
   - spec 026: PING-002, because the kernel's `check_health()` runs the
     driver's required `probe()` where the default was a no-op; and PING-008,
     Memory's no-op row.
   - the Memory drivers' own rows under 007 and 022. Every later driver's rows
     are BK-390's, at that driver's step.
   - [spec 013, by the table above.]
   - [spec 003 BE-021 § Reach's page-boundary paragraph: under BK-389's
     decision 1 a migrated driver has no unmarked page, so the divergence it
     licenses applies only to a class not yet migrated.]
5. The custom-backend guide rewritten as a driver, its `partial-capabilities`
   region included. `scripts/check_custom_backend_guide.py` is re-pointed from
   `Backend.__abstractmethods__` at `Driver`, and the landing page's snippet
   (`docs-src/index.md`, `examples/snippets/homepage.py`) is updated. The
   migration guide gains its section for backend authors, and the CHANGELOG
   says direct `Backend` subclassing is no longer the documented route. Both
   are obligations of RFC-0017 § Impact, Backwards compatibility. All of this
   needs `Driver` to exist, which is why it is here and not in BK-387.
   - **(was BK-325, absorbed here)** The guide's remaining gaps, re-read
     against the driver shape before writing: `Secret`-wrapped credentials and
     the injected `retry=` kwarg (now the driver constructor's); stream-time
     error mapping for `LAZY_READ` (now the kernel's stream wrapper, so the
     guide states what the driver's `stream_catch` must name); the
     `strict_only` file-ancestor fixtures (`reject_write_under_file_ancestor`
     is a kernel option under RFC-0017 D2); and the three small fixes. The
     list and its 2026-09-27 correction are in BK-325's
     [dossier](bk-325-custom-backend-guide-gaps.md).
   - [BK-332's rehearsal runs after this item: it rehearses the guide this
     item rewrites.]
6. ADR-0042's Status set to Accepted and RFC-0017's Status set to Accepted, in
   the same PR. The four amendments then take effect, so the same PR adds the
   repo's inline `*Amended by [ADR-0042](...)*` note at each amended clause
   (`rg -n '\*Amended by' sdd/adrs` shows the convention): ADR-0001's
   *Backend (ABC)*, ADR-0011's transport-concern bullet, ADR-0012's
   Option E dismissal and ADR-0025's scope. It then regenerates
   `sdd/adrs/DIGEST.md`.
7. The re-homing RFC-0017 § Impact names: each open item listed there
   (BK-382, BK-242, BK-325, BK-332, BUG-266, ID-181, ID-140, BUG-287, 288,
   289, ID-217, BK-339) gets the D3 step or item that absorbs, obsoletes or
   leaves it, or is closed. Assigned here by the maintainer at BK-387's close.
   [BK-325 and BK-332 were placed at the split, above.]

**Before it changes the conformance registry** to register drivers beside
`Backend` instances (RFC-0017 D3), ID-244's open decision, where a seeding
hook binds, is taken: the registry change is the place it binds.

## Evidence (2026-10-02, master `9caef6b`)

- **Every Memory error names its backend by literal.** `backend="memory"`
  occurs 42 times in `src/remote_store/backends/_memory.py` and
  `backend="async-memory"` 40 times in
  `src/remote_store/aio/backends/_memory.py` (a count of matches of each
  string in its file). Under the kernel the choke point sets `backend` from
  the driver's `name` (ERR-001), so none of those literals survives into the
  driver.
- The closed-guard, sentinel and root-spelling measurements that bear on this
  item are in BK-389's dossier § Evidence, with the recipe that produced them.

**What it does not include.** The kernel (BK-389); step 2 onward (RFC-0017 D3);
the spec amendments of later steps (BK-390).
