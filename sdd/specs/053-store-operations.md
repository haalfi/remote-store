# 053: Store Operations Specification

## Overview

v1's core API offers exactly the entries of the
[operation catalogue](../observe/catalogue.md): every public operation serves
an entry, and every entry is served in a sync and an async form. This is a
structure spec about the API's surface: a witness of its violation is one
surface, read without a call. Which entries exist, and each one's intent,
target, result kind and offer, are the catalogue's rows; this spec cites them
and never copies one.

Out of scope, each with its owner:

- Each entry's operations, signatures, forms, outcomes and failures, stated
  once for both its forms: the entry's own spec.
- Which entries a store offers, against the catalogue's Offer column (`v1` on
  every store, `optional` only where the backend declares it), how a caller
  learns it, and what an operation of an entry the store does not offer
  answers: the spec of OP-18, which binds that column, and of the entry.
- Constructing and configuring a store, and the Python object protocol of the
  API's types (equality, hashing, representation): the API's spec.
- How an input becomes a key: [spec 052](052-store-key.md).
- Extensions, which build on the core's public operations and may offer what
  no entry does, and what sets an extension apart from the core: the API's
  spec.

**Supersedes** [spec 001](001-store-api.md) STORE-008 and
[spec 029](029-async-store-backend-api.md) ASYNC-046.

## Terms

| Term | Meaning |
| --- | --- |
| Store, AsyncStore | The v1 API's synchronous and asynchronous types through which a caller acts on one store, under whatever names the API's spec gives them. |
| Core API | Store, AsyncStore and the library's public functions outside its extensions. |
| Public operation | A method of Store or AsyncStore whose name has no leading underscore, a context-manager method of either, or a public function of the core API that takes a Store or an AsyncStore. Its form is sync when it takes or belongs to a Store, async when it takes or belongs to an AsyncStore. |
| Entry | A row of the catalogue, named by its ID (`OP-NN`). |
| Serves | A public operation serves an entry when the entry's spec names it as one of the entry's operations. What each one does is that spec's. |

---

## OPS-001: No Operation Outside the Catalogue

**Invariant:** Every public operation serves at least one entry.

## OPS-002: Every Entry in Both Forms

**Invariant:** Every entry is served by at least one public operation of the
sync form and at least one of the async form.

---

## Assumptions

None.

## Notes

Not normative.

- **One entry per intent.** The catalogue lists a thing a caller wants to do
  once, whatever its forms; reading whole, as text or as a stream are forms of
  OP-01, designed in OP-01's session. A public operation may therefore serve
  two entries, and an entry be served by several operations: OPS-001 and
  OPS-002 bound the surface from both sides without fixing that mapping.
- **One contract for both forms.** OPS-002 makes both forms exist; that they
  behave alike is stated once, by the entry's own spec, which designs both.
- **Which stores offer an entry.** What a given store supports is answered in
  one place, OP-18, so its spec binds the catalogue's Offer column rather than
  this spec; a clause here would need a call to witness. Where part of an
  entry differs by backend, such as whether an inspection carries an identity
  token, is a profile of the entry's spec
  ([RFC-0024](../rfcs/rfc-0024-spec-first-reset.md) D6), not an optional
  entry.
- **Extensions.** OPS-001 bounds the core only. An extension adds a feature
  on top of the entries, such as content hashing or an emulated append, and
  needs no entry; the catalogue's Not in v1 list names what the core leaves
  out, and the forms its entries' sessions decide.
- **Why the catalogue is a table beside the spec.** One row per entry needs a
  table, which no section's form gives; the clauses that bind it change only
  when the surface's rules do
  ([RFC-0026](../rfcs/rfc-0026-operation-catalogue.md) C3).
- **Checks.** Each section's witness is a public surface of the v1 API: its
  public operations, and which entry's spec names each. The sections bind code
  once a flow implements that surface (RFC-0024 § R4), and until then have no
  test ([RFC-0026](../rfcs/rfc-0026-operation-catalogue.md) C3).

## Tested against

None: each section's witness is a v1 surface, which no code has yet (Notes,
Checks).
