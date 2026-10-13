/*
 * The store model's axioms AX-1 to AX-8, checked in bounded scope.
 *
 * Source of truth: sdd/research/research-store-model-axioms.md (BK-435).
 * This module restates § 3 and runs § 4, § 5 and § 7 against it; it adds no
 * claim of its own. Where the two disagree, the document is corrected.
 *
 * Every command carries `expect`: 1 for a run that must find an instance,
 * 0 for a check that must find no counterexample. scripts/alloy_check.sh
 * fails when any outcome differs from its expectation.
 *
 * What bounded scope cannot show: anything about an infinite universe
 * (§ 3's "no finiteness axiom", § 9.7's infinite upward chain). A check that
 * passes here holds for every structure up to the scope stated on it, no
 * further.
 */
module StoreAxioms

/* ---------------------------------------------------------------- § 2 --- */

-- Σ: the separator and at least one other symbol.
abstract sig Char {}
one sig Slash extends Char {}
sig Letter extends Char {}

-- U is the set of Entity atoms. name maps U to Σ*; words are compared as
-- sequences, exactly.
sig Entity {
  name: seq Char,
  key: seq Char       -- constrained only by KeyDef (§ 4); free elsewhere
}

-- The structure (F, I, r, C). F and I are free subsets of U, so that the
-- AX-1 rows can break the partition.
one sig M {
  fs: set Entity,
  is: set Entity,
  rt: one Entity,
  cn: Entity -> Entity
}

fun F: set Entity { M.fs }
fun I: set Entity { M.is }
fun Root: one Entity { M.rt }
fun C: Entity -> Entity { M.cn }

-- N: non-empty words in which `/` does not occur.
pred InN[w: seq Char] { some w and Slash not in w.elems }

/* ---------------------------------------------------------------- § 3 --- */

-- One predicate per clause, so that § 5 can break each alone.
pred AX1_disjoint  { no F & I }
pred AX1_covering  { Entity = F + I }
pred AX2           { Root in F }
pred AX3           { C in F -> Entity }
pred AX4           { all x: Entity | lone C.x }
pred AX5           { no C.Root }
pred AX6           { Entity in Root.*C }
pred AX7_root      { no Root.name }
pred AX7_nonempty  { all x: Entity - Root | some x.name }
pred AX7_noslash   { all x: Entity - Root | Slash not in x.name.elems }
pred AX8           { all p: Entity | all disj x, y: p.C | x.name != y.name }

pred Axioms {
  AX1_disjoint and AX1_covering and AX2 and AX3 and AX4 and AX5 and AX6
  and AX7_root and AX7_nonempty and AX7_noslash and AX8
}

/* ---------------------------------------------------------------- § 4 --- */

