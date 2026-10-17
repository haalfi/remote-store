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
