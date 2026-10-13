# Research: A store model as axioms (BK-435)

**Date:** 2026-10-13
**Backlog items:** BK-435 (The store model's axioms have no independence or consistency check)
**Status:** Accepted (maintainer, 2026-10-13). Independence, consistency and L1 to L5 machine-checked in Alloy in bounded scope (2026-10-13, § 10); D1 and L1 to L6 proved in Lean 4 for every universe, finite or not (2026-10-13, § 10).

---

## 1. Problem Statement

A store holds folders and items under one root, each addressed by a key. That
structure is written down in several places as a consequence (a tree type, a
validity predicate, prose in an RFC), but its defining assumptions are not
stated once, set-theoretically, with evidence that they are consistent and that
none of them is redundant or missing.

This document does that, and only that. It is deliberately independent of any
backend, any filesystem or object-store convention, and any operation. The
decision it informs is how the model is formalized next (§10).

**What is claimed.** A small set of axioms (§3) describes the finite and
infinite structures that are "a rooted tree whose nodes are folders or items,
whose non-root nodes carry a name, with unique names among siblings". §5 gives,
for each clause of each axiom, a structure that satisfies every other clause
and breaks that one, which is the evidence the clause does work. §7 lists what
should follow from the axioms; § 10 records their machine checks.

---

## 2. Notation and parameters

| Symbol | Meaning |
|---|---|
| Σ | A fixed alphabet that contains the symbol `/` and at least one other symbol; the witnesses and §5 rows assume the letters they use are in it. Not restricted further. |
| Σ\* | All finite words over Σ. ε is the empty word. |
| N | The names: non-empty words over Σ in which `/` does not occur. |
| U | The universe of entities. |
| F, I | Folders and items. |
| r | The root, a distinguished element. |
| C | Containment, a binary relation on U. `(p, x) ∈ C` reads "p contains x". |
| name | A function U → Σ\*. |

Names are compared as words, exactly: case-sensitive, no normalization.

---

## 3. The axioms

```
AX-1  (partition)        U = F ∪ I and F ∩ I = ∅
AX-2  (root)             r ∈ F
AX-3  (items are leaves) C ⊆ F × U
AX-4  (at most one       ∀x, p, q ∈ U: (p, x) ∈ C ∧ (q, x) ∈ C ⇒ p = q
       container)
AX-5  (root is topmost)  ∀p ∈ U: (p, r) ∉ C
AX-6  (reachability)     ∀x ∈ U: there are n ≥ 0 and x₀, …, xₙ with
                         x₀ = r, xₙ = x, and (xᵢ, xᵢ₊₁) ∈ C for every i < n
AX-7  (names)            name(r) = ε, and for every x ≠ r: name(x) ∈ N,
                         that is name(x) ≠ ε and `/` does not occur in name(x)
AX-8  (sibling names)    ∀p, x, y ∈ U:
                         (p, x) ∈ C ∧ (p, y) ∈ C ∧ name(x) = name(y) ⇒ x = y
```

One line of intuition each:

- **AX-1, AX-2.** Every entity is exactly one of folder or item, and the root is
  a folder, so there is somewhere to put things.
- **AX-3.** Only a folder can contain anything. This is a typing statement on C
  and is the whole content of "items are leaves".
- **AX-4, AX-5.** No entity has two containers, and the root has none.
- **AX-6.** Everything is reachable from the root in finitely many steps.
- **AX-7.** A name is a non-empty word without `/`, except the root's, which is
  empty. The empty name belongs to the root alone.
- **AX-8.** Two different children of one container never share a name. Folders
  and items share this namespace: a folder and an item with the same name
  cannot be siblings.

AX-4 states uniqueness only. That every entity except the root *has* a
container is not an axiom; it follows from AX-6 (D1, §4). No finiteness axiom
is included. AX-6 already gives every entity a finite chain from the root; the
universe as a whole may still be infinite, whether through infinitely many
entities, infinite branching, or an infinite downward branch in which every
entity has a finite depth.

---

## 4. Derived definitions and two consequences

These are definitions and consequences, not axioms. They are well defined only
because of the axioms named.

**D1, every non-root has exactly one container.** Let x ≠ r. By AX-6 there is a
chain r = x₀, …, xₙ = x. If n = 0 then x = r, so n ≥ 1, and xₙ₋₁ contains x.
By AX-4 that container is the only one.

**Chain.** For x ∈ U, the chain of x is the sequence x₀ = r, x₁, …, xₙ = x of
AX-6. It is unique. By AX-5 no xᵢ with i > 0 is r, so r occurs only at index 0.
By AX-4, xₙ₋₁ is the one container of x, xₙ₋₂ the one container of xₙ₋₁, and so
on, until the walk reaches r at index 0. Both the entries and the length are
determined.

**Key.** For x with chain x₀, …, xₙ:

```
Key(x) = name(x₁) / name(x₂) / … / name(xₙ)     (n ≥ 1; names joined by `/`)
Key(r) = ε
```

For a depth-one entity, Key(x) = name(x). Key(r) is the empty join and does not
use name(r). A Key is a string with no leading, trailing or doubled `/`: AX-7
makes every segment non-empty. An entity has one Key, because its chain is
unique (L1). A string such as `a/` is not the Key of any entity, so a string
that is not a Key denotes nothing and is not read as a second spelling of one.

**L2, acyclicity (derivation).** Suppose a cycle y₀, y₁, …, yₖ = y₀ with k ≥ 1
and (yᵢ, yᵢ₊₁) ∈ C. Take y = y₀. By AX-4, the one container of y is yₖ₋₁, and
the one container of yₖ₋₁ is yₖ₋₂, and so on, so the backward walk from y never
leaves the cycle. The chain of y (AX-6) is that backward walk, so it ends at r
and r lies on the cycle. Then r has a container, which contradicts AX-5. AX-6
alone does not give this: with AX-4 dropped,
C = {(r, g₁), (g₁, g₂), (g₂, g₁)} satisfies AX-5 and AX-6 and has a cycle.

**The trie view.** Read each name as a letter on the edge into a node. AX-8
makes the edges leaving a node carry distinct letters, which is the defining
property of a trie. Reading the names along the path from the root gives a
*sequence of names*, and Key(x) is that sequence joined by `/`. The set of
sequences is closed under dropping trailing names; the set of Keys, as
character strings, is not closed under character prefixes (in W1 below, `d/`
is a prefix of `d/f` and is not a Key). The structure is a prefix-closed set of
name sequences, plus a marking of which are items, with every item a leaf.
§7 states this as a lemma (L6).

---

## 5. Why each axiom is there

In every row below, **name(r) = ε, and every other name not stated is a
distinct element of N, unless the row says otherwise**; U, F, I and C are given
in full. Each structure satisfies every axiom clause except the one named,
checked against all eight axioms. AX-1 and AX-7 are conjunctions and have a row
per clause. AX-4's existence half has no row because it is not an axiom (D1).

| Clause broken | Structure | What goes wrong |
|---|---|---|
| AX-1, disjoint | U = {r, x}, F = {r, x}, I = {x}, C = {(r, x)} | x is both a folder and an item. |
| AX-1, covering | U = {r, x}, F = {r}, I = ∅, C = {(r, x)} | x is neither a folder nor an item. Nothing else derives its type; L5 and L6 lose their meaning for it. |
| AX-2 | U = {r}, F = ∅, I = {r}, C = ∅ | The root is an item and cannot contain anything. |
| AX-3 | U = {r, x, y}, F = {r}, I = {x, y}, C = {(r, x), (x, y)} | An item contains an entity. |
| AX-4 | U = {r, a, b, x}, F = {r, a, b}, I = {x}, C = {(r, a), (r, b), (a, x), (b, x)} | x has two containers, hence two chains and two Keys. |
| AX-5 | U = {r, p}, F = {r, p}, I = ∅, C = {(r, p), (p, r)} | The root has a container. Every non-root has exactly one container and is reachable, yet the structure is a cycle through r. |
| AX-6 | U = {r, g₁, g₂}, F = U, I = ∅, C = {(g₁, g₂), (g₂, g₁)} | Every non-root has exactly one container and r has none, but g₁ and g₂ form a detached cycle that no chain from r reaches. |
| AX-7, name(r) = ε | U = {r}, F = {r}, I = ∅, C = ∅, name(r) = `z` | The root has a non-empty name. Nothing in §4 uses name(r), so no consequence fails; only the correspondence of L6, where it would be free data. This clause is a normalization, not a source of any property of Key. |
| AX-7, non-empty | U = {r, x}, F = {r}, I = {x}, C = {(r, x)}, name(x) = ε | Key(x) = ε = Key(r): two entities share a Key. |
| AX-7, no `/` | U = {r, w, a, b}, F = U, I = ∅, C = {(r, w), (r, a), (a, b)}, name(w) = `a/b`, name(a) = `a`, name(b) = `b` | w and b both have Key `a/b`. |
| AX-8 | U = {r, x, y}, F = {r}, I = {x, y}, C = {(r, x), (r, y)}, name(x) = name(y) | Two children of r with one name, hence one Key. |

**Witness models** (consistency evidence; no row above is a model of AX-1 to
AX-8). In each, name(r) = ε and every other name is the one given.

- **W0.** U = {r}, F = {r}, I = ∅, C = ∅. The smallest model; every axiom that
  quantifies over a pair of children holds only vacuously.
- **W1.** U = {r, d, f}, F = {r, d}, I = {f}, C = {(r, d), (d, f)}, name(d) = `d`,
  name(f) = `f`. Keys: ε, `d`, `d/f`.
- **W2.** U = {r, d, e, f}, F = {r, d, e}, I = {f}, C = {(r, d), (d, e), (d, f)},
  name(d) = `d`, name(e) = `e`, name(f) = `f`. Keys: ε, `d`, `d/e`, `d/f`. Here
  AX-8 is exercised by a folder with two differently named children, and `e`
  is an empty non-root folder.

A third kind of evidence, that the axioms *imply* what they are meant to, is
the lemma list in §7.

---

## 6. Decisions taken

| Decision | Chosen | Alternative and what it would change |
|---|---|---|
| Files and folders share one name namespace | Shared (AX-8 over all children) | Typed keys (`a` against `a/`): the label alphabet becomes names × {item, folder}, the trailing `/` becomes a type marker, and AX-8 holds per kind. The same trie structure over a richer alphabet. |
| `a/` as an input spelling | Not a Key of anything | Treating `a/` as a second spelling of folder `a` would be an alias, which this model leaves out. |
| Empty folders | First-class entities | Folders existing only as prefixes of items would add an axiom: every non-root folder has a descendant item. |
| Name alphabet | Non-empty, no `/` | `.` and `..` are ordinary names. Treating `.` as an alias of the containing folder, or `..` as moving to the parent, is navigation and belongs outside the axioms. |
| Finiteness | Not assumed | Adding it would exclude infinite stores. It would not be needed for induction on depth, which AX-6 already supports. |
| Scope | Static structure only | Create, delete, move and copy are a second pass. |

---

## 7. Lemmas to prove (statements only)

Not proved here, except where §4 gives a derivation (D1, chain uniqueness, L2);
all are proved in Lean 4 (§ 10, step 2 result).
They are the claims a proof assistant must establish.

- **L1, chain uniqueness.** Every x ∈ U has exactly one chain. (So Key is a
  function.)
- **L2, acyclicity.** There is no sequence y₀, …, yₖ with k ≥ 1, (yᵢ, yᵢ₊₁) ∈ C
  for every i < k, and yₖ = y₀.
- **L3, Key injectivity.** Key(x) = Key(y) ⇒ x = y, for all x, y ∈ U. Sketch:
  if the Key is ε, both are r (L4). Otherwise both Keys split on `/` into the
  same number of non-empty segments, so the depths and the names along the
  chains agree, and AX-8 identifies the nodes level by level.
- **L4, Key shape.** Key(x) = ε iff x = r. Otherwise Key(x) is non-empty, has
  no leading or trailing `/`, and has no `//`.
- **L5, prefix closure.** If Key(x) = s₁/…/sₙ then for each 0 < i < n the string
  s₁/…/sᵢ is the Key of a folder, namely a proper ancestor of x. An item
  occurs only at the final index of any chain, by AX-3.
- **L6, trie correspondence.** Models of AX-1 to AX-8 correspond, up to
  isomorphism, to pairs (L, K): L a set of finite sequences of names from N,
  closed under taking prefixes and containing the empty sequence, and K a set
  of non-empty sequences in L that have no proper extension in L (the items).
  A leaf of L outside K is an empty folder. The sequences are of names, not of
  characters: closure is under dropping whole trailing names.

---

## 8. Non-goals

- Operations and state change (create, delete, move, copy, list).
- Navigation: `.`, `..`, normalization, aliases.
- Any backend, filesystem, or network behavior.
- Links, permissions, metadata, content.

---

## 9. Comparison with well-known models

Each model below is compared on the same five questions: how many containers a
node has, whether the name sits on the node or on the edge into it, whether
folder and item are distinct kinds, what a key or path is, and what this model
adds or removes. **Verification status** is stated per claim, because the
comparison is only as good as the reading behind it:

- *Textbook:* a standard fact, not checked against one cited text.
- *Summary:* taken from a search result's description of a source that was not
  read in full (§11). Confirm before quoting.

### 9.1 At a glance

| Model | Containers per node | Name lives on | Folder / item | Key or path | Delta from this model |
|---|---|---|---|---|---|
| **This model** | at most one (AX-4); exactly one for a non-root (D1) | node, equivalently its one incoming edge | partition, items are leaves (AX-1, AX-3) | one `/`-joined word, unique (L3) | — |
| Rooted directed tree (arborescence) | exactly one, root none | not modelled | not modelled | unique path from the root | this model is a tree plus typing and names |
| Rooted DAG | one or more | edge | not modelled | a set of paths per node | AX-4 dropped (any number of containers), and acyclicity added as an axiom |
| Trie / prefix-closed word set | exactly one, root none | edge label | word end marks an entry | the word | corresponds to this model (L6, proved in § 10); a trie marks word ends, this model marks items and forbids items having extensions |
| Path-keyed map (tree store) | implied by prefix closure | key segment | a kind per key | the key | a representation, not a rival axiomatization; L6 would connect the two |
| Hierarchical key-value store (ZooKeeper) | one, root none | path segment | none: a node has data and may have children | absolute path | AX-1 and AX-3 do not hold |
| Flat key-value store with a delimiter (pure convention) | none stored | not modelled | none | opaque string | AX-2 to AX-6 dropped; hierarchy is a reading of the keys |
| Alloy file system (course slides) | one, root none | not modelled in the part summarized | Dir and File | not modelled in the part summarized | acyclicity as an invariant, reachability not stated in the part summarized; no names |
| Unix and POSIX file system | one for a directory, several for a file | directory entry (edge) | distinct kinds | path resolved by walking entries | links, `.` and `..` and resolution added; this model keeps the tree part only |

### 9.2 Rooted directed trees (graph theory)

*Textbook.* A rooted directed tree, or arborescence, is a directed graph with a
distinguished root such that the root has in-degree 0, every other node has
in-degree 1, and every node is reachable from the root. Equivalently, there is
exactly one directed path from the root to each node.

AX-4, AX-5, AX-6 and D1 give that characterization, with C as the edge set, so
(U, C) is an arborescence. Acyclicity is a consequence (L2), as in the standard
treatment, not an extra axiom.

**Delta.** Graph theory says nothing about names, node kinds or keys. This
model adds AX-1 and AX-3 (a node is a folder or an item, and only folders have
out-edges) and AX-7 and AX-8 (names, unique among siblings). The unique root
path of graph theory is what makes the chain of §4, and so Key, well defined.

### 9.3 Rooted DAGs

*Textbook.* A rooted DAG allows a node several containers. Dropping AX-4 (any
number of containers per node) gives it, but acyclicity must then be **added as
an axiom**: it no longer follows from reachability (the cycle example in §4,
L2).

Three things change, which is why AX-4 is the axiom that separates a tree from
a DAG:

- **The chain is no longer unique,** so Key(x) becomes a set of words, one per
  path from the root. Key stops being a function.
- **The name moves to the edge, if names may differ per container.** x can be
  called `a` under one container and `b` under another, so name is a function
  of the pair (p, x), not of x. (A DAG with one name per node is also well
  defined; it forces a node to carry the same name everywhere.)
  In the tree, AX-4 and D1 fix the pair from x alone, so putting the name on the
  node (AX-7) loses nothing: name(x) is the label of x's one incoming edge.
- **A word names at most one node** if the labels of edges leaving one node
  stay distinct, but a node is no longer named by one word.

Content-addressed trees (a Merkle DAG) and hard-linked files are usual examples
of this shape.

### 9.4 Tries and prefix-closed word sets

*Textbook.* A trie is a rooted tree whose outgoing edges carry distinct letters;
a set of words closed under taking prefixes is the same thing viewed as data.
AX-8 is the distinct-letters condition, and §4 reads a Key as the word along
the path from the root.

L6 states the correspondence, proved in § 10. **Delta:** a trie marks which
words are ends of entries. This model marks which words are items, and AX-3
requires an item word to have no proper extension, while a folder word may or
may not have one (an empty folder is a leaf that is not an item).

### 9.5 Path-keyed maps (hierarchical tree stores)

A common specification style represents a tree as a partial function from
paths to node kinds, restricted so that the set of defined paths is closed
under prefix and every proper prefix of a path maps to a folder. This avoids
reachability: a path being present is its own witness that its prefixes are.

**Delta.** It is a representation, not a competing set of axioms. By L6 (§ 10),
the two agree. A map with a finite domain, as Dafny's `map` has, describes
finite stores only, so it covers a subset of this model's structures.
`sdd/formal/StoreTree.dfy` §1 is an instance of the map style (`Tree =
map<Key, Kind>`, root a folder, every proper prefix a folder), and §10 records
that checking this against the axioms is not done.

Ordered document trees (XML) differ on two further points: children are
ordered, and an element may carry attributes and children together. This model
has no order and no values.

### 9.6 Hierarchical key-value stores

**ZooKeeper's namespace** (*summary*, from a secondary description of its
documentation). Nodes are addressed by absolute paths; `.` and `..` cannot be
path segments; the null character is not allowed in a path, and the description
lists further disallowed characters; a node holds a small amount of data and
may also have children.

