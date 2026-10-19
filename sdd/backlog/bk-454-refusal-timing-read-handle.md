# BK-454 — A refusal surfaces at the call in one layer and at the first iteration in another
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** BK-449, which stated the rule in spec 003 BE-033
§ Refusal timing and left its implementation here, by the maintainer's choice
recorded in `sdd/decisions/ad497154-50c4-54f3-9b47-d86d1878741d.jsonl` ("Where
is the refusal-timing rule implemented?": "With the handle item (Rec.)"). That
section's table is the measurement; this dossier does not copy it.

**How the table was measured.** Each cell called the member and recorded
whether the refusal raised at the call or at the first `next`/`__anext__`
(a `read()` of the sync stream): `MemoryBackend` and `AsyncMemoryBackend` for
`../x`-style keys and a missing file, the fake driver of `tests/_kernel/_fake.py`
with `close_is_terminal=True` after `close()` for the closed guard, and `Store` /
`AsyncStore` over Memory. Run at BK-449's branch head, 2026-10-17.

**Prescription** (advisory, from BK-449's planning):

- A read handle, `with store.read(path) as stream` and
  `async with store.read(path) as chunks`, that opens the stream on entry, so a
  `NotFound` or a file-versus-folder `InvalidPath` surfaces there, and closes
  it on exit in both runtimes. The async handle also ends the caller's
  `aclose` burden on an abandoned iterator.
- Pure refusals (closed guard, capability gates, malformed key) at the call in
  every layer: the sync and async kernel listings, `glob`, and the async kernel
  `read`. Sync listings change behaviour (CHANGELOG, migration note).
- Listing I/O stays lazy, at the first page.
- Open: whether a bare `async for chunk in store.read(path)` keeps working
  unchanged, and the handle's type in each runtime.

## Moved out of spec 003, 2026-10-19

Verbatim from `sdd/specs/003-backend-adapter-contract.md` at master
`35ea366`, links re-based to this directory, by BK-456's first stage: the
text stated project state, which a spec does not carry
([`SPEC-DESIGN.md` Rule 7](../SPEC-DESIGN.md#no-project-state)). A dated
record, not kept current.

BE-033 **Refusal timing**, the measured table:

> [The rule is stated here and not]
> yet met. Today's timing, measured on Memory and, for the closed guard, the
> fake driver with `close_is_terminal = True`:
>
> | Layer | `read`: pure refusal | `read`: I/O refusal | listing: pure refusal | `glob`: capability |
> |---|---|---|---|---|
> | sync kernel class | call | call | first `next` | first `next` |
> | async kernel class | first `__anext__` | first `__anext__` | first `__anext__` | first `__anext__` |
> | `Store` | call | call | first `next` | first `next` |
> | `AsyncStore` | call for a malformed key; first `__anext__` for the closed guard | first `__anext__` | call for a malformed key; first `__anext__` for the closed guard | call |
>
> BK-454 builds the handle and moves the refusals the rule places at the call;
> ASYNC-006 points here for the async gap.
