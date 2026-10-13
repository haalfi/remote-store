# 051: Store Tree Specification

## Overview

A store is a rooted tree of folders and items, each addressed by one Key.
This spec states that tree as axioms over a set of entities, defines the Key
of an entity, and states the consequences a caller relies on: one entity per
Key, the shape of a Key, and closure of Keys under ancestors. It describes
structure only, at one instant: no operation, backend or encoding.

Rationale, the evidence that each axiom is needed (a countermodel per
clause), and the machine checks live in
[`research/research-store-model-axioms.md`](../research/research-store-model-axioms.md):
`formal/alloy/StoreAxioms.als` checks the axioms in bounded scope and
`formal/lean/StoreAxioms.lean` proves the lemmas over any universe. Section
TREE-*n* restates the research doc's clause of the same meaning; where the two
disagree, a misstatement here is fixed here.

**Layering.** This spec governs Keys and the tree over them. Spec 004 governs
input strings: `RemotePath` normalizes an accepted input onto a Key
(PATH-002 to PATH-006) and rejects the rest (PATH-003, PATH-007, PATH-008), so
the library addresses a subset of the Keys this spec admits. Spec 003's
§ The store tree (RFC-0021, BK-432) states how a backend encodes the tree; its
statement of the tree's structure points here once both have landed.

**Not bound to backends yet.** The sections are tested against a reference
model of the axioms (`tests/test_store_tree.py`). A flat backend can today hold
a raw state in which a key is an item and has keys below it, which no tree
gives; RFC-0021 makes such a state undecodable and refuses the write that
creates it (BK-432). Conformance of each backend's observed tree to this spec
follows that work (BK-436).

**Name equality.** Names compare exactly, with no case folding and no Unicode
normalization; this spec fixes no normalization form, since one would make
differently spelled names aliases of one entity. A backend whose own name
equality is coarser, such as a case-insensitive or normalizing file system,
represents only the stores whose sibling names stay distinct under that
equality; which backends compare names how is measured under BK-436.

**Terms.** Σ is an alphabet that contains `/` and at least one other symbol.
Σ\* is the set of finite words over Σ, and ε the empty word. N, the names, are
the non-empty words over Σ in which `/` does not occur; names compare as words,
exactly. A store is a tuple (U, F, I, r, C, name): a set U of entities, folders
F and items I, a root r, containment C ⊆ U × U where (p, x) ∈ C reads "p
contains x", and name: U → Σ\*. U may be infinite: no section assumes it is
finite.

---

## TREE-001: Partition

**Invariant:** Every entity is a folder or an item, and none is both:
U = F ∪ I and F ∩ I = ∅.

## TREE-002: Root

**Invariant:** The root is a folder: r ∈ F.

## TREE-003: Items Are Leaves

**Invariant:** Only a folder contains anything: C ⊆ F × U.

## TREE-004: At Most One Container

**Invariant:** No entity has two containers: if (p, x) ∈ C and (q, x) ∈ C,
then p = q.

**See also:** that every non-root entity *has* a container follows from
TREE-006 (research § 4, D1); it is not a separate section.

## TREE-005: Root Is Topmost

**Invariant:** Nothing contains the root: (p, r) ∉ C for every p ∈ U.

## TREE-006: Reachability

**Invariant:** Every entity is reached from the root in finitely many
containment steps: for every x ∈ U there are n ≥ 0 and x₀, …, xₙ with x₀ = r,
xₙ = x, and (xᵢ, xᵢ₊₁) ∈ C for every i < n. That sequence is the **chain** of
x; by TREE-004 and TREE-005 it is unique.

## TREE-007: Names

**Invariant:** The root's name is empty and every other name is a name in N:
name(r) = ε, and for every x ≠ r, name(x) is non-empty and contains no `/`.

## TREE-008: Sibling Names

**Invariant:** Two different children of one container never share a name:
if (p, x) ∈ C, (p, y) ∈ C and name(x) = name(y), then x = y. Folders and items
share this namespace, so a folder and an item with one name are never
siblings.

## TREE-009: Key

**Invariant:** The Key of an entity is the names along its chain joined by
`/`, the root's excluded: for x with chain x₀ = r, …, xₙ = x,
Key(x) = name(x₁)/name(x₂)/…/name(xₙ) when n ≥ 1, and Key(r) = ε. A string
that is the Key of no entity, such as `a/` or `a//b`, denotes nothing; it is
not a second spelling of a Key.

## TREE-010: One Entity per Key

**Invariant:** Two entities with the same Key are the same entity:
Key(x) = Key(y) implies x = y.

## TREE-011: Key Shape

**Invariant:** Key(x) is ε exactly when x = r. Every other Key is non-empty
and has no leading `/`, no trailing `/`, and no `//`.

## TREE-012: Prefix Closure

**Invariant:** Every proper ancestor of an entity is a folder whose Key is a
prefix of the entity's Key by whole names: if Key(x) = s₁/…/sₙ, then for each
0 < i < n the string s₁/…/sᵢ is the Key of a folder on the chain of x. An item
occurs only at the last index of any chain.

---

## Notes

Not normative. TREE-010 to TREE-012 are lemmas L3 to L5 of the research doc,
proved in `formal/lean/StoreAxioms.lean`; they are sections because callers
rely on them directly. Acyclicity (L2), chain uniqueness (L1) and the
correspondence with prefix-closed sets of name sequences (L6) are proved there
and not restated.