- The last point is the delta that matters. A node is a value and a possible
  folder at once, so AX-1 (partition) and AX-3 (items are leaves) do not hold.
  With the values erased, a ZooKeeper tree is a model of this one with I = ∅,
  up to the name alphabet: its rules disallow further characters, so its names
  are a subset of N.
- ZooKeeper rejects `.` and `..` as whole path segments; this model accepts
  them as ordinary names and leaves their navigational meaning outside the
  axioms (§6). Both avoid giving them movement semantics.

**Flat key-value stores with a delimiter convention** (an architectural
pattern with no single cited text, in its pure form with no marker entries).
Keys are
opaque strings; a hierarchy appears only because callers agree to read a
delimiter as a separator, and a "folder" is a prefix shared by some keys.

- AX-2 to AX-6 are dropped: no root entity, no containment relation, no parent.
  AX-1, AX-7 and AX-8 have no counterpart as stated: there are no folder
  entities and the keys are opaque.
- Folders are not entities, which is the "folders only as prefixes" alternative
  rejected in §6. In the pure convention a folder with no key beneath it is not
  stored. An implementation that adds marker entries for empty folders has
  stepped outside the pure convention: the folder is then an entry.
- A key may be both an entry and a prefix of other keys. Read as entities, an
  entry `a` beside keys `a/x` is either an item and an implied folder both named
  `a` under the root, which AX-8 forbids, or one entity that is an item with a
  child, which AX-3 forbids.
