# 053: Store Operations Specification

## Overview

v1's core API offers, through its public operations, exactly the entries of
the [operation catalogue](../observe/catalogue.md): every public operation serves
an entry, and every entry is served in a sync and an async form. This is a
structure spec about the API's surface: a witness of its violation is one
surface, read without a call. Which entries exist, and each one's intent,
target, result kind and offer, are the catalogue's rows; this spec cites them
and never copies one.

Out of scope, each with its owner:

- Each entry's operations, signatures, forms, outcomes and failures, stated
  once for both its forms: the entry's own spec.
- Which entries a store offers, against the catalogue's Offer column, how a
  caller learns it, and what an operation of an entry the store does not offer
  answers: the spec of OP-18, which binds that column, and of the entry.
- Callables on the type, and core functions, that take no Store or AsyncStore
  (constructors from configuration, key checks), and the equality, hashing,
  representation, copying and pickling of the API's types: the API's spec.
- How an input becomes a key: [spec 052](052-store-key.md).
- Extensions, which build on the core's public operations and may offer what
  no entry does, and what sets an extension apart from the core: the API's
  spec.

**Supersedes** [spec 001](001-store-api.md) STORE-008,
[spec 029](029-async-store-backend-api.md) ASYNC-046,
[spec 027](027-iter-children.md) ITER-003, [spec 028](028-read-text.md)
RTXT-003 and [spec 030](030-write-text.md) WTXT-003.

## Terms

| Term | Meaning |
| --- | --- |
| Store, AsyncStore | The v1 API's synchronous and asynchronous types through which a caller acts on one store, under whatever names the API's spec gives them. |
| Core API | Store, AsyncStore and the library's public functions outside its extensions. |
| Public operation | On an instance of Store or AsyncStore: anything a caller reaches through a name without a leading underscore (a method, a property, an attribute), and every special method the type defines rather than inherits unchanged from `object`. On the type, and as a function of the core API: a callable that takes a Store or an AsyncStore, constructors and factories included. Excluded: equality, hashing, representation, copying and pickling. Its form is sync when every Store or AsyncStore it takes or is reached on is a Store, async when every one is an AsyncStore; one that takes both has neither form. The table in Notes sets each kind of callable against the term. |
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
- **Public operations.** The term has one rule per access path: on an
  instance, everything the type offers counts; on the type or as a function, a
  callable counts when it takes a store. The table after this list sets each
  kind against it.
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
  once a flow implements that surface (RFC-0024 § R4); why no test witnesses
  them before it is [RFC-0026](../rfcs/rfc-0026-operation-catalogue.md) C3.

| Callable | Public operation |
| --- | --- |
| On an instance: method, property or attribute with a public name, including one that returns a store derived from it (OP-16) | yes |
| On an instance: special method the type defines (context manager, `__contains__`, `__iter__`, `__getitem__`, operators) | yes |
| On an instance: special method inherited unchanged from `object` (`__setattr__`, `__dir__`, `__format__`, default ordering) | no: not the API's |
| Equality, hashing, representation, copying, pickling | no: the API's spec |
| Name with a leading underscore that is not a special method | no: not part of the API |
| On the type: callable taking a Store or an AsyncStore (a constructor or factory from an existing store) | yes |
| On the type: callable taking neither (a constructor from configuration, a key check) | no: the API's spec |
| Core function taking a Store or an AsyncStore | yes |
| Core function taking neither | no: the API's spec |
| Extension function | no: spec 053 bounds the core only |

## Tested against

None.