-- Key(r) = ε; Key(x) = name(x) at depth one; otherwise Key(container) / name.
-- Stated by index arithmetic rather than `append`, so that a key longer than
-- the seq scope makes KeyDef unsatisfiable instead of being truncated.
pred KeyDef {
  no Root.key
  all x: Entity - Root, p: C.x |
    p = Root implies x.key = x.name
    else {
      #x.key = plus[plus[#p.key, 1], #x.name]
      all i: p.key.inds | x.key[i] = p.key[i]
      x.key[#p.key] = Slash
      all j: x.name.inds | x.key[plus[plus[#p.key, 1], j]] = x.name[j]
    }
}

-- A name-length bound for the commands that use KeyDef. With n entities the
-- deepest entity has depth n - 1, so its key has length at most
-- (n - 1) * (L + 1) - 1 for names of length at most L. Each such command
-- picks n, L and a seq scope that admit that length, so KeyDef excludes no
-- structure in its scope.
pred NameLen[n: Int] { all e: Entity | #e.name <= n }

-- A chain of § 4, as data, so that L1 can quantify over chains.
sig Chain { s: seq Entity }
pred ChainTo[c: Chain, x: Entity] {
  c.s.first = Root
  c.s.last = x
  all i: c.s.butlast.inds | c.s[i] -> c.s[plus[i, 1]] in C
}

-- D1: every non-root has exactly one container.
assert D1 { Axioms implies all x: Entity - Root | one C.x }
check D1 for 6 but 5 Int, 6 seq expect 0

-- § 4, L2's remark: with AX-4 dropped, AX-5 and AX-6 admit a cycle.
run L2_needs_AX4 {
  AX5 and AX6 and not AX4
  some disj g1, g2: Entity - Root |
    Entity = Root + g1 + g2 and C = Root -> g1 + g1 -> g2 + g2 -> g1
} for 4 but 5 Int, 6 seq expect 1

/* ---------------------------------------------------------------- § 5 --- */

-- The rows' default: name(r) = ε, and the names of the given entities are
-- distinct elements of N. A row that states a name overrides this for it.
pred DefaultNames[given: set Entity] {
  no Root.name
  all x: given | InN[x.name]
  all disj x, y: given | x.name != y.name
}

-- Each row pins U, F, I and C, and asks for the named clause false and every
-- other clause true. An instance is the row's structure, so expect 1.

run row_AX1_disjoint {
  some x: Entity - Root {
    Entity = Root + x  and  F = Root + x  and  I = x  and  C = Root -> x
    DefaultNames[x]
  }
  not AX1_disjoint
  AX1_covering and AX2 and AX3 and AX4 and AX5 and AX6
  AX7_root and AX7_nonempty and AX7_noslash and AX8
} for 4 but 5 Int, 6 seq expect 1

run row_AX1_covering {
  some x: Entity - Root {
    Entity = Root + x  and  F = Root  and  no I  and  C = Root -> x
    DefaultNames[x]
  }
  not AX1_covering
  AX1_disjoint and AX2 and AX3 and AX4 and AX5 and AX6
  AX7_root and AX7_nonempty and AX7_noslash and AX8
} for 4 but 5 Int, 6 seq expect 1

run row_AX2 {
  Entity = Root  and  no F  and  I = Root  and  no C
  DefaultNames[none]
  not AX2
  AX1_disjoint and AX1_covering and AX3 and AX4 and AX5 and AX6
  AX7_root and AX7_nonempty and AX7_noslash and AX8
} for 4 but 5 Int, 6 seq expect 1

run row_AX3 {
  some disj x, y: Entity - Root {
    Entity = Root + x + y  and  F = Root  and  I = x + y
    C = Root -> x + x -> y
    DefaultNames[x + y]
  }
  not AX3
  AX1_disjoint and AX1_covering and AX2 and AX4 and AX5 and AX6
  AX7_root and AX7_nonempty and AX7_noslash and AX8
} for 4 but 5 Int, 6 seq expect 1

run row_AX4 {
  some disj a, b, x: Entity - Root {
    Entity = Root + a + b + x  and  F = Root + a + b  and  I = x
    C = Root -> a + Root -> b + a -> x + b -> x
    DefaultNames[a + b + x]
  }
  not AX4
  AX1_disjoint and AX1_covering and AX2 and AX3 and AX5 and AX6
  AX7_root and AX7_nonempty and AX7_noslash and AX8
} for 4 but 5 Int, 6 seq expect 1

run row_AX5 {
  some p: Entity - Root {
    Entity = Root + p  and  F = Root + p  and  no I
    C = Root -> p + p -> Root
    DefaultNames[p]
  }
  not AX5
  AX1_disjoint and AX1_covering and AX2 and AX3 and AX4 and AX6
  AX7_root and AX7_nonempty and AX7_noslash and AX8
} for 4 but 5 Int, 6 seq expect 1

run row_AX6 {
  some disj g1, g2: Entity - Root {
    Entity = Root + g1 + g2  and  F = Entity  and  no I
    C = g1 -> g2 + g2 -> g1
    DefaultNames[g1 + g2]
  }
  not AX6
  AX1_disjoint and AX1_covering and AX2 and AX3 and AX4 and AX5
  AX7_root and AX7_nonempty and AX7_noslash and AX8
} for 4 but 5 Int, 6 seq expect 1

run row_AX7_root {
  Entity = Root  and  F = Root  and  no I  and  no C
  some z: Letter | Root.name = 0 -> z
  not AX7_root
  AX1_disjoint and AX1_covering and AX2 and AX3 and AX4 and AX5 and AX6
  AX7_nonempty and AX7_noslash and AX8
} for 4 but 5 Int, 6 seq expect 1

run row_AX7_nonempty {
  some x: Entity - Root {
    Entity = Root + x  and  F = Root  and  I = x  and  C = Root -> x
    no Root.name  and  no x.name
  }
  not AX7_nonempty
  AX1_disjoint and AX1_covering and AX2 and AX3 and AX4 and AX5 and AX6
  AX7_root and AX7_noslash and AX8
} for 4 but 5 Int, 6 seq expect 1

run row_AX7_noslash {
  some disj w, a, b: Entity - Root, disj la, lb: Letter {
    Entity = Root + w + a + b  and  F = Entity  and  no I
    C = Root -> w + Root -> a + a -> b
    no Root.name
    w.name = 0 -> la + 1 -> Slash + 2 -> lb
    a.name = 0 -> la
    b.name = 0 -> lb
  }
  not AX7_noslash
  AX1_disjoint and AX1_covering and AX2 and AX3 and AX4 and AX5 and AX6
  AX7_root and AX7_nonempty and AX8
} for 4 but 5 Int, 6 seq expect 1

run row_AX8 {
  some disj x, y: Entity - Root {
    Entity = Root + x + y  and  F = Root  and  I = x + y
    C = Root -> x + Root -> y
    no Root.name  and  InN[x.name]  and  x.name = y.name
  }
  not AX8
  AX1_disjoint and AX1_covering and AX2 and AX3 and AX4 and AX5 and AX6
  AX7_root and AX7_nonempty and AX7_noslash
} for 4 but 5 Int, 6 seq expect 1

-- The AX-4 row's "two chains": its structure admits two different chains to x.
run row_AX4_two_chains {
  some disj a, b, x: Entity - Root, disj c, d: Chain {
    Entity = Root + a + b + x
    C = Root -> a + Root -> b + a -> x + b -> x
    ChainTo[c, x] and ChainTo[d, x] and c.s != d.s
  }
} for 4 but 5 Int, 6 seq, 2 Chain expect 1

-- The "what goes wrong" column, where it is a claim about Key: the row's
-- structure with KeyDef forces two entities onto one Key. A counterexample
-- would be a row structure whose keys stay distinct.

assert row_AX7_nonempty_shares_key {
  all x: Entity - Root |
    (Entity = Root + x and C = Root -> x and no Root.name and no x.name
     and KeyDef) implies x.key = Root.key
}
check row_AX7_nonempty_shares_key for 4 but 5 Int, 6 seq expect 0

assert row_AX7_noslash_shares_key {
  all disj w, a, b: Entity - Root, disj la, lb: Letter |
    (Entity = Root + w + a + b
     and C = Root -> w + Root -> a + a -> b
     and no Root.name
     and w.name = 0 -> la + 1 -> Slash + 2 -> lb
     and a.name = 0 -> la and b.name = 0 -> lb
     and KeyDef)
    implies w.key = b.key
}
check row_AX7_noslash_shares_key for 4 but 5 Int, 6 seq expect 0

assert row_AX8_shares_key {
  all disj x, y: Entity - Root |
    (Entity = Root + x + y and C = Root -> x + Root -> y
     and no Root.name and x.name = y.name and KeyDef)
    implies x.key = y.key
}
check row_AX8_shares_key for 4 but 5 Int, 6 seq expect 0

/* ------------------------------------------------- § 5, witness models --- */

-- Each witness is a model of AX-1 to AX-8 (run, expect 1), and its keys are
-- the ones the document lists (check, expect 0).

pred W0 { Entity = Root and F = Root and no I and no C and no Root.name }

pred W1[d, f: Entity] {
  Entity = Root + d + f  and  F = Root + d  and  I = f
  C = Root -> d + d -> f
  no Root.name
  some disj ld, lf: Letter | d.name = 0 -> ld and f.name = 0 -> lf
}

pred W2[d, e, f: Entity] {
  Entity = Root + d + e + f  and  F = Root + d + e  and  I = f
  C = Root -> d + d -> e + d -> f
  no Root.name
  some disj ld, le, lf: Letter |
    d.name = 0 -> ld and e.name = 0 -> le and f.name = 0 -> lf
}

run witness_W0 { W0 and Axioms } for 4 but 5 Int, 6 seq expect 1
run witness_W1 { some disj d, f: Entity - Root | W1[d, f] and Axioms }
  for 4 but 5 Int, 6 seq expect 1
run witness_W2 { some disj d, e, f: Entity - Root | W2[d, e, f] and Axioms }
  for 4 but 5 Int, 6 seq expect 1

assert W0_keys { (W0 and KeyDef) implies no Root.key }
check W0_keys for 4 but 5 Int, 6 seq expect 0

-- W1: ε, `d`, `d/f`.
assert W1_keys {
  all disj d, f: Entity - Root | (W1[d, f] and KeyDef) implies {
    no Root.key
    d.key = d.name
    f.key = 0 -> d.name[0] + 1 -> Slash + 2 -> f.name[0]
  }
}
check W1_keys for 4 but 5 Int, 6 seq expect 0

-- W2: ε, `d`, `d/e`, `d/f`.
assert W2_keys {
  all disj d, e, f: Entity - Root | (W2[d, e, f] and KeyDef) implies {
    no Root.key
    d.key = d.name
    e.key = 0 -> d.name[0] + 1 -> Slash + 2 -> e.name[0]
    f.key = 0 -> d.name[0] + 1 -> Slash + 2 -> f.name[0]
  }
}
check W2_keys for 4 but 5 Int, 6 seq expect 0

/* ---------------------------------------------------------------- § 7 --- */

-- Scope for the lemmas: up to 5 entities (depth up to 4) and names of length
-- at most 2, so a key has length at most 4 * 3 - 1 = 11; seq scope 11 and
-- 5-bit Int (to 15) admit it. Two chains are enough for L1's counterexample.

-- The bound is reached: some model in this scope has a key of length 11, so
-- the seq scope does not cut the deepest keys off.
run KeyDef_reaches_scope {
  Axioms and KeyDef and NameLen[2]
  some x: Entity | #x.key = 11
} for 5 but 5 Int, 11 seq expect 1

-- L1: every entity has exactly one chain (existence is AX-6; uniqueness here).
assert L1 {
  Axioms implies all c, d: Chain, x: Entity |
    (ChainTo[c, x] and ChainTo[d, x]) implies c.s = d.s
}
check L1 for 5 but 5 Int, 11 seq, 2 Chain expect 0

-- L2: C has no cycle.
assert L2 { Axioms implies no x: Entity | x in x.^C }
check L2 for 5 but 5 Int, 11 seq expect 0

-- L3: Key is injective.
assert L3 {
  (Axioms and KeyDef and NameLen[2]) implies
    all disj x, y: Entity | x.key != y.key
}
check L3 for 5 but 5 Int, 11 seq expect 0

-- L4: Key(x) = ε iff x = r; otherwise no leading, trailing or doubled `/`.
assert L4 {
  (Axioms and KeyDef and NameLen[2]) implies {
    all x: Entity | no x.key iff x = Root
    all x: Entity - Root | x.key.first != Slash and x.key.last != Slash
    all x: Entity, i: x.key.butlast.inds |
      not (x.key[i] = Slash and x.key[plus[i, 1]] = Slash)
  }
}
check L4 for 5 but 5 Int, 11 seq expect 0

-- L5: each `/`-prefix of a Key is the Key of a folder that is a proper,
-- non-root ancestor; and an item contains nothing.
assert L5 {
  (Axioms and KeyDef and NameLen[2]) implies {
    all x: Entity, k: x.key.inds | x.key[k] = Slash implies
      some a: x.^~C - Root | a in F and a.key = x.key.subseq[0, minus[k, 1]]
    no C[I]
  }
}
check L5 for 5 but 5 Int, 11 seq expect 0

-- L6 (correspondence up to isomorphism with a prefix-closed set of name
-- sequences) quantifies over structures, not within one, and is not stated
-- here. L1, L3 and L5 cover its within-one-structure parts.

/* -------------------------------------------------------------- § 9.7 --- */

-- In a finite universe, "every non-root has a container, the root has none,
-- nothing is its own ancestor" gives reachability (AX-6). The infinite
-- counterexample of § 9.7 is outside any finite scope.
assert finite_acyclic_gives_reach {
  ((all x: Entity - Root | some C.x) and no C.Root
   and no x: Entity | x in x.^C) implies AX6
}
check finite_acyclic_gives_reach for 6 but 5 Int, 6 seq expect 0