- What corresponds to this model is the word view of §4: the stored set is a set
  of words, and the hierarchy is recovered by splitting on the delimiter.

### 9.7 The classic file system model

**The Alloy teaching model** (*summary*; Ana Paiva's MFES course slides).
`Object` is split into `Dir` and `File`; a file system has a root and a
`parent` relation. Its invariant, as summarized, requires that every object
other than the root has a parent, that the root has none, and that no object is
its own ancestor. The part summarized has no names and so no keys. Other Alloy
formulations of file systems may state reachability from the root explicitly;
that was not checked.

As summarized, this matches AX-2 and AX-5 (a root with no parent). It matches
AX-4 if `parent` is functional and AX-1 and AX-3 if only directories have
contents; the summary does not say. Acyclicity is written as an invariant and
reachability is not stated. Whether that matters depends on the universe:

- **In a finite universe the two are equivalent.** A parent chain from any node
  cannot repeat (no cycles) and cannot continue forever, so it ends, and only
  the root has no parent. Reachability follows.
- **In an infinite universe they are not.** An infinite upward chain
  ... → x₂ → x₁ → x₀, each node contained by the next, with the root elsewhere,
  satisfies "every non-root has a parent, the root has none, nothing is its own
  ancestor" and breaks AX-6.

Alloy analyses bounded scopes, so the finite case is what such a model needs.
This model assumes no finiteness (§6), so it keeps AX-6 as an axiom; acyclicity
then follows from AX-4, AX-5 and AX-6 (L2).

**Unix and POSIX** (*summary* for the existence and scope of the specifications
below; the structural points are *textbook*). Morgan and Sufrin's Z
specification of the Unix filing system (IEEE Transactions on Software
Engineering, 1984) is described as set-theoretic, at system-call level, and
staged so that each concept can be read separately. SibylFS (Ridge et al., SOSP
2015) is described as a formal specification in Lem of POSIX file system
behaviour, used as a test oracle for real file systems. Neither is compared
line by line here. The structural differences from this model, which are
general facts about Unix file systems, are:

- **Names live in directory entries,** not in the node a file system calls an
  inode. This is the edge-labelled form of §9.3.
- **A file can have several entries** (hard links), so the structure is a DAG
  for non-directories. Directories carry `.` and `..` entries, which make the
  directory graph cyclic as a graph, and symbolic links add a further
  indirection.
- **Paths are resolved by walking,** which is partial and can fail in several
  ways, so a path is an input to an operation, not an identifier of an entity.

**Delta.** This model is the tree part of that picture, stripped of links,
`.` and `..` and resolution: Key is the canonical identifier of an entity, not
a string to be resolved, and a string that is not a Key (such as `a/` or
`a//b`) names nothing instead of being normalized.

### 9.8 Where this model differs from the models compared

- **Name as a function of the node,** which AX-4 and D1 license. Among the
  models compared in §9.3 and §9.7, those that allow more than one container
  per node put the name on the edge.
- **Folders as first-class entities that may be empty,** with items as leaves.
  Among the models compared: a pure flat store has no folder entities,
  ZooKeeper nodes are not partitioned into folders and items, and a trie marks
  word ends without distinguishing folders from items.
- **Keys with no second spelling.** AX-7 makes every segment non-empty and
  `/`-free, and AX-8 with L3 makes a Key identify one entity. Variants outside
  the Key form (`a/`, `a//b`) denote nothing.
- **Axioms stated so that each clause can be refuted alone** (§5), including
  reachability, which the Alloy slides do not state in the part summarized
  in §9.7.

**Open points the comparison leaves.** Whether a model with values on folders
(the ZooKeeper shape) should be a variant of this one is not decided here.
Neither is whether the DAG variant of §9.3 is ever wanted as a second model,
and the line-by-line comparison with the Z and Lem specifications, which would
settle the Unix and POSIX deltas now stated only structurally.

---

## 10. Recommendation: how to formalize

Prose first (this document), then machine checking in the order of what each
tool is best at:

1. **Alloy.** A finite-scope model finder. Run AX-1 to AX-8 and each row of §5
   to confirm that every witness satisfies the axioms and every countermodel
   violates exactly the clause named. Cheap, and it catches a mis-stated axiom
   before any proof effort.
2. **Lean 4.** The lemmas of §7 over the unrestricted universe. Reachability,
   the unique chain and the induction on depth are proofs by induction, which
   is where a proof assistant is strong and an SMT-based verifier is weak. L3
   needs one auxiliary lemma on strings: splitting the `/`-join of a sequence
   of names from N returns that sequence.
3. **Dafny.** Kept for the operations pass: pre- and postconditions,
   preservation of the axioms by each operation, and executable code.

The prose is the source of truth: each formal artifact is traced to AX-n and
has one job. Three parallel restatements of the axioms are the failure to
avoid.

**Step 1 result (2026-10-13).** `sdd/formal/alloy/StoreAxioms.als` restates
§ 3 clause by clause and runs, via `bash scripts/alloy_check.sh`, 30 commands,
each with an `expect`; all 30 matched (the script's summary table, exit 0). It
found no disagreement with this document. What it established, and within
which scope (entities, sequence length):

- **§ 5 rows.** Each of the eleven structures exists with its named clause
  false and every other clause true (scope 4, 6). The Key claims of the AX-7
  non-empty, AX-7 no-`/` and AX-8 rows hold, and the AX-4 row admits two
  chains to x.
- **Witnesses.** W0, W1 and W2 are models of AX-1 to AX-8, with the Keys
  listed (scope 4, 6).
- **§ 4.** D1 holds (scope 6, 6), and the cycle example shows AX-5 and AX-6
  without AX-4 admit a cycle.
- **§ 7.** L1, L2, L3, L4 and L5 hold (scope 5, 11, names of at most two
  symbols). The bound excludes no structure in scope: a Key there has length
  at most 4 · 3 − 1 = 11 (depth at most 4, a name and a `/` per level, no
  trailing `/`), and a run shows that length is reached. L6 is not stated: it relates structures to one another,
  which Alloy cannot quantify over.
- **§ 9.7.** The finite half holds (scope 6, 6). The infinite half is outside
  any bounded scope, as is everything this document says about infinite
  universes.

The checks are not vacuous: with AX-4 removed from the axioms, D1, L1 and L2
fail; without AX-8, L3; without AX-3, L5; without AX-7's no-`/` clause, L3, L4
and L5. Each mutant was a copy of the model with that one conjunct deleted from
its `Axioms` predicate, run once with `scripts/alloy_check.sh` and not
committed; the failing commands are the ones Alloy reported as "satisfied
against expectation".

**Step 2 result (2026-10-13).** `sdd/formal/lean/StoreAxioms.lean`
restates § 3 clause by clause (one field of `Axioms` per clause), and
§ 2 with one generalization (the alphabet need not hold a symbol besides
`/`; only the infinite model below takes one), and proves, with `bash scripts/lean_check.sh` building it green under
Lean 4.34.1, core library only:

- **§ 4.** D1, and chain uniqueness as `chain_unique`.
- **§ 7.** L1 to L5 as stated, for an arbitrary type as universe, so
  with no finiteness and no scope. The auxiliary lemma of step 2
  took the form of injectivity (`join_inj`): the `/`-join of a sequence
  of names from N determines the sequence.
- **L6.** Five parts: each model gives a pair (L, K) meeting L6's
  conditions; each such pair gives a model (entities the sequences in L,
  items K, root the empty sequence, p contains p followed by one name,
  a sequence's name its last); pair to model to pair is the identity;
  model to pair to model is the identity up to an isomorphism that
  preserves F, I, r, C and name; and two models are isomorphic exactly
  when they give the same pair. A leaf of L outside K is an empty folder
  (`L6_empty_folder`). The isomorphism this fixes is the one the
  statement left informal: it preserves the typing and the names.
- **§ 3, no finiteness axiom.** The axioms have an infinite model (one
  infinite downward branch, no items). Like W0 it shows the axioms
  consistent, so no lemma holds merely because nothing satisfies them.
  Unlike step 1 there are no mutants: nothing here shows each lemma
  needs the axioms it is meant to need.
- **§ 9.7, infinite half.** An infinite upward chain with the root
  elsewhere has every non-root contained, the root uncontained and no
  cycle, and breaks AX-6. Its names are all ε, so it also breaks AX-7
  and is not an independence witness for AX-6.

It found no disagreement with this document. The build fails on a
`sorry`: a scratch copy with `theorem bogus : False := sorry` added,
run with `bash scripts/lean_check.sh <copy>`, failed with "declaration
uses `sorry`" (not committed). A `#guard_msgs` block pins each headline
result's axioms to Lean's standard ones.

**Relation to existing formal work.** `sdd/formal/StoreTree.dfy` §1 models the
store as `Tree = map<Key, Kind>` with `Key = seq<string>`, requiring the root
to be a folder and every proper prefix of a node's key to be a folder. That
reads as the keys-as-words presentation of §4's trie view, with L6 as the
statement that connects them. This document does not check that reading;
reconciling the two is left to the formalization step, and nothing here
depends on it. One mismatch is already visible: `Key = seq<string>` places no
restriction on its segments, so `ValidTree` admits the segments `""` and
`"a/b"`, which AX-7 excludes. AX-8 is automatic in a map keyed by sequences.

**Open questions.**

- Does the model stay shared-namespace, or is the typed-key variant of §6
  wanted as a second model for stores that distinguish `a` from `a/`?
- Is finiteness imposed when the operations are added?
- Does `StoreTree.dfy`'s `Key` gain AX-7's name restriction, or does the model
  state it as a precondition on callers?
- Are the axioms promoted into a spec once machine-checked, and which one?

---

## 11. Sources for § 9

Read on 2026-10-13 through search results, not by reading each source in full.

- Alloy teaching file system (Object, Dir, File, parent invariant):
  [MFES course slides, Alloy](https://paginas.fe.up.pt/~apaiva/teach/MFES_material/8-MFES-Alloy.pdf).
- Z specification of the Unix filing system: C. Morgan and B. Sufrin,
  "Specification of the UNIX Filing System", IEEE Transactions on Software
  Engineering SE-10(2), 1984, DOI 10.1109/TSE.1984.5010215.
- SibylFS: T. Ridge, D. Sheets, T. Tuerk, A. Giugliano, A. Madhavapeddy and
  P. Sewell, "SibylFS: formal specification and oracle-based testing for POSIX
  and real-world file systems", SOSP 2015
  ([abstracts](https://www.cl.cam.ac.uk/~pes20/papers/topic.SibylFS_abstracts.html)).
- ZooKeeper path rules, via a secondary description:
  [zybuluo note](https://zybuluo.com/xtccc/note/192734). The official
  programmer's guide should replace it before the ZooKeeper claims are quoted.
